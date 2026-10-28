from __future__ import annotations

import html as html_lib
import logging
import re
import smtplib
import time
from email.message import EmailMessage

from apps.api.config import get_settings
from packages.notifications.base import NotificationResult

logger = logging.getLogger("puregamma.notifications.email")

_FONT = "Arial,Helvetica,sans-serif"
_LINK_STYLE = "color:#2563eb;text-decoration:underline;"
_P_STYLE = "margin:0 0 14px 0;"
_LIST_STYLE = "margin:0 0 14px 0;padding-left:22px;"
_HEADING_STYLES = {
    1: "margin:4px 0 12px 0;font-size:20px;line-height:1.4;font-weight:bold;color:#030303;",
    2: "margin:18px 0 10px 0;font-size:17px;line-height:1.4;font-weight:bold;color:#030303;",
    3: "margin:14px 0 8px 0;font-size:15px;line-height:1.4;font-weight:bold;color:#171717;",
}
_HR = '<hr style="border:0;border-top:1px solid #e7e8ea;margin:20px 0;"/>'
_CELL = "padding:6px 8px;border-bottom:1px solid #e7e8ea;text-align:left;vertical-align:top;"

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_BULLET = re.compile(r"^\s*[-*+•]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d{1,3}[.)]\s+(.*)$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")
_INLINE = re.compile(
    r"`(?P<code>[^`\n]+)`"
    r"|\[(?P<label>[^\]\n]+)\]\((?P<href>https?://[^\s()<>]+)\)"
    r"|(?P<url>https?://[A-Za-z0-9\-._~:/?#@!$&*+,;=%]+)"
)
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC = re.compile(r"(?<![*A-Za-z0-9])\*(?=[^\s*])([^*]+?)(?<=[^\s*])\*(?![*A-Za-z0-9])")


def _link(href: str, label: str) -> str:
    return f'<a href="{html_lib.escape(href, quote=True)}" style="{_LINK_STYLE}">{label}</a>'


def _emphasis(escaped: str) -> str:
    return _ITALIC.sub(r"<em>\1</em>", _BOLD.sub(r"<strong>\1</strong>", escaped))


def _inline(text: str) -> str:
    """Escape one line and render **bold**, *italic*, `code`, [label](url) and bare links."""
    parts, last = [], 0
    for match in _INLINE.finditer(text):
        parts.append(_emphasis(html_lib.escape(text[last:match.start()])))
        if match.group("code"):
            parts.append(
                '<code style="font-family:Menlo,Consolas,monospace;font-size:13px;background-color:#f3f4f6;'
                f'padding:1px 4px;">{html_lib.escape(match.group("code"))}</code>'
            )
        elif match.group("href"):
            parts.append(_link(match.group("href"), _emphasis(html_lib.escape(match.group("label")))))
        else:
            url = match.group("url")
            trimmed = url.rstrip(".,;:!?")
            parts.append(_link(trimmed, html_lib.escape(trimmed)) + html_lib.escape(url[len(trimmed):]))
        last = match.end()
    parts.append(_emphasis(html_lib.escape(text[last:])))
    return "".join(parts)


def _table_html(rows: list[list[str]], header: bool) -> str:
    cells = []
    for index, row in enumerate(rows):
        tag, weight = ("th", "font-weight:bold;") if header and index == 0 else ("td", "")
        cells.append("<tr>" + "".join(f'<{tag} style="{_CELL}{weight}">{_inline(cell)}</{tag}>' for cell in row) + "</tr>")
    return (
        '<div style="overflow-x:auto;margin:0 0 14px 0;"><table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;font-size:13px;line-height:1.5;">{"".join(cells)}</table></div>'
    )


