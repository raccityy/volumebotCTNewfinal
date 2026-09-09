"""Cancelling an active order and working out what goes back."""

from __future__ import annotations

import time

import store
from packages import get_package

CANCELLATION_FEE = 0.20
MIN_FRACTION = 0.05


def fraction_left(order: dict) -> float:
    activated = order.get("activated_at")
    expires = order.get("expires_at")
    if not activated or not expires:
        return 0.0
    total = float(expires) - float(activated)
    if total <= 0:
        return 0.0
    left = float(expires) - time.time()
    return max(0.0, min(1.0, left / total))


def seconds_left(order: dict) -> int:
    expires = order.get("expires_at")
    if not expires:
        return 0
    return max(0, int(float(expires) - time.time()))


def quote(order: dict) -> dict:
    paid = float(order.get("price") or 0)
    left = fraction_left(order)
    refundable = left >= MIN_FRACTION and paid > 0
    refund = round(paid * left * (1.0 - CANCELLATION_FEE), 4) if refundable else 0.0
    return {
        "paid": paid,
        "fraction_left": left,
        "percent_left": round(left * 100),
        "fee": round(paid * left * CANCELLATION_FEE, 4) if refundable else 0.0,
        "refund": refund,
        "refundable": refundable,
        "seconds_left": seconds_left(order),
    }


def is_cancellable(order: dict) -> bool:
    return order.get("status") == store.STATUS_ACTIVE


def cancel(order_id: str) -> dict | None:
    order = store.get_order(order_id)
    if not order or order.get("status") != store.STATUS_ACTIVE:
        return None

    result = quote(order)
    store.cancel_order(order_id)
    result["children_cancelled"] = []
    _ = get_package(order.get("package_id") or "")

    if result["refund"] > 0:
        entry = store.apply_balance(
            int(order["user_id"]),
            result["refund"],
            store.TX_REFUND,
            note=f"cancelled {order_id} with {result['percent_left']}% unused",
        )
        result["tx_id"] = entry["id"]
        result["balance_after"] = float(entry["balance_after"])
    else:
        result["tx_id"] = ""
        result["balance_after"] = store.get_balance(int(order["user_id"]))

    return result
