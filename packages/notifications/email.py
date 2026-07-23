from __future__ import annotations

import html as html_lib
import os
import re
import smtplib
from email.message import EmailMessage

from apps.api.config import get_settings
from packages.notifications.base import NotificationResult

_LOGO_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "apps", "web", "public", "logo.png"))
_LOGO_CID = "puregamma-logo"
_logo_cache: bytes | None = None


def _logo_bytes() -> bytes | None:
    """Inline brand logo for CID-embedded emails; cached, tolerant of absence."""
    global _logo_cache
    if _logo_cache is not None:
        return _logo_cache
    try:
        with open(_LOGO_PATH, "rb") as handle:
            _logo_cache = handle.read()
    except OSError:
        _logo_cache = b""
    return _logo_cache or None


def _text_to_html(body: str) -> str:
    escaped = html_lib.escape(body or "")
    escaped = re.sub(
        r"(https?://[^\s<]+)",
        r'<a href="\1" style="color:#2563eb;text-decoration:underline;">\1</a>',
        escaped,
    )
    paragraphs = [
        f'<p style="margin:0 0 14px 0;">{chunk.replace(chr(10), "<br/>")}</p>'
        for chunk in escaped.split("\n\n")
        if chunk.strip()
    ]
    return "".join(paragraphs)


def branded_email_html(body: str) -> str:
    """Wrap a plain-text body in the PureGamma brand frame (logo header + footer)."""
    content = _text_to_html(body)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background-color:#f6f7f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f6f7f8;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background-color:#ffffff;border:1px solid #e7e8ea;">
  <tr><td style="background-color:#030303;padding:16px 24px;">
    <img src="cid:{_LOGO_CID}" width="28" height="28" alt="PureGamma" style="display:inline-block;vertical-align:middle;border:0;"/>
    <span style="display:inline-block;vertical-align:middle;margin-left:10px;color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:17px;font-weight:bold;letter-spacing:0.2px;">PureGamma AI</span>
  </td></tr>
  <tr><td style="padding:26px 24px 8px 24px;color:#171717;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.75;">
    {content}
  </td></tr>
  <tr><td style="padding:16px 24px 20px 24px;border-top:1px solid #e7e8ea;color:#8a8f98;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.7;">
    AI decisions for Beta, Alpha, and Long Gamma.<br/>
    <a href="https://puregamma.ai" style="color:#2563eb;text-decoration:underline;">puregamma.ai</a>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def _build_message(recipient: str, subject: str, body: str, sender: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message["Reply-To"] = sender
    message.set_content(body or "", charset="utf-8")
    message.add_alternative(branded_email_html(body), subtype="html")
    logo = _logo_bytes()
    if logo:
        html_part = message.get_payload()[-1]
        html_part.add_related(logo, maintype="image", subtype="png", cid=f"<{_LOGO_CID}>", filename="logo.png")
    return message


def _deliver(message: EmailMessage) -> None:
    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


class EmailProvider:
    channel = "email"

    def send(self, recipient: str, message: str, idempotency_key: str) -> NotificationResult:
        settings = get_settings()
        if not settings.smtp_host:
            return NotificationResult(True, self.channel, {"mode": "mock", "recipient": recipient, "idempotency_key": idempotency_key})
        email = _build_message(recipient, "PureGamma AI", message, f"PureGamma AI <{settings.smtp_user}>")
        _deliver(email)
        return NotificationResult(True, self.channel, {"mode": "smtp", "branded": True})


def send_email(recipient: str, subject: str, body: str) -> bool:
    settings = get_settings()
    if not settings.smtp_host:
        return False
    email = _build_message(recipient, subject, body, f"PureGamma AI <{settings.smtp_user}>")
    _deliver(email)
    return True
