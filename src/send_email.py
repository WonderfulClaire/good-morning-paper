from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email_if_configured(subject: str, body_markdown: str) -> bool:
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("SMTP_FROM")
    to_email = os.getenv("SMTP_TO")

    required = [host, port, username, password, from_email, to_email]
    if not all(required):
        logger.info("SMTP not fully configured. Skip sending email.")
        return False

    msg = MIMEText(body_markdown, _subtype="plain", _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    try:
        with smtplib.SMTP(host, int(port), timeout=30) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        logger.info("Digest email sent to %s", to_email)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Email sending failed: %s", exc)
        return False
