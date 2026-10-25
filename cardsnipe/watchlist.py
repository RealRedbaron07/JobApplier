"""Watchlist of cards to hunt for, stored as JSON the user can edit by hand."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

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
]


@dataclass
class Target:
    name: str
    keywords: list[str]
    max_price: float
    # For eBay auctions: snipe up to this amount. None = alert only.
    max_bid: float | None = None
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

    def enabled_targets(self) -> list[Target]:
        return [t for t in self.targets if t.enabled]

    def to_dict(self) -> dict:
        return {
            "global_exclude": self.global_exclude,
            "tag_ten_score": self.tag_ten_score,
            "tag_near_margin": self.tag_near_margin,
            "targets": [asdict(t) for t in self.targets],
        }


EXAMPLE_TARGETS = [
    Target(
        name="Charizard VMAX Rainbow (Champion's Path 074/073)",
        keywords=["charizard", "vmax", "074/073|rainbow"],
        max_price=250,
        max_bid=270,
        min_price=90,
        exclude=["japanese", "chinese", "spanish", "lot", "bundle", "pack"],
        regrade=True,
        note="Example caps. Set your own numbers. regrade=True also flags PSA/CGC/BGS/TAG 8–9.5 copies under the cap.",
    ),
    Target(
        name="Rayquaza V Alt Art (Evolving Skies 194/203)",
        keywords=["rayquaza", "v", "194/203|alt art|alternate art"],
        max_price=350,
        max_bid=380,
        min_price=120,
        exclude=["vmax", "japanese", "korean", "lot", "bundle", "pack"],
        regrade=True,
        regrade_min_grade=8.5,
        regrade_max_grade=9.5,
        note="Crack-and-regrade example: a TAG 9 (945) under the raw NM price is a PSA 10 lottery ticket.",
    ),
    Target(
        name="Umbreon VMAX Alt Art (Evolving Skies 215/203)",
        keywords=["umbreon", "vmax", "215/203|alt art|alternate art"],
        max_price=600,
        max_bid=None,
        min_price=250,
        exclude=["japanese", "chinese", "lot", "bundle", "pack"],
        note="Alert only (no max_bid).",
    ),
    Target(
        name="PSA 10 Base Set Charizard (any)",
        keywords=["charizard", "base set"],
        max_price=5000,
        min_price=1500,
        graded_only=True,
        min_grade=10,
        exclude=["celebrations", "30th", "lot"],
        sources=["ebay"],
        note="Graded-only example.",
    ),
]


def _target_from_dict(data: dict) -> Target:
    allowed = {f for f in Target.__dataclass_fields__}
    clean = {k: v for k, v in data.items() if k in allowed}
    clean["keywords"] = [str(k) for k in clean.get("keywords", []) if str(k).strip()]
    clean["max_price"] = float(clean.get("max_price", 0))
    if clean.get("max_bid") is not None:
        clean["max_bid"] = float(clean["max_bid"])
    if clean.get("min_price") is not None:
        clean["min_price"] = float(clean["min_price"])
    if clean.get("regrade_max_price") is not None:
        clean["regrade_max_price"] = float(clean["regrade_max_price"])
    for key in ("regrade_min_grade", "regrade_max_grade"):
        if clean.get(key) is not None:
            clean[key] = float(clean[key])
    if clean.get("min_grade") is not None:
        clean["min_grade"] = float(clean["min_grade"])
    clean["sources"] = [s for s in clean.get("sources", list(VALID_SOURCES)) if s in VALID_SOURCES]
    if not clean["keywords"]:
        raise ValueError(f"Target {clean.get('name', '?')!r} has no keywords")
    return Target(**clean)


def load_watchlist(path: str, create_example: bool = True) -> Watchlist:
    """Load the watchlist; write an editable example file if none exists."""
    if not os.path.exists(path):
        watchlist = Watchlist(targets=list(EXAMPLE_TARGETS))
        if create_example:
            save_watchlist(path, watchlist)
        return watchlist
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    targets = [_target_from_dict(item) for item in data.get("targets", [])]
    global_exclude = [str(x).lower() for x in data.get("global_exclude", DEFAULT_GLOBAL_EXCLUDE)]
    return Watchlist(
        targets=targets,
        global_exclude=global_exclude,
        tag_ten_score=int(data.get("tag_ten_score", DEFAULT_TAG_TEN_SCORE)),
        tag_near_margin=int(data.get("tag_near_margin", DEFAULT_TAG_NEAR_MARGIN)),
    )


def save_watchlist(path: str, watchlist: Watchlist) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(watchlist.to_dict(), handle, indent=2, ensure_ascii=False)


def add_target(path: str, target: Target) -> Watchlist:
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
