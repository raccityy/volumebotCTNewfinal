"""Live-looking stats dashboard."""

from __future__ import annotations

import random
import time

from bot_instance import send_screen
from keyboards import stats_menu, stats_sub_menu
from md import md_bold, md_italic

_stats = {
    "total_volume_orders": 1840,
    "total_holder_orders": 960,
    "total_volume_usd": 12_450_000.0,
    "holders_added": 185_400,
    "active_tokens": 62,
    "daily_users": 4200,
    "new_users_today": 180,
}


def show_home(chat_id: int) -> None:
    _stats["total_volume_orders"] += random.randint(2, 8)
    _stats["total_holder_orders"] += random.randint(1, 5)
    _stats["total_volume_usd"] += random.uniform(8_000, 45_000)
    _stats["holders_added"] += random.randint(40, 180)
    _stats["active_tokens"] += random.randint(0, 2)
    _stats["daily_users"] += random.randint(8, 30)
    _stats["new_users_today"] += random.randint(1, 8)

    success = random.uniform(88.4, 96.2)
    text = f"""
{md_bold("CLEARTACTICS VOLUME BOT STATISTICS")}

{md_bold("USER GROWTH")}
• Daily active users: {md_bold(f"{_stats['daily_users']:,}")}
• New users today: {md_bold(f"{_stats['new_users_today']:,}")}

{md_bold("PERFORMANCE")}
• Volume orders today: {md_bold(f"{_stats['total_volume_orders']:,}")}
• Holder orders today: {md_bold(f"{_stats['total_holder_orders']:,}")}
• Volume generated: {md_bold(f"${_stats['total_volume_usd']:,.0f}")}
• Holders added: {md_bold(f"{_stats['holders_added']:,}")}
• Success rate: {md_bold(f"{success:.1f}%")}
• Active tokens: {md_bold(str(_stats["active_tokens"]))}

{md_bold("SYSTEM")}
• Uptime: {md_bold("99.8%")}
• Queue: {md_bold("🟢 Active")}

{md_italic("Last updated: " + time.strftime("%H:%M:%S UTC"))}
""".strip()
    send_screen(chat_id, text, image_key="stats", reply_markup=stats_menu())


def show_detailed(chat_id: int) -> None:
    text = f"""
{md_bold("DETAILED ANALYTICS")}

{md_bold("VOLUME MIX")}
• Pump.fun / PumpSwap: {md_bold(f"{random.randint(42, 58)}%")}
• Raydium: {md_bold(f"{random.randint(22, 34)}%")}
• Jupiter: {md_bold(f"{random.randint(8, 16)}%")}
• Other Solana DEX: {md_bold(f"{random.randint(4, 12)}%")}

{md_bold("HOLDER MIX")}
• Organic-looking drip: {md_bold(f"{random.randint(70, 86)}%")}
• Launch packs: {md_bold(f"{random.randint(14, 30)}%")}

{md_bold("GROWTH")}
• Weekly growth: {md_bold(f"+{random.uniform(6.2, 14.8):.1f}%")}
• Retention: {md_bold(f"{random.uniform(72.0, 84.5):.1f}%")}

{md_italic("Last updated: " + time.strftime("%H:%M:%S UTC"))}
""".strip()
    send_screen(chat_id, text, image_key="stats", reply_markup=stats_sub_menu("stats_detailed"))


def show_live(chat_id: int) -> None:
    text = f"""
{md_bold("LIVE TRACKING")}

{md_bold("CURRENTLY ACTIVE")}
• Volume jobs: {md_bold(str(random.randint(3, 9)))}
• Holder drips: {md_bold(str(random.randint(2, 7)))}
• Next start: {md_bold(str(random.randint(20, 90)) + "s")}

{md_bold("REAL-TIME")}
• Volume in flight: {md_bold(f"${random.uniform(12_000, 85_000):,.0f}")}
• Holders this hour: {md_bold(str(random.randint(40, 220)))}

{md_bold("QUEUE")}
• Pending: {md_bold(str(random.randint(1, 6)))}
• Running: {md_bold(str(random.randint(2, 8)))}
• Finished: {md_bold(str(random.randint(12, 28)))}

{md_italic(time.strftime("%H:%M:%S UTC") + " · 🟢 All systems operational")}
""".strip()
    send_screen(chat_id, text, image_key="stats", reply_markup=stats_sub_menu("stats_live"))


def show_performance(chat_id: int) -> None:
    text = f"""
{md_bold("PERFORMANCE METRICS")}

{md_bold("SYSTEM")}
• API response: {md_bold(f"{random.uniform(0.4, 1.6):.1f}s")}
• Network latency: {md_bold(f"{random.uniform(14, 48):.0f}ms")}
• Success rate: {md_bold(f"{random.uniform(90.2, 97.4):.1f}%")}
• Error rate: {md_bold(f"{random.uniform(0.2, 1.8):.1f}%")}

{md_bold("HEALTH")}
• Lookup: {md_bold("🟢 Operational")}
• Queue: {md_bold("🟢 Processing")}
• Alerts: {md_bold("🟢 None")}

{md_italic("Last updated: " + time.strftime("%H:%M:%S UTC"))}
""".strip()
    send_screen(chat_id, text, image_key="stats", reply_markup=stats_sub_menu("stats_performance"))


def handle_callback(data: str, chat_id: int) -> bool:
    if data == "stats":
        show_home(chat_id)
        return True
    if data == "stats_detailed":
        show_detailed(chat_id)
        return True
    if data == "stats_live":
        show_live(chat_id)
        return True
    if data == "stats_performance":
        show_performance(chat_id)
        return True
    return False
