from dataclasses import replace
from datetime import datetime, timezone
import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from cardsnipe import discovery
from cardsnipe.matcher import Listing
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import Store
from cardsnipe.watchlist import Watchlist, save_watchlist
from config import Config
from test_snipe_dashboard import snipe_client


def listing(source="ebay", item="12345678901", **changes):
    values = dict(source=source, listing_id=item, title="Any Pokémon card", price=20, currency="CAD",
                  shipping=None, url=f"https://www.ebay.ca/itm/{item}" if source == "ebay"
                  else f"https://www.facebook.com/marketplace/item/{item}/", raw={"text": "10% off 3+ with coupon"})
    values.update(changes)
    return Listing(**values)


@pytest.mark.parametrize("title,is_lot", [
    ("Pokemon cards lot of 20", True), ("Bulk Pokemon binder", True),
    ("Pokemon card collection", True), ("Collection of Pokemon cards", True),
    ("Pokemon Cards", True), ("Pokemon Singles For Sale", True),
    ("Pokemon Starmie CGC 9 and Eevee PSA 8 Graded Cards", True),
    ("Pokemon Card Hits", True), ("Pokemon Single Packs", True),
    ("Looking to trade 30th ETB", True),
    ("Lost Origin Charizard single", False), ("Ultra Premium Collection sealed box", False),
    ("Pokemon booster bundle sealed", False),
    ("Pokemon Cards - Mega Charizard ex PFL 125/094", False),
])
def test_lot_filter_preserves_individual_and_sealed_products(title, is_lot):
    assert discovery.is_lot_listing(title) is is_lot


def test_marketplace_placeholder_prices_and_location_only_titles_are_excluded():
    assert not discovery.is_discovery_candidate(listing("facebook", title="Pokemon Cards", price=20))
    assert not discovery.is_discovery_candidate(listing("facebook", title="Markham, ON", price=20))
    assert not discovery.is_discovery_candidate(listing("facebook", title="Charizard ex 125/094", price=1))
    assert not discovery.is_discovery_candidate(listing("facebook", title="Pokemon vintage", price=500))
    assert not discovery.is_discovery_candidate(listing("facebook", title="Pikachu booster pack pre-order", price=12))
    assert discovery.is_discovery_candidate(listing("facebook", title="Charizard ex 125/094", price=40))


def test_auction_searches_run_first_without_specific_card_targets():
    plan = discovery.search_plan()
    assert len(plan) == discovery.MAX_SEARCHES == 17
    assert [(name, mode) for name, mode, _ in plan[:3]] == [("ebay", "auction")] * 3
    assert [name for name, _, _ in plan[3:6]] == ["facebook"] * 3
    assert all("pokemon" in query for _, _, query in plan)


def test_lots_are_not_saved_or_returned_as_discovery_results(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [
        listing(item="lot", title="Pokemon card lot of 20"),
        listing(item="single", title="Charizard single card"),
    ])
    discovery.DiscoveryScanner(settings, store).scan("ebay")
    assert [row.title for row in store.discovery_results()[0]] == ["Charizard single card"]


