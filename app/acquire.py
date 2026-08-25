"""Acquisition layer: the only code path that can spend money.

Every registration passes through `preflight()` first. The gates are
deliberately boring and independent, so a single mistake elsewhere cannot
turn into an unwanted purchase:

  G1  domain is on ACQUIRE_ALLOWLIST          (no generic "buy anything")
  G2  kill-switch file absent                 (instant manual stop)
  G3  AUTO_REGISTER=true                      (live mode only)
  G4  attempt budget in window not exhausted  (anti runaway loop)
  G5  registrar adapter enabled+configured    (fail closed)
  G6  registrar-side availability confirmed   (registry RDAP is not enough)
  G7  price <= MAX_REGISTRATION_COST_USD      (premium/price-spike guard)
  G8  dry-run rehearsal succeeded             (REGISTER_DRY_RUN_FIRST)

Every attempt -- blocked, dry, live, failed -- is written to the
registration_attempts table and alerted on.
"""
import logging
import time

from . import config, db
from .notify import notify
from .providers import registry
from .providers.base import NotConfigured, ProviderError, tld_of

log = logging.getLogger("acquire")


class Blocked(RuntimeError):
    """A safety gate refused the attempt."""


def kill_switch_active():
    return config.KILL_SWITCH_FILE.exists()


def preflight(domain, live):
    """Run the gates. Raises Blocked with a human-readable reason."""
    domain = domain.strip().lower()

    if domain not in [d.lower() for d in config.ACQUIRE_ALLOWLIST]:
        raise Blocked(f"G1 allowlist: {domain} ACQUIRE_ALLOWLIST icinde degil")

    if kill_switch_active():
        raise Blocked(f"G2 kill-switch aktif: {config.KILL_SWITCH_FILE}")

    if live and not config.AUTO_REGISTER:
        raise Blocked("G3 AUTO_REGISTER=false (canli kayit kapali)")

    if live:
        used = db.attempts_in_window(domain, config.REGISTRATION_ATTEMPT_WINDOW_HOURS)
        if used >= config.REGISTRATION_MAX_ATTEMPTS_PER_WINDOW:
            raise Blocked(
                f"G4 deneme butcesi doldu: son {config.REGISTRATION_ATTEMPT_WINDOW_HOURS}h "
                f"icinde {used} canli deneme"
            )
    return domain


def _price_gate(check_info, domain):
    price = check_info.get("price_usd")
    if price is None:
        raise Blocked("G7 fiyat okunamadi; kayit denenmeyecek")
    if price > config.MAX_REGISTRATION_COST_USD:
        raise Blocked(
            f"G7 fiyat tavani asildi: {domain} = ${price:.2f} > "
            f"${config.MAX_REGISTRATION_COST_USD:.2f}"
        )
    if check_info.get("premium"):
        log.warning("%s premium olarak isaretli (fiyat $%.2f)", domain, price)
    return price


def _record(domain, mode, outcome, detail, severity="INFO", subject=None):
    db.record_attempt(domain, mode, outcome, detail)
    db.event(domain, f"registration_{outcome}", f"mode={mode}; {detail}", severity)
    notify(
        subject or f"KAYIT {outcome.upper()} - {domain}",
        f"Domain : {domain}\nMod    : {mode}\nSonuc  : {outcome}\n\n{detail}",
        severity=severity,
        domain=domain,
        dedupe_key=None,  # registration events are never suppressed
    )


def dry_run(domain):
    """Rehearse a registration without spending anything."""
    domain = preflight(domain, live=False)
    provider = registry.registrar_provider(domain)

    try:
        info = provider.check(domain)
    except NotConfigured as exc:
        _record(domain, "dry-run", "blocked", f"G5 adapter hazir degil: {exc}", "WARNING")
        return {"ok": False, "reason": str(exc)}

    if not info["available"]:
        detail = f"registrar musait degil (fiyat={info.get('price_usd')})"
        _record(domain, "dry-run", "blocked", detail)
        return {"ok": False, "reason": detail, "check": info}

    price = _price_gate(info, domain)
    result = provider.register(domain, info["price_cents"], dry_run=True)
    detail = f"fiyat=${price:.2f}; yanit={result}"
    _record(domain, "dry-run", "success", detail)
    return {"ok": True, "check": info, "result": result}


