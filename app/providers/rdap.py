"""RDAP lookup for .com (Verisign registry).

RDAP is the registry's own machine-readable WHOIS successor. It is the
authoritative source for EPP status codes (redemptionPeriod, pendingDelete)
and the expiration date.

HTTP 404 means "no such object in the registry" -> the name is not
registered. That is a monitoring signal, not a purchase lock: the registrar
must confirm availability again before any registration attempt.
"""
import requests

from ..config import RDAP_BASE_URL, RDAP_TIMEOUT, RDAP_USER_AGENT
from .base import Inconclusive, LookupResult, RateLimited

SOURCE = "rdap.verisign"


def _parse(domain, data):
    expiration = created = None
    for ev in data.get("events", []) or []:
        action = (ev.get("eventAction") or "").lower()
        if action == "expiration":
            expiration = ev.get("eventDate")
        elif action == "registration":
            created = ev.get("eventDate")

    registrar = None
    for entity in data.get("entities", []) or []:
        if "registrar" in (entity.get("roles") or []):
            vcard = entity.get("vcardArray")
            if vcard and len(vcard) > 1:
                for item in vcard[1]:
                    if item and item[0] == "fn":
                        registrar = item[3]
                        break
            if registrar:
                break

    nameservers = []
    for ns in data.get("nameservers", []) or []:
        name = ns.get("ldhName") or ns.get("unicodeName")
        if name:
            nameservers.append(name.lower())

    return LookupResult(
        domain=domain,
        available=False,
        statuses=[str(s) for s in (data.get("status") or [])],
        expiration=expiration,
        created=created,
        registrar=registrar,
        nameservers=nameservers,
        source=SOURCE,
        extra={"handle": data.get("handle")},
    )


def lookup(domain, session=None):
    http = session or requests
    url = f"{RDAP_BASE_URL}/domain/{domain}"
    try:
        resp = http.get(
            url,
            headers={"Accept": "application/rdap+json", "User-Agent": RDAP_USER_AGENT},
            timeout=RDAP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise Inconclusive(f"RDAP request failed: {exc}") from exc

    if resp.status_code == 404:
        return LookupResult(
            domain=domain,
            available=True,
            statuses=["available"],
            source=SOURCE,
            extra={"http_status": 404},
        )
    if resp.status_code == 429:
        raise RateLimited("RDAP rate limited (HTTP 429)")
    if resp.status_code >= 500:
        raise Inconclusive(f"RDAP server error HTTP {resp.status_code}")
    if resp.status_code != 200:
        raise Inconclusive(f"unexpected RDAP status HTTP {resp.status_code}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise Inconclusive("RDAP response is not valid JSON") from exc

    return _parse(domain, data)
