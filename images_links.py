"""Local banner images for each bot screen."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
IMAGES = ROOT / "images"

SECTION_IMAGES = {
    "main_menu": ROOT / "image.png",
    "start": ROOT / "image.png",
    "volume": IMAGES / "volume.png",
    "holders": IMAGES / "holders.png",
    "ads": IMAGES / "ads.png",
    "stats": IMAGES / "stats.png",
    "balance": IMAGES / "balance.png",
    "deposit": IMAGES / "balance.png",
    "withdraw": IMAGES / "balance.png",
    "history": IMAGES / "balance.png",
    "promos": IMAGES / "balance.png",
    "orders": IMAGES / "balance.png",
    "payment": IMAGES / "payment.png",
    "preview": IMAGES / "volume.png",
    "support": IMAGES / "support.png",
    "error": IMAGES / "support.png",
}


def resolve_photo(image_key: str) -> Path | None:
    key = (image_key or "").strip()
    if not key:
        return None
    path = SECTION_IMAGES.get(key)
    if path and path.is_file():
        return path
    return None
