"""Private-chat flow: menu -> package -> CA -> preview -> payment -> tx hash."""

from __future__ import annotations

import threading
import time

from telebot.types import CallbackQuery, Message

import ads
import admin_group
import balance
import config
import stats
import store
import token_lookup
from bot_instance import bot, clear_ui, is_back_nav, say, send_screen, track_message
from keyboards import (
    ad_preview_menu,
    back_to_menu,
    describe_action,
    error_menu,
    lookup_retry_menu,
    main_menu,
    package_menu,
    pay_menu,
    preview_menu,
    prompt_menu,
    support_menu,
)
from md import md_bold, md_code, md_error, md_escape, md_italic, md_link
from packages import KIND_AD, KIND_HOLDERS, KIND_LABEL, KIND_VOLUME, get_package, packages_for
from sessions import (
    STEP_AD_LABEL,
    STEP_AD_URL,
    STEP_CA,
    STEP_SUPPORT,
    STEP_TX,
    clear_session,
    get_session,
    set_session,
)

_ORDER_GONE = "That order could not be found anymore."

WELCOME = (
    f"{md_bold('Welcome to ' + config.BOT_NAME)}\n\n"
    f"{md_italic('Paid volume, holders boost, and sponsored ads for Solana tokens.')}\n\n"
    f"New to volume bots? We made it simple.\n"
    f"·  ·  ·\n"
    f"{md_bold('How it works')}\n"
    f"1️⃣ Select how much volume or how many holders you want.\n"
    f"2️⃣ Paste your contract address.\n"
    f"3️⃣ Pay in SOL — or tap pay from balance.\n"
    f"4️⃣ Paste your tx hash. We confirm and handle the rest.\n"
    f"·  ·  ·\n"
    f"{md_bold('Works on')}\n"
    f"Pump.fun · PumpSwap · Raydium · Moonshot · Jupiter · DexScreener\n\n"
    f"{md_bold('Support')}: {md_link(config.SUPPORT_HANDLE, config.SUPPORT_URL)}"
)

KIND_INTRO = {
    KIND_VOLUME: (
        f"🟡 {md_bold('Classic Mode')}\n\n"
        "Your trusted and proven solution for generating consistent and impactful volume.\n\n"
        "Select your desired volume to increase your project's activity according "
        "to your goals. Below is an overview of the available options and prices.\n\n"
        f"{md_bold('ALL COSTS ARE INCLUDED! NO MORE FEES!')}\n\n"
        "➔ Simply choose the option that best fits your requirements, and we will take care of the rest."
    ),
    KIND_HOLDERS: (
        f"🟢 {md_bold('Holders Boost')}\n\n"
        "Add real-looking holder wallets over a drip window so the count "
        "climbs smoothly instead of spiking.\n\n"
        f"{md_italic('Tap a package below.')}"
    ),
    KIND_AD: (
        f"🔊 {md_bold('Sponsored Ads')}\n\n"
        "Put a button under ClearTactics traffic so people tap straight into your "
        "chart, group, or site.\n\n"
        f"{md_italic('Pick a duration, then send the button text and the link it should open.')}"
    ),
}

_KIND_IMAGE = {
    KIND_VOLUME: "volume",
    KIND_HOLDERS: "holders",
    KIND_AD: "ads",
}

SECURITY_NOTICE = (
    f"{md_bold('Wallet connect / wallet import is never available.')}\n"
    "Anyone asking for your seed phrase or private key is a scam."
)


def send_error(chat_id: int, detail: str, retry_action: str = "menu") -> None:
    _ = retry_action
    send_screen(
        chat_id,
        md_error(
            "ERROR SOMETHING WENT WRONG",
            "Nothing was charged. Open the main menu and try again.",
            f"Details: {md_code((detail or '')[:220])}",
        ),
        image_key="error",
        reply_markup=back_to_menu(),
    )


