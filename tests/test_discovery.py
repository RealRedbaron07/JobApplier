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
        return [listing(item=str(len(searches) * 1000 + i), condition="Lightly Played") for i in range(100)]

    def facebook_search(self, target, *, all_dates):
        searches.append(target.search_query)
        assert all_dates and target.card_name == "" and not target.use_market
        return [listing("facebook", str(len(searches) * 1000 + i)) for i in range(100)]

    monkeypatch.setattr(discovery.EbayWeb, "search_page", ebay_search)
    monkeypatch.setattr(discovery.FacebookMarketplace, "find", facebook_search)
    report = discovery.DiscoveryScanner(settings, store, 45).scan()
    rows, scan = store.discovery_results()
    assert len(searches) == report["pages_done"] == 8
    assert len(rows) == report["candidates"] == report["scanned"] == 480
    assert report["new_listings"] == 480 and report["errors"] == []
    assert scan.kind == "broad" and scan.budget == 45 and scan.currency == "CAD"
    assert scan.deals == 0 and scan.bids_scheduled == 0 and not scan.live
    assert all(row.market_value is None and row.matched_target is None for row in rows)
    assert any(row.condition == "Lightly Played" and row.shipping is None for row in rows)
    assert all("coupon" in row.promotion for row in rows)
    assert len(opened) == 1 and opened[0].closed


def test_broad_scan_deduplicates_and_preserves_routes_without_fake_discount_math(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [listing()])
    report = discovery.DiscoveryScanner(settings, store, 45).scan("ebay")
    rows, _ = store.discovery_results()
    assert report["scanned"] == 6 and report["candidates"] == report["new_listings"] == 1
    assert len(rows) == 1 and len(json.loads(rows[0].discovery_routes)) == 6
    assert rows[0].savings_pct is None and rows[0].market_value is None


def test_one_blocked_source_does_not_repeat_or_discard_other_source_results(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    attempts = []

    def blocked(*args):
        attempts.append("ebay")
        raise discovery.SourceUnavailable("eBay requires browser verification")

    monkeypatch.setattr(discovery.EbayWeb, "search_page", blocked)
    monkeypatch.setattr(discovery.FacebookMarketplace, "find", lambda *a, **kw: [listing("facebook")])
    report = discovery.DiscoveryScanner(settings, store, 45).scan()
    assert attempts == ["ebay"] and report["pages_done"] == 3
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
    report = discovery.DiscoveryScanner(settings, store, 45).scan("ebay")
    assert len(attempts) == 4 and report["candidates"] == 1 and len(report["errors"]) == 3


def test_stop_and_budget_are_enforced_without_hiding_unknown_prices(browser_scan, monkeypatch):
    settings, store, opened = browser_scan
    stop = threading.Event()

    def search(*args):
        stop.set()
        return [listing(item="1", price=46), listing(item="2", price=None), listing(item="3", currency="USD")]

    monkeypatch.setattr(discovery.EbayWeb, "search_page", search)
    report = discovery.DiscoveryScanner(settings, store, 45, stop=stop).scan()
    rows, _ = store.discovery_results()
    assert report["stopped"] and report["pages_done"] == 1 and len(rows) == 1
    assert rows[0].listing_id == "2" and rows[0].price is None
    assert opened[0].closed


def test_browser_scan_flag_blocks_all_work(browser_scan, monkeypatch):
    settings, store, opened = browser_scan
    monkeypatch.setattr(Config, "BROWSER_SCANS_ENABLED", False)
    with pytest.raises(ValueError, match="disabled"):
        discovery.DiscoveryScanner(settings, store, 45).scan()
    assert not opened


def test_empty_new_scan_does_not_present_old_results_as_fresh(browser_scan, monkeypatch):
    settings, store, _ = browser_scan
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [listing()])
    discovery.DiscoveryScanner(settings, store, None).scan("ebay")
    assert len(store.discovery_results()[0]) == 1
    monkeypatch.setattr(discovery.EbayWeb, "search_page", lambda *a: [])
    discovery.DiscoveryScanner(settings, store, None).scan("ebay")
    assert store.discovery_results()[0] == []


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
    discovery.DiscoveryScanner(settings, store, 45).scan("ebay")
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
    scanner = discovery.DiscoveryScanner(settings, store, 45)
    scanner.scan("ebay")
    row = store.discovery_results()[0][0]
    assert store.dismiss_listing(row.id)
    report = scanner.scan("ebay")
    assert report["candidates"] == 0 and store.discovery_results()[0] == []


def test_one_click_broad_endpoint_runs_with_an_empty_watchlist_and_cannot_launch_duplicates(snipe_client, monkeypatch):
    import dashboard.snipe_views as views

    client, store, path = snipe_client
    save_watchlist(path, Watchlist(targets=[], budget=45))
    monkeypatch.setattr(Config, "EXTERNAL_ACCESS_ENABLED", False)
    started, release = threading.Event(), threading.Event()

    class Scanner:
        def __init__(self, settings, actual_store, budget, *, stop, progress):
            assert actual_store is store and budget == 45

        def scan(self, source):
            assert source == "all"
            started.set()
            assert release.wait(2)
            return {"message": "Finished: 1 candidate saved", "errors": [], "candidates": 1}

    monkeypatch.setattr(views, "DiscoveryScanner", Scanner)
    try:
        response = client.post("/api/snipe/discovery/scan", json={"source": "all", "live": True, "max_searches": 9999})
        assert response.status_code == 202 and response.get_json()["max_searches"] == 8
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