def try_acquire(domain, live=True):
    """Full acquisition path. Returns a result dict; never raises to the caller."""
    domain = domain.strip().lower()
    try:
        preflight(domain, live=live)
    except Blocked as exc:
        log.warning("kayit engellendi: %s", exc)
        _record(domain, "live" if live else "dry-run", "blocked", str(exc), "WARNING")
        return {"ok": False, "blocked": str(exc)}

    try:
        provider = registry.registrar_provider(domain)
    except NotConfigured as exc:
        _record(domain, "live", "blocked", f"G5 {exc}", "CRITICAL")
        return {"ok": False, "blocked": str(exc)}

    # .com.tr path: no automated registrar contract implemented yet.
    if tld_of(domain) in ("com.tr", "tr"):
        try:
            provider.available(domain)
        except (NotConfigured, NotImplementedError) as exc:
            detail = (
                "TR kaydi otomatiklestirilmedi. Akredite kayit kurulusu paneli/API'si "
                f"uzerinden HEMEN manuel kayit gerekiyor.\nAyrinti: {exc}"
            )
            _record(domain, "live", "blocked", detail, "CRITICAL",
                    subject=f"\U0001F6A8 MANUEL KAYIT GEREKIYOR - {domain}")
            return {"ok": False, "blocked": "trabis adapter not implemented"}

    last_error = None
    for attempt in range(1, config.REGISTRATION_MAX_ATTEMPTS + 1):
        try:
            info = provider.check(domain)
            if not info["available"]:
                detail = f"deneme {attempt}: registrar tarafinda musait degil"
                log.info(detail)
                _record(domain, "live", "blocked", detail, "WARNING")
                return {"ok": False, "blocked": detail, "check": info}

            price = _price_gate(info, domain)

            if config.REGISTER_DRY_RUN_FIRST:
                rehearsal = provider.register(domain, info["price_cents"], dry_run=True)
                would = rehearsal.get("wouldSucceed")
                funds = rehearsal.get("sufficientFunds", True)
                if would is False or funds is False:
                    detail = f"G8 dry-run basarisiz: {rehearsal}"
                    _record(domain, "live", "blocked", detail, "CRITICAL")
                    return {"ok": False, "blocked": detail}
                db.record_attempt(domain, "dry-run", "success", str(rehearsal))

            result = provider.register(domain, info["price_cents"], dry_run=False)

            verified, record = (True, None)
            try:
                verified, record = provider.owns(domain)
            except Exception:
                log.exception("kayit sonrasi dogrulama basarisiz (%s)", domain)
                verified = False

            db.mark_registered_by_us(domain)
            detail = (
                f"deneme {attempt}; fiyat=${price:.2f}; dogrulama={'OK' if verified else 'BEKLEMEDE'}\n"
                f"registrar yaniti: {result}\nhesap kaydi: {record}"
            )
            _record(domain, "live", "success", detail, "CRITICAL",
                    subject=f"✅ DOMAIN ALINDI - {domain}")
            return {"ok": True, "result": result, "verified": verified}

        except (ProviderError, NotConfigured, NotImplementedError, Blocked) as exc:
            last_error = exc
            log.warning("kayit denemesi %s basarisiz (%s): %s", attempt, domain, exc)
            db.record_attempt(domain, "live", "failed", f"deneme {attempt}: {exc}")
            if attempt < config.REGISTRATION_MAX_ATTEMPTS:
                time.sleep(config.REGISTRATION_COOLDOWN_SECONDS)
        except Exception as exc:  # unexpected -- stop immediately, do not retry blindly
            last_error = exc
            log.exception("beklenmeyen kayit hatasi (%s)", domain)
            break

    _record(domain, "live", "failed",
            f"tum denemeler basarisiz. son hata: {last_error}", "CRITICAL",
            subject=f"❌ KAYIT BASARISIZ - {domain}")
    return {"ok": False, "error": str(last_error)}


if __name__ == "__main__":
    raise SystemExit("Bu modul dogrudan calistirilmaz. 'python -m app.cli' kullanin.")