def guard(chat_id: int, retry_action: str = "menu"):
    class _Guard:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc is None:
                return False
            print(f"[user_flow] error: {exc}")
            try:
                send_error(chat_id, str(exc), retry_action)
            except Exception as err:
                print(f"[user_flow] failed to report error: {err}")
            return True

    return _Guard()


def show_menu(chat_id: int) -> None:
    send_screen(chat_id, WELCOME, image_key="main_menu", reply_markup=main_menu())


def show_packages(chat_id: int, kind: str) -> None:
    options = packages_for(kind)
    if not options:
        send_error(chat_id, "No packages configured for that product.")
        return
    text = KIND_INTRO.get(kind, md_bold(KIND_LABEL.get(kind, kind)))
    send_screen(
        chat_id,
        text,
        image_key=_KIND_IMAGE.get(kind, "main_menu"),
        reply_markup=package_menu(kind),
    )


def start_order(call: CallbackQuery, package_id: str) -> None:
    chat_id = call.message.chat.id
    pkg = get_package(package_id)
    if not pkg:
        send_error(chat_id, "That package no longer exists.", "menu")
        return

    order = store.create_order(
        user_id=call.from_user.id,
        username=call.from_user.username or call.from_user.first_name or "",
        kind=pkg.kind,
        package_id=pkg.id,
        price=pkg.price,
    )
    header = (
        f"{md_bold(KIND_LABEL.get(pkg.kind, pkg.kind))} — {md_escape(pkg.label)}\n"
        f"Total price: {md_bold(f'{pkg.price:g} {config.PAYMENT_CURRENCY}')}\n"
        f"Order tag: {md_code(store.order_tag(order))}\n\n"
    )

    if pkg.kind == KIND_AD:
        set_session(call.from_user.id, order_id=order["id"], step=STEP_AD_LABEL)
        send_screen(
            chat_id,
            header
            + f"{md_bold('Send the text you want on your ad button')}\n\n"
            "This is the label people tap, so keep it short. Something like "
            + md_code("BUY $TICKER")
            + " or "
            + md_code("Join the group")
            + " works well.\n\n"
            f"{md_italic('Twenty four characters is the maximum.')}",
            image_key="ads",
            reply_markup=prompt_menu(f"adlabel:{order['id']}"),
        )
        return

    ask_for_contract(chat_id, call.from_user.id, order["id"], header=header)


def ask_for_contract(
    chat_id: int, user_id: int, order_id: str, header: str = ""
) -> None:
    set_session(user_id, order_id=order_id, step=STEP_CA)
    order = store.get_order(order_id)
    kind = order["kind"] if order else ""
    send_screen(
        chat_id,
        header
        + f"{md_bold('Send a contract address')}\n\n"
        "Paste the Solana token CA on its own line.",
        image_key=_KIND_IMAGE.get(kind, "main_menu"),
        reply_markup=prompt_menu(f"newca:{order_id}"),
    )


def _price_label(order: dict) -> str:
    return f"{float(order['price']):g} {config.PAYMENT_CURRENCY}"


