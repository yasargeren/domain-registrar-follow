"""TRABIS (.tr) registration adapter -- fail-closed by design.

TRABIS is the .tr registry. End users cannot register directly against it;
registration goes through an accredited Registration Organization
("Kayit Kurulusu"). Each of those exposes its own API contract, so this
project refuses to guess one: every call raises until a real contract is
implemented and TRABIS_ENABLED=true.

To wire a registrar in:
  1. Pick an accredited registrar from the TRABIS list and sign up for API
     access; obtain the official API documentation and credentials.
  2. Fill TRABIS_* variables in .env.
  3. Implement `lookup()` and `register()` below against that contract,
     returning the shapes documented in each function.
  4. Test with the registrar's sandbox first, on a throwaway domain.
  5. Only then set TRABIS_ENABLED=true.

Monitoring does NOT depend on this module: lifecycle tracking for
.com.tr runs on providers/whois_tr.py (registry WHOIS, read-only).

DO NOT scrape the public TRABIS/nic.tr web forms or bypass any anti-bot
control -- that is both against their terms and operationally fragile.
"""
from ..config import (
    TRABIS_API_BASE_URL,
    TRABIS_API_KEY,
    TRABIS_ENABLED,
    TRABIS_REGISTRAR_NAME,
)
from .base import NotConfigured

SOURCE = "trabis-registrar"


def _guard():
    if not TRABIS_ENABLED:
        raise NotConfigured(
            "TRABIS adapter disabled. Akredite kayit kurulusu secilip resmi API "
            "sozlesmesi uygulanana kadar .com.tr kaydi yapilamaz."
        )
    if not (TRABIS_API_BASE_URL and TRABIS_API_KEY):
        raise NotConfigured("TRABIS_API_BASE_URL / TRABIS_API_KEY missing")


def lookup(domain):
    """Return providers.base.LookupResult from the registrar's API.

    Only needed if you prefer the registrar's view over registry WHOIS.
    """
    _guard()
    raise NotImplementedError(
        f"Implement lookup() for registrar {TRABIS_REGISTRAR_NAME or '<unset>'} "
        "(see app/providers/trabis.py docstring)"
    )


def available(domain):
    """Return bool -- registrar-side availability check before registering."""
    _guard()
    raise NotImplementedError("Implement available() for your accredited TR registrar")


def register(domain, dry_run=True):
    """Return the registrar's registration response as a dict."""
    _guard()
    raise NotImplementedError("Implement register() for your accredited TR registrar")


def owns(domain):
    """Post-registration verification against the registrar's domain list."""
    _guard()
    raise NotImplementedError("Implement owns() for your accredited TR registrar")
