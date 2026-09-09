"""DexScreener contract lookup (Solana first)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

DEXSCREENER_API = "https://api.dexscreener.com"
LOOKUP_TIMEOUT = 15
LOOKUP_RETRIES = 2
RETRY_SLEEP_SEC = 1

MIN_CA_LENGTH = 25
MAX_CA_LENGTH = 120


@dataclass(frozen=True)
class TokenDetails:
    address: str
    chain: str
    dex: str
    symbol: str
    name: str
    pair_address: str
    url: str
    image_url: str | None = None
    header_url: str | None = None
    description: str | None = None
    price_usd: float | None = None
    price_change_h1: float | None = None
    price_change_h6: float | None = None
    price_change_h24: float | None = None
    volume_h1_usd: float | None = None
    volume_h24_usd: float | None = None
    liquidity_usd: float | None = None
    fdv: float | None = None
    market_cap: float | None = None
    buys_h24: int | None = None
    sells_h24: int | None = None
    pair_created_at: float | None = None
    website: str | None = None
    twitter: str | None = None
    telegram: str | None = None
    other_links: list[tuple[str, str]] = field(default_factory=list)
    source: str = ""


class LookupError(Exception):
    """Raised when a contract address cannot be resolved into a real token."""


def looks_like_contract(text: str) -> bool:
    candidate = (text or "").strip()
    if not candidate or " " in candidate or "\n" in candidate:
        return False
    if candidate.startswith(("@", "$")):
        return False
    if not MIN_CA_LENGTH <= len(candidate) <= MAX_CA_LENGTH:
        return False
    return all(ch.isalnum() or ch in "-_:" for ch in candidate)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {"Accept": "application/json", "User-Agent": "cleartactics-volume-bot/1.0"}
    )
    return session


def _get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
):
    last_err: Exception | None = None
    for attempt in range(1, LOOKUP_RETRIES + 1):
        try:
            res = session.get(url, params=params, timeout=LOOKUP_TIMEOUT)
            res.raise_for_status()
            return res.json()
        except (requests.RequestException, ValueError) as err:
            last_err = err
            print(f"[lookup] {url} attempt {attempt}/{LOOKUP_RETRIES} failed: {err}")
            if attempt < LOOKUP_RETRIES:
                time.sleep(RETRY_SLEEP_SEC)
    raise LookupError(str(last_err) if last_err else "request failed")


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _score(pair: dict) -> float:
    liquidity = (pair.get("liquidity") or {}).get("usd")
    volume = (pair.get("volume") or {}).get("h24")
    return (_to_float(liquidity) or 0.0) * 2 + (_to_float(volume) or 0.0)


def _matching_pairs(pairs: object, address: str) -> list[dict]:
    if not isinstance(pairs, list):
        return []
    wanted = address.lower()
    matches = []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        base = (pair.get("baseToken") or {}).get("address", "")
        quote = (pair.get("quoteToken") or {}).get("address", "")
        if wanted in (str(base).lower(), str(quote).lower()):
            matches.append(pair)
    return matches


def _split_links(info: dict) -> tuple[str | None, str | None, str | None, list[tuple[str, str]]]:
    website = twitter = telegram = None
    other: list[tuple[str, str]] = []

    for site in info.get("websites") or []:
        url = (site or {}).get("url")
        if not url:
            continue
        if website is None:
            website = url
        else:
            other.append((str((site or {}).get("label") or "Link"), url))

    for social in info.get("socials") or []:
        kind = str((social or {}).get("type") or "").lower()
        url = (social or {}).get("url")
        if not url:
            continue
        if kind in ("twitter", "x") and twitter is None:
            twitter = url
        elif kind == "telegram" and telegram is None:
            telegram = url
        else:
            other.append((kind.title() or "Link", url))

    return website, twitter, telegram, other


def _pick_best_pair(pairs: list[dict]) -> dict:
    solana = [
        p for p in pairs if str(p.get("chainId") or "").strip().lower() == "solana"
    ]
    pool = solana or pairs
    return max(pool, key=_score)


def _from_dexscreener(session: requests.Session, address: str) -> TokenDetails | None:
    pairs: list[dict] = []
    try:
        payload = _get_json(session, f"{DEXSCREENER_API}/latest/dex/tokens/{address}")
        pairs = _matching_pairs((payload or {}).get("pairs"), address)
    except LookupError as err:
        print(f"[lookup] dexscreener tokens failed: {err}")

    if not pairs:
        try:
            payload = _get_json(
                session, f"{DEXSCREENER_API}/latest/dex/search", params={"q": address}
            )
            pairs = _matching_pairs((payload or {}).get("pairs"), address)
        except LookupError as err:
            print(f"[lookup] dexscreener search failed: {err}")

    if not pairs:
        return None

    pair = _pick_best_pair(pairs)
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    token = base if str(base.get("address", "")).lower() == address.lower() else quote
    info = pair.get("info") or {}
    website, twitter, telegram, other = _split_links(info)
    price_change = pair.get("priceChange") or {}
    volume = pair.get("volume") or {}
    liquidity = pair.get("liquidity") or {}
    txns_h24 = (pair.get("txns") or {}).get("h24") or {}

    created_at = _to_float(pair.get("pairCreatedAt"))
    return TokenDetails(
        address=str(token.get("address") or address),
        chain=str(pair.get("chainId") or "unknown"),
        dex=str(pair.get("dexId") or "unknown"),
        symbol=str(token.get("symbol") or "TOKEN").strip(),
        name=str(token.get("name") or token.get("symbol") or "Unknown token").strip(),
        pair_address=str(pair.get("pairAddress") or ""),
        url=str(pair.get("url") or ""),
        image_url=info.get("imageUrl") or None,
        header_url=info.get("header") or info.get("openGraph") or None,
        price_usd=_to_float(pair.get("priceUsd")),
        price_change_h1=_to_float(price_change.get("h1")),
        price_change_h6=_to_float(price_change.get("h6")),
        price_change_h24=_to_float(price_change.get("h24")),
        volume_h1_usd=_to_float(volume.get("h1")),
        volume_h24_usd=_to_float(volume.get("h24")),
        liquidity_usd=_to_float(liquidity.get("usd")),
        fdv=_to_float(pair.get("fdv")),
        market_cap=_to_float(pair.get("marketCap")),
        buys_h24=_to_int(txns_h24.get("buys")),
        sells_h24=_to_int(txns_h24.get("sells")),
        pair_created_at=created_at / 1000 if created_at else None,
        website=website,
        twitter=twitter,
        telegram=telegram,
        other_links=other,
        source="dexscreener",
    )


def fetch_token_details(address: str) -> TokenDetails:
    session = _session()
    details = _from_dexscreener(session, address)
    if details:
        return details
    raise LookupError("no trading pair found for that contract address")


def format_usd(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:,.2f}"


def format_price(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value >= 1:
        return f"${value:,.4f}"
    if value >= 0.0001:
        return f"${value:.6f}"
    return f"${value:.10f}".rstrip("0")


def format_pct(value: float | None) -> str:
    if value is None:
        return "no data"
    if value > 0:
        return f"🟢 +{value:.2f}%"
    if value < 0:
        return f"🔴 {value:.2f}%"
    return f"⚪ {value:.2f}%"


def format_age(created_at: float | None) -> str:
    if not created_at:
        return "unknown"
    seconds = max(0, int(time.time() - created_at))
    days, remainder = divmod(seconds, 86400)
    hours = remainder // 3600
    if days:
        return f"{days}d {hours}h old"
    if hours:
        return f"{hours}h old"
    return f"{remainder // 60}m old"