def _summary_caption(order: dict) -> str:
    pkg = get_package(order["package_id"])
    label = pkg.label if pkg else order["package_id"]

    if order["kind"] == KIND_AD:
        return "\n".join(
            [
                f"{md_bold('Ad preview')}",
                f"{md_code(store.order_tag(order))}",
                f"{KIND_LABEL.get(order['kind'], order['kind'])} · {md_escape(label)}",
                f"{md_bold(_price_label(order))}",
                "",
                f"🔘 Button: {md_bold(order.get('ad_label') or '-')}",
                f"🔗 Link: {md_code(order.get('ad_url') or '-')}",
                "",
                f"Runs for {md_bold(pkg.duration_label if pkg else '?')}",
                "",
                md_italic("Looks right? Continue below."),
            ]
        )

    symbol = order.get("symbol") or "TOKEN"
    lines = [
        f"{md_bold('Order preview')}",
        f"{md_code(store.order_tag(order))}",
        f"{KIND_LABEL.get(order['kind'], order['kind'])} · {md_escape(label)}",
        f"{md_bold(_price_label(order))}",
        "",
        f"{md_bold('$' + str(symbol).lstrip('$'))} — {md_escape(order.get('name') or 'Unknown')}",
        f"{md_escape(str(order.get('chain') or '?'))} · "
        f"{md_escape(str(order.get('dex') or '?'))}",
        md_code(order.get("ca") or "-"),
        "",
        f"Price {md_bold(str(order.get('price_display') or '?'))}"
        f"  ·  Liq {md_bold(str(order.get('liquidity_display') or '?'))}"
        f"  ·  Mcap {md_bold(str(order.get('marketcap_display') or '?'))}",
        f"1h {md_escape(str(order.get('change_h1_display') or '—'))}"
        f"  ·  24h {md_escape(str(order.get('change_h24_display') or '—'))}",
    ]
    if pkg and order["kind"] == KIND_VOLUME and pkg.volume_usd:
        lines += [
            "",
            f"~{md_bold(f'${pkg.volume_usd:,.0f}')} volume over "
            f"{md_bold(pkg.duration_label)}",
        ]
    if pkg and order["kind"] == KIND_HOLDERS and pkg.holders:
        lines += [
            "",
            f"+{md_bold(f'{pkg.holders:,}')} holders over "
            f"{md_bold(pkg.duration_label)}",
        ]
    lines += ["", md_italic("Looks right? Continue below.")]
    return "\n".join(lines)


def show_preview(chat_id: int, order: dict) -> None:
    if order["kind"] == KIND_AD:
        send_screen(
            chat_id,
            _summary_caption(order),
            image_key="ads",
            reply_markup=ad_preview_menu(order["id"]),
        )
        return
    send_screen(
        chat_id,
        _summary_caption(order),
        image_key=_KIND_IMAGE.get(order["kind"], "preview"),
        reply_markup=preview_menu(order["id"]),
    )


def ask_ad_link(chat_id: int, user_id: int, order_id: str, label: str) -> None:
    set_session(user_id, order_id=order_id, step=STEP_AD_URL)
    send_screen(
        chat_id,
        f"Your button will read {md_bold(label)}\n"
        f"{md_bold('Now send the link that button should open')}\n\n"
        "Paste the full destination on its own line, starting with https.\n\n"
        f"{md_italic('Examples: https://t.me/yourgroup or https://yourproject.io')}",
        image_key="ads",
        reply_markup=prompt_menu(f"adurl:{order_id}"),
    )


def _save_details(order_id: str, address: str, details) -> dict:
    return store.update_order(
        order_id,
        ca=address,
        symbol=details.symbol,
        name=details.name,
        chain=details.chain,
        dex=details.dex,
        pair_address=details.pair_address,
        pair_url=details.url,
        website=details.website or "",
        twitter=details.twitter or "",
        telegram=details.telegram or "",
        price_usd=details.price_usd,
        price_display=token_lookup.format_price(details.price_usd),
        change_h1=details.price_change_h1,
        change_h1_display=token_lookup.format_pct(details.price_change_h1),
        change_h24_display=token_lookup.format_pct(details.price_change_h24),
        liquidity_display=token_lookup.format_usd(details.liquidity_usd),
        volume_display=token_lookup.format_usd(details.volume_h24_usd),
        marketcap_display=token_lookup.format_usd(
            details.market_cap or details.fdv
        ),
        age_display=token_lookup.format_age(details.pair_created_at),
    )


