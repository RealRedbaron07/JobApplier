from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from cardsnipe.matcher import Listing, detect_grade, evaluate, parse_price, parse_time_left
from cardsnipe.runner import BID_PREP_SECONDS, SnipeRunner, bid_fire_time
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import Store
from cardsnipe.watchlist import Target, Watchlist, add_target, load_watchlist, save_watchlist


def _settings(**overrides) -> SnipeSettings:
    base = SnipeSettings.from_env()
    values = {
        "database_url": "sqlite://",
        "notify_macos": False,
        "open_in_browser": False,
        "webhook_url": "",
        "fb_auto_message": True,
        "snipe_lead_seconds": 6,
        "live": False,
    }
    values.update(overrides)
    from dataclasses import replace

    return replace(base, **values)


def _listing(**overrides) -> Listing:
    values = dict(
        source="ebay",
        listing_id="123456789012",
        title="Pokemon Charizard VMAX Rainbow Rare 074/073 Champions Path NM",
        price=180.0,
        currency="CAD",
        url="https://www.ebay.ca/itm/123456789012",
        listing_type="bin",
        shipping=5.0,
    )
    values.update(overrides)
    return Listing(**values)


CHARIZARD = Target(name="Zard", keywords=["charizard", "vmax", "074/073|rainbow"], max_price=250, max_bid=270)


# ── parsing ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,expected",
    [("C $45.00", 45.0), ("$1,234.56", 1234.56), ("US $12 to US $20", 12.0), ("Free shipping", 0.0), ("", None), ("n/a", None)],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


def test_parse_time_left_relative_to_now():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_time_left("1d 4h left", now) == now + timedelta(days=1, hours=4)
    assert parse_time_left("23m 10s left", now) == now + timedelta(minutes=23, seconds=10)
    assert parse_time_left("2h 8m", now) == now + timedelta(hours=2, minutes=8)
    assert parse_time_left("Ends in 45s", now) == now + timedelta(seconds=45)
    assert parse_time_left("Free shipping", now) is None


def test_extract_time_left_line_handles_split_markup():
    from cardsnipe.matcher import extract_time_left_line

    assert extract_time_left_line(["C $33.00", "10 bids ·", "Time left", "7m", "+C $39.01 shipping"]) == "7m"
    assert extract_time_left_line(["Time left 2h 8m", "x"]) == "2h 8m"
    assert extract_time_left_line(["3 bids · 2h 15m left"]) == "3 bids · 2h 15m left"
    assert extract_time_left_line(["Pre-Owned", "C $5.00"]) == ""


def test_detect_grade():
    assert detect_grade("PSA 10 Charizard") == ("PSA", 10.0)
    assert detect_grade("cgc 9.5 gem mint") == ("CGC", 9.5)
    assert detect_grade("Rayquaza V AGS 9.5") == ("AGS", 9.5)
    assert detect_grade("raw near mint") is None


# ── matching rules ───────────────────────────────────────────────────────────

def test_match_within_cap_uses_total_price():
    match = evaluate(_listing(), CHARIZARD, [])
    assert match is not None
    assert match.total_price == 185.0
    assert round(match.savings_pct) == 26


def test_shipping_can_push_listing_over_cap():
    assert evaluate(_listing(price=248.0, shipping=5.0), CHARIZARD, []) is None


def test_requires_every_keyword_and_honours_alternatives():
    assert evaluate(_listing(title="Charizard VMAX rainbow rare"), CHARIZARD, []) is not None
    assert evaluate(_listing(title="Charizard V 079/073"), CHARIZARD, []) is None


def test_global_and_target_excludes_block_junk():
    assert evaluate(_listing(title="Charizard VMAX rainbow PROXY card"), CHARIZARD, ["proxy"]) is None
    picky = Target(name="t", keywords=["charizard"], max_price=1000, exclude=["japanese"])
    assert evaluate(_listing(title="Japanese Charizard"), picky, []) is None


