from __future__ import annotations

import smtplib
from email.message import EmailMessage

from apps.api.config import get_settings
from packages.notifications.base import NotificationResult


class EmailProvider:
    channel = "email"

    def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        settings = get_settings()
        if not settings.smtp_host:
            return NotificationResult(True, self.channel, {"mode": "mock", "recipient": recipient, "idempotency_key": idempotency_key})
        email = EmailMessage()
        email["Subject"] = "PureGamma AI Alert"
        email["From"] = settings.smtp_user
        email["To"] = recipient
        email.set_content(message)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(email)
        return NotificationResult(True, self.channel, {"mode": "smtp"})


def send_email(recipient: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not settings.smtp_host:
        return False
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = f"PureGamma AI <{settings.smtp_user}>"
    email["To"] = recipient
    email["Reply-To"] = settings.smtp_user
    email.set_content(body, charset="utf-8")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(email)
    return True
