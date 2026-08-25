"""Central configuration. Every runtime knob is an environment variable."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv optional: docker/compose injects env directly
    pass

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _int(name, default):
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _float(name, default):
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _list(name, default=""):
    return [x.strip().lower() for x in os.getenv(name, default).split(",") if x.strip()]


def _path(name, default):
    p = Path(os.getenv(name, default)).expanduser()
    return p if p.is_absolute() else (BASE_DIR / p)


# ---------- general ----------
DOMAINS = _list("DOMAINS", "ornek1.com.tr,ornek2.com.tr,ornek.com")
DB_PATH = _path("DB_PATH", "./data/domains.db")
LOG_PATH = _path("LOG_PATH", "./logs/domain-monitor.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

POLL_NORMAL_SECONDS = _int("POLL_NORMAL_SECONDS", 900)
POLL_EXPIRING_SECONDS = _int("POLL_EXPIRING_SECONDS", 300)
POLL_CRITICAL_SECONDS = _int("POLL_CRITICAL_SECONDS", 60)
POLL_JITTER_SECONDS = _int("POLL_JITTER_SECONDS", 15)
EXPIRING_DAYS = _int("EXPIRING_DAYS", 30)

HEARTBEAT_ENABLED = _bool("HEARTBEAT_ENABLED", True)
HEARTBEAT_HOUR = _int("HEARTBEAT_HOUR", 9)

# ---------- .com lookup (RDAP) ----------
RDAP_BASE_URL = os.getenv("RDAP_BASE_URL", "https://rdap.verisign.com/com/v1").rstrip("/")
RDAP_TIMEOUT = _int("RDAP_TIMEOUT", 15)
RDAP_USER_AGENT = os.getenv("RDAP_USER_AGENT", "domain-registrar-follow/2.0")

# ---------- .com.tr lookup (nic.tr WHOIS) ----------
WHOIS_TR_ENABLED = _bool("WHOIS_TR_ENABLED", True)
WHOIS_TR_HOST = os.getenv("WHOIS_TR_HOST", "whois.trabis.gov.tr")
WHOIS_TR_PORT = _int("WHOIS_TR_PORT", 43)
WHOIS_TR_TIMEOUT = _int("WHOIS_TR_TIMEOUT", 20)
WHOIS_TR_MIN_INTERVAL = _int("WHOIS_TR_MIN_INTERVAL", 60)

# ---------- alerts ----------
TELEGRAM_ENABLED = _bool("TELEGRAM_ENABLED")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

EMAIL_ENABLED = _bool("EMAIL_ENABLED")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USE_TLS = _bool("SMTP_USE_TLS", True)
SMTP_USE_SSL = _bool("SMTP_USE_SSL", False)
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "") or SMTP_USERNAME
EMAIL_TO = [x.strip() for x in os.getenv("EMAIL_TO", "").split(",") if x.strip()]
EMAIL_MIN_SEVERITY = os.getenv("EMAIL_MIN_SEVERITY", "WARNING").upper()

WEBHOOK_ENABLED = _bool("WEBHOOK_ENABLED")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_TIMEOUT = _int("WEBHOOK_TIMEOUT", 10)

ALERT_DEDUPE_SECONDS = _int("ALERT_DEDUPE_SECONDS", 21600)

# ---------- registration safety ----------
AUTO_REGISTER = _bool("AUTO_REGISTER", False)
ACQUIRE_ALLOWLIST = _list("ACQUIRE_ALLOWLIST") or list(DOMAINS)
REGISTER_DRY_RUN_FIRST = _bool("REGISTER_DRY_RUN_FIRST", True)
MAX_REGISTRATION_COST_USD = _float("MAX_REGISTRATION_COST_USD", 200.0)
REGISTRATION_MAX_ATTEMPTS = _int("REGISTRATION_MAX_ATTEMPTS", 3)
REGISTRATION_COOLDOWN_SECONDS = _int("REGISTRATION_COOLDOWN_SECONDS", 20)
REGISTRATION_ATTEMPT_WINDOW_HOURS = _int("REGISTRATION_ATTEMPT_WINDOW_HOURS", 24)
REGISTRATION_MAX_ATTEMPTS_PER_WINDOW = _int("REGISTRATION_MAX_ATTEMPTS_PER_WINDOW", 25)
KILL_SWITCH_FILE = _path("KILL_SWITCH_FILE", "./data/STOP")

# ---------- Porkbun (.com registrar) ----------
PORKBUN_ENABLED = _bool("PORKBUN_ENABLED")
PORKBUN_BASE_URL = os.getenv("PORKBUN_BASE_URL", "https://api.porkbun.com/api/json/v3").rstrip("/")
PORKBUN_API_KEY = os.getenv("PORKBUN_API_KEY", "")
PORKBUN_SECRET_API_KEY = os.getenv("PORKBUN_SECRET_API_KEY", "")
PORKBUN_TIMEOUT = _int("PORKBUN_TIMEOUT", 20)
PORKBUN_WHOIS_PRIVACY = _bool("PORKBUN_WHOIS_PRIVACY", True)
PORKBUN_CHECK_MIN_INTERVAL = _int("PORKBUN_CHECK_MIN_INTERVAL", 10)

# ---------- TRABIS accredited registrar (.com.tr) ----------
TRABIS_ENABLED = _bool("TRABIS_ENABLED")
TRABIS_REGISTRAR_NAME = os.getenv("TRABIS_REGISTRAR_NAME", "")
TRABIS_API_BASE_URL = os.getenv("TRABIS_API_BASE_URL", "").rstrip("/")
TRABIS_API_KEY = os.getenv("TRABIS_API_KEY", "")
TRABIS_API_SECRET = os.getenv("TRABIS_API_SECRET", "")
TRABIS_TIMEOUT = _int("TRABIS_TIMEOUT", 20)

CONTACTS = {
    "registrant": os.getenv("REGISTRANT_CONTACT_ID", ""),
    "admin": os.getenv("ADMIN_CONTACT_ID", ""),
    "tech": os.getenv("TECH_CONTACT_ID", ""),
    "billing": os.getenv("BILLING_CONTACT_ID", ""),
}
NAMESERVERS = [x.strip() for x in os.getenv("NAMESERVERS", "").split(",") if x.strip()]


def redacted_summary():
    """Config snapshot safe to log/print (no secrets)."""
    def mask(v):
        return ("set:" + v[:4] + "***") if v else "empty"
    return {
        "domains": DOMAINS,
        "db_path": str(DB_PATH),
        "poll": [POLL_NORMAL_SECONDS, POLL_EXPIRING_SECONDS, POLL_CRITICAL_SECONDS],
        "telegram_enabled": TELEGRAM_ENABLED,
        "telegram_token": mask(TELEGRAM_BOT_TOKEN),
        "email_enabled": EMAIL_ENABLED,
        "email_to": EMAIL_TO,
        "smtp_password": mask(SMTP_PASSWORD),
        "webhook_enabled": WEBHOOK_ENABLED,
        "auto_register": AUTO_REGISTER,
        "acquire_allowlist": ACQUIRE_ALLOWLIST,
        "dry_run_first": REGISTER_DRY_RUN_FIRST,
        "max_cost_usd": MAX_REGISTRATION_COST_USD,
        "kill_switch": str(KILL_SWITCH_FILE),
        "porkbun_enabled": PORKBUN_ENABLED,
        "porkbun_key": mask(PORKBUN_API_KEY),
        "trabis_enabled": TRABIS_ENABLED,
        "whois_tr_enabled": WHOIS_TR_ENABLED,
    }