def test_excludes_match_whole_words_only():
    picky = Target(name="t", keywords=["pinsir"], max_price=100)
    assert evaluate(_listing(title="Pinsir holo rare", price=20), picky, ["pin"]) is not None
    assert evaluate(_listing(title="Pinsir pin badge", price=20), picky, ["pin"]) is None
    metal = Target(name="z", keywords=["charizard"], max_price=300)
    assert evaluate(_listing(title="Charizard VMAX Gold Metal HP330", price=60), metal, ["metal"]) is None


def test_min_price_floor_applies_to_buy_now_but_not_auctions():
    floor = Target(name="f", keywords=["charizard"], max_price=300, min_price=90)
    assert evaluate(_listing(title="Charizard VMAX", price=20), floor, []) is None
    assert evaluate(_listing(title="Charizard VMAX", price=120), floor, []) is not None
    assert evaluate(_listing(title="Charizard VMAX", price=20, listing_type="auction"), floor, []) is not None


def test_default_global_exclude_filters_real_junk_titles():
    from cardsnipe.watchlist import DEFAULT_GLOBAL_EXCLUDE

    junk = [
        "Charizard VMAX (#074/073) Fan-Made Novelty Item",
        "Charizard VMAX - Black Foil Display Card HP330 074/073 Fan Art NM",
        "Charizard VMAX 074/073 Champions Path - Extended Art Case - No Card",
        "MYSTERY PACK - Umbreon VMAX 215/203 Evolving Skies",
        "READ Pokemon Umbreon Vmax 215/203 Soft Warm Plush Blanket 50x60",
        "Pokemon 2020 Charizard VMAX 074/073 Rainbow Gold Metal HP330",
    ]
    loose = Target(name="x", keywords=["vmax"], max_price=1000)
    for title in junk:
        assert evaluate(_listing(title=title, price=50), loose, DEFAULT_GLOBAL_EXCLUDE) is None, title
    assert evaluate(_listing(title="Charizard VMAX (Secret) 074/073 Champions Path Holo", price=150),
                    loose, DEFAULT_GLOBAL_EXCLUDE) is not None


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Rayquaza V Alt Art TAG 9 (945) Evolving Skies", 945),
        ("Rayquaza V TAG 9 945/1000 DIG", 945),
        ("945 TAG 9 Rayquaza V alt art", 945),
        ("TAG Graded 978 Umbreon VMAX", 978),
        ("TAG 10 Rayquaza V 194/203", None),        # 194 is a card number, not a score
        ("TAG 9 Charizard 2021 Celebrations", None),  # a year is out of range
        ("PSA 9 Rayquaza V 945", None),               # no TAG, no score
    ],
)
def test_detect_tag_score(title, expected):
    from cardsnipe.matcher import detect_tag_score

    assert detect_tag_score(title) == expected


def test_detect_clean_hints():
    from cardsnipe.matcher import detect_clean_hints

    hints = detect_clean_hints("PSA 9 Rayquaza V - super clean, pack fresh, looks like a 10")
    assert {"clean", "pack fresh", "looks like a 10"} <= set(hints)
    assert detect_clean_hints("Charizard VMAX heavy play") == []


RAYQUAZA = Target(
    name="Ray", keywords=["rayquaza", "v", "alt art|194/203"], max_price=350, min_price=120,
    regrade=True, regrade_min_grade=8.5, regrade_max_grade=9.5,
)


def test_regrade_lane_flags_lower_graded_copy_under_raw_cap():
    # A PSA 9 under the raw-NM cap still satisfies the primary lane (raw_ok, no min_grade)
    # but is marked as a regrade candidate.
    psa9 = evaluate(_listing(title="PSA 9 Rayquaza V Alt Art 194/203 clean", price=300, shipping=0), RAYQUAZA, [])
    assert psa9 is not None and psa9.lane == "deal" and psa9.regrade_candidate
    assert "clean" in psa9.clean_hints and "♻️" in psa9.headline

    # With a PSA-10-only target the regrade lane is what lets the PSA 9 through.
    tens_only = Target(name="ten", keywords=["rayquaza", "v"], max_price=900, graded_only=True, min_grade=10,
                       regrade=True, regrade_max_price=350)
    match = evaluate(_listing(title="PSA 9 Rayquaza V Alt Art", price=320, shipping=0), tens_only, [])
    assert match is not None and match.lane == "regrade" and match.cap == 350
    assert evaluate(_listing(title="PSA 9 Rayquaza V Alt Art", price=400, shipping=0), tens_only, []) is None
    assert evaluate(_listing(title="PSA 7 Rayquaza V Alt Art", price=100, shipping=0), tens_only, []) is None
    assert evaluate(_listing(title="PSA 10 Rayquaza V Alt Art", price=850, shipping=0), tens_only, []).lane == "deal"


