"""Hosted update transport — Telegram webhook + FastAPI."""

from __future__ import annotations

import logging
import os

import config
import logutil
from bot_instance import bot

_LISTEN = "0.0.0.0"
_PATH = "telegram"
_MAX_CONNECTIONS = 40


def _normalize_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    return value.split("?")[0].rstrip("/")


def _candidate_urls() -> list[str]:
    values = [
        (config.WEBHOOK_URL or "").strip(),
        (os.environ.get("WEBHOOK_URL") or "").strip(),
        (os.environ.get("VERCEL_PROJECT_PRODUCTION_URL") or "").strip(),
        (os.environ.get("VERCEL_URL") or "").strip(),
        (os.environ.get("RENDER_EXTERNAL_URL") or "").strip(),
        (os.environ.get("RENDER_EXTERNAL_HOSTNAME") or "").strip(),
    ]
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _normalize_url(value)
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return normalized


def resolved_base_url() -> str:
    for candidate in _candidate_urls():
        if candidate.lower().startswith(("https://", "http://")):
            return candidate
    host = (os.environ.get("RENDER_EXTERNAL_HOSTNAME") or "").strip()
    if host:
        return f"https://{host}"
    return ""


def public_webhook_url() -> str:
    base = resolved_base_url()
    if not base:
        return ""
    if base.endswith(f"/{_PATH}"):
        return base
    return f"{base}/{_PATH}"


def _port() -> int:
    raw = (os.environ.get("PORT") or "").strip()
    if raw.isdigit():
        return int(raw)
    return 10000


def is_hosted() -> bool:
    if public_webhook_url():
        return True
    if any(os.environ.get(name) for name in ("VERCEL", "VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL")):
        return True
    if (os.environ.get("PORT") or "").strip().isdigit():
        return True
    return False


def ensure_webhook() -> str:
    url = public_webhook_url()
    if not url:
        logutil.error("HTTP is up but no public URL — Telegram webhook not set")
        return ""
    bot.set_webhook(
        url=url,
        max_connections=_MAX_CONNECTIONS,
        drop_pending_updates=True,
        secret_token=None,
    )
    logutil.info(f"Webhook set → {url}")
    return url


def build_app():
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from telebot.types import Update
    except ImportError as err:
        raise SystemExit(
            "Install webhook deps: pip install fastapi uvicorn\n"
            f"{err}"
        ) from err

    logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)

    app = FastAPI(title="Telegram Bot Webhook", redirect_slashes=False)

    @app.get("/")
    async def health() -> dict:
        return {"ok": True}

    async def _process(request: Request):
        try:
            raw = await request.body()
            if not raw:
                return JSONResponse(content={"ok": True}, status_code=200)
            try:
                payload = __import__("json").loads(raw)
            except Exception:
                return JSONResponse(content={"ok": True}, status_code=200)

            if isinstance(payload, dict):
                text = payload.get("message", {}).get("text") or payload.get("edited_message", {}).get("text")
                if text:
                    logutil.info(f"Webhook received: {text}")
            update = Update.de_json(payload)
            if update:
                bot.process_new_updates([update])
        except Exception as err:
            logutil.error(f"Update handler failed: {err}")
        return JSONResponse(content={"ok": True}, status_code=200)

    for route in (f"/{_PATH}", f"/{_PATH}/", "/api/telegram", "/api/telegram/"):
        app.add_api_route(route, _process, methods=["POST"])

    @app.on_event("startup")
    async def _startup() -> None:
        ensure_webhook()

    return app


def start() -> None:
    try:
        import uvicorn
    except ImportError as err:
        raise SystemExit(
            "Install webhook deps: pip install fastapi uvicorn\n"
            f"{err}"
        ) from err

    app = build_app()
    port = _port()
    logutil.info(f"Bot is running — {_LISTEN}:{port}/{_PATH}")
    uvicorn.run(
        app,
        host=_LISTEN,
        port=port,
        log_level="warning",
        access_log=False,
    )
