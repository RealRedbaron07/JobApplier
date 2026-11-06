"""Deal math for priced finds: all-in cost, profit, and a buy verdict.

A listing a few cents under TCGplayer is not a bargain. These rules follow the
buy rule used for GTA card deals: all-in cost (price + shipping + tax) at or
under 70% of market value is strong, 70-80% is good, above 80% is a pass.
A deal must also clear a minimum dollar profit, so cheap bulk cards with a big
percentage gap but a tiny spread do not crowd out real finds.

Auction prices are current bids that will rise, so auctions get a maximum bid
instead of a verdict on today's bid.
"""

from __future__ import annotations

import os

from cardsnipe.matcher import detect_clean_hints

# eBay.ca collects Ontario HST on the item and shipping. Marketplace is local cash.
EBAY_TAX_PCT = float(os.getenv("SNIPE_EBAY_TAX_PCT", "13") or 13)
STRONG_PCT = 70.0     # all-in at or under this % of value
GOOD_PCT = 80.0       # all-in at or under this % of value
MIN_PROFIT = float(os.getenv("SNIPE_MIN_PROFIT", "5") or 5)  # CAD, value minus all-in
# All-in under this % of value usually means a wrong print, fake, damage, or placeholder price.
TOO_GOOD_PCT = 40.0

# A cracked slab sells as a raw card in about the grade's condition. A PSA 7 has
# visible wear, so it does not fetch a Near Mint raw price.
CRACK_VALUE = ((9.0, 1.0), (8.5, 0.95), (8.0, 0.9), (7.5, 0.85), (7.0, 0.8))
# Seller says "no whitening" / "clean": the grade is likely centering, so raw buyers pay closer to NM.
CLEAN_BONUS = 0.1
# Cracking and reselling raw costs a sale; the crack must leave this much margin.
CRACK_PCT = 90.0
# Upside grades priced up to this far above raw are a regrade watch (PSA 10 resubmission).
REGRADE_WATCH_PCT = 10.0
REGRADE_UPSIDE = {"BGS": 8.5, "CGC": 9.0, "TAG": 9.0, "SGC": 9.0}

_SKIP_HINTS = {"mint", "gem", "crack", "regrade", "re-grade", "resub"}


def tax_pct(source: str) -> float:
    return EBAY_TAX_PCT if source == "ebay" else 0.0


def all_in(total_price: float | None, source: str) -> float | None:
    """Price + shipping + sales tax, in the listing's currency."""
    if total_price is None:
        return None
    return round(total_price * (1 + tax_pct(source) / 100), 2)


def max_buy(value: float, source: str, shipping: float | None = 0, pct: float = GOOD_PCT) -> float:
    """Highest item price (before shipping and tax) that keeps all-in at pct% of value."""
    limit = min(value * pct / 100, value - MIN_PROFIT)
    return max(0.0, round(limit / (1 + tax_pct(source) / 100) - (shipping or 0), 2))


def crack_multiplier(grade: float, title: str = "") -> float:
    base = next((mult for floor, mult in CRACK_VALUE if grade >= floor), CRACK_VALUE[-1][1])
    clean = [hint for hint in detect_clean_hints(title) if hint not in _SKIP_HINTS]
    return min(1.0, base + (CLEAN_BONUS if clean else 0.0))


def assess(*, title: str, source: str, listing_type: str, price: float | None, shipping: float | None,
           total_price: float | None, value: float | None, slab: tuple[str, float] | None = None) -> dict:
    """Verdict for one priced listing.

    tier: "strong" | "good" | None. lane: "single" | "crack" | "regrade" | None.
    profit is the resale value (raw NM, or the cracked-out value for slabs) minus all-in.
    """
    empty = {"tier": None, "lane": None, "all_in": all_in(total_price, source), "profit": None,
             "pct_of_value": None, "resale_value": None, "max_buy": None, "flags": [], "auction": False}
    if not value or value <= 0 or total_price is None or (price is not None and price <= 1):
        return empty
    cost = empty["all_in"]
    auction = listing_type == "auction"
    flags = []
    if slab:
        company, grade = slab
        resale = round(value * crack_multiplier(grade, title), 2)
        lane = None
        if cost <= resale * CRACK_PCT / 100 and resale - cost >= MIN_PROFIT:
            lane = "crack"
        elif (REGRADE_UPSIDE.get(company) is not None and grade >= REGRADE_UPSIDE[company]
              and cost <= value * (1 + REGRADE_WATCH_PCT / 100)):
            lane = "regrade"
        pct = cost / resale * 100
        tier = ("strong" if pct <= STRONG_PCT else "good") if lane == "crack" else None
        if resale < value:
            flags.append(f"cracked {company} {grade:g} valued at {resale / value:.0%} of raw NM")
        limit = max_buy(resale, source, shipping, CRACK_PCT)
    else:
        resale = value
        pct = cost / value * 100
        profit = value - cost
        tier = None
        if profit >= MIN_PROFIT:
            tier = "strong" if pct <= STRONG_PCT else "good" if pct <= GOOD_PCT else None
        lane = "single" if tier else None
        limit = max_buy(value, source, shipping)
    if pct < TOO_GOOD_PCT:
        flags.append("too cheap to trust: confirm print, language, condition and that it is real")
    if auction:
        flags.append("current bid, final price will rise")
    if tax_pct(source):
        flags.append(f"includes {tax_pct(source):g}% HST")
    return {"tier": tier, "lane": lane, "all_in": cost, "profit": round(resale - cost, 2),
            "pct_of_value": round(pct, 1), "resale_value": resale, "max_buy": limit,
            "flags": flags, "auction": auction}


def is_bargain(verdict: dict) -> bool:
    """Counts toward the headline bargain total: a buy-now deal or a crack slab, not an open auction."""
    return bool(verdict.get("tier") or verdict.get("lane") == "crack") and not verdict.get("auction")


def rank_key(verdict: dict):
    """Strong before good, then the biggest dollar profit."""
    order = {"strong": 0, "good": 1}.get(verdict.get("tier"), 2)
    return (verdict.get("auction", False), order, -(verdict.get("profit") or 0))