def test_tag_near_miss_qualifies_regardless_of_grade_range():
    tight = Target(name="t", keywords=["rayquaza", "v"], max_price=900, graded_only=True, min_grade=10,
                   regrade=True, regrade_min_grade=9.5, regrade_max_grade=9.5, regrade_max_price=350)
    near = evaluate(_listing(title="TAG 9 (945) Rayquaza V Alt Art", price=300, shipping=0), tight, [])
    assert near is not None and near.lane == "regrade"
    assert near.tag_score == 945 and near.tag_gap == 5 and "5 off 10" in near.headline
    far = evaluate(_listing(title="TAG 9 (905) Rayquaza V Alt Art", price=300, shipping=0), tight, [])
    assert far is None
    # Custom thresholds flow through.
    assert evaluate(_listing(title="TAG 9 (905) Rayquaza V Alt Art", price=300, shipping=0), tight, [],
                    tag_near_margin=50) is not None


def test_regrade_lane_off_by_default_and_respects_min_price_floor():
    plain = Target(name="p", keywords=["rayquaza", "v"], max_price=900, graded_only=True, min_grade=10)
    assert evaluate(_listing(title="TAG 9 (945) Rayquaza V", price=300, shipping=0), plain, []) is None
    assert evaluate(_listing(title="PSA 9 Rayquaza V Alt Art", price=50, shipping=0), RAYQUAZA, []) is None


def test_grade_rules():
    graded = Target(name="g", keywords=["charizard"], max_price=5000, graded_only=True, min_grade=10)
    assert evaluate(_listing(title="PSA 9 Charizard", price=100), graded, []) is None
    assert evaluate(_listing(title="Charizard raw", price=100), graded, []) is None
    assert evaluate(_listing(title="PSA 10 Charizard", price=100), graded, []) is not None


def test_source_filter_and_missing_price():
    ebay_only = Target(name="e", keywords=["charizard"], max_price=500, sources=["ebay"])
    assert evaluate(_listing(source="facebook"), ebay_only, []) is None
    assert evaluate(_listing(price=None), CHARIZARD, []) is None


# ── watchlist persistence ────────────────────────────────────────────────────

def test_watchlist_roundtrip_and_example_creation(tmp_path):
    path = tmp_path / "wl.json"
    created = load_watchlist(str(path))
    assert path.exists() and created.targets
    add_target(str(path), Target(name="Umbreon", keywords=["umbreon", "vmax"], max_price=600, max_bid=620))
    reloaded = load_watchlist(str(path))
    umbreon = next(t for t in reloaded.targets if t.name == "Umbreon")
    assert umbreon.max_bid == 620 and umbreon.sources == ["ebay", "facebook"]
    assert umbreon.regrade is False
    ray = next(t for t in reloaded.targets if t.name.startswith("Rayquaza"))
    assert ray.regrade and ray.regrade_min_grade == 8.5
    data = json.loads(path.read_text())
    assert "global_exclude" in data and data["tag_ten_score"] == 950
    assert reloaded.tag_near_margin == 15


def test_watchlist_rejects_target_without_keywords(tmp_path):
    path = tmp_path / "wl.json"
    path.write_text(json.dumps({"targets": [{"name": "bad", "keywords": [], "max_price": 1}]}))
    with pytest.raises(ValueError):
        load_watchlist(str(path))


# ── store ────────────────────────────────────────────────────────────────────

