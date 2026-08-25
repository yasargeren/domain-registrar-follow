"""Routing table: which provider answers for which domain."""
from . import porkbun, rdap, trabis, whois_tr
from .base import NotConfigured, tld_of


def monitor_provider(domain):
    """Read-only lifecycle source for a domain."""
    tld = tld_of(domain)
    if tld == "com":
        return rdap
    if tld in ("com.tr", "tr"):
        return whois_tr
    raise NotConfigured(f"desteklenmeyen TLD: {domain}")


def registrar_provider(domain):
    """Adapter that can actually buy the domain."""
    tld = tld_of(domain)
    if tld == "com":
        return porkbun
    if tld in ("com.tr", "tr"):
        return trabis
    raise NotConfigured(f"desteklenmeyen TLD: {domain}")


def lookup(domain):
    return monitor_provider(domain).lookup(domain)