def _text_to_html(body: str) -> str:
    """Render a report digest written in light Markdown as email-safe HTML.

    Supports headings, bold/italic, inline code, links, bullet and numbered lists, block
    quotes, horizontal rules and pipe tables; everything else stays escaped plain text.
    """
    blocks: list[str] = []
    paragraph: list[str] = []
    items: list[str] = []
    rows: list[list[str]] = []
    state = {"list": None, "header": False}

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f'<p style="{_P_STYLE}">' + "<br/>".join(_inline(line) for line in paragraph) + "</p>")
            paragraph.clear()

    def flush_list() -> None:
        if items:
            tag = state["list"]
            blocks.append(
                f'<{tag} style="{_LIST_STYLE}">'
                + "".join(f'<li style="margin:0 0 6px 0;">{_inline(item)}</li>' for item in items)
                + f"</{tag}>"
            )
            items.clear()
        state["list"] = None

    def flush_table() -> None:
        if rows:
            blocks.append(_table_html(rows, state["header"]))
            rows.clear()
        state["header"] = False

    def flush() -> None:
        flush_paragraph()
        flush_list()
        flush_table()

    for raw in (body or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            flush()
            continue
        if _TABLE_ROW.match(line):
            flush_paragraph()
            flush_list()
            if _TABLE_RULE.match(line):
                state["header"] = state["header"] or len(rows) == 1
            else:
                rows.append([cell.strip() for cell in line.strip("|").split("|")])
            continue
        flush_table()
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = min(len(heading.group(1)), 3)
            blocks.append(f'<div style="{_HEADING_STYLES[level]}">{_inline(heading.group(2))}</div>')
            continue
        if _RULE.match(line):
            flush()
            blocks.append(_HR)
            continue
        bullet, numbered = _BULLET.match(line), _NUMBERED.match(line)
        if bullet or numbered:
            flush_paragraph()
            tag = "ul" if bullet else "ol"
            if state["list"] != tag:
                flush_list()
                state["list"] = tag
            items.append((bullet or numbered).group(1))
            continue
        if line.startswith(">"):
            flush()
            blocks.append(
                '<div style="margin:0 0 14px 0;padding:2px 0 2px 12px;border-left:3px solid #e7e8ea;color:#4b5563;">'
                f"{_inline(line.lstrip('>').strip())}</div>"
            )
            continue
        if items and raw[:1] in (" ", "\t"):
            items[-1] = f"{items[-1]} {line}"
            continue
        flush_list()
        paragraph.append(line)
    flush()
    return "".join(blocks)


def branded_email_html(body: str) -> str:
    """Wrap a plain-text or light-Markdown body in the PureGamma brand frame (wordmark header + footer).

    The header is a text wordmark: the monochrome PNG logo is invisible on the dark header and
    inline (CID) images are blocked or shown broken by several mail clients.
    """
    content = _text_to_html(body)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background-color:#f6f7f8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f6f7f8;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background-color:#ffffff;border:1px solid #e7e8ea;">
  <tr><td style="background-color:#030303;padding:16px 24px;">
    <span style="color:#ffffff;font-family:{_FONT};font-size:18px;font-weight:bold;letter-spacing:0.3px;">PureGamma AI</span>
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


def _build_message(recipient: str, subject: str, body: str, sender: str, html: str | None = None) -> EmailMessage:
    """Plain-text body plus an HTML alternative: ``html`` when given (a complete email-safe
    document such as the market brief), otherwise the branded rendering of ``body``."""
    message = EmailMessage()
    message["Subject"] = " ".join((subject or "PureGamma AI").split())
    message["From"] = sender
    message["To"] = recipient
    message["Reply-To"] = sender
    message.set_content(body or "", charset="utf-8")
    message.add_alternative(html or branded_email_html(body), subtype="html")
    return message


_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.0


def _deliver(message: EmailMessage) -> None:
    """Deliver via SMTP with bounded retry on transient connection/send failures.

    Transient SMTP errors (connection reset, timeouts, temporary 4xx) can otherwise
    silently drop verification and password-reset emails, leaving accounts registered
    but unverifiable. We retry with a short backoff and only surface the error after
    the final attempt so callers can report delivery failure instead of swallowing it.
    """
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP not configured")
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8) as smtp:
                smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
            return
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, smtplib.SMTPDataError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            logger.warning(
                "smtp_deliver_retry",
                extra={"attempt": attempt + 1, "error": type(exc).__name__},
            )
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_SECONDS * (2**attempt))
        except smtplib.SMTPAuthenticationError:
            raise
    assert last_error is not None
    raise last_error


class EmailProvider:
    channel = "email"

    def send(
        self,
        recipient: str,
        message: str,
        idempotency_key: str,
        email_subject: str | None = None,
        email_html: str | None = None,
    ) -> NotificationResult:
        settings = get_settings()
        if not settings.smtp_host:
            return NotificationResult(True, self.channel, {"mode": "mock", "recipient": recipient, "idempotency_key": idempotency_key})
        email = _build_message(
            recipient, email_subject or "PureGamma AI", message, f"PureGamma AI <{settings.smtp_user}>", html=email_html
        )
        _deliver(email)
        return NotificationResult(True, self.channel, {"mode": "smtp", "branded": True, **({"html": "provided"} if email_html else {})})


def send_email(recipient: str, subject: str, body: str, html: str | None = None) -> bool:
    settings = get_settings()
    if not settings.smtp_host:
        return False
    email = _build_message(recipient, subject, body, f"PureGamma AI <{settings.smtp_user}>", html=html)
    _deliver(email)
    return True
