"""Admin group: activity log, payment verification, approve/reject, replies."""

from __future__ import annotations

import time

import config
import store
from bot_instance import bot
from keyboards import (
    admin_deposit,
    admin_review,
    admin_support,
    admin_withdrawal,
    back_to_menu,
    error_menu,
    menu_btn,
)
from md import md_bold, md_code, md_escape, md_italic
from packages import KIND_AD, KIND_HOLDERS, KIND_LABEL, KIND_VOLUME, get_package

reply_targets: dict[int, int] = {}
admin_reply_state: dict[int, str] = {}
admin_reply_modes: dict[int, str] = {}


def _group_id() -> int | None:
    raw = (config.ADMIN_GROUP_CHAT_ID or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        print("[admin_group] ADMIN_GROUP_CHAT_ID must be an integer")
        return None


def is_admin_group(chat_id: int) -> bool:
    gid = _group_id()
    return gid is not None and int(chat_id) == gid


def _who(user) -> str:
    handle = user.username or user.first_name or "unknown"
    return f"@{md_escape(handle)} · {md_code(str(user.id))}"


def _log_to_group(text: str, markup=None) -> None:
    gid = _group_id()
    if gid is None:
        return
    try:
        bot.send_message(gid, text, reply_markup=markup, disable_notification=True)
    except Exception as err:
        print(f"[admin_group] activity log failed: {err}")


def notify_start(message) -> None:
    _log_to_group(
        f"🚀 {md_bold('This user just clicked START')}\n"
        f"👤 {_who(message.from_user)}",
        admin_support(message.from_user.id),
    )


def notify_click(user, action_label: str) -> None:
    _log_to_group(
        f"👆 {md_bold('Button clicked')}\n"
        f"👤 {_who(user)}\n"
        f"🔘 {md_escape(action_label)}"
    )


def mirror_user_message(message) -> None:
    gid = _group_id()
    if gid is None:
        return
    user = message.from_user
    try:
        bot.send_message(
            gid,
            f"💬 {md_bold('Message from user')}\n"
            f"👤 {_who(user)}\n"
            f"📎 {md_escape(describe_media(message))}",
            reply_markup=admin_support(user.id),
        )
    except Exception as err:
        print(f"[admin_group] mirror header failed: {err}")
        return
    try:
        bot.forward_message(gid, message.chat.id, message.message_id)
    except Exception:
        forward_to_chat(message, gid)


def _subject_block(order: dict) -> str:
    pkg = get_package(order["package_id"])
    if order["kind"] == KIND_AD:
        return (
            f"🔘 Button text: {md_bold(order.get('ad_label') or '-')}\n"
            f"🔗 Button link: {md_code(order.get('ad_url') or '-')}\n"
            f"⚠️ {md_italic('Open that link yourself before approving this ad.')}"
        )
    lines = [
        f"💎 Project: {md_bold(order.get('name') or '-')}",
        f"🔗 CA: {md_code(order.get('ca') or '-')}",
    ]
    if order["kind"] == KIND_VOLUME:
        target = f"${pkg.volume_usd:,.0f}" if pkg and pkg.volume_usd else "?"
        lines.append(f"📊 Volume to generate: {md_bold(target)}")
        lines.append(f"🔀 Pair: {md_escape(str(order.get('dex') or 'unknown'))}")
        lines.append(md_italic("Start the volume job on this pair once approved."))
    elif order["kind"] == KIND_HOLDERS:
        target = f"+{pkg.holders:,}" if pkg and pkg.holders else "?"
        lines.append(f"👥 Holders to add: {md_bold(target)}")
        lines.append(md_italic("Start the holder drip on this token once approved."))
    return "\n".join(lines)


def send_payment_verification(order: dict) -> bool:
    gid = _group_id()
    if gid is None:
        print("[admin_group] no ADMIN_GROUP_CHAT_ID set — verification not sent")
        return False

    pkg = get_package(order["package_id"])
    label = pkg.label if pkg else order["package_id"]
    price_label = f"{float(order['price']):g} {config.PAYMENT_CURRENCY}"
    duration = pkg.duration_label if pkg else "?"
    text = (
        f"🧾 {md_bold('PAYMENT VERIFICATION')}\n"
        f"🆔 Order tag: {md_code(store.order_tag(order))}\n"
        f"📦 {KIND_LABEL.get(order['kind'], order['kind'])} — {md_escape(label)}\n"
        f"💰 Price: {md_bold(price_label)}\n"
        f"⏱️ Duration: {md_escape(duration)}\n\n"
        f"👤 User: @{md_escape(order['username'] or 'unknown')}\n"
        f"🆔 User ID: {md_code(str(order['user_id']))}\n\n"
        f"{_subject_block(order)}\n"
        f"🧾 TX: {md_code(order['tx_hash'])}\n\n"
        f"⏰ {md_italic(time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))}"
    )
    markup = admin_review(order["id"], order["user_id"])
    try:
        sent = bot.send_message(gid, text, reply_markup=markup)
        reply_targets[sent.message_id] = int(order["user_id"])
        return True
    except Exception as err:
        print(f"[admin_group] failed to send verification: {err}")
        return False


def send_support_request(message) -> bool:
    gid = _group_id()
    if gid is None:
        return False
    user = message.from_user
    header = (
        f"🆘 {md_bold('SUPPORT REQUEST')}\n"
        f"👤 @{md_escape(user.username or user.first_name or 'unknown')}\n"
        f"🆔 {md_code(str(user.id))}\n"
        f"💳 Balance: {md_code(f'{store.get_balance(user.id):.4f}')}\n\n"
        f"💬 {md_escape((message.text or message.caption or '(media)')[:600])}"
    )
    markup = admin_support(user.id)
    try:
        sent = bot.send_message(gid, header, reply_markup=markup)
        reply_targets[sent.message_id] = int(user.id)
        if message.content_type != "text":
            forward_to_chat(message, gid)
        return True
    except Exception as err:
        print(f"[admin_group] failed to send support request: {err}")
        return False


_TX_MISSING = "❌ That transaction record no longer exists."
_ORDER_MISSING = "❌ That order could not be found anymore."


def _already_handled(reference: str, status: str | None) -> str:
    return (
        f"⚠️ Nothing happened, because {reference} was already marked as "
        f"{status or 'processed'}."
    )


def send_deposit_request(user, entry: dict) -> bool:
    gid = _group_id()
    if gid is None:
        return False
    amount = f"{float(entry['amount']):.4f} {config.PAYMENT_CURRENCY}"
    text = (
        f"📥 {md_bold('DEPOSIT VERIFICATION')}\n"
        f"🆔 {md_code(entry['id'])}\n"
        f"👤 @{md_escape(user.username or user.first_name or 'unknown')}\n"
        f"🆔 User ID: {md_code(str(user.id))}\n\n"
        f"💰 Claimed: {md_bold(amount)}\n"
        f"🔗 TX: {md_code(entry.get('tx_hash', '-'))}\n"
        f"💳 Balance now: {md_code(f'{store.get_balance(user.id):.4f}')}\n\n"
        f"✅ {md_italic('Credit Balance adds the claimed amount.')}"
    )
    try:
        sent = bot.send_message(
            gid, text, reply_markup=admin_deposit(entry["id"], user.id)
        )
        reply_targets[sent.message_id] = int(user.id)
        return True
    except Exception as err:
        print(f"[admin_group] deposit request failed: {err}")
        return False


def send_withdrawal_request(user, entry: dict, wallet: str) -> bool:
    gid = _group_id()
    if gid is None:
        return False
    amount = f"{abs(float(entry['amount'])):.4f} {config.PAYMENT_CURRENCY}"
    text = (
        f"💸 {md_bold('WITHDRAWAL REQUEST')}\n"
        f"🆔 {md_code(entry['id'])}\n"
        f"👤 @{md_escape(user.username or user.first_name or 'unknown')}\n"
        f"🆔 User ID: {md_code(str(user.id))}\n\n"
        f"💰 Amount: {md_bold(amount)}\n"
        f"⛓️ {md_escape(config.PAYMENT_NETWORK)}\n"
        f"📬 Send to:\n{md_code(wallet)}\n\n"
        f"💳 Balance after hold: {md_code(f'{store.get_balance(user.id):.4f}')}\n"
        f"⏰ {md_italic(time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()))}\n\n"
        f"⚠️ {md_bold('Action required:')} send {md_bold(amount)} to the address above."
    )
    try:
        sent = bot.send_message(
            gid, text, reply_markup=admin_withdrawal(entry["id"], user.id)
        )
        reply_targets[sent.message_id] = int(user.id)
        return True
    except Exception as err:
        print(f"[admin_group] withdrawal request failed: {err}")
        return False


def notify_balance_purchase(user, order: dict) -> None:
    pkg = get_package(order["package_id"])
    label = pkg.label if pkg else order["package_id"]
    price = f"{float(order['price']):g} {config.PAYMENT_CURRENCY}"
    _log_to_group(
        f"💰 {md_bold('PAID FROM BALANCE — auto-activated')}\n"
        f"🆔 {md_code(order['id'])}\n"
        f"👤 {_who(user)}\n"
        f"📦 {KIND_LABEL.get(order['kind'], order['kind'])} — {md_escape(label)}\n"
        f"💵 {md_bold(price)}\n"
        f"💳 Remaining: {md_code(f'{store.get_balance(user.id):.4f}')}",
        admin_support(user.id),
    )


def notify_cancellation(user, order: dict, result: dict) -> None:
    pkg = get_package(order["package_id"])
    label = pkg.label if pkg else order["package_id"]
    paid = f"{result['paid']:g} {config.PAYMENT_CURRENCY}"
    refund = f"{result['refund']:g} {config.PAYMENT_CURRENCY}"
    unused = f"{result['percent_left']}%"
    balance_after = f"{result['balance_after']:.4f}"
    kind_label = KIND_LABEL.get(order["kind"], order["kind"])
    _log_to_group(
        f"🛑 {md_bold('ORDER CANCELLED BY USER — refund issued')}\n"
        f"🆔 {md_code(order['id'])}\n"
        f"👤 {_who(user)}\n"
        f"📦 {kind_label} — {md_escape(label)}\n"
        f"💵 Paid: {md_code(paid)}\n"
        f"⏳ Unused portion: {md_bold(unused)}\n"
        f"💸 Refunded: {md_bold(refund)}\n"
        f"💳 New balance: {md_code(balance_after)}",
        admin_support(user.id),
    )


def _approve_deposit(call, tx_id: str) -> None:
    chat_id = call.message.chat.id
    entry = store.get_transaction(tx_id)
    if not entry:
        bot.send_message(chat_id, _TX_MISSING)
        return
    if entry.get("status") != "pending":
        bot.send_message(chat_id, _already_handled(tx_id, entry.get("status")))
        return

    amount = float(entry["amount"])
    settled = store.settle_transaction(tx_id)
    if not settled:
        bot.send_message(chat_id, f"⚠️ Could not settle {tx_id}.")
        return
    new_balance = float(settled["balance_after"])
    bot.send_message(
        chat_id,
        f"✅ {md_bold('DEPOSIT CREDITED')} {md_code(tx_id)}\n"
        f"💰 {md_bold(f'+{amount:.4f} {config.PAYMENT_CURRENCY}')}\n"
        f"💳 New balance: {md_bold(f'{new_balance:.4f}')}",
    )
    try:
        bot.send_message(
            int(entry["user_id"]),
            f"📥 {md_bold('Deposit credited')}\n"
            f"💰 {md_bold(f'+{amount:.4f} {config.PAYMENT_CURRENCY}')}\n"
            f"💳 New balance: {md_bold(f'{new_balance:.4f} {config.PAYMENT_CURRENCY}')}",
            reply_markup=back_to_menu(),
        )
    except Exception as err:
        print(f"[admin_group] deposit notice failed: {err}")


def _reject_deposit(call, tx_id: str) -> None:
    chat_id = call.message.chat.id
    entry = store.update_transaction(tx_id, status="rejected", note="deposit rejected")
    if not entry:
        bot.send_message(chat_id, _TX_MISSING)
        return
    bot.send_message(
        chat_id,
        f"⛔ {md_bold('DEPOSIT REJECTED')} {md_code(tx_id)}",
    )
    try:
        bot.send_message(
            int(entry["user_id"]),
            f"⛔ {md_bold('Deposit not verified')}\n"
            f"🆔 {md_code(tx_id)}\n\n"
            "We could not confirm that transaction.",
            reply_markup=error_menu("bal:deposit"),
        )
    except Exception as err:
        print(f"[admin_group] deposit rejection notice failed: {err}")


def _approve_withdrawal(call, tx_id: str) -> None:
    chat_id = call.message.chat.id
    entry = store.get_transaction(tx_id)
    if not entry:
        bot.send_message(chat_id, _TX_MISSING)
        return
    if entry.get("status") != "pending":
        bot.send_message(chat_id, _already_handled(tx_id, entry.get("status")))
        return

    amount = abs(float(entry["amount"]))
    store.update_transaction(tx_id, status="completed", note="withdrawal sent")
    bot.send_message(
        chat_id,
        f"✅ {md_bold('WITHDRAWAL MARKED PAID')} {md_code(tx_id)}\n"
        f"💰 Amount sent: {md_bold(f'{amount:.4f} {config.PAYMENT_CURRENCY}')}",
    )
    try:
        bot.send_message(
            int(entry["user_id"]),
            f"✅ {md_bold('Withdrawal sent')}\n"
            f"🆔 {md_code(tx_id)}\n"
            f"💰 {md_bold(f'{amount:.4f} {config.PAYMENT_CURRENCY}')}\n"
            f"📬 {md_code(str(entry.get('wallet', '-')))}",
            reply_markup=back_to_menu(),
        )
    except Exception as err:
        print(f"[admin_group] withdrawal notice failed: {err}")


def _reject_withdrawal(call, tx_id: str) -> None:
    chat_id = call.message.chat.id
    entry = store.get_transaction(tx_id)
    if not entry:
        bot.send_message(chat_id, _TX_MISSING)
        return
    if entry.get("status") != "pending":
        bot.send_message(chat_id, _already_handled(tx_id, entry.get("status")))
        return

    amount = abs(float(entry["amount"]))
    user_id = int(entry["user_id"])
    store.update_transaction(tx_id, status="rejected", note="withdrawal rejected")
    new_balance = store.adjust_balance(
        user_id, amount, store.TX_REFUND, note=f"refund of {tx_id}"
    )
    bot.send_message(
        chat_id,
        f"⛔ {md_bold('WITHDRAWAL REJECTED AND FULLY REFUNDED')} {md_code(tx_id)}\n"
        f"💰 Returned: {md_bold(f'{amount:.4f} {config.PAYMENT_CURRENCY}')}\n"
        f"💳 New balance: {md_bold(f'{new_balance:.4f}')}",
    )
    try:
        bot.send_message(
            user_id,
            f"↩️ {md_bold('Withdrawal cancelled and refunded')}\n"
            f"🆔 {md_code(tx_id)}\n"
            f"💰 {md_bold(f'+{amount:.4f} {config.PAYMENT_CURRENCY}')} back in your balance\n"
            f"💳 Balance: {md_bold(f'{new_balance:.4f} {config.PAYMENT_CURRENCY}')}",
            reply_markup=back_to_menu(),
        )
    except Exception as err:
        print(f"[admin_group] refund notice failed: {err}")


def notify_user_activated(order: dict) -> None:
    pkg = get_package(order["package_id"])
    hours = pkg.duration_label if pkg else "?"
    extra = ""
    if order["kind"] == KIND_VOLUME:
        target = f"${pkg.volume_usd:,.0f}" if pkg and pkg.volume_usd else "your target"
        extra = (
            f"\n📊 {md_italic(f'We are pushing {target} of volume through your pair.')}"
        )
    elif order["kind"] == KIND_HOLDERS:
        target = f"{pkg.holders:,}" if pkg and pkg.holders else "your target"
        extra = (
            f"\n👥 {md_italic(f'We are adding {target} new holder wallets, drip fed across the window.')}"
        )
    elif order["kind"] == KIND_AD:
        extra = (
            f"\n📢 {md_italic('Your sponsored button is now live.')}"
            f"\n🔘 {md_bold(order.get('ad_label') or 'Your button')} → {md_escape(order.get('ad_url') or '')}"
        )
    try:
        bot.send_message(
            int(order["user_id"]),
            f"🟢 {md_bold('YOUR ORDER IS LIVE')}\n"
            f"🆔 {md_code(order['id'])}\n"
            f"📦 {KIND_LABEL.get(order['kind'], order['kind'])}\n"
            f"⏱️ Runs for {md_bold(hours)}{extra}\n\n"
            f"✨ {md_italic('Thanks for using ClearTactics Volume Bot.')}",
            reply_markup=back_to_menu(),
        )
    except Exception as err:
        print(f"[admin_group] could not notify user: {err}")


def notify_user_expired(order: dict) -> None:
    try:
        bot.send_message(
            int(order["user_id"]),
            f"⚫ {md_bold('Order finished')}\n"
            f"🆔 {md_code(order['id'])} — {KIND_LABEL.get(order['kind'], order['kind'])}\n\n"
            f"🔁 {md_italic('Want to keep the momentum? Buy another boost.')}",
            reply_markup=back_to_menu(),
        )
    except Exception as err:
        print(f"[admin_group] could not notify expiry: {err}")


def handle_callback(call) -> None:
    data = call.data or ""
    chat_id = call.message.chat.id

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    if data.startswith("adm_ok:"):
        _approve(call, data.split("adm_ok:", 1)[1])
        return
    if data.startswith("adm_no:"):
        _reject(call, data.split("adm_no:", 1)[1])
        return
    if data.startswith("adm_dep_ok:"):
        _approve_deposit(call, data.split("adm_dep_ok:", 1)[1])
        return
    if data.startswith("adm_dep_no:"):
        _reject_deposit(call, data.split("adm_dep_no:", 1)[1])
        return
    if data.startswith("adm_wd_ok:"):
        _approve_withdrawal(call, data.split("adm_wd_ok:", 1)[1])
        return
    if data.startswith("adm_wd_no:"):
        _reject_withdrawal(call, data.split("adm_wd_no:", 1)[1])
        return
    if data.startswith("adm_reply:"):
        user_chat_id = data.split("adm_reply:", 1)[1]
        admin_reply_state[call.from_user.id] = user_chat_id
        admin_reply_modes[call.from_user.id] = user_chat_id
        bot.send_message(
            chat_id,
            f"📝 {md_bold('Reply mode on')} → user {md_code(user_chat_id)}\n\n"
            "Anything you send here goes to them.\n\n"
            f"🚪 /exit_reply to stop · ℹ️ /reply_status to check",
        )
        return
    if data.startswith("adm_bal:"):
        _balance_prompt(call, data.split("adm_bal:", 1)[1])
        return
    if data == "adm_close":
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass


def _approve(call, order_id: str) -> None:
    chat_id = call.message.chat.id
    order = store.get_order(order_id)
    if not order:
        bot.send_message(chat_id, _ORDER_MISSING)
        return
    pkg = get_package(order["package_id"])
    if not pkg:
        bot.send_message(chat_id, "❌ Package no longer exists.")
        return

    order = store.activate_order(order_id, pkg.seconds)
    if not order:
        bot.send_message(chat_id, _ORDER_MISSING)
        return

    ends = order.get("expires_at")
    ends_txt = time.strftime("%H:%M UTC", time.gmtime(ends)) if ends else "—"
    bot.send_message(
        chat_id,
        f"✅ {md_bold('APPROVED')} {md_code(order_id)}\n"
        f"📦 {KIND_LABEL.get(order['kind'], order['kind'])} — {md_escape(pkg.label)}\n"
        f"⏳ Ends {md_code(ends_txt)}\n"
        f"👤 @{md_escape(order['username'] or str(order['user_id']))}",
    )
    notify_user_activated(order)


def _reject(call, order_id: str) -> None:
    chat_id = call.message.chat.id
    order = store.update_order(order_id, status=store.STATUS_REJECTED)
    if not order:
        bot.send_message(chat_id, _ORDER_MISSING)
        return
    bot.send_message(
        chat_id,
        f"⛔ {md_bold('ORDER REJECTED')} {md_code(order_id)}",
    )
    try:
        bot.send_message(
            int(order["user_id"]),
            f"⛔ {md_bold('Payment not verified')}\n"
            f"🆔 {md_code(order_id)}\n\n"
            "We could not confirm that transaction.\n"
            f"{md_italic('Tap Retry to send the transaction hash again.')}",
            reply_markup=_reject_menu(order_id),
        )
    except Exception as err:
        print(f"[admin_group] could not notify rejection: {err}")


def _reject_menu(order_id: str):
    from telebot.types import InlineKeyboardMarkup

    markup = InlineKeyboardMarkup()
    from telebot.types import InlineKeyboardButton

    markup.add(
        InlineKeyboardButton("🔄 Retry", callback_data=f"verify:{order_id}"),
        menu_btn("Main menu"),
    )
    return markup


def _balance_prompt(call, user_chat_id: str) -> None:
    chat_id = call.message.chat.id
    uid = int(user_chat_id)
    balance = store.get_balance(uid)
    orders = store.orders_by_user(uid)
    totals = store.user_totals(uid)
    transactions = store.user_transactions(uid)
    active = [o for o in orders if o["status"] == store.STATUS_ACTIVE]
    admin_reply_state[call.from_user.id] = f"balance_update_{user_chat_id}"

    lines = [
        f"💰 {md_bold('BALANCE MANAGEMENT')}",
        f"👤 User: {md_code(user_chat_id)}",
        f"💳 Balance: {md_bold(f'{balance:.4f} {config.PAYMENT_CURRENCY}')}",
        "",
        f"📊 Orders: {md_bold(str(len(orders)))} (🟢 {len(active)} active)",
        f"📥 Deposited: {md_code(f'{totals['deposited']:.4f}')}",
        f"🛒 Spent: {md_code(f'{totals['spent']:.4f}')}",
        f"📤 Withdrawn: {md_code(f'{totals['withdrawn']:.4f}')}",
        "",
    ]
    if transactions:
        lines.append(f"📋 {md_bold('LAST MOVEMENTS')}")
        for tx in transactions[:3]:
            change = f"{float(tx['amount']):+.4f}"
            lines.append(
                f"• {tx['type']} {md_bold(change)} ({tx.get('status', '-')})"
            )
        lines.append("")
    lines += [
        f"✍️ Send {md_code('+0.5')} or {md_code('-1.2')} to adjust.",
        f"⚠️ {md_italic('Numbers only after the + or -.')}",
    ]
    bot.send_message(chat_id, "\n".join(lines))


def handle_admin_message(message) -> None:
    admin_id = message.from_user.id
    text = (message.text or "").strip()

    if text == "/exit_reply":
        target = admin_reply_modes.pop(admin_id, None)
        admin_reply_state.pop(admin_id, None)
        if target:
            notice = f"✅ Left reply mode for user {md_code(str(target))}."
        else:
            notice = "ℹ️ You were not in reply mode."
        bot.send_message(message.chat.id, notice)
        return

    if text == "/reply_status":
        target = admin_reply_modes.get(admin_id) or admin_reply_state.get(admin_id)
        if target:
            notice = f"📝 Reply mode on for user {md_code(str(target))}."
        else:
            notice = "❌ You are not in reply mode."
        bot.send_message(message.chat.id, notice)
        return

    if text == "/promos":
        _list_promos(message.chat.id)
        return

    if text == "/pending":
        _list_pending(message.chat.id)
        return

    state = admin_reply_state.get(admin_id, "")
    if state.startswith("balance_update_"):
        _apply_balance_update(message, state.split("balance_update_", 1)[1])
        return

    target = admin_reply_modes.get(admin_id) or admin_reply_state.pop(admin_id, None)
    if not target:
        return

    media_type = describe_media(message)
    forward_to_chat(message, int(target))
    bot.send_message(
        message.chat.id,
        f"✅ That {media_type} was delivered to user {md_code(str(target))}.",
    )


def _apply_balance_update(message, user_chat_id: str) -> None:
    admin_id = message.from_user.id
    raw = (message.text or "").strip()
    number = raw[1:] if raw[:1] in "+-" else ""
    valid = bool(number) and number.count(".") <= 1 and number.replace(".", "").isdigit()
    if not valid:
        bot.send_message(
            message.chat.id,
            f"❌ {md_bold('That balance adjustment was not in a usable format')}\n\n"
            f"✅ Examples: {md_code('+0.5')} {md_code('-1.2')} {md_code('+10')}",
        )
        return

    amount = float(raw)
    new_balance = store.adjust_balance(
        int(user_chat_id),
        amount,
        store.TX_ADMIN,
        note=f"manual adjustment by admin {admin_id}",
    )
    admin_reply_state.pop(admin_id, None)

    bot.send_message(
        message.chat.id,
        f"✅ {md_bold('Balance updated')}\n"
        f"👤 {md_code(user_chat_id)}\n"
        f"💰 Change: {md_bold(f'{amount:+.4f}')}\n"
        f"💳 New: {md_bold(f'{new_balance:.4f} {config.PAYMENT_CURRENCY}')}",
    )
    try:
        bot.send_message(
            int(user_chat_id),
            f"💳 {md_bold('Balance updated')}\n"
            f"Change: {md_bold(f'{amount:+.4f} {config.PAYMENT_CURRENCY}')}\n"
            f"New balance: {md_bold(f'{new_balance:.4f} {config.PAYMENT_CURRENCY}')}",
            reply_markup=back_to_menu(),
        )
    except Exception as err:
        print(f"[admin_group] could not notify balance change: {err}")


def _list_promos(chat_id: int) -> None:
    active = store.active_orders()
    if not active:
        bot.send_message(chat_id, "😴 No paid orders running right now.")
        return
    lines = [f"🟢 {md_bold('ACTIVE ORDERS')}", ""]
    for order in active:
        remaining = max(0, int((order.get("expires_at") or 0) - time.time()))
        hours, minutes = divmod(remaining // 60, 60)
        lines.append(
            f"{KIND_LABEL.get(order['kind'], order['kind'])} "
            f"{md_code(order['id'])} {md_bold(order.get('name') or (order.get('ca') or '')[:10])} "
            f"· ⏳ {hours}h {minutes}m"
        )
    bot.send_message(chat_id, "\n".join(lines))


def _list_pending(chat_id: int) -> None:
    orders = store.orders_by_status(store.STATUS_PENDING)
    movements = store.pending_transactions()
    if not orders and not movements:
        bot.send_message(chat_id, "✅ Nothing is waiting for the team right now.")
        return

    lines = [f"⏳ {md_bold('PENDING')}", ""]
    for order in orders:
        price = f"{float(order['price']):g}"
        lines.append(
            f"📦 {md_code(order['id'])} {KIND_LABEL.get(order['kind'], order['kind'])} "
            f"{md_bold(order.get('name') or (order.get('ca') or '')[:10])} · {md_code(price)}"
        )
    for tx in movements:
        change = f"{float(tx['amount']):+.4f}"
        lines.append(
            f"💳 {md_code(tx['id'])} {tx['type']} {md_bold(change)} "
            f"· user {md_code(str(tx['user_id']))}"
        )
    bot.send_message(chat_id, "\n".join(lines))


def describe_media(message) -> str:
    mapping = [
        ("photo", "📷 Photo"),
        ("video", "🎥 Video"),
        ("animation", "🎬 GIF"),
        ("document", "📄 Document"),
        ("audio", "🎵 Audio"),
        ("voice", "🎤 Voice"),
        ("video_note", "📹 Video note"),
        ("sticker", "🎲 Sticker"),
        ("location", "📍 Location"),
        ("contact", "👤 Contact"),
        ("text", "📝 Text"),
    ]
    for attr, label in mapping:
        if getattr(message, attr, None):
            return label
    return "❓ Message"


def forward_to_chat(message, chat_id: int) -> None:
    try:
        caption = message.caption
        if message.photo:
            bot.send_photo(chat_id, message.photo[-1].file_id, caption=caption)
        elif message.video:
            bot.send_video(chat_id, message.video.file_id, caption=caption)
        elif message.animation:
            bot.send_animation(chat_id, message.animation.file_id, caption=caption)
        elif message.document:
            bot.send_document(chat_id, message.document.file_id, caption=caption)
        elif message.audio:
            bot.send_audio(chat_id, message.audio.file_id, caption=caption)
        elif message.voice:
            bot.send_voice(chat_id, message.voice.file_id, caption=caption)
        elif message.video_note:
            bot.send_video_note(chat_id, message.video_note.file_id)
        elif message.sticker:
            bot.send_sticker(chat_id, message.sticker.file_id)
        elif message.location:
            bot.send_location(
                chat_id, message.location.latitude, message.location.longitude
            )
        elif message.contact:
            bot.send_contact(
                chat_id, message.contact.phone_number, message.contact.first_name
            )
        elif message.text:
            bot.send_message(chat_id, message.text, parse_mode=None)
        else:
            bot.send_message(
                chat_id,
                "Support sent a message this bot cannot show here.",
                parse_mode=None,
            )
    except Exception as err:
        print(f"[admin_group] forward failed: {err}")


def register() -> None:
    @bot.callback_query_handler(
        func=lambda call: (call.data or "").startswith("adm_")
    )
    def on_admin_callback(call) -> None:
        handle_callback(call)

    @bot.message_handler(
        func=lambda m: is_admin_group(m.chat.id),
        content_types=[
            "text",
            "photo",
            "video",
            "animation",
            "document",
            "audio",
            "voice",
            "video_note",
            "sticker",
            "location",
            "contact",
        ],
    )
    def on_group_message(message) -> None:
        try:
            handle_admin_message(message)
        except Exception as err:
            print(f"[admin_group] handler error: {err}")
            try:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ That admin action failed: {err}",
                    parse_mode=None,
                )
            except Exception:
                pass
