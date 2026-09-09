"""Local update transport — long polling."""

from __future__ import annotations

import logutil
from bot_instance import bot


def start() -> None:
    try:
        bot.delete_webhook(drop_pending_updates=False)
    except Exception as err:
        logutil.error(f"Could not clear webhook: {err}")
    logutil.info("Update mode: polling — listening for /start now")
    bot.infinity_polling(skip_pending=False)
