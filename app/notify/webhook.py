"""Generic JSON webhook channel (Slack/Teams/n8n/SIEM)."""
import logging

import requests

from ..config import WEBHOOK_ENABLED, WEBHOOK_TIMEOUT, WEBHOOK_URL

log = logging.getLogger("notify.webhook")
NAME = "webhook"


def enabled():
    return WEBHOOK_ENABLED


def send(subject, body, severity="INFO", domain=None, state=None, **_):
    if not WEBHOOK_ENABLED:
        return False
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_ENABLED=true ama WEBHOOK_URL bos")
    payload = {
        "source": "domain-registrar-follow",
        "severity": severity,
        "subject": subject,
        "text": body,
        "domain": domain,
        "state": state,
    }
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=WEBHOOK_TIMEOUT)
    resp.raise_for_status()
    return True
