"""
Multimodal user messages: local file bytes → OpenAI-style content parts, DB JSON storage.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass, field
from typing import Any

MARKER = "_bb_mm"
MAX_ATTACHMENTS = 12
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_TEXT_FILE_BYTES = 512 * 1024

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".html", ".htm", ".log"}


@dataclass
class PendingAttachment:
    name: str
    mime: str
    data: bytes


def _guess_mime(path: str, fallback: str = "application/octet-stream") -> str:
    m, _ = mimetypes.guess_type(path)
    return m or fallback


def load_attachment_from_path(path: str) -> PendingAttachment | tuple[None, str]:
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return None, str(e)
    name = os.path.basename(path) or "file"
    return PendingAttachment(name=name, mime=_guess_mime(path), data=data), ""


def normalize_attachment(att: PendingAttachment) -> tuple[list[dict[str, Any]], str | None]:
    """
    Returns OpenAI content parts (excluding the main instruction+text part) and optional error.
    """
    ext = os.path.splitext(att.name)[1].lower()
    lower_mime = (att.mime or "").lower()

    if ext in IMAGE_EXT or lower_mime.startswith("image/"):
        if len(att.data) > MAX_IMAGE_BYTES:
            return [], f"{att.name}: image too large (max {MAX_IMAGE_BYTES // (1024*1024)} MB)"
        b64 = base64.standard_b64encode(att.data).decode("ascii")
        mime = att.mime if lower_mime.startswith("image/") else f"image/{ext.lstrip('.')}"
        if mime == "image/jpg":
            mime = "image/jpeg"
        url = f"data:{mime};base64,{b64}"
        return [{"type": "image_url", "image_url": {"url": url}}], None

    if ext in TEXT_EXT or lower_mime.startswith("text/"):
        if len(att.data) > MAX_TEXT_FILE_BYTES:
            return [], f"{att.name}: text file too large (max {MAX_TEXT_FILE_BYTES // 1024} KB)"
        try:
            text = att.data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return [], f"{att.name}: not valid UTF-8 text"
        snippet = text[:120_000]
        if len(text) > 120_000:
            snippet += "\n\n[... truncated ...]"
        return [{"type": "text", "text": f"\n\n--- Attached file: {att.name} ---\n{snippet}"}], None

    # Other binary: try utf-8, else refuse
    try:
        text = att.data.decode("utf-8-sig")
        if len(text) > MAX_TEXT_FILE_BYTES:
            return [], f"{att.name}: file too large as text"
        return [{"type": "text", "text": f"\n\n--- Attached file: {att.name} ---\n{text}"}], None
    except UnicodeDecodeError:
        return [], f"{att.name}: unsupported type (use text or image)"


def build_historical_user_content(
    user_text: str, attachments: list[PendingAttachment]
) -> tuple[str | list[dict[str, Any]], str | None]:
    """
    Content for a past user turn (no instruction wrapper).
    Returns (content, error_message).
    """
    if not attachments:
        return user_text, None
    body = user_text.strip() if user_text.strip() else "(See attached files/images.)"
    parts: list[dict[str, Any]] = [{"type": "text", "text": body}]
    for att in attachments:
        extra, err = normalize_attachment(att)
        if err:
            return body, err
        parts.extend(extra)
    return parts, None


def build_latest_user_content(
    instruction_prefix: str,
    user_text: str,
    attachments: list[PendingAttachment],
) -> tuple[str | list[dict[str, Any]], str | None]:
    """
    Final user message for the current turn.

    Text-only: single string repeats instruction_prefix + user (legacy behavior for plain chat).

    With attachments: multipart list. Do NOT embed instruction_prefix here — the system
    message already carries full instructions; duplicating them plus base64 images often
    exceeds gateway limits and returns 502 upstream_error on OpenAI-compat / Gemini proxies.
    """
    body = user_text.strip()
    if not attachments:
        return instruction_prefix + body, None
    if not body:
        body = "(See attached files/images.)"
    text = (
        "Use the system instructions and preloaded context from earlier in this request.\n\n"
        f"{body}"
    )
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for att in attachments:
        extra, err = normalize_attachment(att)
        if err:
            return text, err
        parts.extend(extra)
    return parts, None


def storage_record(user_text: str, attachments: list[PendingAttachment]) -> str:
    """JSON string for DB (round-trip for history + API)."""
    if not attachments:
        return user_text
    stored_atts = []
    for att in attachments:
        stored_atts.append(
            {
                "name": att.name,
                "mime": att.mime,
                "b64": base64.standard_b64encode(att.data).decode("ascii"),
            }
        )
    return json.dumps(
        {
            "v": 1,
            MARKER: True,
            "text": user_text,
            "attachments": stored_atts,
        },
        ensure_ascii=False,
    )


def parse_stored_user_content(raw: str) -> tuple[str, list[PendingAttachment]]:
    """From DB row → display text + attachments for re-sending to API."""
    if not raw or not raw.strip().startswith("{"):
        return raw, []
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return raw, []
    if not isinstance(d, dict) or not d.get(MARKER):
        return raw, []
    text = d.get("text") or ""
    out: list[PendingAttachment] = []
    for a in d.get("attachments") or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or "file")
        mime = str(a.get("mime") or "application/octet-stream")
        b64 = a.get("b64")
        if not b64:
            continue
        try:
            data = base64.standard_b64decode(b64)
        except Exception:
            continue
        out.append(PendingAttachment(name=name, mime=mime, data=data))
    return text, out


def history_content_for_api(raw: str) -> str | list[dict[str, Any]]:
    """Convert stored user message to OpenAI `content` (same shape as live send)."""
    text, attachments = parse_stored_user_content(raw)
    content, err = build_historical_user_content(text, attachments)
    if err:
        return f"{text}\n\n[Attachment error: {err}]" if isinstance(content, str) else str(content)
    return content


def user_bubble_widgets(raw: str, ft_module) -> list:
    """Flet controls for chat bubble (text + optional thumbnails)."""
    text, attachments = parse_stored_user_content(raw)
    controls: list = []
    if text.strip():
        controls.append(
            ft_module.Markdown(
                text,
                extension_set=ft_module.MarkdownExtensionSet.COMMON_MARK,
                code_theme="atom-one-dark",
                expand=True,
            )
        )
    for att in attachments:
        ext = os.path.splitext(att.name)[1].lower()
        if ext in IMAGE_EXT or (att.mime or "").lower().startswith("image/"):
            b64 = base64.standard_b64encode(att.data).decode("ascii")
            mime = att.mime or "image/png"
            controls.append(
                ft_module.Image(
                    src=f"data:{mime};base64,{b64}",
                    fit=ft_module.BoxFit.CONTAIN,
                    width=min(480, 800),
                )
            )
        else:
            controls.append(
                ft_module.Text(
                    f"📎 {att.name} ({len(att.data)} bytes)",
                    size=12,
                    color="#B0B0B0",
                )
            )
    return controls if controls else [ft_module.Text("(empty)", size=12, color="#757575")]
