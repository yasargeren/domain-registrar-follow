"""Container health probe: DB reachable and the loop is still updating it."""
import sys
from datetime import datetime, timedelta, timezone

from .config import DB_PATH, POLL_NORMAL_SECONDS
from . import db

STALE_FACTOR = 4


def main():
    if not DB_PATH.exists():
        print("unhealthy: db yok (henuz baslamadi?)", file=sys.stderr)
        return 1
    try:
        rows = db.all_domains()
    except Exception as exc:
        print(f"unhealthy: db okunamadi: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("starting: henuz kayit yok")
        return 0

    newest = None
    for row in rows:
        seen = row.get("last_seen")
        if not seen:
            continue
        try:
            dt = datetime.fromisoformat(seen)
        except ValueError:
            continue
        newest = dt if newest is None or dt > newest else newest

    if newest is None:
        print("unhealthy: last_seen yok", file=sys.stderr)
        return 1

    age = datetime.now(timezone.utc) - newest
    if age > timedelta(seconds=POLL_NORMAL_SECONDS * STALE_FACTOR):
        print(f"unhealthy: son guncelleme {age} once", file=sys.stderr)
        return 1

    print(f"healthy: son guncelleme {int(age.total_seconds())}s once")
    return 0


if __name__ == "__main__":
    sys.exit(main())
