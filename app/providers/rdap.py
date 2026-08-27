"""RDAP lookup for .com (Verisign registry).

RDAP is the registry's own machine-readable WHOIS successor. It is the
authoritative source for EPP status codes (redemptionPeriod, pendingDelete)
and the expiration date.

HTTP 404 means "no such object in the registry" -> the name is not
registered. That is a monitoring signal, not a purchase lock: the registrar
must confirm availability again before any registration attempt.

Dual-source cross-check
------------------------
The registry's RDAP response includes (per RFC 9083) a `links` entry with
rel="related" pointing to the sponsoring registrar's own RDAP record for the
same domain. Right after a renewal, the registry's copy can lag behind the
registrar's for a while, which previously caused false EXPIRED_GRACE alerts
on a domain that had actually already been renewed. This module now follows
that link and queries the registrar's RDAP too, picks whichever of the two
shows the later expiration date (a renewal only ever moves this forward,
and "last changed" is not reliably bumped by every responder for a routine
auto-renew) to drive the LookupResult, and keeps both raw summaries in
`extra` so alerts can show both and say which one was fresher. This works
for any .com registrar -- nothing is hardcoded -- because the registrar
RDAP URL is discovered from the registry's own response each time. The
secondary query is best-effort: if it fails, the registry-only result is
returned unchanged.
"""
from datetime import datetime, timezone

import requests

from ..config import RDAP_BASE_URL, RDAP_TIMEOUT, RDAP_USER_AGENT
from .base import Inconclusive, LookupResult, RateLimited

SOURCE = "rdap.verisign"


def _events(data):
    out = {}
    for ev in data.get("events", []) or []:
        action = (ev.get("eventAction") or "").lower()
        date = ev.get("eventDate")
        if action and date:
            out[action] = date
    return out


def _registrar_name(data):
    for entity in data.get("entities", []) or []:
        if "registrar" in (entity.get("roles") or []):
            vcard = entity.get("vcardArray")
            if vcard and len(vcard) > 1:
                for item in vcard[1]:
                    if item and item[0] == "fn":
                        return item[3]
    return None


def _related_rdap_link(data):
    """The registrar's own RDAP URL for this domain, if the registry
    response advertises one (rel="related")."""
    for link in data.get("links", []) or []:
        if (link.get("rel") or "").lower() == "related":
            href = link.get("href")
            if href:
                return href
    return None


def _summarize(data, url):
    events = _events(data)
    nameservers = []
    for ns in data.get("nameservers", []) or []:
        name = ns.get("ldhName") or ns.get("unicodeName")
        if name:
            nameservers.append(name.lower())
    return {
        "url": url,
        "statuses": [str(s) for s in (data.get("status") or [])],
        "expiration": events.get("expiration"),
        "created": events.get("registration"),
        "last_changed": events.get("last changed"),
        "registrar": _registrar_name(data),
        "nameservers": nameservers,
    }


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pick_fresher(registry_summary, registrar_summary):
    """Decide which summary reflects the more current registry state.

    In practice "last changed" is not reliably bumped by every RDAP
    responder for a routine auto-renew (both registry and registrar RDAP
    can keep showing the original registration date there even right after
    a real renewal). Expiration is the trustworthy signal instead: it can
    only move forward on an actual renew, never backward, so whichever
    summary has the later expiration reflects the newer state. "last
    changed" is only used to break a tie when expirations agree.
    """
    reg_exp = _parse_dt(registry_summary.get("expiration"))
    rar_exp = _parse_dt(registrar_summary.get("expiration"))
    if rar_exp and (not reg_exp or rar_exp > reg_exp):
        return "registrar"
    if reg_exp and (not rar_exp or reg_exp > rar_exp):
        return "registry"

    reg_lc = _parse_dt(registry_summary.get("last_changed"))
    rar_lc = _parse_dt(registrar_summary.get("last_changed"))
    if rar_lc and (not reg_lc or rar_lc > reg_lc):
        return "registrar"
    if reg_lc and (not rar_lc or reg_lc > rar_lc):
        return "registry"
    return "same"


def _parse(domain, data, source=SOURCE):
    summary = _summarize(data, source)
    return LookupResult(
        domain=domain,
        available=False,
        statuses=summary["statuses"],
        expiration=summary["expiration"],
        created=summary["created"],
        registrar=summary["registrar"],
        nameservers=summary["nameservers"],
        source=source,
        extra={"handle": data.get("handle")},
    )


def _fetch_related(url, session, timeout):
    """Best-effort secondary lookup at the registrar's own RDAP. Never
    raises -- a failure here must not break the primary (registry) result."""
    try:
        resp = session.get(
            url,
            headers={"Accept": "application/rdap+json", "User-Agent": RDAP_USER_AGENT},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def format_dual_source(extra):
    """Human-readable (Turkish) note for alert bodies when two RDAP sources
    were compared. Returns None if there was only one source."""
    if not extra or not extra.get("dual_source"):
        return None
    sources = extra.get("sources") or {}
    registry = sources.get("registry") or {}
    registrar = sources.get("registrar") or {}
    fresher = extra.get("fresher_source")

    note = {
        "registrar": "-> Registrar kaynagi daha guncel; bildirimde bu deger kullanildi.",
        "registry": "-> Registry kaynagi daha guncel (ya da esit); bildirimde bu deger kullanildi.",
        "same": "-> Iki kaynak ayni veriyi donduruyor.",
    }.get(fresher, "")

    return (
        "Iki RDAP kaynagi karsilastirildi:\n"
        f"  Registry  ({registry.get('url')}): bitis={registry.get('expiration') or '-'} "
        f"statuses={', '.join(registry.get('statuses') or []) or '-'}\n"
        f"  Registrar ({registrar.get('url')}): bitis={registrar.get('expiration') or '-'} "
        f"statuses={', '.join(registrar.get('statuses') or []) or '-'}\n"
        f"{note}"
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

    result = _parse(domain, data, SOURCE)

    related_url = _related_rdap_link(data)
    if not related_url:
        return result

    related_data = _fetch_related(related_url, http, RDAP_TIMEOUT)
    if not related_data:
        result.extra["dual_source"] = False
        result.extra["registrar_rdap_error"] = {
            "url": related_url,
            "note": "registrar RDAP sorgusu basarisiz, sadece registry verisi kullanildi",
        }
        return result

    registry_summary = _summarize(data, SOURCE)
    registrar_summary = _summarize(related_data, related_url)

    fresher = _pick_fresher(registry_summary, registrar_summary)

    result.extra["dual_source"] = True
    result.extra["sources"] = {"registry": registry_summary, "registrar": registrar_summary}
    result.extra["fresher_source"] = fresher

    if fresher == "registrar":
        result.statuses = registrar_summary["statuses"] or result.statuses
        result.expiration = registrar_summary["expiration"] or result.expiration
        result.created = registrar_summary["created"] or result.created
        result.registrar = registrar_summary["registrar"] or result.registrar
        result.nameservers = registrar_summary["nameservers"] or result.nameservers
        result.source = f"{SOURCE}+registrar({related_url})"

    return result