def test_store_dedupes_and_tracks_bids():
    store = Store("sqlite://")
    listing = _listing()
    assert not store.is_seen(listing)
    store.record_listing(listing, None)
    assert store.is_seen(listing)

    match = evaluate(_listing(listing_type="auction", end_time=datetime.now(timezone.utc) + timedelta(hours=1)), CHARIZARD, [])
    fire_at = datetime.now(timezone.utc) + timedelta(minutes=59)
    bid = store.schedule_bid(match, 270, fire_at)
    assert bid is not None
    assert store.schedule_bid(match, 270, fire_at) is None  # no duplicate pending bid
    assert store.claim_bid(bid.id) and not store.claim_bid(bid.id)
    store.finish_bid(bid.id, "dry_run", "ok")
    assert store.all_bids()[0].status == "dry_run"


# ── runner ───────────────────────────────────────────────────────────────────

class FakeSource:
    def __init__(self, name, listings):
        self.name = name
        self.listings = listings
        self.calls = 0

    def find(self, target):
        self.calls += 1
        return list(self.listings)


class FakeNotifier:
    def __init__(self):
        self.deals = []
        self.infos = []
        self.scans = 0

    def begin_scan(self):
        self.scans += 1

    def end_scan(self):
        pass

    def deal(self, match):
        self.deals.append(match)

    def info(self, title, body):
        self.infos.append((title, body))


def test_notifier_caps_opens_and_notifications_per_scan(monkeypatch):
    from cardsnipe.notify import Notifier

    settings = _settings(notify_macos=True, open_in_browser=True, max_opens_per_scan=1, max_notifications_per_scan=2)
    notifier = Notifier(settings)
    notifier.is_mac = True
    opened, notified = [], []
    monkeypatch.setattr(notifier, "_open", lambda url: opened.append(url))
    monkeypatch.setattr(notifier, "_macos", lambda title, body: notified.append(title))
    notifier.begin_scan()
    for i in range(4):
        notifier.deal(evaluate(_listing(listing_id=str(i)), CHARIZARD, []))
    notifier.end_scan()
    assert len(opened) == 1
    assert len(notified) == 3  # 2 deal notifications + 1 "more deals" summary
    assert notified[-1] == "Card sniper"


def test_runner_alerts_once_schedules_bids_and_messages_in_dry_run():
    settings = _settings()
    end_time = datetime.now(timezone.utc) + timedelta(minutes=30)
    auction = _listing(listing_id="555", listing_type="auction", price=120.0, end_time=end_time)
    fb_deal = _listing(source="facebook", listing_id="fb1", price=150.0, shipping=None, url="https://www.facebook.com/marketplace/item/fb1/")
    overpriced = _listing(listing_id="777", price=400.0)
    sent = []

    def messenger(listing, text, live):
        sent.append((listing.listing_id, text, live))
        return "dry_run", "typed only"

    notifier = FakeNotifier()
    store = Store("sqlite://")
    runner = SnipeRunner(
        settings=settings,
        watchlist=Watchlist(targets=[CHARIZARD]),
        store=store,
        sources={"ebay": FakeSource("ebay", [auction, overpriced]), "facebook": FakeSource("facebook", [fb_deal])},
        notifier=notifier,
        messenger=messenger,
    )
    report = runner.scan_once()
    assert report.new_listings == 3 and len(report.deals) == 2 and report.bids_scheduled == 1
    assert sent == [("fb1", settings.fb_message_template, False)]
    pending = store.pending_bids()
    assert len(pending) == 1 and pending[0].max_bid == 270
    assert pending[0].fire_at == bid_fire_time(end_time, settings)

    # Second scan: nothing new, no duplicate alerts.
    report2 = runner.scan_once()
    assert report2.new_listings == 0 and report2.deals == [] and len(notifier.deals) == 2


def test_runner_skips_auctions_ending_too_soon_and_alert_only_targets():
    settings = _settings()
    soon = _listing(listing_id="1", listing_type="auction", price=50.0,
                    end_time=datetime.now(timezone.utc) + timedelta(seconds=2))
    alert_only = Target(name="alert", keywords=["charizard"], max_price=500)  # no max_bid
    store = Store("sqlite://")
    runner = SnipeRunner(settings, Watchlist(targets=[CHARIZARD]), store,
                         {"ebay": FakeSource("ebay", [soon])}, FakeNotifier())
    assert runner.scan_once().bids_scheduled == 0

    store2 = Store("sqlite://")
    later = _listing(listing_id="2", listing_type="auction", price=50.0,
                     end_time=datetime.now(timezone.utc) + timedelta(hours=1))
    runner2 = SnipeRunner(settings, Watchlist(targets=[alert_only]), store2,
                          {"ebay": FakeSource("ebay", [later])}, FakeNotifier())
    report = runner2.scan_once()
    assert len(report.deals) == 1 and report.bids_scheduled == 0


