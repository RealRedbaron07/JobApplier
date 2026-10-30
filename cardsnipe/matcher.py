"""Listing model plus the rules that decide whether a listing is a deal."""

from __future__ import annotations

import re
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from cardsnipe.watchlist import Target

GRADE_RE = re.compile(r"\b(psa|cgc|bgs|sgc|ace|tag|ags)\s*-?\s*(?:(?:pristine|perfect|gem\s+mint|mint|graded|grade)\s+)?"
                      r"(10|9\.5|9|8\.5|8|7|6|5|4|3|2|1)\b", re.I)
# TAG's 1000-point score, written near the word TAG: "TAG 9 (945)", "TAG 945/1000", "945 TAG 9".
TAG_SCORE_AFTER_RE = re.compile(
    r"\btag\b[^0-9]{0,15}(?:(?:10|9\.5|9|8\.5|8|7)\b[^0-9]{0,12})?(\d{3,4})\b(?!\s*/\s*(?!1000)\d)", re.I
)
TAG_SCORE_BEFORE_RE = re.compile(r"\b(\d{3,4})\b(?:\s*/\s*1000)?\s*(?:dig|points?|pts)?[^a-z0-9]{0,6}tag\b", re.I)
# Seller language that suggests an under-graded or crack-worthy copy.
CLEAN_HINTS = [
    "clean", "pack fresh", "looks like a 10", "should be a 10", "undergraded", "under graded",
    "crack", "regrade", "re-grade", "resub", "no whitening", "no scratches", "perfect centering",
    "well centered", "gem", "pristine", "mint",
]
PRICE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?")
DURATION_UNIT_RE = re.compile(r"(\d+)\s*([dhms])\b")
DURATION_SECONDS = {"d": 86400, "h": 3600, "m": 60, "s": 1}


@dataclass
class Listing:
    source: str                # "ebay" | "facebook"
    listing_id: str
    title: str
    price: float | None
    currency: str
    url: str
    listing_type: str = "bin"  # "bin" (buy now / marketplace) | "auction"
    shipping: float | None = None
    end_time: datetime | None = None
    location: str = ""
    condition: str = ""
    image_url: str = ""
    bid_count: int | None = None
    raw: dict = field(default_factory=dict)

    @property
    def total_price(self) -> float | None:
        if (self.price is None or not math.isfinite(self.price) or self.price < 0
                or (self.source == "ebay" and self.shipping is None)
                or (self.shipping is not None and (not math.isfinite(self.shipping) or self.shipping < 0))):
            return None
        return round(self.price + (self.shipping or 0.0), 2)

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.listing_id)


@dataclass
class Match:
    target: Target
    listing: Listing
    total_price: float
    savings_pct: float
    grade: tuple[str, float] | None
    lane: str = "deal"              # "deal" (meets the target as written) | "regrade" (crack-and-regrade lane)
    regrade_candidate: bool = False
    tag_score: int | None = None
    tag_gap: int | None = None      # points short of a TAG 10
    clean_hints: list[str] = field(default_factory=list)
    cap: float = 0.0
    # Market context (None when the target is cap-only)
    market_value: float | None = None   # value for this listing's grade bucket, listing currency
    value_source: str = ""              # which source gave the cheapest figure
    value_bucket: str = ""              # raw / 7 / 8 / 9 / 9.5 / 10
    irregular: bool = False             # suspiciously far under value / condition issue — verify before buying
    irregular_reason: str = ""          # "54% under value" | "condition: damaged"

    @property
    def under_value_pct(self) -> float | None:
        if not self.market_value:
            return None
        return (self.market_value - self.total_price) / self.market_value * 100.0

    @property
    def headline(self) -> str:
        grade = f" [{self.grade[0]} {self.grade[1]:g}]" if self.grade else ""
        kind = "AUCTION" if self.listing.listing_type == "auction" else "BUY NOW"
        lane = " ♻️ REGRADE" if self.lane == "regrade" else (" ♻️" if self.regrade_candidate else "")
        flag = f" ⚠️ IRREGULAR ({self.irregular_reason})" if self.irregular else ""
        extras = []
        if self.tag_score is not None:
            extras.append(f"TAG {self.tag_score}" + (f" ({self.tag_gap} off 10)" if self.tag_gap else ""))
        if self.clean_hints:
            extras.append("hints: " + ", ".join(self.clean_hints[:3]))
        extra = f" · {' · '.join(extras)}" if extras else ""
        if self.market_value:
            basis = (f"{self.under_value_pct:.0f}% under {self.value_bucket} value "
                     f"{self.listing.currency} {self.market_value:.0f} via {self.value_source}")
        else:
            basis = f"{self.savings_pct:.0f}% under cap {self.cap:g}"
        return (
            f"{self.listing.source.upper()} {kind}{lane}{flag}{grade}: {self.listing.title[:70]} — "
            f"{self.listing.currency} {self.total_price:.2f} ({basis}){extra}"
        )