@pytest.fixture
def browser_scan(monkeypatch):
    settings = replace(SnipeSettings.from_env(), ebay_app_id="unused-key", ebay_cert_id="unused-secret",
                       fb_auto_message=True, live=True, webhook_url="https://never-call.invalid")
    opened = []

    class Browser:
        def __init__(self, settings):
            self.closed = False
            opened.append(self)
            assert not settings.ebay_api_enabled and not settings.live
            assert not settings.fb_auto_message and not settings.notify_macos and not settings.webhook_url

        def quit(self):
            self.closed = True

    monkeypatch.setattr(discovery, "Browser", Browser)
    monkeypatch.setattr(discovery, "PAGE_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(Config, "BROWSER_SCANS_ENABLED", True)
    return settings, Store("sqlite://"), opened


def test_broad_scan_is_bounded_and_imports_without_targets_prices_or_condition_filters(browser_scan, monkeypatch):
    settings, store, opened = browser_scan
    searches = []

    def ebay_search(self, url, kind, limit):
        searches.append(url)
        assert limit == 60
        assert "LH_BIN" not in parse_qs(urlsplit(url).query)
        assert "_udhi" not in parse_qs(urlsplit(url).query)
        return [listing(item=str(len(searches) * 1000 + i), condition="Lightly Played") for i in range(100)]

    def facebook_search(self, target, *, all_dates):
        searches.append(target.search_query)
        assert all_dates and target.card_name == "" and not target.use_market and target.max_price is None
        return [listing("facebook", str(len(searches) * 1000 + i)) for i in range(100)]

    monkeypatch.setattr(discovery.EbayWeb, "search_page", ebay_search)
    monkeypatch.setattr(discovery.FacebookMarketplace, "find", facebook_search)
    report = discovery.DiscoveryScanner(settings, store).scan()
    rows, scan = store.discovery_results()
    assert len(searches) == report["pages_done"] == 17
    assert len(rows) == report["candidates"] == report["scanned"] == 17 * 60
    assert report["new_listings"] == 17 * 60 and report["errors"] == []
    assert scan.kind == "broad" and scan.budget is None and scan.currency == "CAD"
    assert scan.deals == 0 and scan.bids_scheduled == 0 and not scan.live
    assert all(row.market_value is None and row.matched_target is None for row in rows)
    assert any(row.condition == "Lightly Played" and row.shipping is None for row in rows)
    assert all("coupon" in row.promotion for row in rows)
    assert len(opened) == 1 and opened[0].closed


def test_broad_scan_deduplicates_and_preserves_routes_without_fake_discount_math(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [listing()])
    report = discovery.DiscoveryScanner(settings, store).scan("ebay")
    rows, _ = store.discovery_results()
    assert report["scanned"] == 7 and report["candidates"] == report["new_listings"] == 1
    assert len(rows) == 1 and len(json.loads(rows[0].discovery_routes)) == 7
    assert rows[0].savings_pct is None and rows[0].market_value is None


def test_broad_scan_prices_exact_single_without_a_paid_api(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    card = listing("facebook", title="Lugia VSTAR 139/195 Silver Tempest", price=5, shipping=0)
    monkeypatch.setattr(discovery.FacebookMarketplace, "find", lambda *a, **kw: [card])
    monkeypatch.setattr(discovery, "bank_of_canada_usd_cad", lambda browser: 1.4)
    monkeypatch.setattr(discovery, "tcgplayer_market", lambda browser, title, claim=None: {"price": 10, "name": "Lugia VSTAR"})
    report = discovery.DiscoveryScanner(settings, store).scan("facebook")
    row = store.discovery_results()[0][0]
    assert report["priced"] == report["bargains"] == 1
    assert row.market_value == 14 and row.savings_pct == pytest.approx((14 - 5) / 14 * 100)
    assert row.matched_target is None and store.recent_deals() == []
    assert row.value_source.startswith("TCGplayer") and "plain print" in row.value_source
    store.revalue(lambda listing: None)
    assert store.discovery_results()[0][0].market_value == 14


def test_removed_find_is_not_repriced_or_counted_as_a_bargain(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    card = listing("facebook", title="Lugia VSTAR 139/195 Silver Tempest", price=5, shipping=0)
    row = store.record_listing(card, None)
    store.dismiss_listing(row.id)
    monkeypatch.setattr(discovery.FacebookMarketplace, "find", lambda *a, **kw: [card])
    monkeypatch.setattr(discovery, "bank_of_canada_usd_cad", lambda browser: pytest.fail("dismissed find was repriced"))
    report = discovery.DiscoveryScanner(settings, store).scan("facebook")
    assert report["candidates"] == report["priced"] == report["bargains"] == 0
    assert store.discovery_results()[0] == []


def test_one_blocked_source_does_not_repeat_or_discard_other_source_results(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    attempts = []

    def blocked(*args):
        attempts.append("ebay")
        raise discovery.SourceUnavailable("eBay requires browser verification")

    monkeypatch.setattr(discovery.EbayWeb, "search_page", blocked)
    monkeypatch.setattr(discovery.FacebookMarketplace, "find", lambda *a, **kw: [listing("facebook")])
    report = discovery.DiscoveryScanner(settings, store).scan()
    assert attempts == ["ebay"] and report["pages_done"] == 11
    assert len(report["errors"]) == 1 and report["candidates"] == 1
    assert store.discovery_results()[0][0].source == "facebook"


def test_transient_query_error_does_not_drop_other_categories_but_two_failures_stop_source(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    attempts = []

    def search(self, url, *args):
        attempts.append(url)
        if len(attempts) in {1, 3, 4}:
            raise RuntimeError("Temporary server error")
        return [listing()]

    monkeypatch.setattr(discovery.EbayWeb, "search_page", search)
    report = discovery.DiscoveryScanner(settings, store).scan("ebay")
    assert len(attempts) == 4 and report["candidates"] == 1 and len(report["errors"]) == 3


def test_stop_keeps_all_prices_without_shared_budget_cap(browser_scan, monkeypatch):
    settings, store, opened = browser_scan
    stop = threading.Event()

    def search(*args):
        stop.set()
        return [listing(item="1", price=46), listing(item="2", price=None), listing(item="3", currency="USD")]

    monkeypatch.setattr(discovery.EbayWeb, "search_page", search)
    report = discovery.DiscoveryScanner(settings, store, stop=stop).scan("ebay")
    rows, _ = store.discovery_results()
    assert report["stopped"] and report["pages_done"] == 1 and len(rows) == 2
    assert {row.listing_id for row in rows} == {"1", "2"}
    assert next(row for row in rows if row.listing_id == "2").price is None
    assert opened[0].closed


def test_browser_scan_flag_blocks_all_work(browser_scan, monkeypatch):
    settings, store, opened = browser_scan
    monkeypatch.setattr(Config, "BROWSER_SCANS_ENABLED", False)
    with pytest.raises(ValueError, match="disabled"):
        discovery.DiscoveryScanner(settings, store).scan()
    assert not opened


def test_empty_new_scan_keeps_unremoved_finds_with_their_older_timestamp(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [listing()])
    discovery.DiscoveryScanner(settings, store).scan("ebay")
    previous = store.discovery_results()[0][0].discovery_at
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [])
    discovery.DiscoveryScanner(settings, store).scan("ebay")
    rows, latest = store.discovery_results()
    assert len(rows) == 1 and rows[0].discovery_at == previous < latest.started


def test_failed_source_keeps_earlier_candidates_with_their_original_scan_time(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [listing(item="ebay-one")])
    discovery.DiscoveryScanner(settings, store).scan("ebay")
    previous = store.discovery_results()[0][0].discovery_at
    def blocked(*args):
        raise discovery.SourceUnavailable("eBay unavailable")

    monkeypatch.setattr(discovery.EbayWeb, "search_page", blocked)
    monkeypatch.setattr(discovery.FacebookMarketplace, "find", lambda *a, **kw: [listing("facebook", "fb-one")])
    discovery.DiscoveryScanner(settings, store).scan()
    rows, latest = store.discovery_results()
    assert {row.source for row in rows} == {"ebay", "facebook"}
    assert next(row for row in rows if row.source == "ebay").discovery_at == previous < latest.started
    assert next(row for row in rows if row.source == "facebook").discovery_at == latest.started


def test_server_error_retries_via_real_homepage_search_bar_without_claiming_sale_filters(monkeypatch):
    class SearchBox:
        def clear(self):
            pass

        def send_keys(self, value):
            if value == "\ue007":
                browser.results = True
            else:
                browser.typed = value

    class Browser:
        results = False
        urls = []

        def get(self, url):
            self.urls.append(url)

        def find_first(self, selectors):
            return SearchBox()

        def wait_until(self, predicate, timeout):
            predicate()
            return True

        def page_text(self):
            return "Results" if self.results else "Something went wrong on our end"

        def js(self, script):
            if script != discovery.EbayWeb.EXTRACT_JS:
                return True
            return [{"id": "12345678901", "href": "https://www.ebay.ca/itm/12345678901",
                     "text": "Pokemon sealed box\nC $20.00\nFree shipping", "price": "C $20.00"}] if self.results else []

    monkeypatch.setattr("cardsnipe.ebay.time.sleep", lambda seconds: None)
    browser = Browser()
    web = discovery.EbayWeb(SnipeSettings.from_env(), browser)
    rows = web.search_page("https://www.ebay.ca/sch/i.html?_nkw=pokemon+sealed&LH_SaleItems=1", "all", 60)
    assert len(rows) == 1 and browser.typed == "pokemon sealed"
    assert browser.urls == ["https://www.ebay.ca/sch/i.html?_nkw=pokemon+sealed&LH_SaleItems=1", "https://www.ebay.ca/"]
    assert web.used_home_search and rows[0].price == 20


def test_homepage_retry_is_not_mislabelled_as_a_confirmed_promotion(browser_scan, monkeypatch):
    settings, store, _ = browser_scan

    def retry(self, *args):
        self.used_home_search = True
        return [listing(raw={"text": "Pokemon card"})]

    monkeypatch.setattr(discovery.EbayWeb, "search_page", retry)
    discovery.DiscoveryScanner(settings, store).scan("ebay")
    row = store.discovery_results()[0][0]
    assert row.promotion == ""
    assert all(route.startswith("search-bar retry (unfiltered):") for route in json.loads(row.discovery_routes))


@pytest.mark.parametrize("text,shipping", [
    ("+C $15.00 shipping · Free returns", 15),
    ("C $20.00 +C $15.00 shipping · Free returns", 15),
    ("Free 4-day shipping · Free returns", 0),
    ("Free returns; shipping calculated at checkout", None),
])
def test_shipping_is_not_mistaken_for_free_returns(text, shipping):
    web = discovery.EbayWeb(SnipeSettings.from_env(), None)
    row = web._parse_card({"id": "12345678901", "href": "https://www.ebay.ca/itm/12345678901",
                           "text": "Pokemon card\n" + text, "price": "C $20.00"}, "all")
    assert row.shipping == shipping


def test_removed_candidates_stay_removed_and_are_not_counted_as_available(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [listing()])
    scanner = discovery.DiscoveryScanner(settings, store)
    scanner.scan("ebay")
    row = store.discovery_results()[0][0]
    assert store.dismiss_listing(row.id)
    report = scanner.scan("ebay")
    assert report["candidates"] == 0 and store.discovery_results()[0] == []


def test_saved_price_check_advances_past_unmatched_cards_and_keeps_removed_out(browser_scan, monkeypatch):
    settings, store, opened = browser_scan
    started = datetime.now(timezone.utc)
    for item in range(3):
        row = store.record_listing(listing("facebook", str(item),
                                           title=f"Pikachu 025/165 Pokemon 151 card {item}", price=10, shipping=0),
                                   None, discovery_at=started)
        if item == 2:
            store.dismiss_listing(row.id)
    store.record_scan(started, started, ["facebook"], False, 3, 3, 0, 0, 0, [], kind="broad")
    monkeypatch.setattr(discovery, "bank_of_canada_usd_cad", lambda browser: 1.4)
    checked = []
    def product(browser, title, claim=None):
        checked.append(title)
        return {"price": 20} if title.endswith("0") else None
    monkeypatch.setattr(discovery, "tcgplayer_market", product)
    safe_settings = replace(settings, ebay_app_id="", ebay_cert_id="", live=False, fb_auto_message=False,
                            notify_macos=False, webhook_url="")
    first = discovery.price_saved_singles(safe_settings, store)
    second = discovery.price_saved_singles(safe_settings, store)
    rows, _ = store.discovery_results()
    assert first["checked"] == 2 and first["priced"] == first["bargains"] == 1
    assert second["checked"] == 0 and len(checked) == 2 and len(opened) == 1 and opened[0].closed
    assert len(rows) == 2 and all(row.price_checked_at for row in rows)


def test_saved_price_stays_on_unchanged_listing_and_resets_when_ask_changes(browser_scan):
    _, store, _ = browser_scan
    started = datetime.now(timezone.utc)
    original = listing(title="Pikachu 025/165 Pokemon 151 card", price=10)
    row = store.record_listing(original, None, discovery_at=started)
    assert store.set_discovery_price(row.id, 14, "browser")
    same = store.record_listing(original, None, discovery_at=started)
    assert same.market_value == 14 and same.price_checked_at is not None
    changed = store.record_listing(listing(title=original.title, price=12), None, discovery_at=started)
    assert changed.market_value is None and changed.price_checked_at is None


def test_saved_price_check_endpoint_is_bounded_and_blocks_duplicate_scan(snipe_client, monkeypatch):
    import dashboard.snipe_views as views

    client, _, _ = snipe_client
    monkeypatch.setattr(Config, "BROWSER_SCANS_ENABLED", True)
    started, release = threading.Event(), threading.Event()
    def check(settings, store, *, stop, progress):
        started.set()
        assert release.wait(2)
        return {"message": "Checked 1 saved single", "checked": 1, "priced": 1, "bargains": 0, "errors": []}
    monkeypatch.setattr(views, "price_saved_singles", check)
    try:
        assert client.post("/api/snipe/discovery/price-check").status_code == 202
        assert started.wait(2)
        assert client.post("/api/snipe/discovery/price-check").status_code == 409
        assert client.post("/api/snipe/discovery/stop").status_code == 202
    finally:
        release.set()
        deadline = time.monotonic() + 2
        while views._scan_state["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
    assert client.get("/api/snipe/discovery/scan").get_json()["checked"] == 1


def test_one_click_broad_endpoint_runs_with_an_empty_watchlist_and_cannot_launch_duplicates(snipe_client, monkeypatch):
    import dashboard.snipe_views as views

    client, store, path = snipe_client
    save_watchlist(path, Watchlist(targets=[], budget=45))
    monkeypatch.setattr(Config, "EXTERNAL_ACCESS_ENABLED", False)
    started, release = threading.Event(), threading.Event()

    class Scanner:
        def __init__(self, settings, actual_store, *, stop, progress):
            assert actual_store is store

        def scan(self, source):
            assert source == "all"
            started.set()
            assert release.wait(2)
            return {"message": "Finished: 1 candidate saved", "errors": [], "candidates": 1}

    monkeypatch.setattr(views, "DiscoveryScanner", Scanner)
    try:
        response = client.post("/api/snipe/discovery/scan", json={"source": "all", "live": True, "max_searches": 9999})
        assert response.status_code == 202 and response.get_json()["max_searches"] == 17
        assert not response.get_json()["paid_apis_enabled"] and started.wait(2)
        assert client.post("/api/snipe/discovery/scan", json={}).status_code == 409
        assert client.post("/api/snipe/discovery/stop").status_code == 202
        assert views._discovery_stop.is_set()
    finally:
        release.set()
        deadline = time.monotonic() + 2
        while views._scan_state["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
    assert not client.get("/api/snipe/discovery/scan").get_json()["running"]
    assert client.post("/api/snipe/valuations/refresh").status_code == 403


def test_cooldown_survives_app_state_reset_and_invalid_sources_cannot_expand_it(snipe_client, monkeypatch):
    client, store, _ = snipe_client
    monkeypatch.setattr(Config, "EXTERNAL_ACCESS_ENABLED", False)
    now = datetime.now(timezone.utc)
    store.record_scan(now, now, ["ebay"], False, 0, 0, 0, 0, 0, [], kind="broad")
    assert client.post("/api/snipe/discovery/scan", json={"source": "all"}).status_code == 429
    for source in ("tcgplayer", "https://elsewhere.invalid", [], True):
        assert client.post("/api/snipe/discovery/scan", json={"source": source}).status_code == 400


def test_search_plan_targets_priceable_cards_not_sealed_or_bulk():
    plan = discovery.search_plan()
    assert not any("sealed" in query for _, _, query in plan)
    assert ("ebay", "auction", "psa 9 pokemon") in plan


def test_rare_cards_are_price_checked_before_bulk_commons():
    titles = ["Baltoy 144/264 Common Fusion Strike NM", "Charizard GX 9/68 Holo Hidden Fates", "Togekiss 085/197 Rare"]
    prices = {titles[0]: 15, titles[1]: 17, titles[2]: 19}
    assert discovery.pick_candidates(titles, str, prices.get) == [titles[1], titles[2], titles[0]]


def test_price_checks_take_auctions_about_to_end_first_and_skip_later_ones():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from cardsnipe.discovery import order_checks
    now = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)

    def item(title, kind="bin", minutes=None, price=50):
        return SimpleNamespace(title=title, listing_type=kind, total_price=price,
                               end_time=None if minutes is None else now + timedelta(minutes=minutes))

    later = item("Charizard 4/102 Base Set Holo PSA 9", "auction", 300)
    soon = item("Blastoise 2/102 Base Set Holo PSA 8", "auction", 50)
    sooner = item("Venusaur 15/102 Base Set Holo", "auction", 10)
    gone = item("Mewtwo 10/102 Base Set Holo", "auction", -1)
    unknown = item("Ninetales 12/102 Base Set Holo", "auction")
    bin_card = item("Gyarados 6/102 Base Set Holo")
    picked = order_checks([later, bin_card, soon, gone, unknown, sooner], lambda i: i.title,
                          lambda i: i.total_price, now=now)
    assert picked == [sooner, soon, bin_card]


def test_results_drop_ended_auctions_and_stale_finds():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from cardsnipe.store import _current
    now = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
    row = lambda **kw: SimpleNamespace(**{"listing_type": "bin", "end_time": None, "discovery_at": None,
                                         "market_value": None, "last_seen": now - timedelta(hours=1), **kw})
    assert _current(row(), now)
    # Unpriced finds leave after 6 hours, priced ones after 24.
    assert not _current(row(last_seen=now - timedelta(hours=7)), now)
    assert _current(row(last_seen=now - timedelta(hours=7), market_value=40), now)
    assert not _current(row(last_seen=now - timedelta(hours=30), market_value=40), now)
    assert not _current(row(listing_type="auction", end_time=(now - timedelta(minutes=1)).replace(tzinfo=None)), now)
    assert _current(row(listing_type="auction", end_time=now + timedelta(minutes=20)), now)


def test_a_new_bid_keeps_the_auctions_price_and_a_missing_countdown_keeps_its_end_time(tmp_path):
    from datetime import datetime, timedelta, timezone
    from cardsnipe.matcher import Listing
    from cardsnipe.store import Store
    store = Store(f"sqlite:///{tmp_path / 't.db'}")
    now = datetime.now(timezone.utc)
    end = now + timedelta(minutes=40)

    def seen(bid, end_time):
        return store.record_listing(Listing(source="ebay", listing_id="1", title="Snorlax 158/214 PSA 8", price=bid,
                                            currency="CAD", url="u", listing_type="auction", shipping=0, end_time=end_time),
                                    None, discovery_at=now, discovery_routes=[], promotion="")

    row = seen(50.0, end)
    assert store.set_discovery_price(row.id, 200.0, "TCGplayer plain print + PriceCharting, sales checked")
    row = seen(80.0, None)
    assert row.market_value == 200.0 and row.price_checked_at is not None and row.savings_pct == 60.0
    assert row.end_time is not None


def _captured(**over):
    return {"id": "287710142453", "href": "https://www.ebay.ca/itm/287710142453", "title": "Pokemon Snorlax 158/214 PSA 8",
            "text": "Pokemon Snorlax 158/214 PSA 8\nC $93.12\n3 bids\nFree shipping", "price": "C $93.12",
            "timeLeft": "23m", "img": "", **over}


def test_a_page_the_user_sends_is_saved_with_its_countdown(tmp_path):
    from datetime import datetime, timezone
    from cardsnipe.store import Store
    settings = SnipeSettings.from_env()
    store = Store(f"sqlite:///{tmp_path / 'c.db'}")
    store.record_scan(started=datetime.now(timezone.utc), finished=datetime.now(timezone.utc), sources=["ebay"], live=False,
                      scanned=0, new_listings=0, deals=0, regrade_deals=0, bids_scheduled=0, errors=[], kind="broad",
                      budget=None, currency="CAD")
    rows = [_captured(), _captured(id="abc"), _captured(id="287710142454", href="https://evil.example/itm/287710142454"), "junk"]
    ids, saved = discovery.save_captured_page(settings, store, rows, "psa 8 pokemon", auction=True)
    assert saved == 1 and len(ids) == 1
    row = store.discovery_results()[0][0]
    assert row.listing_type == "auction" and row.end_time is not None and row.total_price == 93.12
    assert "your eBay page: psa 8 pokemon" in row.discovery_routes


def test_capture_bookmarklet_is_a_local_only_javascript_link():
    from urllib.parse import unquote
    link = discovery.capture_bookmarklet("http://127.0.0.1:5050/")
    assert link.startswith("javascript:") and " " not in link and "\n" not in link
    code = unquote(link)
    assert "http://127.0.0.1:5050/snipe/capture" in code and "LH_Auction" in code


def test_old_cards_are_found_by_name_when_the_number_search_misses(monkeypatch):
    from cardsnipe import bargains
    title = "Dark Blastoise 3/82 Holo Rare Team Rocket Pokémon TCG 1999 WOTC"
    assert bargains.name_query(title) == "Dark Blastoise Team Rocket"
    card = {"name": "Dark Blastoise (3)", "set": "Team Rocket", "number": "#03/82", "price": 215.06, "url": ""}
    searches = []
    monkeypatch.setattr(bargains, "_search_products",
                        lambda browser, query: searches.append(query) or ([card] if query != "3/82" else []))
    assert bargains.tcgplayer_market(None, title) == card
    assert searches == ["3/82", "Dark Blastoise Team Rocket"]


def test_titles_without_a_number_need_one_card_matching_name_and_set():
    from cardsnipe import bargains
    magneton = {"name": "Magneton", "set": "Base Set", "number": "#009/102", "price": 30.0, "url": ""}
    gyarados = {"name": "Gyarados EX", "set": "XY - BREAKpoint", "number": "#114/122", "price": 40.0, "url": ""}
    assert bargains.pick_product([magneton], "1999 Pokemon Base Set Magneton Holo")["matched_by"] == "name and set"
    assert bargains.pick_product([gyarados], "2016 XY Breakpoint Gyarados EX #114")["number"] == "#114/122"
    assert bargains.pick_product([gyarados], "XY Breakpoint Gyarados EX #99") is None
    assert bargains.pick_product([magneton], "Magneton Holo card") is None  # no set named
    assert bargains.pick_product([magneton, {**magneton, "number": "#26/102"}], "Base Set Magneton") is None
