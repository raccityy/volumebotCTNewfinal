"""Sponsored ad helpers — button text and destination URL."""

from __future__ import annotations

LABEL_MAX = 24


def looks_like_url(text: str) -> bool:
    text = (text or "").strip()
    return text.startswith(("http://", "https://", "t.me/")) and " " not in text


def normalise_url(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("t.me/"):
        return f"https://{text}"
    return text
