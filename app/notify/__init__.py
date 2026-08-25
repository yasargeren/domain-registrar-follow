"""Multi-channel alerting with per-key deduplication.

notify() never raises: a broken channel must not stop the monitor loop or
block a registration attempt. Failures are logged and recorded as events.
"""
import logging

from .. import db
from ..config import ALERT_DEDUPE_SECONDS
from . import email_smtp, telegram, webhook

log = logging.getLogger("notify")

CHANNELS = (telegram, email_smtp, webhook)


def active_channels():
    return [c.NAME for c in CHANNELS if c.enabled()]


def notify(subject, body, severity="INFO", domain=None, state=None,
           dedupe_key=None, dedupe_seconds=None, force=False):
    """Fan out one alert to every enabled channel.

    dedupe_key: suppress repeats of the same logical alert. Pass None to
                always send (used for registration attempts).
    Returns a per-channel result dict.
    """
    if dedupe_key and not force:
        window = ALERT_DEDUPE_SECONDS if dedupe_seconds is None else dedupe_seconds
        try:
            if not db.should_send_alert(dedupe_key, window):
                log.debug("uyari bastirildi (dedupe): %s", dedupe_key)
                return {"skipped": "dedupe"}
        except Exception:
            log.exception("dedupe kontrolu basarisiz; uyari yine de gonderiliyor")

    results = {}
    for channel in CHANNELS:
        if not channel.enabled():
            continue
        try:
            results[channel.NAME] = bool(
                channel.send(subject, body, severity=severity, domain=domain, state=state)
            )
        except Exception as exc:
            log.exception("%s kanali basarisiz", channel.NAME)
            results[channel.NAME] = f"error: {exc}"

    if not results:
        log.warning("hicbir uyari kanali aktif degil: %s | %s", subject, body.replace("\n", " ")[:200])
        results["none"] = "no channel enabled"

    try:
        db.event(domain or "-", "alert", f"{subject} :: {results}", severity)
    except Exception:
        log.exception("uyari olayi kaydedilemedi")

    return results
