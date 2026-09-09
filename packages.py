"""Volume Boost, Holders Boost, and Sponsored Ads packages. Prices are in SOL."""

from __future__ import annotations

from dataclasses import dataclass

KIND_VOLUME = "volume"
KIND_HOLDERS = "holders"
KIND_AD = "ad"

KIND_LABEL = {
    KIND_VOLUME: "Volume Boost",
    KIND_HOLDERS: "Holders Boost",
    KIND_AD: "Sponsored Ads",
}


def _short_usd(amount: float) -> str:
    if amount >= 1_000_000:
        val = amount / 1_000_000
        if val == int(val):
            return f"${int(val)}M"
        return f"${val:g}M"
    if amount >= 1_000:
        val = amount / 1_000
        if val == int(val):
            return f"${int(val)}k"
        return f"${val:g}k"
    return f"${amount:g}"


def _sol_label(price: float) -> str:
    if abs(price - 10.5) < 1e-9:
        return "10.5"
    return f"{price:.2f}"


@dataclass(frozen=True)
class Package:
    id: str
    kind: str
    label: str
    price: float
    hours: float
    volume_usd: float | None = None
    holders: int | None = None

    @property
    def seconds(self) -> int:
        return int(self.hours * 3600)

    @property
    def price_label(self) -> str:
        return _sol_label(self.price)

    @property
    def short_duration(self) -> str:
        if self.hours > 24 and self.hours % 24 == 0:
            return f"{int(self.hours // 24)}d"
        return f"{self.hours:g}h"

    @property
    def duration_label(self) -> str:
        if self.hours > 24 and self.hours % 24 == 0:
            return f"{int(self.hours // 24)} days"
        return f"{self.hours:g} hours"

    @property
    def button_label(self) -> str:
        if self.volume_usd:
            return f"{_short_usd(self.volume_usd)} {_sol_label(self.price)} SOL"
        if self.holders:
            return f"+{self.holders:,} · {_sol_label(self.price)} SOL"
        return f"{self.short_duration} · {_sol_label(self.price)} SOL"


PACKAGES: dict[str, Package] = {}


def _add(pkg: Package) -> None:
    PACKAGES[pkg.id] = pkg


_add(Package("vol_200k", KIND_VOLUME, "$200k volume · 3 hours", 2.00, 3, volume_usd=200_000))
_add(Package("vol_500k", KIND_VOLUME, "$500k volume · 6 hours", 2.50, 6, volume_usd=500_000))
_add(Package("vol_800k", KIND_VOLUME, "$800k volume · 12 hours", 3.50, 12, volume_usd=800_000))
_add(Package("vol_1050k", KIND_VOLUME, "$1050k volume · 24 hours", 5.00, 24, volume_usd=1050_000))
_add(Package("vol_1m", KIND_VOLUME, "$1.3M volume · 48 hours", 7.50, 48, volume_usd=1_300_000))
_add(Package("vol_2_5m", KIND_VOLUME, "$2.5M volume · 72 hours", 10.50, 72, volume_usd=2_500_000))

_add(Package("hold_100", KIND_HOLDERS, "+100 holders · 6 hours", 0.50, 6, holders=100))
_add(Package("hold_500", KIND_HOLDERS, "+500 holders · 12 hours", 1.00, 12, holders=500))
_add(Package("hold_1k", KIND_HOLDERS, "+1,000 holders · 24 hours", 1.50, 24, holders=1_000))
_add(Package("hold_2500", KIND_HOLDERS, "+2,500 holders · 24 hours", 2.50, 24, holders=2_500))
_add(Package("hold_5k", KIND_HOLDERS, "+5,000 holders · 48 hours", 4.00, 48, holders=5_000))
_add(Package("hold_10k", KIND_HOLDERS, "+10,000 holders · 72 hours", 6.00, 72, holders=10_000))

_add(Package("ad_6h", KIND_AD, "Button ad · 6 hours", 0.80, 6))
_add(Package("ad_12h", KIND_AD, "Button ad · 12 hours", 1.40, 12))
_add(Package("ad_24h", KIND_AD, "Button ad · 24 hours", 2.20, 24))
_add(Package("ad_72h", KIND_AD, "Button ad · 3 days", 5.00, 72))
_add(Package("ad_7d", KIND_AD, "Button ad · 7 days", 9.00, 168))


def packages_for(kind: str) -> list[Package]:
    return [p for p in PACKAGES.values() if p.kind == kind]


def get_package(package_id: str) -> Package | None:
    return PACKAGES.get(package_id)
