"""Domain lifecycle state machine.

Maps a normalized LookupResult onto a lifecycle state, decides the polling
interval and the alert severity for that state.

.com (ICANN/Verisign) timeline after expiry:
    expiry -> auto-renew grace (~45d) -> redemptionPeriod (30d)
           -> pendingDelete (5d) -> DROP (available)

.com.tr (TRABIS) timeline: the registry runs its own grace/redemption
process; the domain simply disappears from WHOIS when it is released, so
the WHOIS "No match" answer is the only reliable release signal.
"""
from datetime import datetime, timedelta, timezone

from .config import (
    EXPIRING_DAYS,
    POLL_CRITICAL_SECONDS,
    POLL_EXPIRING_SECONDS,
    POLL_NORMAL_SECONDS,
)

ACTIVE = "ACTIVE"
EXPIRING = "EXPIRING"
EXPIRED_GRACE = "EXPIRED_GRACE"
REDEMPTION = "REDEMPTION"
PENDING_DELETE = "PENDING_DELETE"
AVAILABLE = "AVAILABLE"
UNKNOWN = "UNKNOWN"

# States that mean "act now"
CRITICAL_STATES = (REDEMPTION, PENDING_DELETE, AVAILABLE)

SEVERITY = {
    ACTIVE: "INFO",
    EXPIRING: "INFO",
    EXPIRED_GRACE: "WARNING",
    REDEMPTION: "WARNING",
    PENDING_DELETE: "CRITICAL",
    AVAILABLE: "CRITICAL",
    UNKNOWN: "WARNING",
}

STATE_TR = {
    ACTIVE: "Aktif (baskasinin uzerinde)",
    EXPIRING: "Suresi yaklasiyor",
    EXPIRED_GRACE: "Suresi doldu / grace donemi",
    REDEMPTION: "Redemption (geri alim) donemi",
    PENDING_DELETE: "Silinme kuyrugunda (pendingDelete)",
    AVAILABLE: "MUSAIT - kayit edilebilir",
    UNKNOWN: "Bilinmiyor / sorgu basarisiz",
}


def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _norm(statuses):
    return " ".join(statuses or []).lower().replace("_", "").replace(" ", "").replace("-", "")


def classify(result, now=None, expiring_days=None):
    """LookupResult -> lifecycle state."""
    now = now or datetime.now(timezone.utc)
    expiring_days = EXPIRING_DAYS if expiring_days is None else expiring_days

    if result.available:
        return AVAILABLE

    flat = _norm(result.statuses)
    if "pendingdelete" in flat:
        return PENDING_DELETE
    if "redemptionperiod" in flat or "pendingrestore" in flat:
        return REDEMPTION

    exp = parse_dt(result.expiration)
    if exp:
        if exp <= now:
            return EXPIRED_GRACE
        if exp - now <= timedelta(days=expiring_days):
            return EXPIRING
        return ACTIVE

    # No expiry data and no status hints: registered but opaque.
    return ACTIVE if result.statuses else UNKNOWN


def interval_for(state):
    if state in CRITICAL_STATES:
        return POLL_CRITICAL_SECONDS
    if state in (EXPIRING, EXPIRED_GRACE):
        return POLL_EXPIRING_SECONDS
    if state == UNKNOWN:
        return POLL_EXPIRING_SECONDS
    return POLL_NORMAL_SECONDS


def severity_for(state):
    return SEVERITY.get(state, "INFO")


def is_escalation(old_state, new_state):
    """True when the domain moved closer to being purchasable."""
    order = [UNKNOWN, ACTIVE, EXPIRING, EXPIRED_GRACE, REDEMPTION, PENDING_DELETE, AVAILABLE]
    try:
        return order.index(new_state) > order.index(old_state)
    except ValueError:
        return old_state != new_state


def estimated_drop_window(expiration, tld="com"):
    """Rough .com drop estimate. Informational only -- never a purchase trigger.

    Registrars vary; treat the returned range as a planning hint.
    """
    exp = parse_dt(expiration)
    if not exp or tld != "com":
        return None
    redemption_start = exp + timedelta(days=45)
    pending_delete_start = redemption_start + timedelta(days=30)
    drop = pending_delete_start + timedelta(days=5)
    return {
        "expiration": exp.isoformat(),
        "redemption_expected": redemption_start.isoformat(),
        "pending_delete_expected": pending_delete_start.isoformat(),
        "drop_expected": drop.isoformat(),
        "note": "tahmini; registrar politikasina gore +/- gunler kayabilir",
    }


def describe(state):
    return STATE_TR.get(state, state)
