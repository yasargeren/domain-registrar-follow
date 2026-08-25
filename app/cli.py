"""Operator CLI.

    python -m app.cli status               izlenen domainlerin son kayitli durumu
    python -m app.cli check <domain>       canli sorgu (DB'yi de gunceller)
    python -m app.cli check-all            tum domainler icin canli sorgu
    python -m app.cli history [domain]     son olaylar
    python -m app.cli attempts [domain]    kayit denemeleri
    python -m app.cli dry-run <domain>     registrar tarafinda kuru satin alma provasi
    python -m app.cli register <domain>    CANLI KAYIT (onay ister)
    python -m app.cli test-alerts          uyari kanallarini test et
    python -m app.cli ping                 registrar kimlik/baglanti testi
    python -m app.cli config               maskelenmis yapilandirma ozeti
    python -m app.cli stop / resume        kill-switch ac/kapa
"""
import argparse
import json
import sys
from datetime import datetime, timezone

from . import acquire, config, db, lifecycle
from .config import (
    DOMAINS,
    KILL_SWITCH_FILE,
    redacted_summary,
)
from .logging_setup import setup
from .notify import active_channels, notify
from .providers import registry
from .providers.base import tld_of

log = setup("cli")


def _fmt_row(row):
    statuses = row.get("statuses") or "[]"
    try:
        statuses = ", ".join(json.loads(statuses)) or "-"
    except (ValueError, TypeError):
        pass
    return (
        f"{row['domain']:<22} {str(row.get('state')):<15} "
        f"exp={str(row.get('expiration') or '-')[:10]:<12} "
        f"reg={str(row.get('registrar') or '-')[:24]:<26} "
        f"src={row.get('source') or '-'}\n"
        f"{'':22} statuses: {statuses}\n"
        f"{'':22} son sorgu: {row.get('last_seen') or '-'}"
        + (f"  | HATA: {row['last_error']}" if row.get("last_error") else "")
    )


def cmd_status(_args):
    db.init()
    rows = db.all_domains()
    if not rows:
        print("Henuz kayit yok. Once 'python -m app.cli check-all' calistirin.")
        return 0
    print(f"AUTO_REGISTER={config.AUTO_REGISTER} | kill-switch={'AKTIF' if acquire.kill_switch_active() else 'kapali'} "
          f"| kanallar={active_channels() or 'YOK'}\n")
    for row in rows:
        print(_fmt_row(row))
        print("-" * 78)
    return 0


def _check(domain):
    tld = tld_of(domain)
    provider = registry.monitor_provider(domain)
    result = provider.lookup(domain)
    state = lifecycle.classify(result)
    db.save_state(result, state, tld)
    print(f"\n{domain}")
    print(f"  durum      : {state}  ({lifecycle.describe(state)})")
    print(f"  musait mi  : {'EVET' if result.available else 'hayir'}")
    print(f"  statuses   : {', '.join(result.statuses) or '-'}")
    print(f"  bitis      : {result.expiration or '-'}")
    print(f"  olusturma  : {result.created or '-'}")
    print(f"  registrar  : {result.registrar or '-'}")
    print(f"  ns         : {', '.join(result.nameservers) or '-'}")
    print(f"  kaynak     : {result.source}")
    drop = lifecycle.estimated_drop_window(result.expiration, tld)
    if drop:
        print(f"  tahmini redemption : {drop['redemption_expected'][:10]}")
        print(f"  tahmini pendingDel : {drop['pending_delete_expected'][:10]}")
        print(f"  tahmini drop       : {drop['drop_expected'][:10]}  (tahmin)")
    return state


def cmd_check(args):
    db.init()
    _check(args.domain.lower())
    return 0


def cmd_check_all(_args):
    db.init()
    failed = 0
    for domain in DOMAINS:
        try:
            _check(domain)
        except Exception as exc:
            failed += 1
            print(f"\n{domain}\n  HATA: {type(exc).__name__}: {exc}")
    return 1 if failed else 0