def normalize(text: str) -> str:
    text = (text or "").lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9/#'.\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_price(text: str) -> float | None:
    """Parse "C $45.00", "$1,234.56", "US $12 to US $20" (takes the first), "Free"."""
    if not text:
        return None
    lowered = text.lower()
    if "free" in lowered and not any(ch.isdigit() for ch in lowered):
        return 0.0
    match = PRICE_RE.search(text)
    if not match:
        return None
    whole = match.group(1).replace(",", "")
    cents = match.group(2) or "0"
    try:
        return float(f"{whole}.{cents}")
    except ValueError:
        return None


def parse_time_left(text: str, now: datetime | None = None) -> datetime | None:
    """Convert "1d 4h left", "Time left 2h 8m", "Ends in 23m 10s" into an absolute UTC datetime.

    Only feed this a countdown fragment; any "<n>d/h/m/s" tokens are summed.
    """
    if not text:
        return None
    units = DURATION_UNIT_RE.findall(text.lower())
    if not units:
        return None
    total = sum(int(amount) * DURATION_SECONDS[unit] for amount, unit in units)
    now = now or datetime.now(timezone.utc)
    return now + timedelta(seconds=total)


def extract_time_left_line(lines: list[str]) -> str:
    """Find the countdown fragment in a listing card's text lines.

    Handles "2h 8m left" on one line and eBay's newer "Time left" / "2h 8m" pair.
    """
    for index, line in enumerate(lines):
        lowered = line.lower()
        if lowered.startswith("time left") or lowered.startswith("ends in"):
            remainder = line.split(maxsplit=2)[2] if len(line.split()) > 2 else ""
            if DURATION_UNIT_RE.search(remainder.lower()):
                return remainder
            if index + 1 < len(lines) and DURATION_UNIT_RE.search(lines[index + 1].lower()):
                return lines[index + 1]
        elif "left" in lowered and DURATION_UNIT_RE.search(lowered):
            return line
    return ""


# "NOT PSA", "PSA 10 potential", "ungraded", "raw" ... the card is not actually slabbed.
UNGRADED_RE = re.compile(
    r"\b(not|no|non|un)\s*-?\s*(psa|cgc|bgs|sgc|tag|ace|ags|graded|slabbed)\b"
    r"|\b(ungraded|unslabbed|raw card|raw)\b"
    r"|\b(psa|cgc|bgs|tag)\s*-?\s*(10|9\.5|9)?\s*(potential|candidate|ready|worthy|material|possible|quality|contender)\b"
    r"|\b(would|could|should|might)\s+(be\s+a\s+|grade\s+(a\s+)?)?(psa|cgc|bgs)?\s*(10|9\.5|9)\b"
    r"|\bgrade\s+it\b|\bpre-?grad(e|ed|ing)\b",
    re.I,
)
# Seller condition language that rules out NM pricing.
DAMAGE_RE = re.compile(
    r"\b(damaged?|heavily played|heavy play|hp\b|moderately played|mp\b|lightly played|lp\b|played|poor|"
    r"crease[sd]?|creasing|bent|bend|dent(ed)?|tear|torn|water damage|scratch(ed|es)?|whitening|chipped|"
    r"peel(ing|ed)?|ink|stain(ed)?|dinged|edge wear|wear|flaw(s|ed)?|dmg)\b",
    re.I,
)
# Hit points follow a number ("330 HP", "215/203 HP"). A condition phrase does not: "HP condition", "HP/MP".
HIT_POINTS_RE = re.compile(r"(?<![/\d])\b\d{2,4}\s+hp\b(?!\s*(?:/|condition\b|mp\b|lp\b))", re.I)
ACE_GRADE_RE = re.compile(r"\bace\s*-?\s*(?:grading|graded|slab)?\s*-?\s*(10|9\.5|9|8\.5|8|7|6|5|4|3|2|1)\b", re.I)
NO_DAMAGE_RE = re.compile(r"\b(no|zero|without|free of|minimal|little)\s+(?:\w+\s+){0,2}?(damage|whitening|scratch(es)?|wear|flaws?|crease[s]?)\b", re.I)


