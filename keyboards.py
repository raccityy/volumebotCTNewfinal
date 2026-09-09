"""Inline keyboards only. No reply keyboards."""

from __future__ import annotations

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
from packages import KIND_AD, KIND_HOLDERS, KIND_VOLUME, get_package, packages_for


def _btn(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, callback_data=data)


def menu_btn(label: str = "Main Menu") -> InlineKeyboardButton:
    return _btn(label, "menu")


def main_menu() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        _btn("📊 Volume Boost", f"buy:{KIND_VOLUME}"),
        _btn("👥 Holders Boost", f"buy:{KIND_HOLDERS}"),
    )
    markup.add(_btn("🔊 Sponsored Ads", f"buy:{KIND_AD}"))
    markup.add(
        _btn("📈 Stats", "stats"),
        _btn("💰 Balance", "bal:home"),
    )
    markup.add(InlineKeyboardButton("💬 Support", url=config.SUPPORT_URL))
    return markup


def package_menu(kind: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    pkgs = packages_for(kind)
    markup.add(*[_btn(p.button_label, f"pkg:{p.id}") for p in pkgs])
    markup.add(_btn("⬅️ Back", "menu"), _btn("🔝 Main Menu", "menu"))
    return markup


def prompt_menu(retry_action: str) -> InlineKeyboardMarkup:
    """Waiting for text (CA, tx hash, etc.) — Cancel only."""
    _ = retry_action
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(_btn("Cancel", "cancel"), menu_btn())
    return markup


def error_menu(retry_action: str = "menu") -> InlineKeyboardMarkup:
    """Shown when a text prompt fails — Retry + Cancel."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(_btn("Retry", f"retry:{retry_action}"), _btn("Cancel", "cancel"))
    markup.add(menu_btn())
    return markup


def ad_preview_menu(order_id: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(_btn("Looks good — continue to payment", f"pay:{order_id}"))
    markup.add(
        _btn("Change the button text", f"adlabel:{order_id}"),
        _btn("Change the link", f"adurl:{order_id}"),
    )
    markup.add(menu_btn())
    return markup


def preview_menu(order_id: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(_btn("Looks good — continue to payment", f"pay:{order_id}"))
    markup.add(
        _btn("Change CA", f"newca:{order_id}"),
        _btn("Refresh stats", f"recheck:{order_id}"),
    )
    markup.add(menu_btn())
    return markup


def lookup_retry_menu(order_id: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        _btn("Continue anyway", f"cacontinue:{order_id}"),
        _btn("Change CA", f"newca:{order_id}"),
    )
    markup.add(_btn("Retry", f"retry:newca:{order_id}"), _btn("Cancel", "cancel"))
    return markup


def pay_menu(order_id: str, *, can_pay_from_balance: bool) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    if can_pay_from_balance:
        markup.add(_btn("Pay with my balance", f"balpay:{order_id}"))
    else:
        markup.add(_btn("Top up my balance instead", "bal:deposit"))
    markup.add(_btn("I've Paid — Verify", f"verify:{order_id}"))
    markup.add(_btn("💰 Balance", "bal:home"), menu_btn())
    return markup


def back_to_menu() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(menu_btn("Main menu"))
    return markup


def stats_menu() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        _btn("📈 Detailed Analytics", "stats_detailed"),
        _btn("🔴 Live Tracking", "stats_live"),
    )
    markup.add(_btn("⚡ Performance", "stats_performance"))
    markup.add(_btn("🔄 Refresh", "stats"), menu_btn())
    return markup


def stats_sub_menu(retry_action: str) -> InlineKeyboardMarkup:
    _ = retry_action
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(_btn("🔙 Back to Stats", "stats"), menu_btn())
    return markup


def support_menu() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("Open chat with support", url=config.SUPPORT_URL))
    markup.add(_btn("Message here instead", "support_here"))
    markup.add(menu_btn())
    return markup


# --- balance hub ------------------------------------------------------------
def balance_menu(
    *, drafts: int = 0, pending: int = 0, promos: int = 0
) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(_btn("Deposit", "bal:deposit"), _btn("Withdraw", "bal:withdraw"))
    markup.add(
        _btn("Transactions", "bal:history:0"),
        _btn(f"Active Orders ({promos})", "bal:promos"),
    )
    markup.add(
        _btn(f"Pending ({pending})", "bal:pending"),
        _btn(f"Drafts ({drafts})", "bal:drafts"),
    )
    markup.add(_btn("All Orders", "bal:orders"), _btn("Refresh", "bal:home"))
    markup.add(menu_btn())
    return markup


def deposit_amount_menu() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    presets = [
        _btn(f"{amount:g} {config.PAYMENT_CURRENCY}", f"bal:dep:{amount:g}")
        for amount in config.DEPOSIT_PRESETS
    ]
    presets.append(_btn("Custom amount", "bal:depcustom"))
    markup.add(*presets)
    markup.add(_btn("Back to Balance", "back:bal:home"), menu_btn())
    return markup


def deposit_confirm_menu(amount: float) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(_btn("🧾 I have sent it — Verify Payment", f"bal:depverify:{amount:g}"))
    markup.add(
        _btn("Change the amount", "bal:deposit"),
        _btn("Cancel this deposit", "back:bal:home"),
    )
    markup.add(menu_btn())
    return markup


def promos_menu(orders: list[dict]) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    for index, order in enumerate(orders, start=1):
        markup.add(
            _btn(f"🛑 Cancel #{index} — {_promo_tag(order)}", f"bal:cancel:{order['id']}")
        )
    markup.add(_btn("🔄 Refresh", "bal:promos"))
    markup.add(_btn("Back to Balance", "back:bal:home"))
    return markup


def _promo_tag(order: dict) -> str:
    name = (order.get("symbol") or order.get("name") or order["id"])[:12]
    pkg = get_package(order["package_id"])
    kind = pkg.kind if pkg else order.get("kind", "")
    icons = {KIND_VOLUME: "📊", KIND_HOLDERS: "👥", KIND_AD: "🔊"}
    return f"{icons.get(kind, '•')} {name}"


def cancel_confirm_menu(order_id: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(_btn("🛑 Yes, cancel and refund me", f"bal:cancelyes:{order_id}"))
    markup.add(
        _btn("No, keep it running", "back:bal:promos"),
        _btn("💰 Balance", "bal:home"),
    )
    return markup


def balance_back(extra_action: tuple[str, str] | None = None) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    if extra_action:
        markup.add(_btn(extra_action[0], extra_action[1]))
    markup.add(_btn("Back to Balance", "back:bal:home"), menu_btn())
    return markup


def history_nav(page: int, pages: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    nav = []
    if page > 0:
        nav.append(_btn("⬅️ Newer", f"bal:history:{page - 1}"))
    if page < pages - 1:
        nav.append(_btn("Older ➡️", f"bal:history:{page + 1}"))
    if nav:
        markup.add(*nav)
    markup.add(
        _btn("🔄 Refresh", f"bal:history:{page}"),
        _btn("Back to Balance", "back:bal:home"),
    )
    return markup


def drafts_menu(count: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    if count:
        markup.add(_btn("🗑️ Clear All Drafts", "bal:drafts_clear_confirm"))
    markup.add(_btn("🚀 Start New Order", "menu"), _btn("🔄 Refresh", "bal:drafts"))
    markup.add(_btn("Back to Balance", "back:bal:home"))
    return markup


def confirm_clear_drafts() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        _btn("✅ Yes, clear them", "bal:drafts_clear"),
        _btn("❌ Keep them", "bal:drafts"),
    )
    return markup


def admin_deposit(tx_id: str, user_chat_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        _btn("✅ Credit Balance", f"adm_dep_ok:{tx_id}"),
        _btn("⛔ Reject", f"adm_dep_no:{tx_id}"),
    )
    markup.add(
        _btn("📝 Reply", f"adm_reply:{user_chat_id}"),
        _btn("💰 Balance", f"adm_bal:{user_chat_id}"),
    )
    markup.add(_btn("❌ Close", "adm_close"))
    return markup


def admin_withdrawal(tx_id: str, user_chat_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        _btn("✅ Mark Paid", f"adm_wd_ok:{tx_id}"),
        _btn("⛔ Reject & Refund", f"adm_wd_no:{tx_id}"),
    )
    markup.add(
        _btn("📝 Reply", f"adm_reply:{user_chat_id}"),
        _btn("💰 Balance", f"adm_bal:{user_chat_id}"),
    )
    markup.add(_btn("❌ Close", "adm_close"))
    return markup


def admin_review(order_id: str, user_chat_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        _btn("✅ Approve", f"adm_ok:{order_id}"),
        _btn("⛔ Reject", f"adm_no:{order_id}"),
    )
    markup.add(
        _btn("📝 Reply", f"adm_reply:{user_chat_id}"),
        _btn("💰 Balance", f"adm_bal:{user_chat_id}"),
    )
    markup.add(_btn("❌ Close", "adm_close"))
    return markup


def admin_support(user_chat_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        _btn("📝 Reply", f"adm_reply:{user_chat_id}"),
        _btn("💰 Balance", f"adm_bal:{user_chat_id}"),
    )
    markup.add(_btn("❌ Close", "adm_close"))
    return markup


_STATIC_LABELS = {
    "menu": "🏠 Main menu",
    "cancel": "❌ Cancel",
    "support": "💬 Support",
    "support_here": "🆘 Message support in bot",
    "stats": "📈 Stats",
    "stats_detailed": "📈 Detailed analytics",
    "stats_live": "🔴 Live tracking",
    "stats_performance": "⚡ Performance",
    "close": "❌ Close",
    f"buy:{KIND_VOLUME}": "📊 Volume Boost",
    f"buy:{KIND_HOLDERS}": "👥 Holders Boost",
    f"buy:{KIND_AD}": "🔊 Sponsored Ads",
    "bal:home": "💰 Balance",
    "bal:deposit": "💳 Deposit",
    "bal:depcustom": "✍️ Custom deposit amount",
    "bal:withdraw": "💸 Withdraw",
    "bal:promos": "🚀 Active orders",
    "bal:pending": "⏳ Pending orders",
    "bal:drafts": "🧾 Drafts",
    "bal:orders": "📦 All Orders",
    "bal:drafts_clear_confirm": "🗑️ Clear drafts (asked)",
    "bal:drafts_clear": "🗑️ Clear drafts (confirmed)",
}

_PREFIX_LABELS = {
    "pay:": "✅ Continue to payment",
    "balpay:": "💰 Pay from Balance",
    "verify:": "🧾 I've Paid — Verify",
    "preview:": "⬅️ Back to preview",
    "recheck:": "🔄 Refresh stats",
    "newca:": "Change CA",
    "cacontinue:": "✅ Continue with CA",
    "adlabel:": "Change the ad button text",
    "adurl:": "Change the ad link",
    "bal:history:": "📋 Transactions page",
    "bal:depverify:": "🧾 Verify deposit payment",
    "bal:dep:": "💎 Deposit amount",
    "bal:cancelyes:": "🛑 Confirmed cancel + refund",
    "bal:cancel:": "🛑 Cancel order (asked)",
}


def describe_action(data: str) -> str:
    if not data:
        return "unknown"
    if data.startswith("back:"):
        rest = data.split("back:", 1)[1]
        return f"Back → {describe_action(rest)}" if rest else "Back"
    if data.startswith("retry:"):
        return f"🔄 Retry → {describe_action(data.split('retry:', 1)[1])}"
    if data in _STATIC_LABELS:
        return _STATIC_LABELS[data]
    if data.startswith("pkg:"):
        pkg = get_package(data.split("pkg:", 1)[1])
        return f"📦 Package {pkg.label} ({pkg.price:g} SOL)" if pkg else data
    for prefix, label in _PREFIX_LABELS.items():
        if data.startswith(prefix):
            suffix = data.split(prefix, 1)[1]
            return f"{label} ({suffix})" if suffix else label
    return data
