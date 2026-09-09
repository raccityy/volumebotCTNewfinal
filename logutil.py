"""Startup / error logging."""

from __future__ import annotations

import logging
import sys
import time

_original = print


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def info(msg: str) -> None:
    _original(f"[{_stamp()}] {msg}", flush=True)


def error(msg: str) -> None:
    _original(f"[{_stamp()}] ERROR {msg}", file=sys.stderr, flush=True)


def silence() -> None:
    logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