def detect_grade(title: str) -> tuple[str, float] | None:
    """Grade from a slab mention; None when the title says the card is raw / 'PSA 10 potential'."""
    text = title or ""
    match = GRADE_RE.search(text)
    if not match:
        return None
    text = re.sub(r"\b(?:not|no|non|un)\s*-?\s*(psa|cgc|bgs|sgc|ace|tag|ags)\b",
                  lambda m: m.group(0) if m.group(1).lower() == match.group(1).lower() else "", text, flags=re.I)
    if UNGRADED_RE.search(text):
        return None
    return match.group(1).upper(), float(match.group(2))


def detect_condition_issue(title: str) -> str | None:
    """Return the damage/condition word the seller used ("damaged", "creased", "hp"), else None."""
    text = title or ""
    if NO_DAMAGE_RE.search(text):
        text = NO_DAMAGE_RE.sub(" ", text)
    text = HIT_POINTS_RE.sub(" ", text)
    match = DAMAGE_RE.search(text)
    if not match:
        return None
    word = match.group(0).lower()
    # "wear" alone is weak ("edge wear" / "no wear" handled above); require it with a qualifier.
    if word == "wear" and not re.search(r"\b(edge|corner|surface|heavy|visible)\s+wear\b", text, re.I):
        return None
    return word


def detect_tag_score(title: str) -> int | None:
    """Return the TAG 1000-point score if the seller put it in the title."""
    text = title or ""
    for pattern in (TAG_SCORE_AFTER_RE, TAG_SCORE_BEFORE_RE):
        for match in pattern.finditer(text):
            score = int(match.group(1))
            if 500 <= score <= 1000:
                return score
    return None


def detect_clean_hints(title: str) -> list[str]:
    haystack = normalize(title)
    return [hint for hint in CLEAN_HINTS if _term_present(hint, haystack, whole_word=True)]


def _term_present(term: str, haystack: str, whole_word: bool) -> bool:
    term = normalize(term)
    if not term:
        return False
    pattern = r"\b" + re.escape(term) + (r"\b" if whole_word else "")
    return re.search(pattern, haystack) is not None


def _keyword_present(keyword: str, haystack: str) -> bool:
    # "074/073|rainbow" means any one alternative satisfies the keyword.
    # Prefix match so "charizard" also hits "charizards".
    return any(_term_present(alt, haystack, whole_word=False) for alt in keyword.split("|") if alt.strip())


def normalize_number(number: str | None) -> str:
    parts = re.findall(r"[A-Za-z]*\d+[A-Za-z]*", number or "")
    return "/".join(re.sub(r"\d", "", part).upper() + str(int(re.sub(r"\D", "", part))) for part in parts)


def same_number(have: str, want: str) -> bool:
    if not have or not want:
        return False
    return have == want or ("/" not in have or "/" not in want) and have.split("/")[0] == want.split("/")[0]


