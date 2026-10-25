"""Market valuations: TCGPlayer + PriceCharting (+ eBay sold comps when signed in).

A card is valued per grade bucket (raw, 7, 8, 9, 9.5, 10) as the CHEAPEST figure any
source reports for that bucket — the conservative number. Listings are then judged
against that value instead of a hand-typed cap:

  bargain    total <= value * (1 - bargain_pct/100)
  irregular  total <  value * (1 - irregular_pct/100)   (too good: fake, damaged, mislabelled — or a real mistake)

All source prices are USD; valuations are converted to the listing currency with a
cached FX rate.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import quote_plus

import requests

from cardsnipe.matcher import PRICE_BUCKETS as BUCKETS, bucket_for_grade, detect_grade, parse_price
from cardsnipe.settings import SnipeSettings
from cardsnipe.watchlist import Target

logger = logging.getLogger("cardsnipe.pricing")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

SOURCES = ("tcgplayer", "pricecharting", "ebay_sold")


def normalize_number(number: str | None) -> str:
    """'074/073' -> '74/73', '21' -> '21', '#194/203' -> '194/203'."""
    if not number:
        return ""
    parts = re.findall(r"[A-Za-z]*\d+[A-Za-z]*", number)
    cleaned = []
    for part in parts:
        digits = re.sub(r"\D", "", part)
        letters = re.sub(r"\d", "", part).upper()
        cleaned.append(f"{letters}{int(digits)}" if digits else letters)
    return "/".join(cleaned)


@dataclass
class SourcePrice:
    source: str
    bucket: str
    price_usd: float
    detail: str = ""      # e.g. "market" / "median of 7 sold"
    url: str = ""


@dataclass
class Valuation:
    target_name: str
    currency: str
    fx: float                                # USD -> currency
    prices: list[SourcePrice] = field(default_factory=list)
    floor_usd: float | None = None           # cheapest listed anywhere (TCGPlayer lowest) — reference only
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: list[str] = field(default_factory=list)
    card_url: str = ""

    def value_usd(self, bucket: str) -> tuple[float, str] | None:
        """Cheapest source figure for the bucket -> (usd, source)."""
        candidates = [p for p in self.prices if p.bucket == bucket and p.price_usd and p.price_usd > 0]
        if not candidates:
            return None
        best = min(candidates, key=lambda p: p.price_usd)
        return best.price_usd, best.source

    def value(self, bucket: str) -> tuple[float, str] | None:
        """Same as value_usd but converted to the listing currency."""
        found = self.value_usd(bucket)
        if not found:
            return None
        return round(found[0] * self.fx, 2), found[1]

    @property
    def has_data(self) -> bool:
        return any(p.price_usd for p in self.prices)

    def to_dict(self) -> dict:
        return {
            "target_name": self.target_name, "currency": self.currency, "fx": self.fx,
            "floor_usd": self.floor_usd, "fetched_at": self.fetched_at.isoformat(timespec="seconds"),
            "notes": self.notes, "card_url": self.card_url,
            "prices": [p.__dict__ for p in self.prices],
            "values": {
                b: {"value": v[0], "source": v[1], "usd": self.value_usd(b)[0]}
                for b in BUCKETS if (v := self.value(b))
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Valuation":
        fetched = data.get("fetched_at")
        return cls(
            target_name=data["target_name"], currency=data["currency"], fx=float(data["fx"]),
            prices=[SourcePrice(**p) for p in data.get("prices", [])],
            floor_usd=data.get("floor_usd"),
            fetched_at=datetime.fromisoformat(fetched) if fetched else datetime.now(timezone.utc),
            notes=list(data.get("notes", [])), card_url=data.get("card_url", ""),
        )


# ── FX ────────────────────────────────────────────────────────────────────────

_fx_cache: dict[str, tuple[float, float]] = {}


def usd_rate(currency: str, fallback: float, session: requests.Session | None = None) -> float:
    """USD -> currency. Free endpoint, cached 12h in-process, env fallback when offline."""
    currency = currency.upper()
    if currency == "USD":
        return 1.0
    cached = _fx_cache.get(currency)
    if cached and time.time() - cached[1] < 12 * 3600:
        return cached[0]
    try:
        resp = (session or requests).get("https://open.er-api.com/v6/latest/USD", timeout=10)
        rate = float(resp.json()["rates"][currency])
        _fx_cache[currency] = (rate, time.time())
        return rate
    except Exception as exc:
        logger.warning("FX lookup failed (%s); using fallback %.3f", exc, fallback)
        return fallback


# ── TCGPlayer ─────────────────────────────────────────────────────────────────

class TcgPlayer:
    SEARCH_URL = "https://mp-search-api.tcgplayer.com/v1/search/request"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": UA, "Origin": "https://www.tcgplayer.com",
                                     "Referer": "https://www.tcgplayer.com/"})

    def search(self, query: str, size: int = 12) -> list[dict]:
        body = {
            "algorithm": "sales_synonym_v2", "from": 0, "size": size,
            "filters": {"term": {"productLineName": ["pokemon"], "productTypeName": ["Cards"]}, "range": {}, "match": {}},
            "listingSearch": {"context": {"cart": {}}, "filters": {"term": {"sellerStatus": "Live", "channelId": 0},
                                                                   "range": {"quantity": {"gte": 1}},
                                                                   "exclude": {"channelExclusion": 0}}},
            "context": {"cart": {}, "shippingCountry": "US"},
            "settings": {"useFuzzySearch": True, "didYouMean": {}}, "sort": {},
        }
        resp = self.session.post(f"{self.SEARCH_URL}?q={quote_plus(query)}&isList=false", json=body, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results") or []
        return (results[0].get("results") or []) if results else []

    @staticmethod
    def pick(results: list[dict], number: str, name_hint: str = "") -> dict | None:
        want = normalize_number(number)
        hint = (name_hint or "").lower()
        for row in results:
            have = normalize_number((row.get("customAttributes") or {}).get("number"))
            if want and have == want and (not hint or hint.split()[0] in (row.get("productName") or "").lower()):
                return row
        if not want and hint:
            for row in results:
                if hint in (row.get("productName") or "").lower():
                    return row
        return None

    def lookup(self, target: Target) -> list[SourcePrice] | None:
        """Raw market price (and lowest listed as floor) for the card."""
        query = target.market_query
        rows = self.search(query)
        row = self.pick(rows, target.number, target.card_name or target.keywords[0])
        if row is None:
            logger.info("tcgplayer: no match for %r (%s)", query, target.number)
            return None
        url = f"https://www.tcgplayer.com/product/{int(row['productId'])}"
        prices = []
        if row.get("marketPrice"):
            prices.append(SourcePrice("tcgplayer", "raw", float(row["marketPrice"]), "market price", url))
        lowest = row.get("lowestPrice")
        if lowest:
            prices.append(SourcePrice("tcgplayer", "floor", float(lowest), "lowest listed (any condition)", url))
        return prices


# ── PriceCharting ─────────────────────────────────────────────────────────────

class PriceCharting:
    SEARCH_URL = "https://www.pricecharting.com/search-products"
    # td ids -> grade buckets for Pokémon pages (columns: Ungraded, 7, 8, 9, 9.5, PSA 10)
    COLUMNS = {
        "used_price": "raw", "complete_price": "7", "new_price": "8",
        "graded_price": "9", "box_only_price": "9.5", "manual_only_price": "10",
    }

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": UA})

    def fetch(self, query: str) -> tuple[str, str]:
        resp = self.session.get(self.SEARCH_URL, params={"q": query, "type": "prices"}, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        return resp.text, resp.url

    def fetch_url(self, url: str) -> str:
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text

    @staticmethod
    def query_for(target: Target) -> str:
        """PriceCharting likes '<name> <number> <set>' with the bare number: 'umbreon vmax 215 evolving skies'."""
        name = re.sub(r"\(.*?\)", " ", target.card_name or target.search_query)
        name = re.sub(r"\s+", " ", name).strip()
        digits = re.findall(r"\d+", target.number or "")
        number = str(int(digits[0])) if digits else ""
        return " ".join(p for p in (name, number, target.set_name) if p).lower()

    @staticmethod
    def parse_results(html: str) -> list[dict]:
        """Rows of a multi-result search page -> [{title, set, url}]."""
        rows = []
        for m in re.finditer(r'<tr id="product-\d+".*?</tr>', html, re.S):
            row = m.group(0)
            href = re.search(r'<td class="title">\s*<a href="([^"]+)"[^>]*>\s*([^<]+)</a>', row, re.S)
            console = re.search(r'<a href="/console/[^"]+">\s*([^<]+)</a>', row)
            if href:
                rows.append({"url": href.group(1).strip(), "title": unescape(href.group(2)).strip(),
                             "set": unescape(console.group(1)).strip() if console else ""})
        return rows

    @staticmethod
    def choose(rows: list[dict], target: Target) -> dict | None:
        """Pick the result matching name words, number and set; avoid [variant] rows unless asked for."""
        name = re.sub(r"\(.*?\)", " ", target.card_name or target.search_query).lower()
        name_words = [w for w in re.findall(r"[a-z0-9]+", name) if len(w) > 1]
        digits = re.findall(r"\d+", target.number or "")
        number = str(int(digits[0])) if digits else ""
        set_words = [w for w in re.findall(r"[a-z0-9]+", (target.set_name or "").lower()) if w not in {"the", "of", "and"}]
        wants_variant = "[" in (target.card_name or "") or any(w in name for w in ("1st edition", "shadowless"))

        def score(row: dict) -> int:
            title, set_name = row["title"].lower(), row["set"].lower()
            if number and not re.search(rf"#\s*{number}\b", title):
                return -1
            if not all(w in title for w in name_words):
                return -1
            if set_words and not all(w in set_name for w in set_words):
                return -1
            points = 10
            if "[" in title and not wants_variant:
                points -= 5
            for lang in ("japanese", "korean", "chinese", "german", "french", "italian", "spanish", "portuguese"):
                if lang in set_name and lang not in set_words:
                    points -= 6
            if "base set 2" in set_name and "2" not in set_words:
                points -= 6
            return points

        ranked = sorted(((score(r), r) for r in rows), key=lambda x: -x[0])
        return ranked[0][1] if ranked and ranked[0][0] > 0 else None

    @classmethod
    def parse(cls, html: str, url: str = "") -> list[SourcePrice]:
        prices = []
        for td_id, bucket in cls.COLUMNS.items():
            m = re.search(rf'id="{td_id}"[^>]*>\s*<span class="price js-price">\s*([^<]+)', html)
            if not m:
                continue
            value = parse_price(unescape(m.group(1)).strip())
            if value:
                prices.append(SourcePrice("pricecharting", bucket, value, "sold-comps average", url))
        return prices

    @staticmethod
    def product_name(html: str) -> str:
        m = re.search(r'id="product_name"[^>]*>\s*([^<]+)', html)
        return unescape(m.group(1)).strip() if m else ""

    def lookup(self, target: Target) -> list[SourcePrice] | None:
        query = self.query_for(target)
        html, url = self.fetch(query)
        if "search-products" in url:
            # Several candidates: pick the right printing and open its page.
            chosen = self.choose(self.parse_results(html), target)
            if not chosen:
                logger.info("pricecharting: no unambiguous match for %r", query)
                return None
            url = chosen["url"]
            html = self.fetch_url(url)
        elif target.number and not self.slug_matches_number(url, target.number):
            logger.info("pricecharting: landed on %s, number mismatch for %s", url, target.number)
            return None
        return self.parse(html, url)

    @staticmethod
    def slug_matches_number(url: str, number: str) -> bool:
        """Product slugs end with the card number: .../charizard-vmax-74 for 074/073."""
        slug = url.rsplit("/", 1)[-1].split("?")[0]
        slug_numbers = re.findall(r"\d+", slug)
        want = re.findall(r"\d+", number)
        if not slug_numbers or not want:
            return True  # nothing to compare against; trust the search
        return int(slug_numbers[-1]) == int(want[0])


# ── eBay sold comps (needs the signed-in sniper Chrome) ──────────────────────

class EbaySold:
    def __init__(self, browser, domain: str, currency: str, fx: float):
        self.browser = browser
        self.domain = domain
        self.currency = currency
        self.fx = fx  # listing currency per USD; sold prices are converted back to USD

    def lookup(self, target: Target, limit: int = 60) -> list[SourcePrice] | None:
        from cardsnipe.ebay import EbayWeb

        url = (f"https://www.{self.domain}/sch/i.html?_nkw={quote_plus(target.search_query)}"
               f"&LH_Sold=1&LH_Complete=1&_sop=13&_ipg={limit}")
        self.browser.get(url)
        title = (self.browser.js("return document.title") or "").lower()
        if "sign in" in title or "error page" in title:
            raise RuntimeError("eBay sold comps need a signed-in eBay session (run `make login`)")
        rows = self.browser.js(EbayWeb.EXTRACT_JS) or []
        by_bucket: dict[str, list[float]] = {}
        for row in rows:
            lines = [ln.strip() for ln in row["text"].split("\n") if ln.strip()]
            title_line = next((ln for ln in lines if not ln.lower().startswith(("sold", "c $", "us $", "$"))), "")
            price_line = next((ln for ln in lines if re.search(r"(C\s?\$|US\s?\$|\$)\s?\d", ln)), "")
            price = parse_price(price_line)
            if not price or not title_line:
                continue
            haystack = title_line.lower()
            if not all(any(alt.strip() in haystack for alt in k.split("|")) for k in target.keywords):
                continue
            by_bucket.setdefault(bucket_for_grade(detect_grade(title_line)), []).append(price / self.fx)
        prices = []
        for bucket, values in by_bucket.items():
            if len(values) >= 2:
                prices.append(SourcePrice("ebay_sold", bucket, round(statistics.median(values), 2),
                                          f"median of {len(values)} sold", url))
        return prices or None


# ── service ───────────────────────────────────────────────────────────────────

class PriceService:
    """Fetches, caches (in the Store) and converts valuations per target."""

    def __init__(self, settings: SnipeSettings, store, browser=None, session: requests.Session | None = None):
        self.settings = settings
        self.store = store
        self.browser = browser
        self.session = session or requests.Session()
        self.tcg = TcgPlayer(self.session)
        self.pc = PriceCharting(self.session)
        self._memo: dict[str, Valuation] = {}

    @property
    def fx(self) -> float:
        return usd_rate(self.settings.ebay_currency, self.settings.usd_rate_fallback, self.session)

    def valuation(self, target: Target, force: bool = False) -> Valuation | None:
        if not target.use_market:
            return None
        ttl = timedelta(hours=self.settings.price_ttl_hours)
        cached = self._memo.get(target.name)
        if cached is None and not force:
            stored = self.store.load_valuation(target.name)
            if stored:
                cached = Valuation.from_dict(stored)
        if cached and not force and datetime.now(timezone.utc) - cached.fetched_at < ttl:
            self._memo[target.name] = cached
            return cached
        fresh = self.refresh(target)
        if fresh is None and cached:
            return cached
        return fresh

    def refresh(self, target: Target) -> Valuation | None:
        fx = self.fx
        val = Valuation(target_name=target.name, currency=self.settings.ebay_currency, fx=fx)
        for name, fn in (("tcgplayer", self.tcg.lookup), ("pricecharting", self.pc.lookup)):
            try:
                prices = fn(target)
            except Exception as exc:
                val.notes.append(f"{name}: {exc}")
                logger.warning("%s lookup failed for %r: %s", name, target.name, exc)
                continue
            if not prices:
                val.notes.append(f"{name}: no match for {target.market_query!r}")
                continue
            for p in prices:
                if p.bucket == "floor":
                    val.floor_usd = p.price_usd
                    val.card_url = val.card_url or p.url
                else:
                    val.prices.append(p)
                    val.card_url = val.card_url or p.url
        if self.browser is not None and self.settings.ebay_sold_comps:
            try:
                sold = EbaySold(self.browser, self.settings.ebay_domain, self.settings.ebay_currency, fx).lookup(target)
                if sold:
                    val.prices.extend(sold)
            except Exception as exc:
                val.notes.append(f"ebay_sold: {exc}")
        if not val.has_data:
            logger.warning("no market data for %r — falling back to max_price", target.name)
            self._memo.pop(target.name, None)
            return None
        self._memo[target.name] = val
        try:
            self.store.save_valuation(val)
        except Exception as exc:
            logger.warning("could not persist valuation: %s", exc)
        return val


def describe(val: Valuation) -> str:
    """One-line summary for CLI output."""
    parts = []
    for bucket in BUCKETS:
        found = val.value(bucket)
        if found:
            label = "raw" if bucket == "raw" else f"g{bucket}"
            parts.append(f"{label} {val.currency} {found[0]:.0f} ({found[1][:3]})")
    floor = f" · floor US${val.floor_usd:.0f}" if val.floor_usd else ""
    return " | ".join(parts) + floor
