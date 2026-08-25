"""Telegram channel with retry and 429 handling."""
import logging
import time

import requests

from ..config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ENABLED

log = logging.getLogger("notify.telegram")
NAME = "telegram"
MAX_LEN = 4000


def enabled():
    return TELEGRAM_ENABLED


def send(subject, body, severity="INFO", **_):
    if not TELEGRAM_ENABLED:
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("TELEGRAM_ENABLED=true ama token/chat_id bos")

    icon = {"CRITICAL": "\U0001F6A8", "WARNING": "⚠️"}.get(severity, "ℹ️")
    text = f"{icon} {subject}\n\n{body}"[:MAX_LEN]
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for attempt in range(1, 4):
        try:
            resp = requests.post(
                url,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                      "disable_web_page_preview": True},
                timeout=15,
            )
            if resp.status_code == 429:
                retry_after = 5
                try:
                    retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
                except Exception:
                    pass
                log.warning("telegram 429, %ss bekleniyor", retry_after)
                time.sleep(min(retry_after, 60))
                continue
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            log.warning("telegram gonderim hatasi (deneme %s): %s", attempt, exc)
            if attempt < 3:
                time.sleep(2 ** attempt)
    return False
