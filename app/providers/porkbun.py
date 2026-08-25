"""Porkbun registrar adapter for .com registration.

Official API (v3), documented at https://porkbun.com/api/json/v3/documentation

Endpoints used here:
    POST /ping                          -> credential check, caller IP
    POST /domain/checkDomain/{domain}   -> availability + price
                                           (default limit: 1 call / 10s / account)
    POST /domain/create/{domain}        -> registration from account credit
                                           (limit: 1 attempt / 10s;
                                            50 successes / 24h)
    POST /domain/listAll                -> post-registration verification

Registration notes:
    * `cost` is sent in PENNIES and must match the current price exactly.
    * `agreeToTerms` must be "yes".
    * `dryRun: true` validates the whole request without charging -- this
      adapter uses it as a mandatory rehearsal step by default.
    * The account must be pre-funded with credit; there is no card-on-file
      purchase path in the API.
"""
import threading
import time

import requests

from ..config import (
    PORKBUN_API_KEY,
    PORKBUN_BASE_URL,
    PORKBUN_CHECK_MIN_INTERVAL,
    PORKBUN_ENABLED,
    PORKBUN_SECRET_API_KEY,
    PORKBUN_TIMEOUT,
    PORKBUN_WHOIS_PRIVACY,
)
from .base import Inconclusive, LookupResult, NotConfigured, ProviderError, RateLimited

SOURCE = "porkbun"

_check_lock = threading.Lock()
_last_check_ts = 0.0


def _auth():
    if not PORKBUN_ENABLED:
        raise NotConfigured("PORKBUN_ENABLED=false")
    if not PORKBUN_API_KEY or not PORKBUN_SECRET_API_KEY:
        raise NotConfigured("PORKBUN_API_KEY / PORKBUN_SECRET_API_KEY missing")
    return {"apikey": PORKBUN_API_KEY, "secretapikey": PORKBUN_SECRET_API_KEY}


def _post(path, payload=None, session=None):
    http = session or requests
    body = _auth()
    body.update(payload or {})
    url = f"{PORKBUN_BASE_URL}{path}"
    try:
        resp = http.post(url, json=body, timeout=PORKBUN_TIMEOUT)
    except requests.RequestException as exc:
        raise Inconclusive(f"porkbun request failed: {exc}") from exc

    if resp.status_code == 429:
        raise RateLimited("porkbun rate limited (HTTP 429)")
    if resp.status_code >= 500:
        raise Inconclusive(f"porkbun server error HTTP {resp.status_code}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise Inconclusive(f"porkbun non-JSON response (HTTP {resp.status_code})") from exc

    if str(data.get("status", "")).upper() != "SUCCESS":
        message = data.get("message") or data.get("error") or str(data)
        low = str(message).lower()
        if "rate" in low or "limit" in low or "throttle" in low:
            raise RateLimited(f"porkbun: {message}")
        raise ProviderError(f"porkbun error: {message}")
    return data


def ping(session=None):
    return _post("/ping", session=session)


def _throttle_check():
    global _last_check_ts
    with _check_lock:
        wait = PORKBUN_CHECK_MIN_INTERVAL - (time.monotonic() - _last_check_ts)
        if wait > 0:
            time.sleep(wait)
        _last_check_ts = time.monotonic()


def _price_to_cents(value):
    if value is None:
        raise Inconclusive("porkbun returned no price")
    try:
        return int(round(float(str(value).replace("$", "").strip()) * 100))
    except (TypeError, ValueError) as exc:
        raise Inconclusive(f"unparseable porkbun price: {value!r}") from exc


def check(domain, session=None):
    """Registrar-side availability + price. Returns a dict."""
    _throttle_check()
    data = _post(f"/domain/checkDomain/{domain}", session=session)
    resp = data.get("response") or {}

    avail_raw = resp.get("avail", resp.get("available"))
    available = str(avail_raw).lower() in ("yes", "true", "1")
    price = resp.get("price", resp.get("registerPrice"))

    return {
        "domain": domain,
        "available": available,
        "premium": str(resp.get("premium", "no")).lower() in ("yes", "true", "1"),
        "price_usd": float(str(price).replace("$", "")) if price not in (None, "") else None,
        "price_cents": _price_to_cents(price) if price not in (None, "") else None,
        "raw": resp,
        "limits": data.get("limits"),
        "ttl_remaining": data.get("ttlRemaining"),
    }


def lookup(domain, session=None):
    """LookupResult shape, for CLI parity. Registry RDAP stays the monitor source."""
    info = check(domain, session=session)
    return LookupResult(
        domain=domain,
        available=info["available"],
        statuses=["available"] if info["available"] else ["registered"],
        source=SOURCE,
        extra={"price_usd": info["price_usd"], "premium": info["premium"]},
    )


def register(domain, cost_cents, dry_run=True, session=None):
    """Register `domain`. `cost_cents` must equal the current price in pennies.

    Always call with dry_run=True first; acquire.py enforces that ordering.
    """
    payload = {
        "cost": int(cost_cents),
        "agreeToTerms": "yes",
        "whoisPrivacy": bool(PORKBUN_WHOIS_PRIVACY),
    }
    if dry_run:
        payload["dryRun"] = True
    return _post(f"/domain/create/{domain}", payload, session=session)


def owns(domain, session=None):
    """Post-registration verification: is the domain in our account?"""
    data = _post("/domain/listAll", {"domain": domain}, session=session)
    for item in data.get("domains", []) or []:
        if str(item.get("domain", "")).lower() == domain.lower():
            return True, item
    return False, None
