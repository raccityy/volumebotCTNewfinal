"""JSON-backed store for orders, balances and the ledger."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
STORE_PATH = (
    Path("/tmp/cleartactics-store.json")
    if os.environ.get("VERCEL")
    else DATA_DIR / "store.json"
)

STATUS_DRAFT = "draft"
STATUS_PENDING = "pending"
STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"

TX_DEPOSIT = "deposit"
TX_WITHDRAWAL = "withdrawal"
TX_SPEND = "spend"
TX_ADMIN = "admin"
TX_REFUND = "refund"

FIRST_ORDER_NO = 173

_lock = threading.RLock()
_data: dict[str, Any] = {
    "counter": FIRST_ORDER_NO - 1,
    "tx_counter": 0,
    "orders": {},
    "balances": {},
    "transactions": {},
    "users": {},
}


def _load() -> None:
    global _data
    try:
        raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            loaded_counter = int(raw.get("counter", 0))
            _data = {
                "counter": max(loaded_counter, FIRST_ORDER_NO - 1),
                "tx_counter": int(raw.get("tx_counter", 0)),
                "orders": dict(raw.get("orders") or {}),
                "balances": dict(raw.get("balances") or {}),
                "transactions": dict(raw.get("transactions") or {}),
                "users": dict(raw.get("users") or {}),
            }
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass


def _save() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(_data, indent=2), encoding="utf-8")


_load()


def order_tag(order_or_id: dict | str | int | None) -> str:
    if isinstance(order_or_id, int):
        return f"#{order_or_id:05d}"
    raw = ""
    if isinstance(order_or_id, dict):
        raw = str(order_or_id.get("id") or "")
    elif order_or_id:
        raw = str(order_or_id)
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits:
        return f"#{int(digits):05d}"
    return raw or "-"


def _order_id_keys(order_id: str) -> list[str]:
    raw = str(order_id or "").strip()
    keys = [raw]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits:
        n = int(digits)
        keys.extend([f"#{n:05d}", f"ORD{n:05d}", f"{n:05d}"])
    seen: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.append(key)
    return seen


def create_order(user_id: int, username: str, kind: str, package_id: str, price: float) -> dict:
    with _lock:
        _data["counter"] = max(int(_data["counter"] or 0), FIRST_ORDER_NO - 1) + 1
        order_id = order_tag(_data["counter"])
        order = {
            "id": order_id,
            "user_id": int(user_id),
            "username": username or "",
            "kind": kind,
            "package_id": package_id,
            "price": float(price),
            "full_price": float(price),
            "ca": "",
            "name": "",
            "symbol": "",
            "chain": "",
            "dex": "",
            "pair_address": "",
            "pair_url": "",
            "description": "",
            "website": "",
            "twitter": "",
            "telegram": "",
            "ad_label": "",
            "ad_url": "",
            "tx_hash": "",
            "status": STATUS_DRAFT,
            "created_at": time.time(),
            "activated_at": None,
            "expires_at": None,
        }
        _data["orders"][order_id] = order
        _save()
        return dict(order)


def get_order(order_id: str) -> dict | None:
    with _lock:
        for key in _order_id_keys(order_id):
            order = _data["orders"].get(key)
            if order:
                return dict(order)
        return None


def update_order(order_id: str, **fields: Any) -> dict | None:
    with _lock:
        order = None
        for key in _order_id_keys(order_id):
            order = _data["orders"].get(key)
            if order:
                break
        if not order:
            return None
        order.update(fields)
        _save()
        return dict(order)


def orders_by_user(user_id: int) -> list[dict]:
    with _lock:
        return [
            dict(o)
            for o in _data["orders"].values()
            if int(o.get("user_id", 0)) == int(user_id)
        ]


def get_user_meta(user_id: int) -> dict:
    with _lock:
        return dict(_data["users"].get(str(user_id)) or {})


def set_user_meta(user_id: int, **fields: Any) -> dict:
    with _lock:
        entry = _data["users"].setdefault(str(user_id), {})
        entry.update(fields)
        _save()
        return dict(entry)


def cancel_order(order_id: str) -> dict | None:
    return update_order(order_id, status=STATUS_CANCELLED, cancelled_at=time.time())


def all_orders() -> list[dict]:
    with _lock:
        return [dict(o) for o in _data["orders"].values()]


def orders_by_status(status: str) -> list[dict]:
    with _lock:
        return [dict(o) for o in _data["orders"].values() if o.get("status") == status]


def activate_order(order_id: str, duration_seconds: int) -> dict | None:
    now = time.time()
    return update_order(
        order_id,
        status=STATUS_ACTIVE,
        activated_at=now,
        expires_at=now + duration_seconds,
    )


def expire_due_orders() -> list[dict]:
    now = time.time()
    expired: list[dict] = []
    with _lock:
        for order in _data["orders"].values():
            if order.get("status") != STATUS_ACTIVE:
                continue
            expires_at = order.get("expires_at")
            if expires_at and now >= float(expires_at):
                order["status"] = STATUS_EXPIRED
                expired.append(dict(order))
        if expired:
            _save()
    return expired


def active_orders(kind: str | None = None) -> list[dict]:
    with _lock:
        out = [dict(o) for o in _data["orders"].values() if o.get("status") == STATUS_ACTIVE]
    if kind:
        out = [o for o in out if o.get("kind") == kind]
    return out


def draft_orders(user_id: int) -> list[dict]:
    return [o for o in orders_by_user(user_id) if o.get("status") == STATUS_DRAFT]


def clear_drafts(user_id: int) -> int:
    with _lock:
        cleared = 0
        for order in _data["orders"].values():
            if (
                int(order.get("user_id", 0)) == int(user_id)
                and order.get("status") == STATUS_DRAFT
            ):
                order["status"] = STATUS_CANCELLED
                cleared += 1
        if cleared:
            _save()
        return cleared


def get_balance(user_id: int) -> float:
    with _lock:
        return float(_data["balances"].get(str(user_id), 0.0))


def apply_balance(
    user_id: int,
    amount: float,
    kind: str = TX_ADMIN,
    *,
    tx_hash: str = "",
    note: str = "",
    status: str = "completed",
    **extra: Any,
) -> dict:
    with _lock:
        key = str(user_id)
        new_value = float(_data["balances"].get(key, 0.0)) + float(amount)
        _data["balances"][key] = new_value
        _data["tx_counter"] = int(_data["tx_counter"]) + 1
        tx_id = f"TX{_data['tx_counter']:05d}"
        entry = {
            "id": tx_id,
            "user_id": int(user_id),
            "type": kind,
            "amount": float(amount),
            "balance_after": new_value,
            "tx_hash": tx_hash,
            "note": note,
            "status": status,
            "timestamp": time.time(),
        }
        entry.update(extra)
        _data["transactions"][tx_id] = entry
        _save()
        return dict(entry)


def adjust_balance(user_id: int, amount: float, kind: str = TX_ADMIN, **kwargs: Any) -> float:
    return float(apply_balance(user_id, amount, kind, **kwargs)["balance_after"])


def settle_transaction(tx_id: str) -> dict | None:
    with _lock:
        entry = _data["transactions"].get(tx_id)
        if not entry or entry.get("status") != "pending":
            return None
        key = str(entry["user_id"])
        new_value = float(_data["balances"].get(key, 0.0)) + float(entry["amount"])
        _data["balances"][key] = new_value
        entry["status"] = "completed"
        entry["balance_after"] = new_value
        entry["settled_at"] = time.time()
        _save()
        return dict(entry)


def add_transaction(
    user_id: int,
    kind: str,
    amount: float,
    *,
    tx_hash: str = "",
    note: str = "",
    status: str = "pending",
) -> dict:
    with _lock:
        _data["tx_counter"] = int(_data["tx_counter"]) + 1
        tx_id = f"TX{_data['tx_counter']:05d}"
        entry = {
            "id": tx_id,
            "user_id": int(user_id),
            "type": kind,
            "amount": float(amount),
            "balance_after": float(_data["balances"].get(str(user_id), 0.0)),
            "tx_hash": tx_hash,
            "note": note,
            "status": status,
            "timestamp": time.time(),
        }
        _data["transactions"][tx_id] = entry
        _save()
        return dict(entry)


def get_transaction(tx_id: str) -> dict | None:
    with _lock:
        entry = _data["transactions"].get(tx_id)
        return dict(entry) if entry else None


def update_transaction(tx_id: str, **fields: Any) -> dict | None:
    with _lock:
        entry = _data["transactions"].get(tx_id)
        if not entry:
            return None
        entry.update(fields)
        _save()
        return dict(entry)


def pending_transactions() -> list[dict]:
    with _lock:
        return [
            dict(t)
            for t in _data["transactions"].values()
            if t.get("status") == "pending"
        ]


def user_transactions(user_id: int) -> list[dict]:
    with _lock:
        rows = [
            dict(t)
            for t in _data["transactions"].values()
            if int(t.get("user_id", 0)) == int(user_id)
        ]
    rows.sort(key=lambda t: t.get("timestamp", 0), reverse=True)
    return rows


def user_totals(user_id: int) -> dict:
    deposited = withdrawn = spent = 0.0
    pending_withdrawals = 0
    for tx in user_transactions(user_id):
        amount = float(tx.get("amount", 0.0))
        kind = tx.get("type")
        status = tx.get("status")

        if kind == TX_WITHDRAWAL:
            if status in ("pending", "completed"):
                withdrawn += abs(amount)
            if status == "pending":
                pending_withdrawals += 1
            continue

        if status != "completed":
            continue
        if kind == TX_DEPOSIT:
            deposited += amount
        elif kind == TX_SPEND:
            spent += abs(amount)
        elif kind == TX_ADMIN:
            if amount > 0:
                deposited += amount
            else:
                withdrawn += abs(amount)

    return {
        "deposited": deposited,
        "withdrawn": withdrawn,
        "spent": spent,
        "pending_withdrawals": pending_withdrawals,
    }
