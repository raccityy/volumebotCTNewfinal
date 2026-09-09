"""Balance hub — deposits, withdrawals, ledger, orders."""

from __future__ import annotations

import time

import config
import refunds
import sessions
import store
from bot_instance import say, send_long, send_screen
from keyboards import (
    balance_back,
    balance_menu,
    cancel_confirm_menu,
    confirm_clear_drafts,
    deposit_amount_menu,
    deposit_confirm_menu,
    drafts_menu,
    error_menu,
    history_nav,
    promos_menu,
    prompt_menu,
)
from md import md_bold, md_code, md_error, md_escape, md_italic
from packages import KIND_LABEL, get_package

HISTORY_PAGE_SIZE = 8

_TX_ICON = {
    store.TX_DEPOSIT: "📥",
    store.TX_WITHDRAWAL: "📤",
    store.TX_SPEND: "🛒",
    store.TX_ADMIN: "🛠️",
    store.TX_REFUND: "↩️",
}

_STATUS_ICON = {
    store.STATUS_DRAFT: "🧾",
    store.STATUS_PENDING: "⏳",
    store.STATUS_ACTIVE: "🟢",
    store.STATUS_EXPIRED: "⚫",
    store.STATUS_REJECTED: "🔴",
    store.STATUS_CANCELLED: "❌",
}


def fmt(amount: float) -> str:
    return f"{amount:.4f} {config.PAYMENT_CURRENCY}"


def clock(ts: float | None) -> str:
    if not ts:
        return "-"
    return time.strftime("%d %b %H:%M", time.gmtime(ts))


