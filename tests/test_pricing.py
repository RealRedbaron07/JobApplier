"""Market valuation: source parsers, cheapest-of-sources logic, value-aware matching, Collectr import."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from cardsnipe.collectr import parse_showcase_text
from cardsnipe.matcher import Listing, bucket_for_grade, evaluate
from cardsnipe.pricing import PriceCharting, PriceService, SourcePrice, TcgPlayer, Valuation, normalize_number
from cardsnipe.runner import SnipeRunner
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import Store
from cardsnipe.watchlist import Target, Watchlist, load_watchlist, save_watchlist

ZARD = Target(name="Zard", keywords=["charizard", "vmax"], card_name="Charizard VMAX", set_name="Champion's Path",
              number="074/073", regrade=True)


def _val(**buckets) -> Valuation:
    """Valuation with one price per bucket, fx=1 so numbers read directly."""
    return Valuation(target_name="Zard", currency="CAD", fx=1.0,
                     prices=[SourcePrice("test", b, v) for b, v in buckets.items()])


def _listing(**overrides) -> Listing:
    values = dict(source="ebay", listing_id="1", title="Charizard VMAX 074/073 Champions Path", price=100.0,
                  currency="CAD", url="https://www.ebay.ca/itm/1", listing_type="bin", shipping=0.0)
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


def test_valuation_takes_cheapest_source_per_bucket_and_converts():
    val = Valuation(target_name="x", currency="CAD", fx=1.4, prices=[
        SourcePrice("tcgplayer", "raw", 200.0), SourcePrice("pricecharting", "raw", 150.0),
        SourcePrice("pricecharting", "10", 300.0), SourcePrice("ebay_sold", "10", 0.0),
    ])
    assert val.value_usd("raw") == (150.0, "pricecharting")
    assert val.value("raw") == (210.0, "pricecharting")
    assert val.value("10") == (420.0, "pricecharting")   # zero prices ignored
    assert val.value("9") is None
    roundtrip = Valuation.from_dict(val.to_dict())
    assert roundtrip.value("raw") == val.value("raw") and roundtrip.to_dict()["values"]["10"]["usd"] == 300.0


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
    assert prices == {"raw": 157.5, "7": 142.38, "8": 143.5, "9": 168.24, "9.5": 172.51, "10": 290.0}
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
    match = evaluate(_listing(price=60.0), ZARD, [], valuation=val)
    assert match and match.irregular and match.irregular_reason == "70% under value" and "IRREGULAR" in match.headline
    assert not evaluate(_listing(price=101.0), ZARD, [], valuation=val).irregular
    # An auction's current bid is not a price signal.
    auction = evaluate(_listing(price=20.0, listing_type="auction"), ZARD, [], valuation=val)
    assert auction and not auction.irregular


@pytest.mark.parametrize("title,expected", [
    ("PSA 10 Charizard VMAX 074/073", ("PSA", 10.0)),
    ("Charizard VMAX 074/073 NOT PSA 10 graded", None),
    ("Charizard VMAX 074/073 PSA 10 potential", None),
    ("Charizard VMAX raw ungraded would be a PSA 9", None),
    ("Charizard VMAX 074/073 pack fresh psa ready", None),
    ("CGC 9.5 Charizard VMAX 074/073 no PSA", None),
    ("Charizard VMAX 074/073 TAG 9 (945)", ("TAG", 9.0)),
])
def test_detect_grade_ignores_not_graded_language(title, expected):
    from cardsnipe.matcher import detect_grade

    assert detect_grade(title) == expected


@pytest.mark.parametrize("title,expected", [
    ("Umbreon VMAX 215/203 Damage", "damage"),
    ("Umbreon VMAX 215/203 heavily played", "heavily played"),
    ("Umbreon VMAX 215/203 HP condition", "hp"),
    ("Umbreon VMAX 215/203 creased", "creased"),
    ("Umbreon VMAX 215/203 no damage pack fresh", None),
    ("Umbreon VMAX 215/203 no whitening NM", None),
    ("Umbreon VMAX 215/203 edge wear", "edge wear"),
    ("Umbreon VMAX 215/203 NM/M", None),
])
def test_detect_condition_issue(title, expected):
    from cardsnipe.matcher import detect_condition_issue

    assert detect_condition_issue(title) == expected


def test_damaged_copy_is_flagged_irregular_not_a_clean_deal():
    val = _val(raw=2493.0)
    match = evaluate(_listing(title="Umbreon VMAX Alternate Art 215/203 Damage", price=1334.0),
                     Target(name="u", keywords=["umbreon", "vmax"]), [], valuation=val)
    assert match and match.irregular and match.irregular_reason == "condition: damage"
    # Slabs carry their grade; "PSA 8 ... whitening" is a PSA 8, not a condition flag.
    slab = evaluate(_listing(title="PSA 8 Umbreon VMAX 215/203 light whitening", price=1500.0),
                    Target(name="u", keywords=["umbreon", "vmax"]), [], valuation=_val(**{"8": 2521.0}))
    assert slab and not slab.irregular


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
        return [_listing(listing_id="a", price=150.0), _listing(listing_id="b", title="PSA 10 Charizard VMAX 074/073", price=60.0)]


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
    assert rows["b"].market_value == 400.0 and rows["b"].irregular is True and rows["b"].savings_pct == 85.0
    assert store.summary()["irregular_total"] == 1


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
        return [SourcePrice("pricecharting", "raw", 157.5), SourcePrice("pricecharting", "10", 290.0)]

    monkeypatch.setattr(TcgPlayer, "lookup", fake_tcg)
    monkeypatch.setattr(PriceCharting, "lookup", fake_pc)
    monkeypatch.setattr("cardsnipe.pricing.usd_rate", lambda *a, **k: 1.4)

    first = service.valuation(ZARD)
    assert first.value("raw") == (220.5, "pricecharting") and first.floor_usd == 63.0
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


def test_collection_store_and_api(tmp_path, monkeypatch):
    import dashboard.app as dashboard_app
    import dashboard.snipe_views as views

    store = Store("sqlite://")
    views.set_store(store)
    monkeypatch.setattr("dashboard.snipe_views.usd_rate", lambda *a, **k: 1.4)
    try:
        result = parse_showcase_text(SHOWCASE_TEXT)
        snap = store.replace_collection(result.items, result.total_value_usd, "https://app.getcollectr.com/x", owner=result.owner)
        assert snap.total_cards == 4 and snap.total_value_usd == 295.47
        items, latest = store.collection()
        assert items[0].name == "Mega Darkrai ex" and latest.owner == "Mustafa Alp"

        dashboard_app.app.config.update(TESTING=True)
        client = dashboard_app.app.test_client()
        data = client.get("/api/snipe/collection").get_json()
        assert data["snapshot"]["total_value_usd"] == 295.47 and len(data["items"]) == 3 and data["fx"] == 1.4
        assert data["history"][-1]["total_cards"] == 4

        bad = client.post("/api/snipe/collection/sync", json={"url": "https://evil.example/"})
        assert bad.status_code == 400

        vals = client.get("/api/snipe/valuations").get_json()
        assert "valuations" in vals and vals["currency"]
    finally:
        views.set_store(None)
