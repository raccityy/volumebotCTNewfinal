"""Single shared TeleBot instance so modules avoid circular imports."""

from __future__ import annotations

import threading
from pathlib import Path

import telebot

import config
from md import PARSE_MODE

if not (config.TELEGRAM_BOT_TOKEN or "").strip() or ":" not in config.TELEGRAM_BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is missing or invalid in config.py")

bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN, parse_mode=PARSE_MODE)

CHUNK_TARGET = 3600
CAPTION_MAX = 1024

_screen_ids: dict[int, list[int]] = {}
_screen_lock = threading.Lock()
_file_ids: dict[str, str] = {}


def track_message(chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    with _screen_lock:
        bucket = _screen_ids.setdefault(int(chat_id), [])
        if message_id not in bucket:
            bucket.append(message_id)


def is_back_nav(data: str) -> bool:
    d = (data or "").strip()
    if d in {"menu", "cancel", "close"}:
        return True
    return d.startswith(("back:", "preview:"))


def clear_ui(chat_id: int, *extra_ids: int | None) -> None:
    with _screen_lock:
        ids = list(_screen_ids.pop(int(chat_id), []))
    for mid in extra_ids:
        if mid and mid not in ids:
            ids.append(mid)
    if not ids:
        return

    def _delete() -> None:
        for mid in ids:
            try:
                bot.delete_message(chat_id, mid)
            except Exception:
                pass

    threading.Thread(target=_delete, daemon=True).start()


def _caption_fit(text: str) -> str:
    body = (text or "").strip()
    if len(body) <= CAPTION_MAX:
        return body
    return body[: CAPTION_MAX - 1].rstrip() + "…"


def _send_local_photo(
    chat_id: int,
    path: Path,
    *,
    caption: str,
    reply_markup=None,
) -> bool:
    kwargs = {
        "caption": caption,
        "reply_markup": reply_markup,
        "parse_mode": PARSE_MODE,
    }
    key = str(path)
    cached = _file_ids.get(key)
    if cached:
        try:
            msg = bot.send_photo(chat_id, cached, **kwargs)
            track_message(chat_id, msg.message_id)
            return True
        except Exception:
            _file_ids.pop(key, None)

    with path.open("rb") as handle:
        msg = bot.send_photo(chat_id, handle, **kwargs)
    try:
        if msg.photo:
            _file_ids[key] = msg.photo[-1].file_id
    except Exception:
        pass
    track_message(chat_id, msg.message_id)
    return True


def say(chat_id: int, text: str, reply_markup=None, *, replace: bool = False, **kwargs):
    if replace:
        clear_ui(chat_id)
    kwargs.setdefault("parse_mode", PARSE_MODE)
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup, **kwargs)
    track_message(chat_id, msg.message_id)
    return msg


def send_screen(
    chat_id: int,
    text: str,
    image_key: str = "",
    reply_markup=None,
    *,
    replace: bool = False,
) -> None:
    import images_links

    if replace:
        clear_ui(chat_id)
    body = (text or "").strip()
    if not body:
        return

    photo = images_links.resolve_photo(image_key) if image_key else None
    if photo is not None:
        try:
            _send_local_photo(
                chat_id,
                photo,
                caption=_caption_fit(body),
                reply_markup=reply_markup,
            )
            return
        except Exception as err:
            print(f"[media] photo failed for {image_key!r}: {err}")

    if "\n" in body and len(body) > CHUNK_TARGET:
        send_long(chat_id, body.split("\n"), reply_markup=reply_markup, replace=False)
        return
    msg = bot.send_message(
        chat_id, body, reply_markup=reply_markup, parse_mode=PARSE_MODE
    )
    track_message(chat_id, msg.message_id)


def send_long(
    chat_id: int,
    lines: list[str],
    reply_markup=None,
    image_key: str = "",
    *,
    replace: bool = False,
) -> None:
    import images_links

    if replace:
        clear_ui(chat_id)

    blocks: list[list[str]] = [[]]
    for line in lines:
        blocks[-1].append(line)
        if not line.strip():
            blocks.append([])

    chunks: list[list[str]] = []
    current: list[str] = []
    size = 0
    for block in blocks:
        length = sum(len(line) + 1 for line in block)
        if current and size + length > CHUNK_TARGET:
            chunks.append(current)
            current, size = [], 0
        current.extend(block)
        size += length
    if current:
        chunks.append(current)

    chunks = [c for c in chunks if "\n".join(c).strip()]
    if not chunks:
        return

    photo = images_links.resolve_photo(image_key) if image_key else None
    photo_sent = False

    for index, chunk in enumerate(chunks):
        is_last = index == len(chunks) - 1
        text = "\n".join(chunk).strip()
        markup = reply_markup if is_last else None

        if photo is not None and not photo_sent:
            try:
                fitted = _caption_fit(text)
                _send_local_photo(
                    chat_id,
                    photo,
                    caption=fitted,
                    reply_markup=markup if fitted == text else None,
                )
                photo_sent = True
                if fitted == text:
                    continue
                msg = bot.send_message(
                    chat_id, text, reply_markup=markup, parse_mode=PARSE_MODE
                )
                track_message(chat_id, msg.message_id)
                continue
            except Exception as err:
                print(f"[media] photo failed for {image_key!r}: {err}")
                photo = None

        msg = bot.send_message(
            chat_id, text, reply_markup=markup, parse_mode=PARSE_MODE
        )
        track_message(chat_id, msg.message_id)
