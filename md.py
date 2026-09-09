"""Telegram HTML helpers."""

from __future__ import annotations

from html import escape as _html_escape

PARSE_MODE = "HTML"


def md_escape(text: str) -> str:
    if not text:
        return ""
    return _html_escape(str(text), quote=False)


def md_bold(text: str) -> str:
    return f"<b>{md_escape(text)}</b>"


def md_italic(text: str) -> str:
    return f"<i>{md_escape(text)}</i>"


def md_code(text: str) -> str:
    return f"<code>{md_escape(text)}</code>"


def md_link(label: str, url: str) -> str:
    safe_url = (url or "").replace('"', "%22")
    return f'<a href="{safe_url}">{md_escape(label)}</a>'


def md_quote(text: str) -> str:
    cleaned = " ".join((text or "").split()).strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("“") and cleaned.endswith("”")
    ):
        cleaned = cleaned[1:-1].strip()
    return f"<blockquote>{md_escape(cleaned)}</blockquote>"


def md_error(title: str, guidance: str, *extra: str) -> str:
    label = " ".join((title or "ERROR").split()).strip()
    if label and not label.isupper():
        label = label.upper()
    lines = [f"❌ {md_bold(label)}", "", md_quote(guidance)]
    for bit in extra:
        bit = (bit or "").strip()
        if bit:
            lines += ["", bit]
    return "\n".join(lines)
