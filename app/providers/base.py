"""Normalized provider contract shared by every lookup/registration backend."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ProviderError(RuntimeError):
    """Base class for provider failures."""


class RateLimited(ProviderError):
    """Upstream refused the query because of rate limiting."""


class Inconclusive(ProviderError):
    """Upstream answered but the answer cannot be trusted.

    Never downgrade this to 'available' -- an unreadable answer must not be
    turned into a purchase decision.
    """


class NotConfigured(ProviderError):
    """Adapter is disabled or missing credentials (fail-closed)."""


@dataclass
class LookupResult:
    domain: str
    available: bool
    statuses: List[str] = field(default_factory=list)
    expiration: Optional[str] = None      # ISO-8601 UTC
    created: Optional[str] = None         # ISO-8601 UTC
    registrar: Optional[str] = None
    nameservers: List[str] = field(default_factory=list)
    source: str = ""                      # "rdap" | "whois.nic.tr" | "porkbun" | ...
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self):
        return {
            "domain": self.domain,
            "available": self.available,
            "statuses": self.statuses,
            "expiration": self.expiration,
            "created": self.created,
            "registrar": self.registrar,
            "nameservers": self.nameservers,
            "source": self.source,
            "extra": self.extra,
        }


def tld_of(domain: str) -> str:
    d = domain.strip().lower().strip(".")
    if d.endswith(".com.tr"):
        return "com.tr"
    if d.endswith(".tr"):
        return "tr"
    return d.rsplit(".", 1)[-1]
