"""SQLite state store: current domain state, event history, alert dedupe."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from .config import DB_PATH

SCHEMA_VERSION = 2


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with connect() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            domain            TEXT PRIMARY KEY,
            tld               TEXT NOT NULL,
            state             TEXT,
            available         INTEGER,
            statuses          TEXT,
            expiration        TEXT,
            created           TEXT,
            registrar         TEXT,
            nameservers       TEXT,
            source            TEXT,
            last_seen         TEXT,
            last_ok           TEXT,
            consecutive_errors INTEGER DEFAULT 0,
            last_error        TEXT,
            registered_by_us  INTEGER DEFAULT 0
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       TEXT NOT NULL,
            domain   TEXT NOT NULL,
            event    TEXT NOT NULL,
            severity TEXT DEFAULT 'INFO',
            detail   TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_domain_ts ON events(domain, ts DESC)")
        c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            key      TEXT PRIMARY KEY,
            last_sent TEXT NOT NULL,
            count    INTEGER DEFAULT 1
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS registration_attempts (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       TEXT NOT NULL,
            domain   TEXT NOT NULL,
            mode     TEXT NOT NULL,          -- dry-run | live
            outcome  TEXT NOT NULL,          -- success | failed | blocked
            detail   TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_attempts_domain_ts ON registration_attempts(domain, ts DESC)")
        c.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))


# ---------------- domain state ----------------

def get(domain):
    with connect() as c:
        row = c.execute("SELECT * FROM domains WHERE domain=?", (domain,)).fetchone()
        return dict(row) if row else None


def all_domains():
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM domains ORDER BY domain").fetchall()]


def save_state(result, state, tld):
    """result: providers.base.LookupResult"""
    with connect() as c:
        c.execute("""
        INSERT INTO domains(domain,tld,state,available,statuses,expiration,created,
                            registrar,nameservers,source,last_seen,last_ok,
                            consecutive_errors,last_error)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,NULL)
        ON CONFLICT(domain) DO UPDATE SET
            tld=excluded.tld, state=excluded.state, available=excluded.available,
            statuses=excluded.statuses, expiration=excluded.expiration,
            created=excluded.created, registrar=excluded.registrar,
            nameservers=excluded.nameservers, source=excluded.source,
            last_seen=excluded.last_seen, last_ok=excluded.last_ok,
            consecutive_errors=0, last_error=NULL
        """, (
            result.domain, tld, state, int(bool(result.available)),
            json.dumps(result.statuses), result.expiration, result.created,
            result.registrar, json.dumps(result.nameservers), result.source,
            now_iso(), now_iso(),
        ))


def save_error(domain, tld, message):
    with connect() as c:
        c.execute("""
        INSERT INTO domains(domain,tld,last_seen,last_error,consecutive_errors)
        VALUES(?,?,?,?,1)
        ON CONFLICT(domain) DO UPDATE SET
            last_seen=excluded.last_seen,
            last_error=excluded.last_error,
            consecutive_errors=domains.consecutive_errors+1
        """, (domain, tld, now_iso(), message[:500]))
        row = c.execute("SELECT consecutive_errors FROM domains WHERE domain=?", (domain,)).fetchone()
        return row["consecutive_errors"] if row else 1


def mark_registered_by_us(domain):
    with connect() as c:
        c.execute("UPDATE domains SET registered_by_us=1 WHERE domain=?", (domain,))


# ---------------- events ----------------

def event(domain, name, detail="", severity="INFO"):
    with connect() as c:
        c.execute(
            "INSERT INTO events(ts,domain,event,severity,detail) VALUES(?,?,?,?,?)",
            (now_iso(), domain, name, severity, str(detail)[:2000]),
        )


def recent_events(limit=30, domain=None):
    with connect() as c:
        if domain:
            rows = c.execute(
                "SELECT * FROM events WHERE domain=? ORDER BY id DESC LIMIT ?", (domain, limit)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


# ---------------- alert dedupe ----------------

def should_send_alert(key, dedupe_seconds):
    """True if this alert key has not been sent within the dedupe window."""
    with connect() as c:
        row = c.execute("SELECT last_sent FROM alerts WHERE key=?", (key,)).fetchone()
        if row:
            try:
                last = datetime.fromisoformat(row["last_sent"])
            except ValueError:
                last = None
            if last and datetime.now(timezone.utc) - last < timedelta(seconds=dedupe_seconds):
                return False
        c.execute("""
        INSERT INTO alerts(key,last_sent,count) VALUES(?,?,1)
        ON CONFLICT(key) DO UPDATE SET last_sent=excluded.last_sent, count=alerts.count+1
        """, (key, now_iso()))
        return True


# ---------------- registration attempts ----------------

def record_attempt(domain, mode, outcome, detail=""):
    with connect() as c:
        c.execute(
            "INSERT INTO registration_attempts(ts,domain,mode,outcome,detail) VALUES(?,?,?,?,?)",
            (now_iso(), domain, mode, outcome, str(detail)[:2000]),
        )


def attempts_in_window(domain, hours):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with connect() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM registration_attempts "
            "WHERE domain=? AND ts>=? AND mode='live'",
            (domain, since),
        ).fetchone()
        return row["n"] if row else 0


def last_attempts(domain=None, limit=20):
    with connect() as c:
        if domain:
            rows = c.execute(
                "SELECT * FROM registration_attempts WHERE domain=? ORDER BY id DESC LIMIT ?",
                (domain, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM registration_attempts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# ---------------- misc ----------------

def set_meta(k, v):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)", (k, str(v)))


def get_meta(k, default=None):
    with connect() as c:
        row = c.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return row["v"] if row else default