def test_fire_due_bids_claims_once_and_records_result():
    settings = _settings()
    store = Store("sqlite://")
    end_time = datetime.now(timezone.utc) + timedelta(seconds=BID_PREP_SECONDS + 10)
    match = evaluate(_listing(listing_type="auction", price=100.0, end_time=end_time), CHARIZARD, [])
    store.schedule_bid(match, 270, bid_fire_time(end_time, settings))
    executed = []

    def executor(bid):
        executed.append(bid.id)
        return "dry_run", "simulated"

    notifier = FakeNotifier()
    runner = SnipeRunner(settings, Watchlist(targets=[CHARIZARD]), store, {}, notifier, bid_executor=executor)
    # fire_at is in the past relative to a far-future "now", but the auction has not ended.
    results = runner.fire_due_bids(now=end_time - timedelta(seconds=5))
    assert len(results) == 1 and results[0][1] == "dry_run"
    assert executed == [results[0][0].id]
    assert runner.fire_due_bids(now=end_time - timedelta(seconds=4)) == []
    assert notifier.infos and "dry_run" in notifier.infos[0][0]


def test_fire_due_bids_fails_ended_auctions_without_executing():
    settings = _settings()
    store = Store("sqlite://")
    end_time = datetime.now(timezone.utc) + timedelta(minutes=5)
    match = evaluate(_listing(listing_type="auction", price=100.0, end_time=end_time), CHARIZARD, [])
    store.schedule_bid(match, 270, bid_fire_time(end_time, settings))
    runner = SnipeRunner(settings, Watchlist(targets=[CHARIZARD]), store, {}, FakeNotifier(),
                         bid_executor=lambda bid: pytest.fail("should not execute"))
    assert runner.fire_due_bids(now=end_time + timedelta(seconds=1)) == []
    assert store.all_bids()[0].status == "failed"


def test_source_errors_are_reported_not_raised():
    class Broken:
        name = "ebay"

        def find(self, target):
            raise RuntimeError("boom")

    runner = SnipeRunner(_settings(), Watchlist(targets=[CHARIZARD]), Store("sqlite://"), {"ebay": Broken()}, FakeNotifier())
    report = runner.scan_once()
    assert report.errors and "boom" in report.errors[0]


def test_cli_aliases_and_default_command(monkeypatch, tmp_path):
    import snipe

    calls = []
    for name in ("cmd_watch", "cmd_scan", "cmd_deals", "cmd_add", "cmd_list"):
        monkeypatch.setattr(snipe, name, lambda args, settings, _n=name: calls.append((_n, settings.live)) or 0)
    monkeypatch.setenv("SNIPE_WATCHLIST", str(tmp_path / "wl.json"))
    # Parsers are built after patching, so the patched functions are what get wired in.
    assert snipe.main([]) == 0 and calls[-1] == ("cmd_watch", False)
    assert snipe.main(["--live", "w"]) == 0 and calls[-1] == ("cmd_watch", True)
    assert snipe.main(["s"]) == 0 and calls[-1][0] == "cmd_scan"
    assert snipe.main(["d"]) == 0 and calls[-1][0] == "cmd_deals"
    assert snipe.main(["l"]) == 0 and calls[-1][0] == "cmd_list"


