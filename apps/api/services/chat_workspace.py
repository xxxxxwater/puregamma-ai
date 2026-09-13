"""Tenant-owned durable attachments and per-conversation execution permissions."""
from __future__ import annotations

import base64
import hashlib
import io
import os
import zipfile
from pathlib import PurePath
from xml.etree import ElementTree

from sqlalchemy import func
from sqlalchemy.orm import Session

from packages.database.models import AgentAttachmentRecord, User

MAX_FILE_BYTES = int(os.getenv("AGENT_ATTACHMENT_MAX_BYTES", "10485760"))
MAX_USER_BYTES = int(os.getenv("AGENT_ATTACHMENT_USER_BYTES", "104857600"))
MAX_FILES = 8
MAX_CONTEXT_CHARS = 50000
PERMISSION_MODES = ("read-only", "workspace-write", "full-access")
READ_TOOLS = frozenset({
    "get_market_quote", "get_market_history", "get_recent_news", "search_news",
    "search_source_documents", "search_online_sources", "get_defi_protocol_metrics",
    "get_chain_metrics", "get_onchain_snapshot", "get_data_source_status",
    "list_research_strategies", "get_strategy_performance", "get_sentiment_context",
    "get_account_snapshot", "get_position_snapshot", "get_open_orders",
    "get_strategy_status", "get_options_context", "get_earnings_gamma",
    # Read-only by construction, and named explicitly so the confirmation card
    # stays reserved for calls that really do change or spend something: an order
    # PREVIEW changes no state, and the research plan's market-data backtest runs
    # on stored data. Prompting for these only teaches the user to click through
    # the card without reading it.
    "generate_order_preview", "run_nautilus_backtest",
})

# Requires confirmation in "workspace-write". Empty today because no tool in the
# agent's registry mutates account, plan, balance or filesystem state; the set is
# the explicit home for the first one that does, so it cannot ship as an
# unreviewed implicit "ask" by falling outside READ_TOOLS.
STATEFUL_TOOLS = frozenset()


def permission_mode(value: str | None) -> str:
    mode = value or "workspace-write"
    if mode not in PERMISSION_MODES:
        raise ValueError("INVALID_PERMISSION_MODE")
    return mode


def tool_permission(mode: str, tool: str) -> str:
    """Additional restriction only; existing entitlement/control-plane gates still apply.

    Read-only tools are allowed in every mode; tools that change state require an
    explicit confirmation in "workspace-write" and are refused in "read-only"; a
    tool nobody has classified is refused in the two restrictive modes rather
    than silently promoted to a confirmation the user did not expect.
    """
    mode = permission_mode(mode)
    if tool in READ_TOOLS:
        return "allow"
    if mode == "full-access":
        return "allow"
    if mode == "read-only":
        return "deny"
    return "ask" if tool in STATEFUL_TOOLS else "deny"


def attachment_metadata(row: AgentAttachmentRecord) -> dict:
    return {"id": row.id, "name": row.name, "mime": row.mime, "size": row.size,
            "sha256": row.sha256, "kind": row.kind, "content": "",
            "url": f"/api/agent/attachments/{row.id}/content"}


def owned_attachment(db: Session, user_id: str, attachment_id: str) -> AgentAttachmentRecord:
    row = db.query(AgentAttachmentRecord).filter_by(id=attachment_id, user_id=user_id).one_or_none()
    if row is None:
        raise LookupError("ATTACHMENT_NOT_FOUND")
    return row


def _prepare_image(raw: bytes) -> tuple[str, str, str, bytes]:
    """Validate and, only when it changes something, normalise an image.

    A decoder failure is a bad upload, not a server fault: every Pillow/OSError
    here becomes ATTACHMENT_INVALID so the router answers 400 instead of 500.
    """
    from PIL import Image, ImageOps
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP", "GIF"} or image.width * image.height > 20_000_000:
                raise ValueError("ATTACHMENT_IMAGE_LIMIT")
            # Re-encoding is only worth doing when it changes something. Writing a
            # small, already-supported image through a JPEG round trip turned a
            # valid icon into a rejected upload, so a file that is already inside
            # the pixel budget and in a format the API serves back is stored as it
            # arrived; anything larger is downscaled into a fresh JPEG.
            if max(image.width, image.height) <= 2048 and image.format in {"PNG", "JPEG"}:
                image.load()  # a truncated file must fail here, not reach the model
                if not image.info.get("exif"):
                    mime = {"PNG": "image/png", "JPEG": "image/jpeg"}[image.format]
                    return "image", mime, "", raw
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((2048, 2048))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - any decoder failure is the caller's input
        raise ValueError("ATTACHMENT_INVALID") from exc
    return "image", "image/jpeg", "", output.getvalue()