def run_contract_lookup(chat_id: int, user_id: int, order_id: str, address: str) -> None:
    order = store.get_order(order_id)
    if not order:
        clear_session(user_id)
        send_error(chat_id, "That order could not be found anymore.", "menu")
        return

    address = (address or "").strip()
    if not token_lookup.looks_like_contract(address):
        set_session(user_id, order_id=order_id, step="")
        say(
            chat_id,
            md_error(
                "ERROR TOKEN NOT FOUND",
                "Please paste the token contract address — not a wallet, "
                "pair address, or chart link.",
                f"What you sent: {md_code((address or 'nothing')[:60])}",
            ),
            reply_markup=lookup_retry_menu(order_id),
        )
        return

    say(chat_id, md_italic("Looking up that contract…"))

    try:
        details = token_lookup.fetch_token_details(address)
    except token_lookup.LookupError as err:
        store.update_order(order_id, ca=address, chain="unknown")
        set_session(user_id, order_id=order_id, step="")
        say(
            chat_id,
            md_error(
                "ERROR TOKEN NOT FOUND",
                "No trading pair was found for that contract yet. "
                "You can still continue with this CA, or paste a different one.",
                f"What you sent: {md_code(address[:60])}",
                f"Reason: {md_escape(str(err))}",
            ),
            reply_markup=lookup_retry_menu(order_id),
        )
        return
    except Exception as err:
        print(f"[user_flow] unexpected lookup failure: {err}")
        store.update_order(order_id, ca=address, chain="unknown")
        set_session(user_id, order_id=order_id, step="")
        say(
            chat_id,
            md_error(
                "ERROR LOOKUP TIMEOUT",
                "The lookup service did not respond in time. You can continue "
                "with this CA anyway, or try again.",
                f"What you sent: {md_code(address[:60])}",
            ),
            reply_markup=lookup_retry_menu(order_id),
        )
        return

    order = _save_details(order_id, address, details)
    set_session(user_id, order_id=order_id, step="")
    show_preview(chat_id, order)


def show_payment(chat_id: int, user_id: int, order: dict) -> None:
    price = float(order["price"])
    user_balance = store.get_balance(user_id)
    covered = user_balance >= price
    pkg = get_package(order["package_id"])
    label = pkg.label if pkg else order["package_id"]
    starts = {
        KIND_VOLUME: "Your volume starts flowing the moment payment clears.",
        KIND_HOLDERS: "Your holder count starts climbing the moment payment clears.",
        KIND_AD: "Your sponsored button goes live the moment payment clears.",
    }.get(order["kind"], "Your order starts the moment payment clears.")
    text = (
        f"{md_bold('Payment')}\n"
        f"Order tag: {md_code(store.order_tag(order))}\n"
        f"{KIND_LABEL.get(order['kind'], order['kind'])} — {md_escape(label)}\n"
        f"Amount: {md_bold(_price_label(order))}\n"
        f"Network: {md_escape(config.PAYMENT_NETWORK)}\n\n"
        f"{md_bold('Send payment to')}\n"
        f"{md_code(config.PAYMENT_WALLET)}\n\n"
        "1. Send the exact amount to the wallet above\n"
        "2. Copy your transaction hash\n"
        "3. Tap I've Paid — Verify and paste the hash\n\n"
        f"{md_italic(starts)}\n\n"
        f"{md_bold('Your balance:')} {md_bold(f'{user_balance:.4f} {config.PAYMENT_CURRENCY}')}"
    )
    if covered:
        text += f"\n{md_italic('You have enough in your balance to pay instantly.')}"
    else:
        short = price - user_balance
        text += (
            f"\n{md_italic(f'You are {short:.4f} {config.PAYMENT_CURRENCY} short of paying from your balance.')}"
        )
    send_screen(
        chat_id,
        text,
        image_key="payment",
        reply_markup=pay_menu(order["id"], can_pay_from_balance=covered),
    )


def show_support(chat_id: int, user_id: int) -> None:
    set_session(user_id, step="")
    send_screen(
        chat_id,
        f"{md_bold('Support')}\n\n"
        f"Talk to {md_link(config.SUPPORT_HANDLE, config.SUPPORT_URL)} "
        "on Telegram, or send a message here and the support team will get it.\n\n"
        f"{SECURITY_NOTICE}",
        image_key="support",
        reply_markup=support_menu(),
    )