def test_cli_add_regrade_target_roundtrip(tmp_path, monkeypatch):
    import snipe

    monkeypatch.setenv("SNIPE_WATCHLIST", str(tmp_path / "wl.json"))
    monkeypatch.setenv("SNIPE_DATABASE_URL", "sqlite://")
    assert snipe.main(["a", "Moonbreon", "--min", "250", "--max", "550", "--max-bid", "600", "--regrade",
                       "--regrade-grades", "9", "9.5", "--keywords", "umbreon", "vmax", "alt art|215/203"]) == 0
    target = next(t for t in load_watchlist(str(tmp_path / "wl.json")).targets if t.name == "Moonbreon")
    assert target.regrade and target.regrade_min_grade == 9 and target.regrade_max_grade == 9.5
    assert target.min_price == 250 and target.max_bid == 600 and target.keywords[-1] == "alt art|215/203"


def test_settings_live_toggle_and_api_detection(monkeypatch):
    monkeypatch.setenv("EBAY_APP_ID", "id")
    monkeypatch.setenv("EBAY_CERT_ID", "cert")
    settings = SnipeSettings.from_env()
    assert settings.ebay_api_enabled and not settings.live
    assert settings.with_live(True).live


def test_ebay_api_listing_mapping():
    from cardsnipe.ebay import EbayBrowseAPI

    api = EbayBrowseAPI(_settings())
    item = {
        "itemId": "v1|334455667788|0",
        "title": "Charizard VMAX Rainbow",
        "price": {"value": "150.00", "currency": "CAD"},
        "currentBidPrice": {"value": "61.00", "currency": "CAD"},
        "buyingOptions": ["AUCTION"],
        "itemEndDate": "2026-11-01T18:00:00.000Z",
        "itemWebUrl": "https://www.ebay.ca/itm/334455667788",
        "shippingOptions": [{"shippingCost": {"value": "4.99", "currency": "CAD"}}],
        "itemLocation": {"city": "Toronto", "country": "CA"},
        "bidCount": 3,
    }
    listing = api._to_listing(item)
    assert listing.listing_id == "334455667788"
    assert listing.listing_type == "auction" and listing.price == 61.0 and listing.shipping == 4.99
    assert listing.end_time == datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)
    assert listing.location == "Toronto, CA"


def test_ebay_web_card_parsing():
    from cardsnipe.browser import Browser
    from cardsnipe.ebay import EbayWeb

    web = EbayWeb(_settings(), Browser(_settings()))
    row = {
        "id": "123456789012",
        "href": "https://www.ebay.ca/itm/123456789012",
        "text": "New Listing\nCharizard VMAX Rainbow Rare 074/073\nPre-Owned\nC $120.00\n3 bids · 2h 15m left\n+C $5.00 shipping",
        "img": "",
    }
    listing = web._parse_card(row, "auction")
    assert listing.title.startswith("Charizard VMAX")
    assert listing.price == 120.0 and listing.shipping == 5.0 and listing.bid_count == 3
    assert listing.listing_type == "auction" and listing.end_time is not None

    new_markup = {
        "id": "407309019578", "href": "https://www.ebay.ca/itm/407309019578", "img": "", "timeLeft": "",
        "text": "Pokemon CGC Pristine 10 Charizard VMAX 017/184\nOpens in a new window or tab\nNew (Other)\n"
                "C $33.00\n10 bids · \nTime left\n7m\n+C $39.01 shipping estimate\nfrom United Kingdom",
    }
    listing = web._parse_card(new_markup, "auction")
    assert listing.price == 33.0 and listing.shipping == 39.01 and listing.bid_count == 10
    delta = (listing.end_time - datetime.now(timezone.utc)).total_seconds()
    assert 6 * 60 < delta <= 7 * 60


def test_facebook_card_parsing():
    from cardsnipe.browser import Browser
    from cardsnipe.facebook import FacebookMarketplace

    fb = FacebookMarketplace(_settings(), Browser(_settings()))
    row = {"id": "987", "href": "https://www.facebook.com/marketplace/item/987/",
           "text": "CA$140\nCharizard VMAX rainbow rare champions path\nToronto, ON", "img": ""}
    listing = fb._parse_card(row)
    assert listing.price == 140.0 and listing.title.startswith("Charizard") and listing.location == "Toronto, ON"
    assert fb.search_url(CHARIZARD).startswith("https://www.facebook.com/marketplace/")
    assert "maxPrice=250" in fb.search_url(CHARIZARD)
