"""Per-user conversation state."""

from __future__ import annotations

import threading

STEP_CA = "ca"
STEP_TX = "tx"
STEP_AD_LABEL = "ad_label"
STEP_AD_URL = "ad_url"
STEP_SUPPORT = "support"
STEP_DEPOSIT_AMOUNT = "deposit_amount"
STEP_DEPOSIT_TX = "deposit_tx"
STEP_WITHDRAW_AMOUNT = "withdraw_amount"
STEP_WITHDRAW_WALLET = "withdraw_wallet"

_sessions: dict[int, dict] = {}
_lock = threading.RLock()


def get_session(user_id: int) -> dict | None:
    with _lock:
        sess = _sessions.get(user_id)
        return dict(sess) if sess else None


def set_session(user_id: int, **fields) -> None:
    with _lock:
        _sessions.setdefault(user_id, {}).update(fields)


def clear_session(user_id: int) -> None:
    with _lock:
        _sessions.pop(user_id, None)


def current_step(user_id: int) -> str:
    with _lock:
        return (_sessions.get(user_id) or {}).get("step", "")