def ask_support_here(chat_id: int, user_id: int) -> None:
    set_session(user_id, step=STEP_SUPPORT)
    send_screen(
        chat_id,
        f"{md_bold('Support ticket')} · {time.strftime('%H:%M')}\n\n"
        "Please continue typing and the support team will assist you.\n\n"
        f"{SECURITY_NOTICE}\n\n"
        f"{md_italic('You can send text, a screenshot, or a video in this chat.')}",
        image_key="support",
        reply_markup=prompt_menu("support_here"),
    )


def handle_step_text(message: Message, session: dict) -> None:
    chat_id = message.chat.id
    user_id = message.from_user.id
    step = session.get("step")
    order_id = session.get("order_id")
    text = (message.text or message.caption or "").strip()

    if balance.handle_step(message, session):
        return

    if step == STEP_SUPPORT:
        admin_group.send_support_request(message)
        say(
            chat_id,
            f"✅ {md_bold('Message received')}\n\n"
            f"{md_italic('This ticket stays open — keep sending updates here.')}",
            reply_markup=prompt_menu("support_here"),
            replace=False,
        )
        return

    if not order_id:
        show_menu(chat_id)
        return

    order = store.get_order(order_id)
    if not order:
        clear_session(user_id)
        send_error(chat_id, "That order no longer exists.", "menu")
        return

    if step == STEP_CA:
        run_contract_lookup(chat_id, user_id, order_id, text)
        return

    if step == STEP_AD_LABEL:
        label = " ".join(text.split())
        if len(label) < 3 or len(label) > ads.LABEL_MAX:
            say(
                chat_id,
                md_error(
                    "ERROR BUTTON TEXT INVALID",
                    f"Please send between 3 and {ads.LABEL_MAX} characters.",
                    f"Examples: {md_code('BUY $TICKER')} or {md_code('Join the group')}",
                ),
                reply_markup=error_menu(f"adlabel:{order_id}"),
            )
            return
        store.update_order(order_id, ad_label=label)
        ask_ad_link(chat_id, user_id, order_id, label)
        return

    if step == STEP_AD_URL:
        url = ads.normalise_url(text)
        if not ads.looks_like_url(url):
            say(
                chat_id,
                md_error(
                    "ERROR LINK INVALID",
                    "Please send one full URL starting with https and with no spaces.",
                    f"Examples: {md_code('https://t.me/yourgroup')} or {md_code('https://yourproject.io')}",
                ),
                reply_markup=error_menu(f"adurl:{order_id}"),
            )
            return
        order = store.update_order(order_id, ad_url=url[:200])
        set_session(user_id, order_id=order_id, step="")
        show_preview(chat_id, order)
        return

    if step == STEP_TX:
        if len(text) < 32:
            say(
                chat_id,
                md_error(
                    "ERROR TX HASH INVALID",
                    "Please copy the full Solana signature from your wallet "
                    "or Solscan and paste it here on its own.",
                ),
                reply_markup=error_menu(f"verify:{order_id}"),
            )
            return
        order = store.update_order(
            order_id, tx_hash=text[:120], status=store.STATUS_PENDING
        )
        set_session(user_id, step="")
        admin_group.send_payment_verification(order)
        say(
            chat_id,
            f"{md_bold('Your payment has been submitted for confirmation')}\n"
            f"Order tag: {md_code(store.order_tag(order))}\n"
            f"Transaction hash: {md_code(order['tx_hash'])}\n\n"
            f"{md_italic('You will get a message in this chat when your order goes live.')}",
            reply_markup=back_to_menu(),
        )
        return

    show_menu(chat_id)


