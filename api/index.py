"""Vercel serverless entry point for the Telegram webhook bot."""

from __future__ import annotations

import threading
import time

import admin_group
import logutil
import store
import user_flow
from webhook import build_app


def _expire_loop() -> None:
    while True:
        try:
            expired = store.expire_due_orders()
            for order in expired:
                try:
                    admin_group.notify_user_expired(order)
                except Exception as err:
                    logutil.error(f"expiry notice failed: {err}")
        except Exception as err:
            logutil.error(f"expire loop failed: {err}")
        time.sleep(30)


user_flow.register()
admin_group.register()
threading.Thread(target=_expire_loop, daemon=True).start()
app = build_app()
