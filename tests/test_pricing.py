"""Market valuation: source parsers, cheapest-of-sources logic, value-aware matching, Collectr import."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from cardsnipe.collectr import item_bucket, market_target, parse_showcase_import, parse_showcase_text, revalue_collection, value_items
from cardsnipe.matcher import Listing, bucket_for_grade, evaluate
from cardsnipe.pricing import EbaySold, PriceCharting, PriceService, SourcePrice, TcgPlayer, Valuation, normalize_number, variant_words
from cardsnipe.runner import SnipeRunner
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import Store
from cardsnipe.watchlist import Target, Watchlist, load_watchlist, save_watchlist

ZARD = Target(name="Zard", keywords=["charizard", "vmax"], card_name="Charizard VMAX", set_name="Champion's Path",
              number="074/073", regrade=True)


def _val(**buckets) -> Valuation:
    """Valuation with one trusted price per bucket, fx=1 so numbers read directly."""
    return Valuation(target_name="Zard", currency="CAD", fx=1.0, prices=[
        SourcePrice("tcgplayer" if b == "raw" else "pricecharting", b, v) for b, v in buckets.items()
    ])


def _listing(**overrides) -> Listing:
    values = dict(source="ebay", listing_id="1", title="Charizard VMAX 074/073 Champions Path", price=100.0,
                  currency="CAD", url="https://www.ebay.ca/itm/1", listing_type="bin", shipping=0.0, condition="Near Mint")
    values.update(overrides)
    return Listing(**values)


# ── helpers ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [("074/073", "74/73"), ("74/73", "74/73"), ("#194/203", "194/203"),
                                          ("21", "21"), ("SWSH001", "SWSH1"), ("", "")])
def test_normalize_number(raw, expected):
    assert normalize_number(raw) == expected


@pytest.mark.parametrize("grade,bucket", [(None, "raw"), (("PSA", 10), "10"), (("CGC", 9.5), "9.5"), (("PSA", 9), "9"),
                                          (("BGS", 8.5), "8"), (("PSA", 7), "7"), (("PSA", 5), "7")])
def test_bucket_for_grade(grade, bucket):
    assert bucket_for_grade(grade) == bucket


def test_valuation_takes_cheapest_trusted_source_per_bucket_and_converts():
    val = Valuation(target_name="x", currency="CAD", fx=1.4, prices=[
        SourcePrice("tcgplayer", "raw", 200.0), SourcePrice("pricecharting", "raw_any", 150.0),
        SourcePrice("ebay_sold", "raw_any", 90.0),
        SourcePrice("pricecharting", "10", 300.0), SourcePrice("ebay_sold", "10", 280.0),
        SourcePrice("collectr", "10", 50.0), SourcePrice("ebay_sold", "10", 0.0),
    ])
    assert val.value_usd("raw") == (200.0, "tcgplayer")          # mixed-condition raw is ignored
    assert val.value("raw") == (280.0, "tcgplayer")
    assert val.value("10") == (392.0, "ebay_sold")               # cheapest graded source; Collectr excluded
    assert val.value("9") is None
    roundtrip = Valuation.from_dict(val.to_dict())
    assert roundtrip.value("raw") == val.value("raw") and roundtrip.to_dict()["values"]["10"]["usd"] == 280.0


# ── source parsers ────────────────────────────────────────────────────────────

PC_HTML = """
<h1 id="product_name" class="chart_title">Charizard VMAX #74</h1>
<table id="price_data"><tbody><tr>
<td id="used_price"><span class="price js-price">$157.50</span></td>
<td id="complete_price"><span class="price js-price">$142.38</span></td>
<td id="new_price"><span class="price js-price">$143.50</span></td>
<td id="graded_price"><span class="price js-price">$168.24</span></td>
<td id="box_only_price" class="tablet-portrait-hidden"><span class="price js-price">$172.51</span></td>
<td id="manual_only_price" class="tablet-portrait-hidden"><span class="price js-price">$290.00</span></td>
</tr></tbody></table>
"""


def test_pricecharting_parse_maps_columns_to_grade_buckets():
    prices = {p.bucket: p.price_usd for p in PriceCharting.parse(PC_HTML, "u")}
    assert prices == {"raw_any": 157.5, "7": 142.38, "8": 143.5, "9": 168.24, "9.5": 172.51, "10": 290.0}
    assert PriceCharting.product_name(PC_HTML) == "Charizard VMAX #74"


def test_pricecharting_query_and_slug_check():
    assert PriceCharting.query_for(ZARD) == "charizard vmax 74 champion's path"
    rayq = Target(name="r", keywords=["rayquaza"], card_name="Rayquaza V (Alternate Full Art)", set_name="Evolving Skies", number="194/203")
    assert PriceCharting.query_for(rayq) == "rayquaza v 194 evolving skies"
    assert PriceCharting.slug_matches_number("https://www.pricecharting.com/game/pokemon-champion%27s-path/charizard-vmax-74?q=x", "074/073")
    assert not PriceCharting.slug_matches_number("https://www.pricecharting.com/game/x/charizard-v-79", "074/073")


PC_RESULTS = """
<tr id="product-1"><td class="title"><a href="https://pc/game/pokemon-base-set/charizard-1st-edition-4" title="1">Charizard [1st Edition] #4</a>
<div class="console-in-title"><a href="/console/pokemon-base-set">Pokemon Base Set</a></div></td></tr>
<tr id="product-2"><td class="title"><a href="https://pc/game/pokemon-base-set/charizard-4" title="2">Charizard #4</a>
<div class="console-in-title"><a href="/console/pokemon-base-set">Pokemon Base Set</a></div></td></tr>
<tr id="product-3"><td class="title"><a href="https://pc/game/pokemon-base-set-2/charizard-4" title="3">Charizard #4</a>
<div class="console-in-title"><a href="/console/pokemon-base-set-2">Pokemon Base Set 2</a></div></td></tr>
<tr id="product-4"><td class="title"><a href="https://pc/game/pokemon-japanese-base-set/charizard-4" title="4">Charizard #4</a>
<div class="console-in-title"><a href="/console/pokemon-japanese-base-set">Pokemon Japanese Base Set</a></div></td></tr>
"""


def test_pricecharting_choose_prefers_plain_english_printing():
    rows = PriceCharting.parse_results(PC_RESULTS)
    assert len(rows) == 4
    base = Target(name="b", keywords=["charizard"], card_name="Charizard", set_name="Base Set", number="4/102")
    assert PriceCharting.choose(rows, base)["url"].endswith("pokemon-base-set/charizard-4")
    first_ed = replace(base, card_name="Charizard [1st Edition]")
    assert PriceCharting.choose(rows, first_ed)["url"].endswith("charizard-1st-edition-4")
    assert PriceCharting.choose(rows, replace(base, number="6")) is None


def test_tcgplayer_pick_matches_by_number_and_name():
    results = [
        {"productId": 1, "productName": "Charizard V (Secret)", "customAttributes": {"number": "79/73"}, "marketPrice": 250},
        {"productId": 2, "productName": "Charizard VMAX (Secret)", "customAttributes": {"number": "74/73"}, "marketPrice": 192},
    ]
    assert TcgPlayer.pick(results, "074/073", "Charizard VMAX")["productId"] == 2
    assert TcgPlayer.pick(results, "001/073", "Charizard") is None
    # Collectr often gives the bare number ("21") while TCGPlayer has "21/98".
    gyarados = [{"productId": 3, "productName": "Gyarados (21)", "customAttributes": {"number": "21/98"}, "marketPrice": 64}]
    assert TcgPlayer.pick(gyarados, "21", "Gyarados")["productId"] == 3
    assert TcgPlayer.pick(gyarados, "21/100", "Gyarados") is None


def test_pricing_rejects_other_printings_even_when_numbers_match(monkeypatch):
    base = Target(name="b", keywords=["charizard"], card_name="Charizard", set_name="Base Set", number="4/102")
    wrong = {"productId": 1, "productName": "Charizard", "setName": "Base Set (Shadowless)",
             "customAttributes": {"number": "4/102"}, "marketPrice": 2000}
    right = wrong | {"productId": 2, "setName": "Base Set", "marketPrice": 900}
    assert TcgPlayer.pick([wrong, right], base.number, base.card_name, base.set_name)["productId"] == 2
    assert TcgPlayer.pick([wrong], base.number, base.card_name, base.set_name) is None
    rows = PriceCharting.parse_results(PC_RESULTS)
    assert PriceCharting.choose(rows[:1], base) is None
    assert PriceCharting.choose(rows[3:], base) is None
    pc = PriceCharting()
    monkeypatch.setattr(pc, "fetch", lambda q: (PC_HTML, "https://www.pricecharting.com/game/pokemon-wrong-set/charizard-vmax-74"))
    assert pc.lookup(ZARD) is None
    ambiguous = [{"title": "Charizard #4", "set": "Pokemon Base Set", "url": "a"},
                 {"title": "Charizard #5", "set": "Pokemon Base Set", "url": "b"}]
    assert PriceCharting.choose(ambiguous, replace(base, number="")) is None


def test_nonfinite_source_prices_do_not_become_market_values():
    val = _val(raw=float("nan"), **{"10": float("inf"), "9": -100})
    assert not val.has_data and val.to_dict()["values"] == {}


def test_cached_timestamps_preserve_their_timezone_offset():
    original = _val(raw=200).to_dict()
    original["fetched_at"] = "2026-10-26T10:00:00-04:00"
    restored = Valuation.from_dict(original)
    assert restored.fetched_at.astimezone(timezone.utc).hour == 14


@pytest.mark.parametrize("title", [
    "Charizard VMAX Rainbow 079/073", "Charizard VMAX 074/073 Japanese", "Charizard VMAX 074/073 Korean",
    "Charizard VMAX 074/073 German", "Charizard VMAX 074/073 jumbo", "Charizard VMAX 074/073 reverse holo",
])
def test_listing_identity_cannot_borrow_another_printings_value(title):
    assert evaluate(_listing(title=title, price=150), ZARD, [], valuation=_val(raw=200)) is None


def test_undergraded_and_expired_listings_do_not_borrow_higher_grade_values():
    assert evaluate(_listing(title="PSA 5 Charizard VMAX 074/073", price=150), ZARD, [],
                    valuation=_val(**{"7": 200})) is None
    assert evaluate(_listing(price=150, end_time=datetime.now(timezone.utc) - timedelta(minutes=1)), ZARD, [],
                    valuation=_val(raw=200)) is None
    assert evaluate(_listing(price=150, currency="USD"), ZARD, [], valuation=_val(raw=200)) is None
    assert evaluate(_listing(price=150, shipping=None), ZARD, [], valuation=_val(raw=200)) is None


@pytest.mark.parametrize("title", ["Charizard VMAX 074/073 damaged", "CGC Pristine 10 Charizard VMAX 074/073",
                                 "PSA 5 Charizard VMAX 074/073"])
def test_budget_does_not_replace_a_missing_condition_or_grade_valuation(title):
    assert evaluate(_listing(title=title, price=150), replace(ZARD, max_price=500), [],
                    valuation=_val(raw=200, **{"10": 1000})) is None


def test_condition_outside_the_title_survives_storage_and_revaluation():
    from cardsnipe.runner import revalue_store

    store = Store("sqlite://")
    listing = _listing(price=150, condition="Moderately played (Very Good)")
    store.record_listing(listing, None)
    assert evaluate(listing, replace(ZARD, max_price=500), [], valuation=_val(raw=200)) is None
    stats = revalue_store(store, Watchlist(targets=[replace(ZARD, max_price=500)]), FakePricer(_val(raw=200)))
    assert stats["matched"] == 0 and store.recent_listings()[0].condition == listing.condition


@pytest.mark.parametrize("condition", ["", "Pre-Owned", "Ungraded", "unverified", "Not Near Mint"])
def test_raw_market_matching_requires_verified_seller_condition(condition):
    listing = _listing(price=150, title="Charizard VMAX 074/073 NM", condition=condition)
    assert evaluate(listing, ZARD, [], valuation=_val(raw=200)) is None
    assert evaluate(_listing(price=150, condition="Ungraded - Near Mint or Better"), ZARD, [],
                    valuation=_val(raw=200)) is not None


@pytest.mark.parametrize("rows", [[], [{"title": "wrong card", "price": "C $10", "text": "Sold Oct 25\nwrong card\nC $10"}]])
def test_empty_or_unrelated_sold_results_are_unpriced(rows):
    class Browser:
        def get(self, url):
            pass

        def js(self, script):
            return "eBay sold results" if script == "return document.title" else rows

    assert EbaySold(Browser(), "ebay.ca", "CAD", 1.4).lookup(ZARD) is None


def test_sold_median_uses_all_exact_sales_and_separates_grading_companies():
    def row(title, price, extra=""):
        return {"title": title, "price": price, "text": f"Sold Oct 25\n{title}\n{price}\n{extra}"}

    class Browser:
        def get(self, url):
            pass

        def js(self, script):
            return "eBay sold results" if script == "return document.title" else [
                row("PSA 10 Charizard VMAX 074/073", "C $280"),
                row("PSA 10 Charizard VMAX 074/073", "US $300"),
                row("CGC 10 Charizard VMAX 074/073", "C $14"),
                row("PSA 10 Charizard VMAX 074/073 Japanese", "C $28"),
                row("PSA 10 Charizard VMAX 074/073", "C $999", "Best offer accepted"),
            ]

    prices = EbaySold(Browser(), "ebay.ca", "CAD", 1.4).lookup(ZARD)
    assert len(prices) == 1 and prices[0].bucket == "10" and prices[0].price_usd == 250
    assert prices[0].detail == "median of 2 sold"


def test_expired_valuation_is_not_silently_reused_on_refresh_failure(monkeypatch):
    store = Store("sqlite://")
    stale = _val(raw=200)
    stale.market_query = ZARD.market_query
    stale.fetched_at = datetime.now(timezone.utc) - timedelta(hours=48)
    store.save_valuation(stale)
    service = PriceService(replace(SnipeSettings.from_env(), price_ttl_hours=6), store)
    monkeypatch.setattr(service, "refresh", lambda target: None)
    assert service.valuation(ZARD) is None
    assert service.valuation(ZARD, cached_only=True) is None


def test_unidentified_graded_collection_item_is_not_a_raw_card():
    assert item_bucket({"name": "Charizard", "graded": True}) is None
    assert item_bucket({"name": "Charizard", "grade": "unknown slab"}) is None


def test_variant_words_and_pricecharting_variant_pass(monkeypatch):
    assert variant_words("Umbreon (Cosmos Holo)") == "cosmos holo"
    assert variant_words("Gyarados (21)") == ""
    assert variant_words("Rayquaza V (Alternate Full Art)") == "alternate full art"

    pc = PriceCharting()
    plain = '<h1 id="product_name">Umbreon #59</h1><td id="used_price"><span class="price js-price">$1.54</span>'
    cosmos = '<h1 id="product_name">Umbreon [Cosmos Holo] #59</h1><td id="used_price"><span class="price js-price">$14.00</span>'
    pages = {"umbreon 59 cosmos holo": (cosmos, "https://www.pricecharting.com/game/pokemon-prismatic-evolutions/umbreon-cosmos-holo-59"),
             "umbreon 59": (plain, "https://www.pricecharting.com/game/pokemon-prismatic-evolutions/umbreon-59")}
    monkeypatch.setattr(pc, "fetch", lambda q: pages[q])
    cosmos_target = Target(name="c", keywords=["umbreon"], card_name="Umbreon (Cosmos Holo)", number="059/131")
    assert pc.lookup(cosmos_target)[0].price_usd == 14.0
    # A variant that PriceCharting does not list separately falls back to the plain print.
    pages["umbreon 59 alternate art"] = pages["umbreon 59"]
    alt = Target(name="a", keywords=["umbreon"], card_name="Umbreon (Alternate Art)", number="059/131")
    assert pc.lookup(alt)[0].price_usd == 1.54


# ── matching against market value ────────────────────────────────────────────

def test_market_value_sets_the_cap_and_savings():
    val = _val(raw=200.0, **{"9": 240.0, "10": 400.0})
    # 20% under raw value (160) is the threshold: 150 qualifies, 170 does not.
    deal = evaluate(_listing(price=150.0), ZARD, [], valuation=val)
    assert deal and deal.lane == "deal" and deal.market_value == 200.0 and deal.value_bucket == "raw"
    assert deal.under_value_pct == 25.0 and not deal.irregular
    assert evaluate(_listing(price=170.0), ZARD, [], valuation=val) is None
    # Graded copies are judged against their own bucket.
    ten = evaluate(_listing(title="PSA 10 Charizard VMAX 074/073", price=300.0), ZARD, [], valuation=val)
    assert ten and ten.value_bucket == "10" and ten.market_value == 400.0
    assert "under 10 value CAD 400" in ten.headline


def test_irregular_flag_for_too_good_to_be_true():
    val = _val(raw=200.0)
    assert evaluate(_listing(price=60.0), ZARD, [], valuation=val) is None  # 70% under NM is a fake
    assert evaluate(_listing(price=101.0), ZARD, [], valuation=val) is not None
    assert evaluate(_listing(price=20.0, listing_type="auction"), ZARD, [], valuation=val) is None


@pytest.mark.parametrize("title,expected", [
    ("PSA 10 Charizard VMAX 074/073", ("PSA", 10.0)),
    ("Charizard VMAX 074/073 NOT PSA 10 graded", None),
    ("Charizard VMAX 074/073 PSA 10 potential", None),
    ("Charizard VMAX raw ungraded would be a PSA 9", None),
    ("Charizard VMAX 074/073 pack fresh psa ready", None),
    ("CGC 9.5 Charizard VMAX 074/073 no PSA", ("CGC", 9.5)),
    ("CGC Pristine 10 Charizard VMAX 074/073", ("CGC", 10)),
    ("Charizard VMAX 074/073 TAG 9 (945)", ("TAG", 9.0)),
])
def test_detect_grade_ignores_not_graded_language(title, expected):
    from cardsnipe.matcher import detect_grade

    assert detect_grade(title) == expected


@pytest.mark.parametrize("title,expected", [
    ("Umbreon VMAX 215/203 Damage", "damage"),
    ("Umbreon VMAX 215/203 heavily played", "heavily played"),
    ("Umbreon VMAX 215/203 HP condition", "hp"),
    ("Umbreon VMAX 215/203 HP/MP", "hp"),
    ("Umbreon VMAX 215/203", None),
    ("Umbreon VMAX 215/203 creased", "creased"),
    ("Umbreon VMAX 215/203 no damage pack fresh", None),
    ("Umbreon VMAX 215/203 no whitening NM", None),
    ("Umbreon VMAX 215/203 edge wear", "edge wear"),
    ("Umbreon VMAX 215/203 NM/M", None),
    ("Umbreon VMAX Evolving Skies 215/203 Full Art Holo 330 HP", None),
    ("Umbreon VMAX 215/203 HP", "hp"),
])
def test_detect_condition_issue(title, expected):
    from cardsnipe.matcher import detect_condition_issue

    assert detect_condition_issue(title) == expected


def test_bin_priced_under_the_real_floor_is_dropped_as_a_fake():
    val = _val(raw=200.0)
    val.floor_usd = 100.0
    assert evaluate(_listing(price=50.0), ZARD, [], valuation=val) is None
    assert evaluate(_listing(price=110.0), ZARD, [], valuation=val) is not None
    assert evaluate(_listing(price=20.0, listing_type="auction"), ZARD, [], valuation=val) is None


def test_played_raw_is_not_valued_as_near_mint():
    val = _val(raw=2493.0)
    target = Target(name="u", keywords=["umbreon", "vmax"])
    assert evaluate(_listing(title="Umbreon VMAX Alternate Art 215/203 Damage", price=1334.0), target, [], valuation=val) is None
    assert evaluate(_listing(title="Umbreon VMAX 215/203 MP", price=1800.0), target, [], valuation=val) is None
    # Hit points are not "HP" condition, so a clean title still uses the NM value.
    clean = evaluate(_listing(title="Umbreon VMAX 215/203 Full Art Holo 330 HP", price=1800.0), target, [], valuation=val)
    assert clean and clean.value_bucket == "raw" and clean.market_value == 2493.0
    # Slabs carry their grade; "PSA 8 ... whitening" is a PSA 8, not a condition flag.
    slab = evaluate(_listing(title="PSA 8 Umbreon VMAX 215/203 light whitening", price=1500.0),
                    target, [], valuation=_val(**{"8": 2521.0}))
    assert slab and not slab.irregular and slab.value_bucket == "8"


def test_cheap_psa_slab_is_dropped_as_a_fake():
    val = _val(raw=269.0, **{"10": 406.0, "9": 236.0})
    assert evaluate(_listing(title="PSA 10 Charizard VMAX 074/073", price=13.49), ZARD, [], valuation=val) is None
    assert evaluate(_listing(title="PSA 9 Rayquaza V 194/203", price=63.5), replace(ZARD, keywords=["rayquaza"]), [], valuation=val) is None


def test_ace_slabs_are_never_matches():
    val = _val(raw=400.0, **{"10": 37000.0, "9": 500.0})
    target = Target(name="z", keywords=["charizard"], regrade=True, max_price=50000)
    assert evaluate(_listing(title="Charizard 4/102 Base Set ACE 10", price=475.0), target, [], valuation=val) is None
    assert evaluate(_listing(title="ACE 9 Charizard 4/102", price=80.0), target, [], valuation=val) is None
    assert evaluate(_listing(title="Charizard ACE-graded 10", price=90.0), target, [], valuation=val) is None


def test_non_psa_slabs_do_not_use_psa_prices():
    val = _val(raw=400.0, **{"10": 37000.0, "9.5": 800.0, "9": 500.0})
    target = Target(name="z", keywords=["charizard"], graded_only=True, min_grade=9)
    ace = evaluate(_listing(title="Charizard 4/102 Base Set ACE 10", price=475.0), target, [], valuation=val)
    cgc = evaluate(_listing(title="CGC 10 Charizard 4/102", price=800.0), target, [], valuation=val)
    psa = evaluate(_listing(title="PSA 10 Charizard 4/102", price=20000.0), target, [], valuation=val)
    half = evaluate(_listing(title="CGC 9.5 Charizard 4/102", price=500.0), target, [], valuation=val)
    assert ace is None and cgc is None
    assert psa and psa.value_bucket == "10" and psa.market_value == 37000.0
    assert half and half.value_bucket == "9.5" and half.market_value == 800.0


def test_hard_max_price_still_limits_market_cap():
    capped = replace(ZARD, max_price=120.0)
    val = _val(raw=200.0)
    assert evaluate(_listing(price=150.0), capped, [], valuation=val) is None
    assert evaluate(_listing(price=110.0), capped, [], valuation=val).cap == 120.0


def test_regrade_lane_uses_raw_value_as_cap():
    val = _val(raw=200.0, **{"9": 240.0})
    # A PSA 9 at 195 is above the 9-bucket deal threshold (240 − 20% = 192) but under a raw copy: crack candidate.
    match = evaluate(_listing(title="PSA 9 Charizard VMAX 074/073", price=195.0), ZARD, [], valuation=val)
    assert match and match.lane == "regrade" and match.cap == 200.0 and match.value_bucket == "raw"
    # At 190 it is simply a deal on the PSA 9 bucket.
    assert evaluate(_listing(title="PSA 9 Charizard VMAX 074/073", price=190.0), ZARD, [], valuation=val).lane == "deal"
    assert evaluate(_listing(title="PSA 9 Charizard VMAX 074/073", price=210.0), ZARD, [], valuation=val) is None


def test_without_valuation_falls_back_to_max_price_or_skips():
    assert evaluate(_listing(price=50.0), ZARD, []) is None                       # no value, no cap
    capped = replace(ZARD, max_price=120.0)
    match = evaluate(_listing(price=100.0), capped, [])
    assert match and match.market_value is None and match.cap == 120.0 and "under cap 120" in match.headline


# ── service caching + runner integration ─────────────────────────────────────

class FakePricer:
    def __init__(self, valuation):
        self.valuation_obj = valuation
        self.calls = 0

    def valuation(self, target, force=False):
        self.calls += 1
        return self.valuation_obj


class Source:
    def __init__(self):
        self.ceilings = []

    def find(self, target):
        self.ceilings.append(target.max_price)
        return [_listing(listing_id="a", price=150.0), _listing(listing_id="b", title="PSA 10 Charizard VMAX 074/073", price=280.0)]


class Quiet:
    def deal(self, match): pass

    def info(self, title, body): pass


def test_runner_uses_valuation_for_search_ceiling_and_records_market_fields():
    settings = replace(SnipeSettings.from_env(), database_url="sqlite://", notify_macos=False, open_in_browser=False,
                       webhook_url="", fb_auto_message=False, live=False)
    store = Store("sqlite://")
    source = Source()
    runner = SnipeRunner(settings, Watchlist(targets=[ZARD]), store, {"ebay": source}, Quiet(),
                         pricer=FakePricer(_val(raw=200.0, **{"10": 400.0})))
    report = runner.scan_once()
    assert source.ceilings == [320.0]                          # highest bucket (400) minus 20%
    assert len(report.deals) == 2 and report.errors == []
    rows = {r.listing_id: r for r in store.recent_deals()}
    assert rows["a"].market_value == 200.0 and rows["a"].value_bucket == "raw" and rows["a"].irregular is False
    assert rows["b"].market_value == 400.0 and rows["b"].value_bucket == "10" and rows["b"].irregular is False
    assert store.summary()["irregular_total"] == 0


def test_revalue_rejudges_stored_listings_with_market_values():
    from cardsnipe.runner import revalue_store

    store = Store("sqlite://")
    capped = replace(ZARD, max_price=250.0, use_market=False)
    # Old world: cap-only matches, including one that market data will reject.
    store.record_listing(_listing(listing_id="ok", price=150.0), evaluate(_listing(listing_id="ok", price=150.0), capped, []))
    store.record_listing(_listing(listing_id="meh", price=240.0), evaluate(_listing(listing_id="meh", price=240.0), capped, []))
    store.record_listing(_listing(listing_id="junk", title="Pikachu", price=5.0), None)
    assert len(store.recent_deals()) == 2

    stats = revalue_store(store, Watchlist(targets=[ZARD]), FakePricer(_val(raw=200.0)))
    assert stats == {"checked": 3, "matched": 1, "unmatched": 2, "changed": 2}
    deals = store.recent_deals()
    assert [d.listing_id for d in deals] == ["ok"] and deals[0].market_value == 200.0 and deals[0].savings_pct == 25.0


def test_runner_skips_target_with_no_value_and_no_cap():
    settings = replace(SnipeSettings.from_env(), database_url="sqlite://", notify_macos=False, open_in_browser=False,
                       webhook_url="", fb_auto_message=False, live=False)
    source = Source()
    runner = SnipeRunner(settings, Watchlist(targets=[ZARD]), Store("sqlite://"), {"ebay": source}, Quiet(),
                         pricer=FakePricer(None))
    report = runner.scan_once()
    assert source.ceilings == [] and len(report.errors) == 1 and "skipped" in report.errors[0]


def test_price_service_caches_in_store(monkeypatch):
    settings = replace(SnipeSettings.from_env(), database_url="sqlite://", price_ttl_hours=6, ebay_sold_comps=False)
    store = Store("sqlite://")
    service = PriceService(settings, store)
    calls = {"tcg": 0, "pc": 0}

    def fake_tcg(self, target):
        calls["tcg"] += 1
        return [SourcePrice("tcgplayer", "raw", 192.0), SourcePrice("tcgplayer", "floor", 63.0)]

    def fake_pc(self, target):
        calls["pc"] += 1
        return [SourcePrice("pricecharting", "raw_any", 157.5), SourcePrice("pricecharting", "10", 290.0)]

    monkeypatch.setattr(TcgPlayer, "lookup", fake_tcg)
    monkeypatch.setattr(PriceCharting, "lookup", fake_pc)
    monkeypatch.setattr("cardsnipe.pricing.usd_rate", lambda *a, **k: 1.4)

    first = service.valuation(ZARD)
    assert first.value("raw") == (268.8, "tcgplayer") and first.floor_usd == 63.0
    assert calls == {"tcg": 1, "pc": 1}

    # Fresh service instance reads the stored copy without refetching.
    again = PriceService(settings, store).valuation(ZARD)
    assert again.value("10") == (406.0, "pricecharting") and calls == {"tcg": 1, "pc": 1}

    # Expired cache refetches.
    stale = store.load_valuation("Zard")
    stale["fetched_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    store.save_valuation(Valuation.from_dict(stale))
    PriceService(settings, store).valuation(ZARD)
    assert calls == {"tcg": 2, "pc": 2}
    assert len(store.all_valuations()) == 1

    # Editing the printing must invalidate both the running watcher's memo and the saved cache.
    changed = replace(ZARD, number="999/999")
    assert service.valuation(changed).market_query == changed.market_query
    assert calls == {"tcg": 3, "pc": 3}
    assert PriceService(settings, store).valuation(ZARD).market_query == ZARD.market_query
    assert calls == {"tcg": 4, "pc": 4}


def test_store_migration_adds_new_columns(tmp_path):
    """An older cardsnipe.db (without market columns) must keep working."""
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE seen_listings (id INTEGER PRIMARY KEY, source VARCHAR(20) NOT NULL, listing_id VARCHAR(80) NOT NULL, title TEXT)")
    conn.commit()
    conn.close()
    store = Store(f"sqlite:///{path}")
    store.record_listing(_listing(), None)
    assert store.recent_listings()[0].market_value is None


# ── watchlist persistence of market fields ────────────────────────────────────

def test_watchlist_roundtrip_keeps_market_fields(tmp_path):
    path = str(tmp_path / "w.json")
    save_watchlist(path, Watchlist(targets=[ZARD, replace(ZARD, name="Capped", max_price=120.0, use_market=False)]))
    loaded = load_watchlist(path).targets
    assert loaded[0].max_price is None and loaded[0].card_name == "Charizard VMAX" and loaded[0].number == "074/073"
    assert loaded[0].bargain_pct == 20.0 and loaded[0].market_query == "Charizard VMAX Champion's Path 074/073"
    assert loaded[1].max_price == 120.0 and loaded[1].use_market is False
    assert ZARD.with_ceiling(300.0).max_price == 300.0 and loaded[1].with_ceiling(300.0).max_price == 120.0


# ── Collectr ──────────────────────────────────────────────────────────────────

SHOWCASE_TEXT = """
Login
Mustafa Alp
Estimated Portfolio Value
$295.47
Total Cards
5
Total Sealed
0
Total Graded
0
Find a Product
Mega Darkrai ex
Pitch Black
Special Illustration Rare
•
116/084
$122.80
+$5.78
(4.94%)
Qty: 1
Team Rocket's Crobat ex
Glory of Team Rocket
Special Art Rare
•
127/098
$52.57
-$1.12
(-2.09%)
Qty: 2
Gyarados (21)
Ancient Origins
Holo Rare
•
21
$56.87
+$0.36
(0.63%)
Qty: 1
"""


def test_parse_collectr_showcase():
    result = parse_showcase_text(SHOWCASE_TEXT)
    assert result.owner == "Mustafa Alp" and result.total_value_usd == 295.47
    assert result.total_cards == 5 and result.total_graded == 0
    assert [i["name"] for i in result.items] == ["Mega Darkrai ex", "Team Rocket's Crobat ex", "Gyarados (21)"]
    crobat = result.items[1]
    assert crobat["set_name"] == "Glory of Team Rocket" and crobat["number"] == "127/098"
    assert crobat["value_usd"] == 52.57 and crobat["change_usd"] == -1.12 and crobat["change_pct"] == -2.09
    assert crobat["quantity"] == 2 and crobat["graded"] is False


COPIED_SHOWCASE = """Collectr
USD
Trainer
Estimated Portfolio Value
$40.00
Total Cards
3
Total Graded
0
Card A
Card A
Set A
Rare
•
SM210
Near Mint
•
Holofoil
$20.00
-$1.00
(-4.76%)
Qty: 1
Card B
Card B
Set B
Ultra Rare
•
142
Lightly Played
•
Holofoil
$10.00
+$0.50
(5.26%)
Qty: 2
"""


def test_copied_collectr_import_preserves_condition_and_ignores_finish_bullets():
    result = parse_showcase_import(COPIED_SHOWCASE)
    assert result.total_cards == 3 and result.total_value_usd == 40
    assert [i["name"] for i in result.items] == ["Card A", "Card B"]
    assert [i["condition"] for i in result.items] == ["Near Mint", "Lightly Played"]
    assert all(i["finish"] == "Holofoil" for i in result.items)
    assert result.items[1]["quantity"] == 2 and result.items[1]["change_pct"] == 5.26


@pytest.mark.parametrize("text", [None, {}, "", COPIED_SHOWCASE.replace("$", "CA$"),
    COPIED_SHOWCASE.replace("Total Cards\n3", "Total Cards\n4"),
    COPIED_SHOWCASE.replace("$40.00", "$400.00"), COPIED_SHOWCASE.replace("Qty: 2", ""),
])
def test_collectr_import_rejects_wrong_currency_partial_or_invalid_data(text):
    with pytest.raises(ValueError):
        parse_showcase_import(text)


@pytest.mark.parametrize("condition", [None, "Lightly Played", "Moderately Played", "Damaged"])
def test_collection_never_prices_unknown_or_played_raw_cards_as_near_mint(condition):
    items = [{"name": "Card", "condition": condition, "value_usd": 200}]
    pricer = ByNamePricer({"Card": _val(raw=300)})
    value_items(items, pricer)
    assert items[0]["market_value_usd"] is None and not pricer.targets


def test_local_collection_import_preview_and_save_are_separate_and_never_fetch(monkeypatch):
    import dashboard.app as dashboard_app
    import dashboard.snipe_views as views

    monkeypatch.setattr(dashboard_app.Config, "EXTERNAL_ACCESS_ENABLED", False)
    store = Store("sqlite://")
    views.set_store(store)
    store.replace_collection([{"name": "Old card", "market_value_usd": 999}], 100, "")
    try:
        client = dashboard_app.app.test_client()
        preview = client.post("/api/snipe/collection/import", json={"text": COPIED_SHOWCASE})
        assert preview.status_code == 200 and preview.get_json()["preview"] is True
        assert store.collection()[0][0].name == "Old card"
        bad = client.post("/api/snipe/collection/import", json={"text": COPIED_SHOWCASE.replace("$", "CA$"), "confirm": True})
        assert bad.status_code == 400 and store.collection()[0][0].name == "Old card"
        saved = client.post("/api/snipe/collection/import", json={"text": COPIED_SHOWCASE, "confirm": True})
        assert saved.status_code == 200 and saved.get_json()["local_only"] is True
        data = client.get("/api/snipe/collection").get_json()
        assert data["snapshot"]["total_cards"] == 3 and data["snapshot"]["market_value_usd"] is None
        assert data["automatic_sync"] is False
        assert {i["condition"] for i in data["items"]} == {"Near Mint", "Lightly Played"}
        assert all(i["finish"] == "Holofoil" for i in data["items"])
    finally:
        views.set_store(None)


def test_collection_store_and_api(tmp_path, monkeypatch):
    import dashboard.app as dashboard_app
    import dashboard.snipe_views as views

    monkeypatch.setattr(dashboard_app.Config, "EXTERNAL_ACCESS_ENABLED", False)
    monkeypatch.setenv("SNIPE_USD_RATE", "1.25")
    monkeypatch.setenv("EBAY_CURRENCY", "CAD")
    store = Store("sqlite://")
    views.set_store(store)
    monkeypatch.setattr("dashboard.snipe_views.usd_rate", lambda *a, **k: pytest.fail("Saved collection must not fetch live FX"))
    try:
        result = parse_showcase_text(SHOWCASE_TEXT)
        snap = store.replace_collection(result.items, result.total_value_usd, "https://app.getcollectr.com/x", owner=result.owner)
        assert snap.total_cards == 4 and snap.total_value_usd == 295.47
        items, latest = store.collection()
        assert items[0].name == "Mega Darkrai ex" and latest.owner == "Mustafa Alp"

        dashboard_app.app.config.update(TESTING=True)
        client = dashboard_app.app.test_client()
        data = client.get("/api/snipe/collection").get_json()
        assert data["snapshot"]["total_value_usd"] == 295.47 and len(data["items"]) == 3 and data["fx"] == 1.25
        assert data["fx_estimated"] is True
        assert data["history"][-1]["total_cards"] == 4

        bad = client.post("/api/snipe/collection/sync", json={"url": "https://evil.example/"})
        assert bad.status_code == 403

        vals = client.get("/api/snipe/valuations").get_json()
        assert "valuations" in vals and vals["currency"]
    finally:
        views.set_store(None)


class ByNamePricer:
    """Returns a valuation per card name (None when the card is unknown)."""

    def __init__(self, table: dict):
        self.table = table
        self.targets = []

    def valuation(self, target, force=False):
        self.targets.append(target)
        return self.table.get(target.card_name)


def test_market_target_cleans_collectr_names():
    t = market_target({"name": "Gyarados (21)", "set_name": "Ancient Origins", "number": "21"})
    assert t.card_name == "Gyarados" and t.market_query == "Gyarados Ancient Origins 21"
    t = market_target({"name": "Umbreon GX (Full Art)", "set_name": "Sun & Moon Base Set", "number": "142"})
    assert t.card_name == "Umbreon GX (Full Art)" and t.set_name == "Sun & Moon"
    t = market_target({"name": "Umbreon (Cosmos Holo)", "set_name": "Miscellaneous Cards & Products", "number": "059/131"})
    assert t.set_name == "" and t.market_query == "Umbreon (Cosmos Holo) 059/131"
    assert item_bucket({"name": "Charizard VMAX"}) == "raw"
    assert item_bucket({"name": "PSA 10 Charizard VMAX"}) == "10"
    assert item_bucket({"name": "Umbreon", "grade": "CGC 9.5"}) == "9.5"


def test_value_items_never_uses_collectr_as_the_value():
    items = [
        {"name": "Mega Darkrai ex", "set_name": "Pitch Black", "number": "116/084", "value_usd": 122.8, "quantity": 1, "condition": "Near Mint"},
        {"name": "Mystery Promo", "set_name": "", "number": "1", "value_usd": 99.0, "quantity": 1, "condition": "Near Mint"},
        {"name": "PSA 9 Rare Slab", "set_name": "", "number": "2", "value_usd": 300.0, "quantity": 2},        # slab, unknown
        {"name": "PSA 10 Darkrai", "set_name": "Pitch Black", "number": "116/084", "value_usd": 900.0, "quantity": 1},
    ]
    darkrai = Valuation(target_name="d", currency="CAD", fx=1.4, prices=[
        SourcePrice("tcgplayer", "raw", 143.91), SourcePrice("pricecharting", "raw", 166.82), SourcePrice("pricecharting", "10", 710.6)])
    value_items(items, ByNamePricer({"Mega Darkrai ex": darkrai, "PSA 10 Darkrai": darkrai}))

    assert (items[0]["market_value_usd"], items[0]["market_source"], items[0]["market_bucket"]) == (143.91, "tcgplayer", "raw")
    assert items[0]["collectr_usd"] is None                          # raw Collectr number is dropped
    assert items[1]["market_value_usd"] is None and items[1]["collectr_usd"] is None
    assert items[2]["market_value_usd"] is None and items[2]["collectr_usd"] == 300.0  # graded, glance only
    assert (items[3]["market_value_usd"], items[3]["market_bucket"]) == (710.6, "10")

    store = Store("sqlite://")
    snap = store.replace_collection(items, 1421.8, "https://app.getcollectr.com/x")
    assert snap.market_value_usd == pytest.approx(143.91 + 710.6)
    assert snap.unvalued_items == 2 and snap.total_value_usd == 1421.8
    rows, _ = store.collection()
    assert rows[0].name == "PSA 10 Darkrai" and rows[-1].market_value_usd is None  # ordered by our value

    # Re-pricing refreshes ours and still does not adopt Collectr, even for the unknown slab.
    snap2 = revalue_collection(store, ByNamePricer({"Mystery Promo": Valuation("m", "CAD", 1.4, [SourcePrice("tcgplayer", "raw", 5.0)])}))
    assert snap2.unvalued_items == 3 and snap2.market_value_usd == pytest.approx(5.0)
    assert snap2.total_value_usd == 1421.8
    assert revalue_collection(Store("sqlite://"), ByNamePricer({})) is None


def test_collection_api_exposes_our_value_and_revalue(monkeypatch):
    import dashboard.app as dashboard_app
    import dashboard.snipe_views as views
    monkeypatch.setattr(dashboard_app.Config, "EXTERNAL_ACCESS_ENABLED", True)

    store = Store("sqlite://")
    views.set_store(store)
    monkeypatch.setattr("dashboard.snipe_views.usd_rate", lambda *a, **k: 1.4)
    try:
        items = [{"name": "Card A", "set_name": "S", "number": "1", "value_usd": 50.0, "quantity": 1,
                  "market_value_usd": 40.0, "market_source": "pricecharting", "market_bucket": "raw"}]
        store.replace_collection(items, 50.0, "https://app.getcollectr.com/x")
        dashboard_app.app.config.update(TESTING=True)
        client = dashboard_app.app.test_client()
        data = client.get("/api/snipe/collection").get_json()
        assert data["snapshot"]["market_value_usd"] == 40.0 and data["items"][0]["market_source"] == "pricecharting"

        monkeypatch.setattr(views, "PriceService", lambda settings, store: ByNamePricer({}))
        r = client.post("/api/snipe/collection/revalue")
        assert r.status_code == 200 and "1 unpriced" in r.get_json()["message"]
        views.set_store(Store("sqlite://"))
        assert client.post("/api/snipe/collection/revalue").status_code == 400
    finally:
        views.set_store(None)
