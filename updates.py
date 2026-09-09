"""Pick polling locally, webhook when hosted (Render, Vercel, or WEBHOOK_URL is set)."""

from __future__ import annotations

import polling
import webhook


def start() -> None:
    if webhook.is_hosted():
        webhook.start()
        return
    polling.start()