def handle_callback(call: CallbackQuery) -> None:
    data = call.data or ""
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    admin_group.notify_click(call.from_user, describe_action(call.data or ""))

    raw = call.data or ""
    going_back = is_back_nav(raw)
    if raw.startswith("back:"):
        data = raw.split("back:", 1)[1] or "menu"
        call.data = data
    else:
        data = raw
    if going_back:
        clear_ui(chat_id, getattr(call.message, "message_id", None))

    with guard(chat_id, "menu"):
        if data.startswith("retry:"):
            data = data.split("retry:", 1)[1] or "menu"
            call.data = data

        if data == "close":
            return

        if balance.handle_callback(call):
            return

        if stats.handle_callback(data, chat_id):
            return

        if data == "menu":
            clear_session(user_id)
            show_menu(chat_id)
            return

        if data == "cancel":
            clear_session(user_id)
            say(
                chat_id,
                f"{md_bold('That order has been cancelled and nothing was charged')}\n\n"
                f"{md_italic('You can start again from the main menu. Your balance stays where it is.')}",
                reply_markup=back_to_menu(),
                replace=False,
            )
            return

        if data == "support":
            show_support(chat_id, user_id)
            return

        if data == "support_here":
            ask_support_here(chat_id, user_id)
            return

        if data.startswith("buy:"):
            show_packages(chat_id, data.split("buy:", 1)[1])
            return

        if data.startswith("pkg:"):
            start_order(call, data.split("pkg:", 1)[1])
            return

        if data.startswith("newca:"):
            order_id = data.split("newca:", 1)[1]
            ask_for_contract(chat_id, user_id, order_id)
            return

        if data.startswith("cacontinue:"):
            order = store.get_order(data.split("cacontinue:", 1)[1])
            if not order or not order.get("ca"):
                send_error(chat_id, _ORDER_GONE, "menu")
                return
            set_session(user_id, order_id=order["id"], step="")
            show_preview(chat_id, order)
            return

        if data.startswith("preview:"):
            order = store.get_order(data.split("preview:", 1)[1])
            if not order:
                send_error(chat_id, _ORDER_GONE, "menu")
                return
            set_session(user_id, step="")
            show_preview(chat_id, order)
            return

        if data.startswith("recheck:"):
            order_id = data.split("recheck:", 1)[1]
            order = store.get_order(order_id)
            if not order or not order.get("ca"):
                send_error(chat_id, _ORDER_GONE, "menu")
                return
            run_contract_lookup(chat_id, user_id, order_id, order["ca"])
            return

        if data.startswith("adlabel:"):
            order_id = data.split("adlabel:", 1)[1]
            set_session(user_id, order_id=order_id, step=STEP_AD_LABEL)
            send_screen(
                chat_id,
                f"{md_bold('Send the new text for your ad button')}\n\n"
                f"{md_italic(f'Anything up to {ads.LABEL_MAX} characters is fine.')}",
                image_key="ads",
                reply_markup=prompt_menu(f"adlabel:{order_id}"),
            )
            return

        if data.startswith("adurl:"):
            order_id = data.split("adurl:", 1)[1]
            set_session(user_id, order_id=order_id, step=STEP_AD_URL)
            send_screen(
                chat_id,
                f"{md_bold('Send the new link for your ad button')}\n\n"
                f"{md_italic('Paste the full https URL on its own line.')}",
                image_key="ads",
                reply_markup=prompt_menu(f"adurl:{order_id}"),
            )
            return

        if data.startswith("pay:"):
            order = store.get_order(data.split("pay:", 1)[1])
            if not order:
                send_error(chat_id, _ORDER_GONE, "menu")
                return
            if order["kind"] == KIND_AD and (
                not order.get("ad_label") or not order.get("ad_url")
            ):
                say(
                    chat_id,
                    md_error(
                        "ERROR AD DETAILS MISSING",
                        "Please set the button text and the destination link first.",
                    ),
                    reply_markup=ad_preview_menu(order["id"]),
                )
                return
            show_payment(chat_id, user_id, order)
            return

        if data.startswith("verify:"):
            order_id = data.split("verify:", 1)[1]
            order = store.get_order(order_id)
            if not order:
                send_error(chat_id, _ORDER_GONE, "menu")
                return
            set_session(user_id, order_id=order_id, step=STEP_TX)
            say(
                chat_id,
                f"{md_bold('Paste the transaction hash for your payment')}\n\n"
                "Copy the full Solana signature from your wallet or Solscan, "
                "then send it here on its own.\n\n"
                f"{md_italic('Confirmation starts as soon as the hash arrives.')}",
                reply_markup=prompt_menu(f"verify:{order_id}"),
                replace=False,
            )
            return


