"""Watchlist of cards to hunt for, stored as JSON the user can edit by hand."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace

VALID_SOURCES = ("ebay", "facebook")

# Terms that almost always mean "not the real card" or a listing you can't price.
# Matched on whole words, so "pin" does not hit "Pinsir".
DEFAULT_GLOBAL_EXCLUDE = [
    # fakes / novelty / display items
    "proxy", "custom", "custom card", "custom made", "replica", "fake", "reprint", "novelty",
    "fan art", "fan-art", "fan made", "fan-made", "metal", "metal card", "gold foil", "gold plated",
    "gold card", "gold charizard", "gold pokemon", "golden", "24k",
    "black foil", "silver foil", "vinyl", "display card", "display only", "for display",
    "extended art", "extended artwork", "no card", "case only", "frame", "framed",
    # not cards
    "digital", "online code", "code card", "ptcgo", "ptcgl", "tcg pocket", "orica", "sticker",
    "playmat", "sleeve", "sleeves", "binder", "deck box", "blanket", "plush", "poster", "print",
    "keychain", "pin", "figure", "coin only", "mystery pack", "mystery box", "mystery bundle",
    # not for sale
    "wanted", "wtb", "looking for", "iso",
    "homemade", "hand made", "hand-made", "unofficial", "counterfeit", "bootleg", "knockoff",
    "knock-off", "jumbo", "oversized", "card lot", "art print", "postcard", "magnet",
    "phone case", "t-shirt", "hoodie", "for decoration", "decorative", "not authentic",
    "not official", "not real", "unlicensed", "tribute", "inspired by", "recreation",
    "recreated", "1:1", "dupe", "clone", "nft", "acrylic", "standee", "3d printed",
    "laminated", "blank back", "altered", "painted", "colorized", "ai generated", "ai art",
    "fake slab", "replica slab", "lab slab",
]


@dataclass
class Target:
    name: str
    keywords: list[str]
    # Hard ceiling on total price. None = purely market-driven (see use_market).
    max_price: float | None = None
    # For eBay auctions: snipe up to this amount. None = alert only.
    max_bid: float | None = None
    # Market valuation (TCGPlayer / PriceCharting / eBay sold). card_name + set_name + number
    # identify the exact printing; the value per grade is the cheapest figure any source reports.
    use_market: bool = True
    card_name: str = ""
    set_name: str = ""
    number: str = ""
    # A listing is a bargain at >= bargain_pct under value, and "irregular" (too good — fake,
    # damaged, mislabelled, or a genuine mistake) at >= irregular_pct under value.
    bargain_pct: float = 20.0
    irregular_pct: float = 50.0
    # Buy-It-Now / Marketplace listings below this are treated as fakes or junk.
    # Not applied to auctions (a low current bid is normal).
    min_price: float | None = None
    exclude: list[str] = field(default_factory=list)
    graded_only: bool = False
    min_grade: float | None = None
    raw_ok: bool = True
    # Crack-and-regrade lane: also flag graded copies between regrade_min_grade and
    # regrade_max_grade priced at or under regrade_max_price (default: max_price, i.e.
    # "cheaper than a raw NM copy"). TAG cards scored within tag_near_margin of a 10
    # qualify regardless of the grade range (e.g. the TAG 9 @ 945 that became a PSA 10).
    regrade: bool = False
    regrade_min_grade: float = 8.0
    regrade_max_grade: float = 9.5
    regrade_max_price: float | None = None
    sources: list[str] = field(default_factory=lambda: list(VALID_SOURCES))
    enabled: bool = True
    note: str = ""

    @property
    def search_query(self) -> str:
        # "vmax|v max" style alternatives: search with the first spelling.
        return " ".join(k.split("|")[0].strip() for k in self.keywords if k.strip())

    @property
    def market_query(self) -> str:
        """Query for price sources: '<card name> <set name> [number]' when known, else the keywords."""
        if self.card_name:
            return " ".join(p for p in (self.card_name, self.set_name, self.number) if p)
        return self.search_query

    def with_ceiling(self, ceiling: float | None) -> "Target":
        """Copy with max_price filled in (used for search price filters when market-driven)."""
        if ceiling is None or self.max_price is not None:
            return self
        return replace(self, max_price=ceiling)

    def within_budget(self, budget: float | None) -> "Target":
        if budget is None:
            return self
        return replace(self, max_price=min(budget, self.max_price) if self.max_price is not None else budget)

    def uses_source(self, source: str) -> bool:
        return self.enabled and source in self.sources


# TAG grades on a 1000-point scale; 950+ is a TAG 10 (a 945 is "5 points off").
DEFAULT_TAG_TEN_SCORE = 950
DEFAULT_TAG_NEAR_MARGIN = 15


@dataclass
class Watchlist:
    targets: list[Target] = field(default_factory=list)
    global_exclude: list[str] = field(default_factory=lambda: list(DEFAULT_GLOBAL_EXCLUDE))
    tag_ten_score: int = DEFAULT_TAG_TEN_SCORE
    tag_near_margin: int = DEFAULT_TAG_NEAR_MARGIN
    budget: float | None = None

    def enabled_targets(self) -> list[Target]:
        return [t for t in self.targets if t.enabled]

    def scan_targets(self) -> list[Target]:
        return [t.within_budget(self.budget) for t in self.enabled_targets()]

    def to_dict(self) -> dict:
        return {
            "budget": self.budget,
            "global_exclude": self.global_exclude,
            "tag_ten_score": self.tag_ten_score,
            "tag_near_margin": self.tag_near_margin,
            "targets": [asdict(t) for t in self.targets],
        }


EXAMPLE_TARGETS = [
    Target(
        name="Charizard VMAX Rainbow (Champion's Path 074/073)",
        keywords=["charizard", "vmax", "074/073|rainbow"],
        card_name="Charizard VMAX", set_name="Champion's Path", number="074/073",
        exclude=["japanese", "chinese", "spanish", "lot", "bundle", "pack"],
        regrade=True,
        note="Market-driven: alerts at 20%+ under the cheapest TCGPlayer/PriceCharting value for the grade. "
             "regrade=True also flags PSA/CGC/BGS/TAG 8–9.5 copies priced under the raw value.",
    ),
    Target(
        name="Rayquaza V Alt Art (Evolving Skies 194/203)",
        keywords=["rayquaza", "v", "194/203|alt art|alternate art"],
        card_name="Rayquaza V (Alternate Full Art)", set_name="Evolving Skies", number="194/203",
        exclude=["vmax", "japanese", "korean", "lot", "bundle", "pack"],
        regrade=True,
        regrade_min_grade=8.5,
        regrade_max_grade=9.5,
        note="Crack-and-regrade example: a TAG 9 (945) under the raw NM value is a PSA 10 lottery ticket.",
    ),
    Target(
        name="Umbreon VMAX Alt Art (Evolving Skies 215/203)",
        keywords=["umbreon", "vmax", "215/203|alt art|alternate art"],
        card_name="Umbreon VMAX (Alternate Art Secret)", set_name="Evolving Skies", number="215/203",
        exclude=["japanese", "chinese", "lot", "bundle", "pack"],
        note="Alert only (no max_bid). Set max_bid to snipe auctions.",
    ),
    Target(
        name="PSA 10 Base Set Charizard (any)",
        keywords=["charizard", "base set"],
        card_name="Charizard", set_name="Base Set", number="4/102",
        graded_only=True,
        min_grade=10,
        exclude=["celebrations", "30th", "lot", "shadowless", "1st edition"],
        sources=["ebay"],
        note="Graded-only example, valued against the PSA 10 bucket.",
    ),
]


def optional_budget(value, name: str = "budget") -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a positive number") from None
    if isinstance(value, bool) or not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


def target_from_dict(data: dict) -> Target:
    if not isinstance(data, dict):
        raise ValueError("Each target must be an object")
    allowed = {f for f in Target.__dataclass_fields__}
    clean = {k: v for k, v in data.items() if k in allowed}
    if not isinstance(clean.get("name"), str) or not clean["name"].strip():
        raise ValueError("A target name is required")
    clean["name"] = clean["name"].strip()
    for key in ("keywords", "exclude", "sources"):
        if key in clean and (not isinstance(clean[key], list) or any(not isinstance(x, str) for x in clean[key])):
            raise ValueError(f"{key} must be a list of text values")
    for key in ("enabled", "use_market", "graded_only", "raw_ok", "regrade"):
        if key in clean and not isinstance(clean[key], bool):
            raise ValueError(f"{key} must be true or false")
    clean["keywords"] = [str(k) for k in clean.get("keywords", []) if str(k).strip()]
    for key in ("max_price", "max_bid", "regrade_max_price"):
        clean[key] = optional_budget(clean.get(key), key)
    for key in ("bargain_pct", "irregular_pct", "min_price", "min_grade", "regrade_min_grade", "regrade_max_grade"):
        if clean.get(key) in (None, ""):
            clean.pop(key, None)
            continue
        value = clean[key]
        try:
            clean[key] = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number") from None
        if isinstance(value, bool) or not math.isfinite(clean[key]) or clean[key] < 0:
            raise ValueError(f"{key} must be a non-negative finite number")
    for key in ("card_name", "set_name", "number"):
        clean[key] = str(clean.get(key) or "")
    clean["sources"] = clean.get("sources", list(VALID_SOURCES))
    if not clean["sources"] or any(s not in VALID_SOURCES for s in clean["sources"]):
        raise ValueError("Choose eBay, Facebook, or both")
    if not clean["keywords"]:
        raise ValueError(f"Target {clean.get('name', '?')!r} has no keywords")
    target = Target(**clean)
    if target.bargain_pct >= 100 or target.irregular_pct > 100:
        raise ValueError("Discount percentages must be between 0 and 100, with bargain below 100")
    if any(value is not None and value > 10 for value in (target.min_grade, target.regrade_min_grade, target.regrade_max_grade)):
        raise ValueError("Grades must be between 0 and 10")
    if target.regrade_min_grade > target.regrade_max_grade:
        raise ValueError("Regrade minimum cannot exceed maximum")
    if target.max_price is not None and target.min_price is not None and target.min_price > target.max_price:
        raise ValueError("Minimum price cannot exceed the card budget")
    return target


def load_watchlist(path: str, create_example: bool = True) -> Watchlist:
    """Load the watchlist; write an editable example file if none exists."""
    if not os.path.exists(path):
        watchlist = Watchlist(targets=list(EXAMPLE_TARGETS))
        if create_example:
            save_watchlist(path, watchlist)
        return watchlist
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    targets = [target_from_dict(item) for item in data.get("targets", [])]
    saved_exclude = [str(x).lower() for x in data.get("global_exclude", [])]
    # New default fake/junk terms apply even when an older watchlist file is missing them.
    global_exclude = list(dict.fromkeys([*saved_exclude, *DEFAULT_GLOBAL_EXCLUDE])) if saved_exclude else list(DEFAULT_GLOBAL_EXCLUDE)
    return Watchlist(
        targets=targets,
        global_exclude=global_exclude,
        tag_ten_score=int(data.get("tag_ten_score", DEFAULT_TAG_TEN_SCORE)),
        tag_near_margin=int(data.get("tag_near_margin", DEFAULT_TAG_NEAR_MARGIN)),
        budget=optional_budget(data.get("budget")),
    )


def save_watchlist(path: str, watchlist: Watchlist) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            json.dump(watchlist.to_dict(), handle, indent=2, ensure_ascii=False, allow_nan=False)
        # A running watcher must never read a half-written budget or target list.
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def add_target(path: str, target: Target) -> Watchlist:
    target = target_from_dict(asdict(target))
    watchlist = load_watchlist(path)
    watchlist.targets = [t for t in watchlist.targets if t.name.lower() != target.name.lower()]
    watchlist.targets.append(target)
    save_watchlist(path, watchlist)
    return watchlist


def remove_target(path: str, name: str) -> bool:
    watchlist = load_watchlist(path)
    before = len(watchlist.targets)
    watchlist.targets = [t for t in watchlist.targets if t.name.lower() != name.lower()]
    save_watchlist(path, watchlist)
    return len(watchlist.targets) < before
