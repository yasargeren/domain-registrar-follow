"""SMTP e-mail channel (Gmail app password friendly)."""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate

from ..config import (
    EMAIL_ENABLED,
    EMAIL_FROM,
    EMAIL_MIN_SEVERITY,
    EMAIL_TO,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_SSL,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)

log = logging.getLogger("notify.email")
NAME = "email"

_ORDER = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


def enabled():
    return EMAIL_ENABLED


def _severity_ok(severity):
    return _ORDER.get(severity, 0) >= _ORDER.get(EMAIL_MIN_SEVERITY, 1)


def send(subject, body, severity="INFO", **_):
    if not EMAIL_ENABLED:
        return False
    if not _severity_ok(severity):
        log.debug("e-posta atlandi (severity %s < %s)", severity, EMAIL_MIN_SEVERITY)
        return False
    if not (SMTP_HOST and EMAIL_TO and EMAIL_FROM):
        raise RuntimeError("EMAIL_ENABLED=true ama SMTP_HOST/EMAIL_FROM/EMAIL_TO eksik")

    msg = EmailMessage()
    msg["Subject"] = f"[domain-monitor][{severity}] {subject}"
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(EMAIL_TO)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)

    context = ssl.create_default_context()
    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=20) as smtp:
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
            smtp.ehlo()
            if SMTP_USE_TLS:
                smtp.starttls(context=context)
                smtp.ehlo()
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
    return True