def register() -> None:
    _start_inflight: set[int] = set()
    _start_inflight_lock = threading.Lock()

    try:
        from telebot.types import BotCommand

        bot.set_my_commands(
            [
                BotCommand("start", "Welcome / intro"),
                BotCommand("menu", "Open the main menu"),
                BotCommand("cancel", "Cancel the current order"),
            ]
        )
    except Exception as err:
        print(f"[user_flow] set_my_commands failed: {err}")

    @bot.message_handler(commands=["start"])
    def on_start(message: Message) -> None:
        chat_id = int(message.chat.id)
        with _start_inflight_lock:
            if chat_id in _start_inflight:
                return
            _start_inflight.add(chat_id)
        try:
            try:
                clear_session(message.from_user.id)
                clear_ui(chat_id, message.message_id)
            except Exception:
                pass

            def _notify() -> None:
                try:
                    admin_group.notify_start(message)
                except Exception as err:
                    print(f"[user_flow] notify_start failed: {err}")

            threading.Thread(target=_notify, daemon=True).start()

            try:
                user_id = message.from_user.id
                meta = store.get_user_meta(user_id)
                if not meta.get("first_seen_at"):
                    store.set_user_meta(user_id, first_seen_at=time.time())
                show_menu(chat_id)
            except Exception as err:
                print(f"[user_flow] /start failed: {err}")
                try:
                    bot.send_message(
                        chat_id,
                        "Welcome to ClearTactics Volume Bot. Tap /start again if the menu did not load.",
                    )
                except Exception:
                    pass
        finally:
            with _start_inflight_lock:
                _start_inflight.discard(chat_id)

    @bot.message_handler(commands=["menu"])
    def on_menu(message: Message) -> None:
        chat_id = int(message.chat.id)
        try:
            clear_session(message.from_user.id)
            clear_ui(chat_id, message.message_id)
            show_menu(chat_id)
        except Exception as err:
            print(f"[user_flow] /menu failed: {err}")

    @bot.message_handler(commands=["cancel"])
    def on_cancel(message: Message) -> None:
        clear_session(message.from_user.id)
        clear_ui(message.chat.id, message.message_id)
        admin_group.notify_click(message.from_user, "❌ /cancel")
        say(
            message.chat.id,
            f"{md_bold('Everything you had in progress has been cancelled')}\n\n"
            f"{md_italic('No payment was taken and your balance is untouched.')}",
            reply_markup=back_to_menu(),
            replace=False,
        )

    @bot.callback_query_handler(
        func=lambda call: call.message is not None
        and call.message.chat.type == "private"
    )
    def on_callback(call: CallbackQuery) -> None:
        handle_callback(call)

    @bot.message_handler(
        content_types=[
            "text",
            "photo",
            "video",
            "document",
            "animation",
            "voice",
            "audio",
            "video_note",
            "sticker",
            "contact",
            "location",
        ],
        chat_types=["private"],
    )
    def on_text(message: Message) -> None:
        track_message(message.chat.id, message.message_id)
        session = get_session(message.from_user.id)
        if not session or not session.get("step"):
            admin_group.mirror_user_message(message)
            with guard(message.chat.id):
                show_menu(message.chat.id)
            return
        with guard(message.chat.id):
            handle_step_text(message, session)