def time_left(order: dict) -> str:
    expires_at = order.get("expires_at")
    if not expires_at:
        return ""
    remaining = int(float(expires_at) - time.time())
    if remaining <= 0:
        return "expiring"
    hours, minutes = divmod(remaining // 60, 60)
    return f"{hours}h {minutes}m left"


def order_title(order: dict) -> str:
    pkg = get_package(order["package_id"])
    name = order.get("name") or (order.get("ca") or "")[:10] or "untitled"
    label = pkg.label if pkg else order["package_id"]
    return f"{md_bold(name)} — {md_escape(label)}"


def _held_amount(user_id: int) -> float:
    return sum(
        abs(float(tx["amount"]))
        for tx in store.user_transactions(user_id)
        if tx["type"] == store.TX_WITHDRAWAL and tx.get("status") == "pending"
    )


def _parse_amount(text: str | None) -> float | None:
    try:
        value = float((text or "").strip().replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


def show_home(chat_id: int, user) -> None:
    user_id = user.id
    balance = store.get_balance(user_id)
    totals = store.user_totals(user_id)
    held = _held_amount(user_id)
    orders = store.orders_by_user(user_id)

    by_status: dict[str, int] = {}
    for order in orders:
        by_status[order["status"]] = by_status.get(order["status"], 0) + 1

    active = [o for o in orders if o["status"] == store.STATUS_ACTIVE]
    drafts = by_status.get(store.STATUS_DRAFT, 0)
    pending = by_status.get(store.STATUS_PENDING, 0)

    handle = user.username or user.first_name or "there"
    status_line = "🟢 Funded" if balance > 0 else "🔴 No funds"

    lines = [
        f"💰 {md_bold('ACCOUNT BALANCE')}",
        f"👤 @{md_escape(handle)} · {md_code(str(user_id))}",
        f"⛓️ {md_escape(config.PAYMENT_NETWORK)}",
        "",
        f"💵 {md_bold('BALANCE')}",
        f"• Available: {md_bold(fmt(balance))}",
        f"• On hold: {md_code(fmt(held))}",
        f"• Status: {md_bold(status_line)}",
        "",
        f"📊 {md_bold('ACCOUNT SUMMARY')}",
        f"• Total orders: {md_bold(str(len(orders)))}",
        f"• 🟢 Active: {md_bold(str(len(active)))}",
        f"• ⏳ Awaiting confirmation: {md_bold(str(pending))}",
        f"• 🧾 Unfinished drafts: {md_bold(str(drafts))}",
        f"• ⚫ Finished: {md_bold(str(by_status.get(store.STATUS_EXPIRED, 0)))}",
        "",
        f"💹 {md_bold('LIFETIME')}",
        f"• 📥 Deposited: {md_bold(fmt(totals['deposited']))}",
        f"• 🛒 Spent: {md_bold(fmt(totals['spent']))}",
        f"• 📤 Withdrawn: {md_bold(fmt(totals['withdrawn']))}",
        "",
        f"🕒 {md_italic('Updated ' + time.strftime('%H:%M:%S UTC', time.gmtime()))}",
    ]

    send_long(
        chat_id,
        lines,
        reply_markup=balance_menu(drafts=drafts, pending=pending, promos=len(active)),
        image_key="balance",
    )


def _tx_line(tx: dict) -> str:
    icon = _TX_ICON.get(tx["type"], "•")
    amount = float(tx["amount"])
    sign = f"{amount:+.4f}"
    tail = ""
    if tx.get("status") == "pending":
        tail = " ⏳"
    elif tx.get("status") == "rejected":
        tail = " 🔴"
    note = f" · {md_escape(tx['note'])}" if tx.get("note") else ""
    return (
        f"{icon} {md_bold(sign)} {config.PAYMENT_CURRENCY} · "
        f"{md_italic(clock(tx.get('timestamp')))}{note}{tail}"
    )


def show_deposit(chat_id: int, user_id: int) -> None:
    sessions.set_session(user_id, step="")
    presets = ", ".join(
        f"{amount:g} {config.PAYMENT_CURRENCY}" for amount in config.DEPOSIT_PRESETS
    )
    send_screen(
        chat_id,
        f"💳 {md_bold('DEPOSIT — CHOOSE HOW MUCH TO TOP UP')}\n"
        f"⛓️ Network: {md_escape(config.PAYMENT_NETWORK)}\n"
        f"💰 Your balance right now: {md_bold(fmt(store.get_balance(user_id)))}\n\n"
        f"💡 {md_bold('Why it is worth topping up first')}\n"
        "Money sitting in your balance lets you buy volume or holders with a "
        "single tap, instead of sending a transfer every time.\n\n"
        f"👇 {md_bold('Pick one of the amounts below to continue')}\n"
        f"{md_italic('Quick options: ' + presets + '. Tap custom for any other amount.')}",
        image_key="deposit",
        reply_markup=deposit_amount_menu(),
    )


def show_deposit_instructions(chat_id: int, user_id: int, amount: float) -> None:
    sessions.set_session(user_id, step="", deposit_amount=amount)
    send_screen(
        chat_id,
        f"💎 {md_bold('DEPOSIT OF ' + fmt(amount).upper())}\n"
        f"💰 Amount to send: {md_bold(fmt(amount))}\n"
        f"⛓️ Network: {md_escape(config.PAYMENT_NETWORK)}\n\n"
        f"📬 {md_bold('Send the funds to this address')}\n"
        f"{md_code(config.PAYMENT_WALLET)}\n\n"
        f"1️⃣ Send exactly {md_bold(fmt(amount))} to the address above\n"
        "2️⃣ Wait until your wallet says the transfer is confirmed\n"
        "3️⃣ Come back here and tap the verify button underneath\n\n"
        f"🧾 {md_bold('Only tap verify once the transfer has actually gone out')}. "
        "The bot will then ask for the transaction hash so it can be confirmed.\n\n"
        f"⏳ {md_italic('Your balance is credited as soon as the transaction is confirmed.')}",
        image_key="deposit",
        reply_markup=deposit_confirm_menu(amount),
    )


def ask_deposit_custom_amount(chat_id: int, user_id: int) -> None:
    sessions.set_session(user_id, step=sessions.STEP_DEPOSIT_AMOUNT)
    say(
        chat_id,
        f"✍️ {md_bold('Tell me how much you want to deposit')}\n"
        f"⛓️ Network: {md_escape(config.PAYMENT_NETWORK)}\n"
        f"💰 Your balance right now: {md_bold(fmt(store.get_balance(user_id)))}\n\n"
        "Send the number on its own, like "
        f"{md_code('1.75')} or {md_code('12')}.\n\n"
        f"📉 {md_italic(f'Minimum is {config.MIN_DEPOSIT:g} {config.PAYMENT_CURRENCY}.')}",
        reply_markup=prompt_menu("bal:depcustom"),
    )


def handle_deposit_amount(message, user_id: int) -> None:
    amount = _parse_amount(message.text)
    if amount is None or amount < config.MIN_DEPOSIT:
        say(
            message.chat.id,
            md_error(
                "ERROR DEPOSIT AMOUNT INVALID",
                f"Please send digits only, at least "
                f"{config.MIN_DEPOSIT:g} {config.PAYMENT_CURRENCY}. "
                "Examples: 0.5 or 2.25.",
            ),
            reply_markup=error_menu("bal:depcustom"),
        )
        return
    show_deposit_instructions(message.chat.id, user_id, amount)


def ask_deposit_hash(chat_id: int, user_id: int, amount: float) -> None:
    sessions.set_session(
        user_id, step=sessions.STEP_DEPOSIT_TX, deposit_amount=amount
    )
    say(
        chat_id,
        f"🔗 {md_bold('Now paste the transaction hash of that payment')}\n"
        f"💰 Deposit being verified: {md_bold(fmt(amount))}\n\n"
        "Open your wallet history or Solscan, copy the full transaction "
        "signature, and send it here on its own line.\n\n"
        f"⏳ {md_italic('It goes into confirmation, then your balance is credited.')}",
        reply_markup=prompt_menu(f"bal:depverify:{amount:g}"),
    )


def handle_deposit_tx(message, session: dict, user_id: int) -> None:
    import admin_group

    tx_hash = (message.text or "").strip()
    amount = float(session.get("deposit_amount") or 0.0)

    if len(tx_hash) < 32:
        say(
            message.chat.id,
            md_error(
                "ERROR TX HASH INVALID",
                "Please copy the full Solana signature from your wallet or "
                "Solscan and paste it here on its own.",
            ),
            reply_markup=error_menu(f"bal:depverify:{amount:g}"),
        )
        return

    entry = store.add_transaction(
        user_id,
        store.TX_DEPOSIT,
        amount,
        tx_hash=tx_hash,
        note="deposit awaiting verification",
        status="pending",
    )
    sessions.clear_session(user_id)
    admin_group.send_deposit_request(message.from_user, entry)
    say(
        message.chat.id,
        f"🧾 {md_bold('Your deposit has been submitted for confirmation')}\n"
        f"🆔 Reference: {md_code(entry['id'])}\n"
        f"💰 Amount claimed: {md_bold(fmt(amount))}\n"
        f"🔗 Transaction hash: {md_code(tx_hash)}\n\n"
        f"⏳ {md_italic('Your balance will be topped up the moment it is confirmed.')}",
        reply_markup=balance_back(),
    )


def show_withdraw(chat_id: int, user_id: int) -> None:
    balance = store.get_balance(user_id)
    if balance < config.MIN_WITHDRAWAL:
        send_screen(
            chat_id,
            f"💸 {md_bold('WITHDRAW')}\n"
            f"💰 Available: {md_bold(fmt(balance))}\n\n"
            + md_error(
                "ERROR INSUFFICIENT BALANCE",
                f"Please deposit first — you need at least "
                f"{config.MIN_WITHDRAWAL:g} {config.PAYMENT_CURRENCY} to withdraw.",
            ),
            image_key="withdraw",
            reply_markup=balance_back(("💳 Deposit", "bal:deposit")),
        )
        return

    sessions.set_session(user_id, step=sessions.STEP_WITHDRAW_AMOUNT)
    send_screen(
        chat_id,
        f"💸 {md_bold('WITHDRAW')}\n"
        f"💰 Available: {md_bold(fmt(balance))}\n"
        f"📤 Maximum: {md_bold(fmt(balance))}\n"
        f"⛓️ {md_escape(config.PAYMENT_NETWORK)}\n\n"
        f"⚠️ {md_bold('Before you continue')}\n"
        "• Withdrawals are usually completed within 24 hours\n"
        "• Network fees may apply\n"
        "• Double-check your address — transfers cannot be reversed\n\n"
        f"✍️ {md_bold('How much do you want to withdraw?')}\n"
        f"{md_italic('Send the number only, or send the word all for everything.')}",
        image_key="withdraw",
        reply_markup=prompt_menu("bal:withdraw"),
    )


def handle_withdraw_amount(message, user_id: int) -> None:
    balance = store.get_balance(user_id)
    raw = (message.text or "").strip().lower()
    amount = balance if raw in ("all", "max") else _parse_amount(raw)

    if amount is None or amount < config.MIN_WITHDRAWAL:
        say(
            message.chat.id,
            md_error(
                "ERROR WITHDRAWAL AMOUNT INVALID",
                f"Please send digits only. Minimum is "
                f"{config.MIN_WITHDRAWAL:g} {config.PAYMENT_CURRENCY}.",
            ),
            reply_markup=error_menu("bal:withdraw"),
        )
        return
    if amount > balance:
        say(
            message.chat.id,
            md_error(
                "ERROR AMOUNT TOO HIGH",
                "Please send a smaller number, or type all. "
                f"Your available balance is {fmt(balance)}.",
            ),
            reply_markup=error_menu("bal:withdraw"),
        )
        return

    sessions.set_session(
        user_id, step=sessions.STEP_WITHDRAW_WALLET, withdraw_amount=amount
    )
    say(
        message.chat.id,
        f"✅ Withdrawing {md_bold(fmt(amount))} from your balance\n\n"
        f"📬 {md_bold('Now send the Solana address that should receive it')}\n"
        f"{md_italic('Paste the full wallet address on its own line.')}",
        reply_markup=prompt_menu("bal:withdraw"),
    )


def handle_withdraw_wallet(message, session: dict, user_id: int) -> None:
    import admin_group

    wallet = (message.text or "").strip()
    if len(wallet) < 32:
        say(
            message.chat.id,
            md_error(
                "ERROR WALLET ADDRESS INVALID",
                "Please paste the full Solana address alone — no extra words.",
            ),
            reply_markup=error_menu("bal:withdraw"),
        )
        return

    amount = float(session.get("withdraw_amount") or 0.0)
    balance = store.get_balance(user_id)
    if amount > balance:
        sessions.clear_session(user_id)
        say(
            message.chat.id,
            md_error(
                "ERROR BALANCE CHANGED",
                f"Please start the withdrawal again. Available now: {fmt(balance)}.",
            ),
            reply_markup=error_menu("bal:withdraw"),
        )
        return

    entry = store.apply_balance(
        user_id,
        -amount,
        store.TX_WITHDRAWAL,
        note=f"to {wallet[:10]}…",
        status="pending",
        wallet=wallet,
    )
    sessions.clear_session(user_id)

    admin_group.send_withdrawal_request(message.from_user, entry, wallet)
    say(
        message.chat.id,
        f"💸 {md_bold('Your withdrawal request has been submitted')}\n"
        f"🆔 Reference: {md_code(entry['id'])}\n"
        f"💰 Amount: {md_bold(fmt(amount))}\n"
        f"📬 Going to: {md_code(wallet)}\n"
        f"💳 Remaining balance: {md_bold(fmt(store.get_balance(user_id)))}\n\n"
        f"⏰ {md_italic('Processed within 24 hours. Rejected requests are refunded automatically.')}",
        reply_markup=balance_back(),
    )


def show_history(chat_id: int, user_id: int, page: int = 0) -> None:
    rows = store.user_transactions(user_id)
    if not rows:
        send_screen(
            chat_id,
            f"📋 {md_bold('TRANSACTIONS')}\n\n"
            f"📭 {md_bold('There is nothing in your history yet')}\n"
            f"{md_italic('Deposits, withdrawals and purchases will appear here.')}",
            reply_markup=balance_back(("💳 Deposit", "bal:deposit")),
        )
        return

    pages = max(1, (len(rows) + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    window = rows[page * HISTORY_PAGE_SIZE : (page + 1) * HISTORY_PAGE_SIZE]

    totals = store.user_totals(user_id)
    lines = [
        f"📋 {md_bold('TRANSACTIONS')}",
        f"📊 Total: {md_bold(str(len(rows)))} · Page {md_bold(f'{page + 1}/{pages}')}",
        f"📥 In {md_code(fmt(totals['deposited']))}  "
        f"📤 Out {md_code(fmt(totals['withdrawn']))}  "
        f"🛒 Spent {md_code(fmt(totals['spent']))}",
        "",
    ]
    for index, tx in enumerate(window, start=page * HISTORY_PAGE_SIZE + 1):
        lines.append(f"{index}. {_tx_line(tx)}")
        lines.append(
            f"　　{md_code(tx['id'])} · bal {md_code(fmt(float(tx.get('balance_after', 0))))}"
        )
        if tx.get("tx_hash"):
            lines.append(f"　　🔗 {md_code(tx['tx_hash'][:24])}")
        lines.append("")

    lines.append(md_italic("Newest transactions are shown first."))
    send_screen(
        chat_id,
        "\n".join(lines),
        reply_markup=history_nav(page, pages),
    )


def show_promos(chat_id: int, user_id: int) -> None:
    orders = store.orders_by_user(user_id)
    active = [o for o in orders if o["status"] == store.STATUS_ACTIVE]
    if not active:
        send_screen(
            chat_id,
            f"🚀 {md_bold('ACTIVE ORDERS')}\n\n"
            f"😴 {md_bold('You have nothing running at the moment')}\n"
            f"{md_italic('Buy Volume Boost or Holders Boost from the main menu.')}",
            reply_markup=balance_back(("🚀 Buy a boost", "menu")),
        )
        return

    cancellable = [o for o in active if refunds.is_cancellable(o)]
    lines = [f"🚀 {md_bold('ACTIVE ORDERS')}", ""]
    for index, order in enumerate(active, start=1):
        lines.append(
            f"{index}. {KIND_LABEL.get(order['kind'], order['kind'])} {order_title(order)}"
        )
        lines.append(f"　　🆔 {md_code(order['id'])}")
        lines.append(f"　　⏳ {md_bold(time_left(order))}")
        lines.append(f"　　🕒 Ends {md_code(clock(order.get('expires_at')))}")
        quote = refunds.quote(order)
        if quote["refundable"]:
            unused = f"{quote['percent_left']}% unused"
            lines.append(
                f"　　🛑 Cancel now and get back {md_bold(fmt(quote['refund']))} "
                f"({md_code(unused)})"
            )
        else:
            lines.append(
                f"　　🛑 {md_italic('Too close to the end to refund anything now')}"
            )
        lines.append("")

    lines += [
        f"↩️ {md_bold('CANCELLING AND REFUNDS')}",
        f"Unused time comes back to your balance minus a "
        f"{md_bold(f'{refunds.CANCELLATION_FEE * 100:g}% cancellation fee')}.",
    ]
    send_long(chat_id, lines, reply_markup=promos_menu(cancellable))


def show_cancel_confirm(chat_id: int, user_id: int, order_id: str) -> None:
    order = store.get_order(order_id)
    if not order or int(order["user_id"]) != int(user_id):
        say(
            chat_id,
            md_error(
                "ERROR ORDER NOT FOUND",
                "Please open your active orders again and pick one from the list.",
            ),
            reply_markup=balance_back(("🚀 Active orders", "bal:promos")),
        )
        return
    if not refunds.is_cancellable(order):
        say(
            chat_id,
            f"⚠️ {md_bold('That order cannot be cancelled')}\n\n"
            f"{md_italic('It has already finished.')}",
            reply_markup=balance_back(("🚀 Active orders", "bal:promos")),
        )
        return

    quote = refunds.quote(order)
    unused = f"{quote['percent_left']}%"
    lines = [
        f"🛑 {md_bold('CANCEL THIS ORDER?')}",
        f"📦 {KIND_LABEL.get(order['kind'], order['kind'])} {order_title(order)}",
        f"🆔 {md_code(order['id'])}",
        f"⏳ Time remaining: {md_bold(time_left(order) or 'almost none')}",
        "",
        f"💰 {md_bold('WHAT YOU GET BACK')}",
        f"• You paid: {md_code(fmt(quote['paid']))}",
        f"• Unused portion: {md_bold(unused)}",
    ]
    if quote["refundable"]:
        lines += [
            f"• Cancellation fee kept: {md_code(fmt(quote['fee']))}",
            f"• 💸 Refunded to your balance: {md_bold(fmt(quote['refund']))}",
        ]
    else:
        lines.append(
            md_italic("There is too little time left for a refund.")
        )
    lines += [
        "",
        f"⚠️ {md_bold('This cannot be undone once you confirm it')}.",
    ]
    send_long(chat_id, lines, reply_markup=cancel_confirm_menu(order_id))


def do_cancel(chat_id: int, user, order_id: str) -> None:
    import admin_group

    order = store.get_order(order_id)
    if not order or int(order["user_id"]) != int(user.id):
        say(
            chat_id,
            md_error(
                "ERROR ORDER NOT FOUND",
                "Please open your active orders and try again.",
            ),
            reply_markup=balance_back(("🚀 Active orders", "bal:promos")),
        )
        return

    result = refunds.cancel(order_id)
    if not result:
        say(
            chat_id,
            md_error(
                "ERROR ORDER ALREADY STOPPED",
                "Nothing was refunded.",
            ),
            reply_markup=balance_back(("🚀 Active orders", "bal:promos")),
        )
        return

    lines = [
        f"🛑 {md_bold('ORDER CANCELLED')}",
        f"🆔 {md_code(order_id)}",
        f"📦 {KIND_LABEL.get(order['kind'], order['kind'])} {order_title(order)}",
        "",
    ]
    if result["refund"] > 0:
        lines += [
            f"💸 Refunded: {md_bold(fmt(result['refund']))}",
            f"🧾 Reference: {md_code(result['tx_id'])}",
            f"💳 New balance: {md_bold(fmt(result['balance_after']))}",
        ]
    else:
        lines.append(f"💸 Refunded: {md_bold(fmt(0))}")

    send_screen(
        chat_id,
        "\n".join(lines),
        reply_markup=balance_back(("🚀 Buy another boost", "menu")),
    )
    admin_group.notify_cancellation(user, order, result)


def show_pending(chat_id: int, user_id: int) -> None:
    pending = [
        o for o in store.orders_by_user(user_id) if o["status"] == store.STATUS_PENDING
    ]
    pending_tx = [
        t for t in store.user_transactions(user_id) if t.get("status") == "pending"
    ]

    lines = [f"⏳ {md_bold('AWAITING VERIFICATION')}", ""]
    if not pending and not pending_tx:
        lines.append(f"✅ {md_bold('There is nothing waiting for confirmation')}")
    else:
        if pending:
            lines.append(f"📦 {md_bold('ORDERS')}")
            for order in pending:
                lines.append(f"• {order_title(order)}")
                lines.append(
                    f"　　🆔 {md_code(order['id'])} · 💰 {md_code(fmt(float(order['price'])))}"
                )
                lines.append(f"　　🔗 {md_code((order.get('tx_hash') or '-')[:24])}")
                lines.append("")
        if pending_tx:
            lines.append(f"💳 {md_bold('BALANCE MOVEMENTS')}")
            for tx in pending_tx:
                lines.append(f"• {_tx_line(tx)}")
                lines.append(f"　　🆔 {md_code(tx['id'])}")
                lines.append("")
        lines.append(md_italic("These are usually cleared within the hour."))
    send_screen(chat_id, "\n".join(lines), reply_markup=balance_back())


def show_drafts(chat_id: int, user_id: int) -> None:
    drafts = store.draft_orders(user_id)
    lines = [f"🧾 {md_bold('UNFINISHED DRAFTS')}", ""]
    if not drafts:
        lines.append(f"✅ {md_bold('You do not have any unfinished drafts')}")
        send_screen(chat_id, "\n".join(lines), reply_markup=drafts_menu(0))
        return

    lines.append(md_italic("These were started but never paid for."))
    lines.append("")
    for order in drafts:
        lines.append(f"• {order_title(order)}")
        lines.append(
            f"　　🆔 {md_code(order['id'])} · 💰 {md_code(fmt(float(order['price'])))}"
        )
        lines.append(f"　　🕒 Started {md_code(clock(order.get('created_at')))}")
        lines.append("")
    send_screen(
        chat_id,
        "\n".join(lines),
        reply_markup=drafts_menu(len(drafts)),
    )


def show_clear_drafts_confirm(chat_id: int, user_id: int) -> None:
    count = len(store.draft_orders(user_id))
    if not count:
        show_drafts(chat_id, user_id)
        return
    say(
        chat_id,
        f"⚠️ {md_bold('Clear all drafts?')}\n\n"
        f"You are about to discard {md_bold(str(count))} unfinished order(s).\n\n"
        f"🔒 {md_italic('Paid and active orders are not affected.')}",
        reply_markup=confirm_clear_drafts(),
    )


def clear_drafts(chat_id: int, user_id: int) -> None:
    cleared = store.clear_drafts(user_id)
    say(
        chat_id,
        f"✅ {md_bold('Drafts cleared')}\n"
        f"🗑️ Removed {md_bold(str(cleared))} unfinished order(s).",
        reply_markup=balance_back(("🚀 Start a new order", "menu")),
    )


def show_all_orders(chat_id: int, user_id: int) -> None:
    orders = sorted(
        store.orders_by_user(user_id),
        key=lambda o: o.get("created_at", 0),
        reverse=True,
    )
    if not orders:
        send_screen(
            chat_id,
            f"📦 {md_bold('ALL ORDERS')}\n\n"
            f"📭 {md_bold('You have not placed any orders yet')}",
            reply_markup=balance_back(("🚀 Buy a boost", "menu")),
        )
        return

    spent = sum(
        float(o["price"])
        for o in orders
        if o["status"] in (store.STATUS_ACTIVE, store.STATUS_EXPIRED)
    )
    lines = [
        f"📦 {md_bold('ALL ORDERS')}",
        f"📊 {md_bold(str(len(orders)))} total · 💰 {md_bold(fmt(spent))} delivered",
        "",
    ]
    for order in orders[:12]:
        icon = _STATUS_ICON.get(order["status"], "•")
        lines.append(
            f"{icon} {KIND_LABEL.get(order['kind'], order['kind'])} {order_title(order)}"
        )
        detail = f"　　🆔 {md_code(order['id'])} · {md_bold(order['status'].upper())}"
        if order["status"] == store.STATUS_ACTIVE:
            detail += f" · ⏳ {time_left(order)}"
        lines.append(detail)
        lines.append(f"　　🕒 {md_code(clock(order.get('created_at')))}")
        lines.append("")
    if len(orders) > 12:
        lines.append(md_italic(f"… and {len(orders) - 12} older orders"))
    send_screen(chat_id, "\n".join(lines), reply_markup=balance_back())


def pay_from_balance(chat_id: int, user, order_id: str) -> None:
    import admin_group

    order = store.get_order(order_id)
    if not order:
        say(
            chat_id,
            md_error(
                "ERROR ORDER NOT FOUND",
                "Nothing was taken from your balance. Start again from the main menu.",
            ),
            reply_markup=balance_back(),
        )
        return

    price = float(order["price"])
    bal = store.get_balance(user.id)
    if bal < price:
        say(
            chat_id,
            md_error(
                "ERROR INSUFFICIENT BALANCE",
                f"Please deposit first. You have {fmt(bal)}, this costs "
                f"{fmt(price)} (short {fmt(price - bal)}).",
            ),
            reply_markup=balance_back(("💳 Deposit", "bal:deposit")),
        )
        return

    pkg = get_package(order["package_id"])
    if not pkg:
        say(
            chat_id,
            md_error(
                "ERROR PACKAGE UNAVAILABLE",
                "Your balance was not touched. Pick a current package from the menu.",
            ),
            reply_markup=balance_back(),
        )
        return

    store.apply_balance(
        user.id,
        -price,
        store.TX_SPEND,
        note=f"{KIND_LABEL.get(order['kind'], order['kind'])} {order['id']}",
    )
    store.update_order(order_id, tx_hash="paid from balance")
    order = store.activate_order(order_id, pkg.seconds) or order

    say(
        chat_id,
        f"🟢 {md_bold('PAID FROM BALANCE — ORDER IS LIVE')}\n"
        f"🆔 {md_code(order['id'])}\n"
        f"📦 {KIND_LABEL.get(order['kind'], order['kind'])} — {md_escape(pkg.label)}\n"
        f"💰 Charged: {md_bold(fmt(price))}\n"
        f"💳 Remaining: {md_bold(fmt(store.get_balance(user.id)))}\n"
        f"⏱️ Runs for {md_bold(pkg.duration_label)}\n\n"
        f"✨ {md_italic('It started the moment you tapped that button.')}",
        reply_markup=balance_back(),
    )
    admin_group.notify_balance_purchase(user, order)


def handle_callback(call) -> bool:
    data = call.data or ""
    chat_id = call.message.chat.id
    user = call.from_user

    if data.startswith("balpay:"):
        pay_from_balance(chat_id, user, data.split("balpay:", 1)[1])
        return True

    if not data.startswith("bal:"):
        return False

    action = data.split("bal:", 1)[1]

    if action == "home":
        sessions.set_session(user.id, step="")
        show_home(chat_id, user)
    elif action == "deposit":
        show_deposit(chat_id, user.id)
    elif action == "depcustom":
        ask_deposit_custom_amount(chat_id, user.id)
    elif action.startswith("dep:"):
        amount = _parse_amount(action.split("dep:", 1)[1])
        if amount is None:
            show_deposit(chat_id, user.id)
        else:
            show_deposit_instructions(chat_id, user.id, amount)
    elif action.startswith("depverify:"):
        amount = _parse_amount(action.split("depverify:", 1)[1])
        if amount is None:
            show_deposit(chat_id, user.id)
        else:
            ask_deposit_hash(chat_id, user.id, amount)
    elif action == "withdraw":
        show_withdraw(chat_id, user.id)
    elif action.startswith("history:"):
        sessions.set_session(user.id, step="")
        try:
            page = int(action.split("history:", 1)[1])
        except ValueError:
            page = 0
        show_history(chat_id, user.id, page)
    elif action == "promos":
        sessions.set_session(user.id, step="")
        show_promos(chat_id, user.id)
    elif action.startswith("cancelyes:"):
        sessions.set_session(user.id, step="")
        do_cancel(chat_id, user, action.split("cancelyes:", 1)[1])
    elif action.startswith("cancel:"):
        sessions.set_session(user.id, step="")
        show_cancel_confirm(chat_id, user.id, action.split("cancel:", 1)[1])
    elif action == "pending":
        sessions.set_session(user.id, step="")
        show_pending(chat_id, user.id)
    elif action == "drafts":
        sessions.set_session(user.id, step="")
        show_drafts(chat_id, user.id)
    elif action == "drafts_clear_confirm":
        show_clear_drafts_confirm(chat_id, user.id)
    elif action == "drafts_clear":
        clear_drafts(chat_id, user.id)
    elif action == "orders":
        sessions.set_session(user.id, step="")
        show_all_orders(chat_id, user.id)
    else:
        sessions.set_session(user.id, step="")
        show_home(chat_id, user)
    return True


def handle_step(message, session: dict) -> bool:
    step = session.get("step")
    user_id = message.from_user.id

    if step == sessions.STEP_DEPOSIT_AMOUNT:
        handle_deposit_amount(message, user_id)
    elif step == sessions.STEP_DEPOSIT_TX:
        handle_deposit_tx(message, session, user_id)
    elif step == sessions.STEP_WITHDRAW_AMOUNT:
        handle_withdraw_amount(message, user_id)
    elif step == sessions.STEP_WITHDRAW_WALLET:
        handle_withdraw_wallet(message, session, user_id)
    else:
        return False
    return True
