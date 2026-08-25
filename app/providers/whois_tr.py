"""WHOIS (port 43) lookup for .tr / .com.tr via nic.tr.

TRABIS does not publish an RDAP service for .tr, so lifecycle monitoring
uses the registry WHOIS server. Two rules keep this safe and polite:

1. Rate limiting -- nic.tr enforces strict query limits and will block a
   noisy client. A process-wide minimum interval is enforced here
   (WHOIS_TR_MIN_INTERVAL, default 60s).
2. Fail closed -- a domain is reported AVAILABLE only on an explicit
   "no match" answer. Rate-limit / truncated / unparseable answers raise
   RateLimited or Inconclusive so the monitor never invents availability.

This module only reads. Registration for .com.tr must go through an
accredited Registration Organization (see providers/trabis.py).
"""
import re
import socket
import threading
import time
from datetime import datetime, timezone

from ..config import (
    WHOIS_TR_ENABLED,
    WHOIS_TR_HOST,
    WHOIS_TR_MIN_INTERVAL,
    WHOIS_TR_PORT,
    WHOIS_TR_TIMEOUT,
)
from .base import Inconclusive, LookupResult, NotConfigured, RateLimited

SOURCE = "whois.nic.tr"

_lock = threading.Lock()
_last_query_ts = 0.0

NO_MATCH_PATTERNS = (
    "no match found",
    "no match for",
    "kayit bulunamadi",
    "kayıt bulunamadı",
    "not found in database",
)

BLOCKED_PATTERNS = (
    "access limit",
    "query limit",
    "exceeded",
    "denied",
    "blocked",
    "try again later",
    "too many",
    "sorgu limiti",
    "erisim engellendi",
)

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "oca": 1, "sub": 2, "nis": 4, "haz": 6, "tem": 7, "agu": 8,
    "eyl": 9, "eki": 10, "kas": 11, "ara": 12,
}

_DATE_RE = re.compile(r"(\d{4})[-./](\w{3,9})[-./](\d{1,2})")
_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_date(value):
    """nic.tr prints dates like '2027-Jan-05.' -- normalize to ISO-8601 UTC."""
    if not value:
        return None
    v = value.strip().rstrip(".")

    m = _DATE_RE.search(v)
    if m:
        year, mon, day = m.group(1), m.group(2)[:3].lower(), int(m.group(3))
        if mon in MONTHS:
            return datetime(int(year), MONTHS[mon], day, tzinfo=timezone.utc).isoformat()

    m = _ISO_RE.search(v)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        tzinfo=timezone.utc).isoformat()
    return None


def parse(domain, text):
    """Parse a raw nic.tr WHOIS answer into a LookupResult."""
    if not text or not text.strip():
        raise Inconclusive("empty WHOIS response")

    low = text.lower()

    if any(p in low for p in BLOCKED_PATTERNS):
        raise RateLimited("nic.tr refused the query (rate limit / access denied)")

    if any(p in low for p in NO_MATCH_PATTERNS):
        return LookupResult(
            domain=domain,
            available=True,
            statuses=["available"],
            source=SOURCE,
            extra={"reason": "no-match"},
        )

    expiration = created = None
    registrar = None
    statuses = []
    nameservers = []
    section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low_line = line.lower()

        if low_line.startswith("**"):
            header = low_line.strip("* ").rstrip(":").strip()
            if "registrar" in header:
                section = "registrar"
            elif "domain servers" in header or "nameserver" in header:
                section = "ns"
            elif "domain status" in header or "status" == header:
                section = "status"
            elif "additional info" in header:
                section = "info"
            elif "registrant" in header:
                section = "registrant"
            else:
                section = None
            continue

        if "expires on" in low_line:
            expiration = parse_date(line.split(":", 1)[-1])
            continue
        if "created on" in low_line:
            created = parse_date(line.split(":", 1)[-1])
            continue

        if section == "registrar" and "organization name" in low_line:
            registrar = line.split(":", 1)[-1].strip()
            continue
        if section == "status":
            statuses.append(line)
            continue
        if section == "ns":
            token = line.split()[0].lower().rstrip(".")
            if "." in token:
                nameservers.append(token)
            continue

    if not any([expiration, created, registrar, nameservers, statuses]):
        raise Inconclusive("WHOIS answer could not be parsed (format change?)")

    if not statuses:
        statuses = ["registered"]

    return LookupResult(
        domain=domain,
        available=False,
        statuses=statuses,
        expiration=expiration,
        created=created,
        registrar=registrar,
        nameservers=nameservers,
        source=SOURCE,
    )


def query_raw(domain, host=None, port=None, timeout=None):
    """Send one WHOIS query, honouring the process-wide minimum interval."""
    global _last_query_ts
    host = host or WHOIS_TR_HOST
    port = port or WHOIS_TR_PORT
    timeout = timeout or WHOIS_TR_TIMEOUT

    with _lock:
        wait = WHOIS_TR_MIN_INTERVAL - (time.monotonic() - _last_query_ts)
        if wait > 0:
            time.sleep(wait)
        _last_query_ts = time.monotonic()

    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(f"{domain}\r\n".encode("utf-8"))
            chunks = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
    except (socket.timeout, OSError) as exc:
        raise Inconclusive(f"WHOIS connection failed: {exc}") from exc

    return b"".join(chunks).decode("utf-8", errors="replace")


def lookup(domain):
    if not WHOIS_TR_ENABLED:
        raise NotConfigured("WHOIS_TR_ENABLED=false")
    return parse(domain, query_raw(domain))