def cmd_history(args):
    db.init()
    for row in reversed(db.recent_events(args.limit, args.domain)):
        print(f"{row['ts'][:19]}  {row['severity']:<8} {row['domain']:<20} {row['event']}: {row['detail'][:120]}")
    return 0


def cmd_attempts(args):
    db.init()
    rows = db.last_attempts(args.domain, args.limit)
    if not rows:
        print("kayit denemesi yok")
        return 0
    for row in reversed(rows):
        print(f"{row['ts'][:19]}  {row['mode']:<8} {row['outcome']:<8} {row['domain']:<20} {row['detail'][:120]}")
    return 0


def cmd_dry_run(args):
    db.init()
    result = acquire.dry_run(args.domain.lower())
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


def cmd_register(args):
    db.init()
    domain = args.domain.lower()
    print("!" * 70)
    print(f"CANLI KAYIT: {domain} -- bu islem PARA HARCAR ve geri alinamaz.")
    print("!" * 70)
    if not args.yes:
        answer = input(f"Onaylamak icin domaini tam yazin ({domain}): ").strip().lower()
        if answer != domain:
            print("iptal edildi")
            return 1
    result = acquire.try_acquire(domain, live=True)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


def cmd_test_alerts(_args):
    db.init()
    channels = active_channels()
    if not channels:
        print("Aktif kanal yok. .env icinde TELEGRAM_ENABLED / EMAIL_ENABLED ayarlayin.")
        return 1
    print(f"Aktif kanallar: {channels}")
    result = notify(
        "Test uyarisi",
        "domain-registrar-follow kanal testi.\n"
        f"Zaman: {datetime.now(timezone.utc).isoformat()}\n"
        f"Izlenen: {', '.join(DOMAINS)}",
        severity="CRITICAL",
        dedupe_key=None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if all(v is True for k, v in result.items() if k != "none") else 1


def cmd_ping(_args):
    from .providers import porkbun
    try:
        print(json.dumps(porkbun.ping(), indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"porkbun ping basarisiz: {type(exc).__name__}: {exc}")
        return 1


def cmd_config(_args):
    print(json.dumps(redacted_summary(), indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_stop(_args):
    KILL_SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    KILL_SWITCH_FILE.write_text(datetime.now(timezone.utc).isoformat())
    print(f"KILL SWITCH AKTIF -> {KILL_SWITCH_FILE}")
    return 0


def cmd_resume(_args):
    if not KILL_SWITCH_FILE.exists():
        print("kill-switch zaten kapali")
        return 0
    try:
        KILL_SWITCH_FILE.unlink()
    except OSError as exc:
        print(f"kill-switch dosyasi silinemedi: {exc}\n"
              f"Elle silin: rm {KILL_SWITCH_FILE}")
        return 1
    print("kill-switch kaldirildi")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status").set_defaults(func=cmd_status)

    p = sub.add_parser("check"); p.add_argument("domain"); p.set_defaults(func=cmd_check)
    sub.add_parser("check-all").set_defaults(func=cmd_check_all)

    p = sub.add_parser("history"); p.add_argument("domain", nargs="?")
    p.add_argument("--limit", type=int, default=30); p.set_defaults(func=cmd_history)

    p = sub.add_parser("attempts"); p.add_argument("domain", nargs="?")
    p.add_argument("--limit", type=int, default=20); p.set_defaults(func=cmd_attempts)

    p = sub.add_parser("dry-run"); p.add_argument("domain"); p.set_defaults(func=cmd_dry_run)

    p = sub.add_parser("register"); p.add_argument("domain")
    p.add_argument("--yes", action="store_true", help="onay sorusunu atla (dikkat)")
    p.set_defaults(func=cmd_register)

    sub.add_parser("test-alerts").set_defaults(func=cmd_test_alerts)
    sub.add_parser("ping").set_defaults(func=cmd_ping)
    sub.add_parser("config").set_defaults(func=cmd_config)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    sub.add_parser("resume").set_defaults(func=cmd_resume)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