def identity_matches(title: str, target: Target) -> bool:
    """Require the requested card number and reject other languages and same-number printings."""
    text = normalize(title)
    wanted = normalize(target.market_query)
    if target.number:
        number_text = GRADE_RE.sub(" ", text)
        numbers = [normalize_number(n) for n in re.findall(
            r"\b[a-z]*\d+[a-z]*(?:\s*/\s*[a-z]*\d+[a-z]*)?\b", number_text)]
        want = normalize_number(target.number)
        full_numbers = [n for n in numbers if "/" in n]
        if full_numbers and "/" in want:
            numbers = full_numbers
        if not any(same_number(n, want) for n in numbers):
            return False
    name = re.sub(r"\([^)]*\)|\[[^]]*\]", " ", target.card_name)
    if any(not _term_present(w, text, whole_word=True) for w in normalize(name).split()):
        return False
    for variants in (
        "japanese|japan|jpn|jp", "korean|korea|kor|kr", "chinese|china|chn", "german|deutsch",
        "french|francais", "italian|italiano", "spanish|espanol", "portuguese", "thai", "indonesian",
        "1st edition|first edition", "shadowless", "reverse holo|reverse holographic|reverse holofoil|reverse foil", "cosmos holo",
        "master ball|masterball", "poke ball|pokeball", "base set 2", "legendary collection",
        "jumbo|oversized", "black dot error", "corocoro",
    ):
        found = any(_term_present(v, text, whole_word=True) for v in variants.split("|"))
        asked = any(_term_present(v, wanted, whole_word=True) for v in variants.split("|"))
        if found != asked:
            return False
    return True


PRICE_BUCKETS = ("raw", "7", "8", "9", "9.5", "10")


def bucket_for_grade(grade: tuple[str, float] | None) -> str:
    """Numeric bucket for a grade. Raw -> 'raw'; 8.5 -> '8'; 9.5 -> '9.5'."""
    if grade is None:
        return "raw"
    value = grade[1]
    if value >= 10:
        return "10"
    if value >= 9.5:
        return "9.5"
    if value >= 9:
        return "9"
    if value >= 8:
        return "8"
    return "7"


def trusted_value_bucket(grade: tuple[str, float] | None) -> str | None:
    """Which stored price this slab may be judged against.

    PriceCharting's 7/8/9/10 columns are PSA sales, and the 10 column is labeled PSA 10.
    A CGC, ACE, AGS or TAG 10 is not a PSA 10. BGS/CGC 9.5 is the one non-PSA grade that
    matches a column (PriceCharting's 9.5). Anything else has no trusted value.
    """
    if grade is None:
        return "raw"
    company = grade[0].upper()
    bucket = bucket_for_grade(grade)
    if company == "PSA":
        return bucket if grade[1] in {7, 8, 9, 10} else None
    if company in {"BGS", "CGC"} and bucket == "9.5":
        return "9.5"
    return None


def _primary_grade_ok(target: Target, grade: tuple[str, float] | None) -> bool:
    if target.graded_only and grade is None:
        return False
    if grade is None and not target.raw_ok:
        return False
    if grade is not None and target.min_grade is not None and grade[1] < target.min_grade:
        return False
    return True