def prepare_file(name: str, raw: bytes) -> tuple[str, str, str, bytes]:
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError("ATTACHMENT_SIZE_LIMIT")
    ext = PurePath(name).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return _prepare_image(raw)
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError("ATTACHMENT_PDF_LIMIT")
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(map(len, parts)) > MAX_CONTEXT_CHARS:
                raise ValueError("ATTACHMENT_TEXT_LIMIT")
        text = "\n".join(parts)
        mime = "application/pdf"
    elif ext == ".docx":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            member = archive.getinfo("word/document.xml")
            if member.file_size > 2_000_000:
                raise ValueError("ATTACHMENT_TEXT_LIMIT")
            xml = archive.read(member)
            if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                raise ValueError("ATTACHMENT_INVALID")
            root = ElementTree.fromstring(xml)
            text = "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext in {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".py", ".js", ".ts", ".yaml", ".yml"}:
        text = raw.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("ATTACHMENT_INVALID")
        mime = "text/plain"
    else:
        raise ValueError("ATTACHMENT_UNSUPPORTED")
    if not text.strip():
        raise ValueError("ATTACHMENT_NO_TEXT")
    if len(text) > MAX_CONTEXT_CHARS:
        raise ValueError("ATTACHMENT_TEXT_LIMIT")
    return "file", mime, text, raw


def save_attachment(db: Session, user: User, name: str, raw: bytes) -> dict:
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(c for c in name if ord(c) >= 32)[:160]
    if not name:
        raise ValueError("ATTACHMENT_INVALID")
    try:
        kind, mime, extracted, payload = prepare_file(name, raw)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("ATTACHMENT_INVALID") from exc
    # Serialize quota checks on the tenant row so concurrent uploads cannot exceed it.
    db.query(User).filter_by(id=user.id).with_for_update().one()
    used = db.query(func.coalesce(func.sum(AgentAttachmentRecord.size), 0)).filter_by(user_id=user.id).scalar()
    if used + len(payload) > MAX_USER_BYTES:
        raise ValueError("ATTACHMENT_STORAGE_LIMIT")
    row = AgentAttachmentRecord(user_id=user.id, name=name, mime=mime, kind=kind,
                               size=len(payload), payload=payload, extracted_text=extracted,
                               sha256=hashlib.sha256(payload).hexdigest())
    db.add(row)
    db.commit()
    db.refresh(row)
    return attachment_metadata(row)


def resolve_attachments(db: Session, user_id: str, items: list[dict]) -> list[dict]:
    if len(items) > MAX_FILES:
        raise ValueError("ATTACHMENT_COUNT_LIMIT")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("ATTACHMENT_INVALID")
        if item.get("id"):
            row = owned_attachment(db, user_id, str(item["id"]))
            result.append({**attachment_metadata(row), "content": row.extracted_text})
        else:
            # Existing clients and historical inline text remain supported.
            content = str(item.get("content", ""))
            if len(content.encode()) > 20000:
                raise ValueError("ATTACHMENT_TEXT_LIMIT")
            result.append({"name": str(item.get("name", "attachment"))[:160],
                           "mime": "text/plain", "content": content})
    if sum(len(item["content"]) for item in result) > MAX_CONTEXT_CHARS:
        raise ValueError("ATTACHMENT_TEXT_LIMIT")
    return result


def image_urls(db: Session, user_id: str, items: list[dict]) -> list[str]:
    urls = []
    for item in items:
        if item.get("kind") == "image" and item.get("id"):
            row = owned_attachment(db, user_id, item["id"])
            if hashlib.sha256(row.payload).hexdigest() != row.sha256:
                raise ValueError("ATTACHMENT_INTEGRITY_ERROR")
            urls.append(f"data:{row.mime};base64," + base64.b64encode(row.payload).decode())
    return urls
