"""24/7 monitoring loop.

Per-domain scheduler: each domain gets its own next-check time derived from
its lifecycle state, so a critical domain is polled every minute while a
quiet one stays on the 15-minute cadence. Errors back off exponentially and
are alerted after repeated failures.
"""
import json
import random
import signal
import sys
import time
from datetime import datetime, timezone

from . import acquire, config, db, lifecycle
from .config import (
    DOMAINS,
    HEARTBEAT_ENABLED,
    HEARTBEAT_HOUR,
    POLL_CRITICAL_SECONDS,
    POLL_JITTER_SECONDS,
    redacted_summary,
)
from .logging_setup import setup
from .notify import active_channels, notify
from .providers import registry
from .providers.base import Inconclusive, NotConfigured, RateLimited, tld_of

log = setup("monitor")

_running = True
ERROR_ALERT_THRESHOLD = 3


def _stop(signum, _frame):
    global _running
    log.info("sinyal alindi (%s), duzgun kapaniyor", signum)
    _running = False


def check_once(domain):
    """One lookup + state persistence + alerting. Returns (state, interval)."""
    tld = tld_of(domain)
    provider = registry.monitor_provider(domain)

    previous = db.get(domain) or {}
    old_state = previous.get("state") or lifecycle.UNKNOWN

    try:
        result = provider.lookup(domain)
    except (RateLimited, Inconclusive, NotConfigured, NotImplementedError) as exc:
        errors = db.save_error(domain, tld, f"{type(exc).__name__}: {exc}")
        log.warning("%s sorgu basarisiz (%s ardisik): %s", domain, errors, exc)
        if errors >= ERROR_ALERT_THRESHOLD:
            notify(
                f"Sorgu tekrar tekrar basarisiz - {domain}",
                f"{errors} ardisik hata.\nKaynak: {getattr(provider, 'SOURCE', provider.__name__)}\n"
                f"Hata: {exc}\n\nIzleme durdu sayilmaz ama durum guncel degil.",
                severity="WARNING", domain=domain,
                dedupe_key=f"error:{domain}",
            )
        backoff = min(POLL_CRITICAL_SECONDS * (2 ** min(errors, 5)), 3600)
        return lifecycle.UNKNOWN, backoff

    state = lifecycle.classify(result)
    db.save_state(result, state, tld)

    log.info(
        "%s -> %s | statuses=%s exp=%s registrar=%s src=%s",
        domain, state, result.statuses, result.expiration, result.registrar, result.source,
    )

    if state != old_state:
        db.event(domain, "state_change", f"{old_state} -> {state}", lifecycle.severity_for(state))
        if lifecycle.is_escalation(old_state, state) or state in lifecycle.CRITICAL_STATES:
            drop = lifecycle.estimated_drop_window(result.expiration, tld)
            body = (
                f"Domain     : {domain}\n"
                f"Yeni durum : {state} ({lifecycle.describe(state)})\n"
                f"Onceki     : {old_state}\n"
                f"Statuses   : {', '.join(result.statuses) or '-'}\n"
                f"Bitis      : {result.expiration or '-'}\n"
                f"Registrar  : {result.registrar or '-'}\n"
                f"Kaynak     : {result.source}\n"
            )
            if drop:
                body += f"\nTahmini dusme (drop) : {drop['drop_expected']}\n(bilgi amacli tahmin)\n"
            if state == lifecycle.AVAILABLE:
                body += "\nHEMEN KAYIT GEREKIYOR."
            notify(
                f"{domain}: {lifecycle.describe(state)}",
                body,
                severity=lifecycle.severity_for(state),
                domain=domain, state=state,
                dedupe_key=f"state:{domain}:{state}",
            )

    if state == lifecycle.AVAILABLE:
        if config.AUTO_REGISTER:
            log.warning("%s MUSAIT -- kayit denemesi baslatiliyor", domain)
            acquire.try_acquire(domain, live=True)
        else:
            log.warning("%s MUSAIT ama AUTO_REGISTER=false -- manuel islem gerekli", domain)

    return state, lifecycle.interval_for(state)


def _heartbeat_if_due():
    if not HEARTBEAT_ENABLED:
        return
    now = datetime.now()
    key = f"heartbeat:{now.date().isoformat()}"
    if now.hour != HEARTBEAT_HOUR or db.get_meta("last_heartbeat") == key:
        return

    rows = db.all_domains()
    lines = []
    for row in rows:
        try:
            statuses = ", ".join(json.loads(row.get("statuses") or "[]")) or "-"
        except (ValueError, TypeError):
            statuses = "-"
        lines.append(
            f"- {row['domain']}: {row.get('state')} | bitis={row.get('expiration') or '-'} "
            f"| registrar={row.get('registrar') or '-'} | statuses={statuses}"
        )
    notify(
        "Gunluk durum ozeti",
        "Izleme calisiyor.\n\n" + "\n".join(lines) +
        f"\n\nAUTO_REGISTER={config.AUTO_REGISTER} | kanallar={active_channels()}",
        severity="INFO",
        dedupe_key=key, dedupe_seconds=23 * 3600,
    )
    db.set_meta("last_heartbeat", key)


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    db.init()
    log.info("domain-monitor basliyor: %s", ", ".join(DOMAINS))
    log.info("yapilandirma: %s", redacted_summary())

    if not DOMAINS:
        log.error("DOMAINS bos; .env dosyasini kontrol edin")
        return 1
    if not active_channels():
        log.warning("hicbir uyari kanali aktif degil (TELEGRAM_ENABLED / EMAIL_ENABLED)")

    schedule = {domain: 0.0 for domain in DOMAINS}

    while _running:
        now = time.monotonic()
        for domain in DOMAINS:
            if not _running:
                break
            if now < schedule[domain]:
                continue
            try:
                _state, interval = check_once(domain)
            except Exception:
                log.exception("%s icin beklenmeyen hata", domain)
                interval = POLL_CRITICAL_SECONDS * 5
            jitter = random.uniform(0, POLL_JITTER_SECONDS)
            schedule[domain] = time.monotonic() + interval + jitter

        try:
            _heartbeat_if_due()
        except Exception:
            log.exception("heartbeat basarisiz")

        sleep_until = min(schedule.values()) if schedule else time.monotonic() + 60
        for _ in range(int(max(1, min(60, sleep_until - time.monotonic())) * 2)):
            if not _running:
                break
            time.sleep(0.5)

    db.set_meta("last_shutdown", datetime.now(timezone.utc).isoformat())
    log.info("domain-monitor durdu")
    return 0


if __name__ == "__main__":
    sys.exit(main())
