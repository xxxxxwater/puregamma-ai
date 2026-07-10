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
        email["Subject"] = "PureGamma.ai Alert"
        email["From"] = settings.smtp_user
        email["To"] = recipient
        email.set_content(message)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(email)
        return NotificationResult(True, self.channel, {"mode": "smtp"})