def evaluate(
    listing: Listing,
    target: Target,
    global_exclude: list[str] | None = None,
    tag_ten_score: int = 950,
    tag_near_margin: int = 15,
    valuation=None,
    allow_unverified_condition: bool = False,
) -> Match | None:
    """Return a Match when the listing satisfies the target, else None.

    Two lanes: "deal" (the target as written) and, when target.regrade is on,
    "regrade" (a lower-graded or TAG near-miss copy priced under the raw value/cap).

    With a `valuation` (cardsnipe.pricing.Valuation) the cap for a listing is
    value(grade bucket) * (1 - bargain_pct/100), further limited by target.max_price when
    set. Listings more than irregular_pct under value are still returned but flagged
    `irregular` so you verify them before buying. Without market data the plain
    max_price cap applies (and targets with neither are skipped).
    """
    if not target.uses_source(listing.source):
        return None
    # Auctions are listed, never bid. A low current bid is not a deal.
    if listing.listing_type == "auction":
        return None
    if listing.end_time and listing.end_time <= datetime.now(timezone.utc):
        return None
    haystack = normalize(listing.title)
    if not haystack:
        return None
    if not all(_keyword_present(k, haystack) for k in target.keywords):
        return None
    if (target.card_name or target.number) and not identity_matches(listing.title, target):
        return None
    if valuation and (listing.currency or "").upper() != valuation.currency.upper():
        return None
    for banned in list(target.exclude) + list(global_exclude or []):
        if _term_present(banned, haystack, whole_word=True):
            return None

    total = listing.total_price
    if total is None:
        return None
    if target.max_price is not None and listing.source == "ebay" and listing.shipping is None:
        return None
    if target.max_price is not None and total > target.max_price:
        return None
    if listing.listing_type != "auction" and target.min_price is not None and total < target.min_price:
        return None
    # A Buy-It-Now under the cheapest real copy on TCGPlayer is a fake or a wrong card.
    # Auctions are left alone: a low current bid is normal and we do not bid on them here.
    if (listing.listing_type != "auction" and valuation is not None and valuation.floor_usd
            and total < valuation.floor_usd * valuation.fx * 0.9):
        return None

    # ACE slabs are never a deal, a regrade, or a match. "Ace Spec" is a card type and stays.
    if ACE_GRADE_RE.search(listing.title or ""):
        return None

    grade = detect_grade(listing.title)
    tag_score = detect_tag_score(listing.title)
    tag_gap = tag_ten_score - tag_score if tag_score is not None and tag_score < tag_ten_score else None
    tag_near = tag_gap is not None and tag_gap <= tag_near_margin
    clean_hints = detect_clean_hints(listing.title)
    condition_issue = detect_condition_issue(f"{listing.title} {listing.condition}") if grade is None else None
    condition_verified = bool(re.search(r"\b(?:near[ -]mint|nm(?:/m)?|mint)\b", listing.condition, re.I))
    if re.search(r"\b(?:not|no|non)\s+(?:near[ -]mint|mint|nm)\b", listing.condition, re.I):
        condition_verified = False
    if (valuation is not None and grade is None and not condition_verified
            and not allow_unverified_condition):
        return None
    if listing.condition == "unverified" and not allow_unverified_condition:
        return None

    regrade_candidate = False
    if target.regrade and (grade is not None or tag_near):
        graded_below_ten = grade is None or grade[1] < 10
        in_range = grade is not None and target.regrade_min_grade <= grade[1] <= target.regrade_max_grade
        regrade_candidate = graded_below_ten and (in_range or tag_near)

    # Market values (listing currency) for this listing's grade and for a raw copy.
    # Played/damaged raw copies are not Near Mint, so the NM figure is not their value.
    bucket = trusted_value_bucket(grade)
    graded_value = valuation.value(bucket) if valuation and bucket and not condition_issue else None
    raw_value = valuation.value("raw") if valuation else None

    def _build(lane: str, cap: float, value: tuple[float, str] | None, value_bucket: str) -> Match:
        reason = ""
        if condition_issue:
            reason = f"condition: {condition_issue}"
        elif value and total < value[0] * (1 - target.irregular_pct / 100.0):
            # A BIN this far under a trusted value is a fake, a wrong card, or a damaged copy.
            return None
        return Match(
            target=target, listing=listing, total_price=total,
            savings_pct=(cap - total) / cap * 100.0 if cap else 0.0, grade=grade, lane=lane,
            regrade_candidate=regrade_candidate, tag_score=tag_score, tag_gap=tag_gap,
            clean_hints=clean_hints, cap=cap,
            market_value=value[0] if value else None, value_source=value[1] if value else "",
            value_bucket=value_bucket if value else "", irregular=bool(reason), irregular_reason=reason,
        )

    # Lane 1: the target as written.
    if _primary_grade_ok(target, grade):
        if graded_value:
            cap = graded_value[0] * (1 - target.bargain_pct / 100.0)
            if target.max_price:
                cap = min(cap, target.max_price)
            if total <= cap:
                return _build("deal", cap, graded_value, bucket)
        elif valuation is None and target.max_price and total <= target.max_price:
            return _build("deal", target.max_price, None, "")

    # Lane 2: crack-and-regrade — a graded 8–9.5 (or TAG near-miss) priced under a raw NM copy.
    if regrade_candidate:
        if target.regrade_max_price:
            cap = target.regrade_max_price
        elif raw_value:
            cap = raw_value[0]
        else:
            cap = target.max_price
        if cap and total <= cap:
            return _build("regrade", cap, raw_value, "raw")
    return None


def best_match(listing: Listing, targets: list[Target], global_exclude: list[str] | None = None, **kwargs) -> Match | None:
    matches = [m for m in (evaluate(listing, t, global_exclude, **kwargs) for t in targets) if m]
    if not matches:
        return None
    return max(matches, key=lambda m: m.savings_pct)
