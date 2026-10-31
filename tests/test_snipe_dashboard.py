"""Card sniper dashboard: scan history persistence + /snipe API over an in-memory store."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import threading
import time

import pytest

from cardsnipe.matcher import Listing
from cardsnipe.runner import ScanReport, SnipeRunner, scanner_session
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import Store
from cardsnipe.watchlist import Target, Watchlist, load_watchlist, save_watchlist

# Wants a PSA 10 but will consider a PSA 8–9.5 as a crack-and-regrade candidate.
ZARD = Target(name="Zard", keywords=["charizard", "vmax"], max_price=250, max_bid=270,
              graded_only=False, min_grade=10, regrade=True)


def _listing(**overrides) -> Listing:
    values = dict(
        source="ebay", listing_id="1", title="Pokemon Charizard VMAX 074/073 NM", price=180.0,
        currency="CAD", url="https://www.ebay.ca/itm/1", listing_type="bin", shipping=5.0,
    )
    values.update(overrides)
    return Listing(**values)


class Source:
    def __init__(self, listings, error=None):
        self.listings, self.error = listings, error

    def find(self, target):
        if self.error:
            raise RuntimeError(self.error)
        return list(self.listings)


class Quiet:
    def deal(self, match):
        pass

    def info(self, title, body):
        pass


def _settings(**overrides) -> SnipeSettings:
    base = SnipeSettings.from_env()
    return replace(base, database_url="sqlite://", notify_macos=False, open_in_browser=False, webhook_url="",
                   fb_auto_message=False, live=False, **overrides)


@pytest.fixture
def snipe_client(tmp_path, monkeypatch):
    import dashboard.app as dashboard_app
    import dashboard.snipe_views as views
    # Legacy scanner tests exercise fakes; the real app keeps this hard-disabled.
    monkeypatch.setattr(dashboard_app.Config, "EXTERNAL_ACCESS_ENABLED", True)

    store = Store("sqlite://")
    views.set_store(store)
    watchlist_path = str(tmp_path / "watchlist.json")
    save_watchlist(watchlist_path, Watchlist(targets=[ZARD]))
    monkeypatch.setenv("SNIPE_WATCHLIST", watchlist_path)
    monkeypatch.setenv("SNIPE_CHROME_PROFILE", str(tmp_path / "chrome"))
    monkeypatch.setenv("EBAY_CURRENCY", "CAD")
    monkeypatch.setattr(views, "_scan_state", {"running": False, "started": None, "message": "No dashboard scan started.", "errors": []})
    views._facebook_login_action.clear()
    dashboard_app.app.config.update(TESTING=True)
    yield dashboard_app.app.test_client(), store, watchlist_path
    views.set_store(None)


@pytest.mark.parametrize("path", [
    "/api/snipe/scan", "/api/snipe/facebook/login", "/api/snipe/facebook/login/finish",
    "/api/snipe/valuations/refresh", "/api/snipe/collection/sync", "/api/snipe/collection/revalue",
])
def test_local_only_blocks_external_actions_before_any_work(snipe_client, monkeypatch, path):
    from config import Config
    from cardsnipe.browser import Browser
    import dashboard.snipe_views as views
    import snipe

    monkeypatch.setattr(Config, "EXTERNAL_ACCESS_ENABLED", False)
    monkeypatch.setattr(Config, "BROWSER_SCANS_ENABLED", False)
    monkeypatch.setenv("EXTERNAL_ACCESS_ENABLED", "true")
    monkeypatch.setattr(snipe, "_build_runner", lambda *a: pytest.fail("No scanner may start"))
    monkeypatch.setattr(Browser, "get", lambda *a: pytest.fail("No scanner browser may open"))
    monkeypatch.setattr(views.PriceService, "refresh", lambda *a: pytest.fail("No price provider may run"))
    response = snipe_client[0].post(path, json={"source": "all", "external_access_enabled": True})
    assert response.status_code == 403
    assert response.get_json()["local_only"] is True


def test_local_only_views_and_saved_revalue_never_fetch_sources_or_fx(snipe_client, monkeypatch):
    from config import Config
    import dashboard.snipe_views as views

    monkeypatch.setattr(Config, "EXTERNAL_ACCESS_ENABLED", False)
    monkeypatch.setattr(Config, "BROWSER_SCANS_ENABLED", False)
    monkeypatch.setattr(views, "usd_rate", lambda *a: pytest.fail("No live FX lookup"))
    monkeypatch.setattr(views.PriceService, "refresh", lambda *a: pytest.fail("No live prices"))
    client, _, _ = snipe_client
    for path in ("/snipe", "/api/snipe/summary", "/api/snipe/collection", "/api/snipe/valuations",
                 "/api/snipe/watchlist", "/api/snipe/discovery", "/api/snipe/scan", "/api/snipe/scans",
                 "/api/snipe/deals", "/api/snipe/listings", "/api/snipe/bids"):
        assert client.get(path).status_code == 200, path
    assert client.post("/api/snipe/revalue").status_code == 200
    collection = client.get("/api/snipe/collection").get_json()
    assert collection["local_only"] and collection["fx_estimated"]
    assert client.get("/api/health").get_json()["external_access_enabled"] is False
    page = client.get("/snipe").get_data(as_text=True)
    assert "Local-only · no external calls" in page and "Open eBay home" in page
    assert 'id="scan-source"' not in page


def test_local_only_blocks_workers_even_without_an_http_request(snipe_client, monkeypatch):
    from config import Config
    from cardsnipe.browser import Browser
    import dashboard.snipe_views as views

    monkeypatch.setattr(Config, "EXTERNAL_ACCESS_ENABLED", False)
    monkeypatch.setattr(Config, "BROWSER_SCANS_ENABLED", False)
    monkeypatch.setattr(Browser, "get", lambda *a: pytest.fail("No external browser"))
    monkeypatch.setattr(views.PriceService, "refresh", lambda *a: pytest.fail("No external price provider"))
    settings = _settings()
    views._run_dashboard_scan(settings, Watchlist(targets=[ZARD]))
    assert not views._scan_state["running"] and "disabled" in views._scan_state["message"]
    views._run_facebook_login(settings)
    assert not views._scan_state["running"] and "disabled" in views._scan_state["message"]


def _populate(store: Store) -> None:
    runner = SnipeRunner(
        settings=_settings(),
        watchlist=Watchlist(targets=[ZARD]),
        store=store,
        sources={
            "ebay": Source([
                _listing(),
                _listing(listing_id="2", title="PSA 9 Charizard VMAX 074/073", price=150.0),
                _listing(listing_id="3", price=900.0),
            ]),
            "facebook": Source([], error="Facebook not logged in — run `make login`"),
        },
        notifier=Quiet(),
    )
    runner.scan_once()
    runner.scan_once()  # second pass: nothing new


def test_scan_runs_are_recorded_with_counts_and_errors():
    store = Store("sqlite://")
    _populate(store)
    scans = store.recent_scans()
    assert len(scans) == 2
    first, second = scans[1], scans[0]
    assert first.scanned == 3 and first.new_listings == 3 and first.deals == 2 and first.regrade_deals == 1
    assert first.bids_scheduled == 0 and first.sources == "ebay,facebook" and first.live is False
    assert "Facebook not logged in" in first.errors
    assert second.new_listings == 0 and second.deals == 0
    assert first.duration_seconds is not None and first.duration_seconds >= 0

    summary = store.summary()
    assert summary["scans_total"] == 2 and summary["deals_total"] == 2 and summary["regrade_total"] == 1
    assert summary["listings_seen"] == 3 and summary["deals_by_source"] == {"ebay": 2}
    assert summary["deals_by_target"] == {"Zard": 2} and summary["bids_by_status"] == {}
    assert summary["last_scan"]["scanned"] == 3
    assert summary["last_scan"]["started"].endswith("+00:00")


def test_parallel_dashboard_requests_initialize_the_database_once(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import dashboard.snipe_views as views

    calls = []
    sentinel = object()

    def build(url):
        calls.append(url)
        time.sleep(0.01)
        return sentinel

    monkeypatch.setattr(views, "_store", None)
    monkeypatch.setattr(views, "Store", build)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: views.get_store(), range(4))) == [sentinel] * 4
    assert len(calls) == 1


def test_snipe_page_and_summary(snipe_client):
    client, store, _ = snipe_client
    _populate(store)
    page = client.get("/snipe")
    assert page.status_code == 200 and b"Card sniper" in page.data and b"snipe.js" in page.data
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]

    summary = client.get("/api/snipe/summary").get_json()
    assert summary["deals_total"] == 2 and summary["settings"]["poll_seconds"] > 0
    assert summary["last_scan"]["deals"] == 0  # the second (empty) pass


def test_deals_listings_bids_and_scans_endpoints(snipe_client):
    client, store, _ = snipe_client
    _populate(store)

    deals = client.get("/api/snipe/deals").get_json()["deals"]
    assert len(deals) == 2 and {d["lane"] for d in deals} == {"deal", "regrade"}
    regrade = client.get("/api/snipe/deals?lane=regrade").get_json()["deals"]
    assert len(regrade) == 1 and regrade[0]["grade"] == "PSA 9" and regrade[0]["listing_type"] == "bin"
    assert client.get("/api/snipe/deals?source=facebook").get_json()["deals"] == []

    listings = client.get("/api/snipe/listings").get_json()["listings"]
    assert len(listings) == 3 and sum(1 for l in listings if l["matched_target"]) == 2

    assert client.get("/api/snipe/bids").get_json()["bids"] == []
    removed = deals[0]["id"]
    assert client.delete(f"/api/snipe/listings/{removed}").status_code == 200
    assert all(d["id"] != removed for d in client.get("/api/snipe/deals").get_json()["deals"])
    assert all(row["id"] != removed for row in client.get("/api/snipe/listings").get_json()["listings"])
    assert client.delete(f"/api/snipe/listings/{removed}").status_code == 404
    assert client.get("/api/snipe/summary").get_json()["deals_total"] == 1

    scans = client.get("/api/snipe/scans").get_json()["scans"]
    assert len(scans) == 2 and scans[1]["deals"] == 2 and scans[1]["errors"][0].startswith("facebook")


def test_old_deals_stay_in_history_without_claiming_to_be_current(snipe_client):
    from cardsnipe.store import SeenListing

    client, store, _ = snipe_client
    _populate(store)
    with store.session() as session:
        for row in session.query(SeenListing).all():
            row.last_seen = datetime.now(timezone.utc) - timedelta(days=2)
        session.commit()
    assert client.get("/api/snipe/deals").get_json()["deals"] == []
    assert len(client.get("/api/snipe/listings").get_json()["listings"]) == 3
    assert client.get("/api/snipe/summary").get_json()["deals_total"] == 0


def test_budget_and_disabled_targets_immediately_recheck_saved_results(snipe_client):
    client, store, _ = snipe_client
    _populate(store)
    assert client.patch("/api/snipe/budget", json={"budget": 100}).status_code == 200
    assert client.get("/api/snipe/deals").get_json()["deals"] == []
    client.patch("/api/snipe/budget", json={"budget": None})
    assert len(client.get("/api/snipe/deals").get_json()["deals"]) == 2
    client.patch("/api/snipe/watchlist/Zard", json={"enabled": False})
    assert client.get("/api/snipe/deals").get_json()["deals"] == []
    assert client.get("/api/snipe/summary").get_json()["deals_total"] == 0


def test_watchlist_crud_via_api(snipe_client):
    client, _, _ = snipe_client
    data = client.get("/api/snipe/watchlist").get_json()
    assert [t["name"] for t in data["targets"]] == ["Zard"] and data["tag_ten_score"] == 950

    bad = client.post("/api/snipe/watchlist", json={"name": "x", "keywords": [], "max_price": 1})
    assert bad.status_code == 400

    added = client.post("/api/snipe/watchlist", json={
        "name": "Umbreon", "keywords": ["umbreon", "vmax", "alt art|215/203"], "max_price": "300", "min_price": "40",
        "max_bid": "320", "exclude": ["japanese"], "regrade": True, "regrade_min_grade": 8.5, "regrade_max_grade": 9.5,
        "sources": ["ebay"],
    }).get_json()
    umbreon = next(t for t in added["targets"] if t["name"] == "Umbreon")
    assert umbreon["max_price"] == 300 and umbreon["min_price"] == 40 and umbreon["max_bid"] == 320
    assert umbreon["regrade"] is True and umbreon["regrade_min_grade"] == 8.5 and umbreon["sources"] == ["ebay"]
    assert umbreon["exclude"] == ["japanese"]

    paused = client.patch("/api/snipe/watchlist/umbreon", json={"enabled": False}).get_json()
    assert next(t for t in paused["targets"] if t["name"] == "Umbreon")["enabled"] is False

    assert client.delete("/api/snipe/watchlist/nope").status_code == 404
    removed = client.delete("/api/snipe/watchlist/Umbreon").get_json()
    assert [t["name"] for t in removed["targets"]] == ["Zard"]


def test_job_dashboard_links_to_sniper(dashboard_client):
    client, _, _ = dashboard_client
    assert b'href="/snipe"' in client.get("/").data


def test_bargain_review_has_clear_navigation_and_saved_result_sections(snipe_client):
    client, _, _ = snipe_client
    page = client.get("/snipe").get_data(as_text=True)
    for marker in ('data-view="bargains"', 'id="view-bargains"', 'data-view-link="bargains"',
                   'id="bargain-reviewed"', 'id="bargain-candidates"', 'id="bargain-more"'):
        assert marker in page


def test_budget_survives_target_edits_and_can_be_cleared(snipe_client):
    client, _, path = snipe_client
    data = client.patch("/api/snipe/budget", json={"budget": "125.50"}).get_json()
    assert data["budget"] == 125.5 and data["currency"] == "CAD"
    edited = client.patch("/api/snipe/watchlist/Zard", json={"name": "Custom Zard", "max_price": 90, "keywords": ["charizard", "074/073"]})
    assert edited.status_code == 200
    saved = load_watchlist(path)
    assert saved.budget == 125.5 and len(saved.targets) == 1
    target = saved.targets[0]
    assert target.name == "Custom Zard" and target.max_price == 90 and target.max_bid == ZARD.max_bid
    assert target.regrade is True and target.keywords == ["charizard", "074/073"]
    assert client.patch("/api/snipe/budget", json={"budget": ""}).get_json()["budget"] is None


@pytest.mark.parametrize("shared,card,expected", [(100,150,"100.00"),(200,90,"90.00"),(None,None,None)])
def test_regular_browser_search_links_use_exact_queries_and_effective_price_cap(snipe_client, shared, card, expected):
    from urllib.parse import parse_qs, urlparse

    client, _, path = snipe_client
    watchlist = Watchlist(targets=[replace(ZARD, keywords=["charizard", "074/073|rainbow"], max_price=card)], budget=shared)
    save_watchlist(path, watchlist)
    target = client.get("/api/snipe/watchlist").get_json()["targets"][0]
    links = target["search_links"]
    ebay = parse_qs(urlparse(links["ebay"]).query)
    facebook = parse_qs(urlparse(links["facebook"]).query)
    assert ebay["_nkw"] == facebook["query"] == ["charizard 074/073"]
    assert ebay["LH_BIN"] == ["1"]
    assert ebay.get("_udhi") == facebook.get("maxPrice") == ([expected] if expected else None)
    assert set(links) == {"ebay", "facebook"}


@pytest.mark.parametrize("budget", [500, None])
def test_discovery_searches_beyond_watchlist_without_changing_saved_data(snipe_client, budget):
    from urllib.parse import parse_qs, urlparse

    client, store, path = snipe_client
    save_watchlist(path, Watchlist(targets=[], budget=budget))
    before = open(path).read()
    response = client.get("/api/snipe/discovery", query_string={"query": "pokemon PSA"})
    assert response.status_code == 200
    data = response.get_json()
    ebay = parse_qs(urlparse(data["search_links"]["ebay"]).query)
    facebook = parse_qs(urlparse(data["search_links"]["facebook"]).query)
    assert ebay["_nkw"] == facebook["query"] == ["pokemon PSA"]
    assert "LH_BIN" not in ebay and "LH_Auction" not in ebay
    assert ebay.get("_udhi") == facebook.get("maxPrice") == (["500.00"] if budget else None)
    assert "daysSinceListed" not in facebook
    assert data["budget"] == budget and data["currency"] == "CAD"
    assert not store.recent_scans() and not store.recent_listings()
    assert open(path).read() == before


@pytest.mark.parametrize("query", ["", "   ", "pokemon cards"])
def test_broad_discovery_modes_do_not_inherit_specific_card_or_grade_filters(snipe_client, query):
    from urllib.parse import parse_qs, urlparse

    client, _, path = snipe_client
    save_watchlist(path, Watchlist(targets=[replace(ZARD, graded_only=True, min_grade=10)], budget=75))
    data = client.get("/api/snipe/discovery", query_string={"query": query}).get_json()
    assert data["query"] == "pokemon cards"
    for mode, links in data["search_modes"].items():
        params = parse_qs(urlparse(links["ebay"]).query)
        assert params["_nkw"] == ["pokemon cards"] and params["_udhi"] == ["75.00"]
        assert "LH_BIN" not in params and "LH_ItemCondition" not in params
        assert params.get("LH_SaleItems") == (["1"] if mode == "sale" else None)
        assert params.get("LH_Auction") == (["1"] if mode == "auction" else None)
        assert params.get("LH_BO") == (["1"] if mode == "offers" else None)
        assert params["_sop"] == (["1"] if mode == "auction" else ["10"])
        assert parse_qs(urlparse(links["facebook"]).query)["query"] == ["pokemon cards"]


@pytest.mark.parametrize("query", ["a" * 161, "pokemon\ncards"])
def test_discovery_rejects_invalid_queries(snipe_client, query):
    client, _, _ = snipe_client
    assert client.get("/api/snipe/discovery", query_string={"query": query}).status_code == 400


def test_search_controls_are_real_links_even_before_javascript_loads(snipe_client):
    from html.parser import HTMLParser
    from urllib.parse import parse_qs, urlparse

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.links.append(dict(attrs))

    client, _, path = snipe_client
    save_watchlist(path, Watchlist(targets=[], budget=75))
    parser = Links()
    parser.feed(client.get("/snipe").get_data(as_text=True))
    categories = [link for link in parser.links if "data-discovery-query" in link]
    assert len(categories) == 8
    for link in categories:
        url = urlparse(link["href"])
        params = parse_qs(url.query)
        assert url.hostname == "www.ebay.ca"
        assert params["_nkw"] == [link["data-discovery-query"]]
        assert params["_udhi"] == ["75.00"]
        assert link["target"] == "_blank" and "noopener" in link["rel"]
    assert any(link.get("id") == "discovery-ebay" for link in parser.links)
    lanes = [link for link in parser.links if "data-discovery-mode" in link]
    assert {link["data-discovery-mode"] for link in lanes} == {"all", "sale", "auction", "offers"}
    assert all("LH_BIN" not in parse_qs(urlparse(link["href"]).query) for link in categories + lanes)


@pytest.mark.parametrize("budget", [0, -1, True, "NaN", "Infinity", "not money", []])
def test_invalid_budget_never_changes_saved_data(snipe_client, budget):
    client, _, path = snipe_client
    before = open(path).read()
    assert client.patch("/api/snipe/budget", json={"budget": budget}).status_code == 400
    assert open(path).read() == before


@pytest.mark.parametrize("changes", [
    {"max_price": -1}, {"max_price": "NaN"}, {"keywords": "charizard"}, {"keywords": []},
    {"enabled": "false"}, {"sources": ["unknown"]}, {"bargain_pct": 100},
    {"regrade_min_grade": 10, "regrade_max_grade": 8}, {"min_price": 500},
])
def test_invalid_target_edits_preserve_original(snipe_client, changes):
    client, _, path = snipe_client
    before = open(path).read()
    assert client.patch("/api/snipe/watchlist/Zard", json=changes).status_code == 400
    assert open(path).read() == before


def test_new_card_can_use_shared_budget_and_duplicate_is_not_overwritten(snipe_client):
    client, _, path = snipe_client
    client.patch("/api/snipe/budget", json={"budget": 100})
    payload = {"name": "Eevee", "keywords": ["eevee", "TG11/TG30"], "sources": ["ebay"]}
    assert client.post("/api/snipe/watchlist", json=payload).status_code == 200
    before = open(path).read()
    assert client.post("/api/snipe/watchlist", json=payload | {"max_price": 25}).status_code == 400
    assert client.patch("/api/snipe/watchlist/Zard", json={"name": "Eevee"}).status_code == 400
    assert open(path).read() == before


@pytest.mark.parametrize("selected", ["all", "ebay", "facebook"])
def test_dashboard_scans_selected_sources_in_background_and_rejects_duplicates(snipe_client, monkeypatch, selected):
    import snipe
    import dashboard.snipe_views as views

    client, _, _ = snipe_client
    started, release, closed = threading.Event(), threading.Event(), threading.Event()

    class Runner:
        def scan_once(self):
            started.set()
            assert release.wait(2)
            return ScanReport(scanned=3, new_listings=2)

    class Browser:
        def quit(self):
            closed.set()

    def build(settings, source, watchlist):
        assert source == selected and watchlist.targets[0].name == "Zard"
        assert not settings.live and not settings.fb_auto_message and not settings.open_in_browser
        assert not settings.notify_macos and not settings.webhook_url
        return Runner(), Browser()

    monkeypatch.setattr(snipe, "_build_runner", build)
    try:
        response = client.post("/api/snipe/scan", json={"source": selected})
        assert response.status_code == 202 and response.get_json()["running"] is True
        assert started.wait(2)
        assert client.get("/api/snipe/scan").get_json()["running"] is True
        assert client.post("/api/snipe/scan").status_code == 409
    finally:
        release.set()
        assert closed.wait(2)
        deadline = time.monotonic() + 2
        while views._scan_state["running"] and time.monotonic() < deadline:
            time.sleep(0.01)
    result = client.get("/api/snipe/scan").get_json()
    assert not result["running"] and result["errors"] == [] and "scanned 3" in result["message"]


def test_tcgplayer_price_scan_works_without_chrome_or_ebay_keys(snipe_client, monkeypatch):
    import snipe
    import dashboard.snipe_views as views
    from cardsnipe.pricing import SourcePrice, Valuation

    client, _, path = snipe_client
    watchlist = load_watchlist(path)
    watchlist.targets[0].card_name = "Charizard VMAX"
    watchlist.targets[0].number = "074/073"
    save_watchlist(path, watchlist)
    monkeypatch.setattr(snipe, "_build_runner", lambda *a: pytest.fail("Price scans must not start Chrome"))
    monkeypatch.setattr(views.PriceService, "refresh", lambda self, target: Valuation(
        target.name, "CAD", 1.4, prices=[SourcePrice("tcgplayer", "raw", 200)]))
    views._run_dashboard_scan(_settings(), watchlist, "tcgplayer")
    result = client.get("/api/snipe/scan").get_json()
    assert result["source"] == "tcgplayer" and result["tcgplayer"]["updated"] == 1
    assert result["errors"] == [] and not result["running"]


def test_dashboard_facebook_login_waits_for_confirmation_and_keeps_incomplete_login_open(snipe_client, monkeypatch):
    from cardsnipe.browser import Browser
    from cardsnipe.facebook import FacebookMarketplace
    import dashboard.snipe_views as views

    client, _, path = snipe_client
    calls = []
    authenticated = iter([False, True, True])

    class Actions:
        attempts = 0

        def wait(self, timeout):
            self.attempts += 1
            assert "closed" not in calls
            if self.attempts == 1:
                return False  # Entering credentials does not finish the dashboard operation.
            if self.attempts == 3:
                assert views._scan_state["login_waiting"] and views._scan_state["errors"]
            assert self.attempts <= 3
            assert client.post("/api/snipe/facebook/login/finish").status_code == 202
            return True

        def clear(self):
            pass

        def set(self):
            pass

    views._scan_state.update(running=True, operation="login", source="facebook")
    monkeypatch.setattr(views, "_facebook_login_action", Actions())
    monkeypatch.setattr(Browser, "get", lambda self, url: calls.append(url))
    monkeypatch.setattr(Browser, "current_url", lambda self: "https://www.facebook.com/login/")
    monkeypatch.setattr(Browser, "wait_until", lambda self, predicate, **kwargs: predicate())
    monkeypatch.setattr(Browser, "quit", lambda self: calls.append("closed"))
    monkeypatch.setattr(FacebookMarketplace, "is_logged_in", lambda self: next(authenticated))
    monkeypatch.setattr(FacebookMarketplace, "message_seller", lambda *a: pytest.fail("Sign-in must not message sellers"))
    views._run_facebook_login(_settings(chrome_profile_dir=path + ".chrome"))
    status = client.get("/api/snipe/scan").get_json()
    assert not status["running"] and not status["login_waiting"] and status["errors"] == []
    assert "verified and saved" in status["message"]
    assert calls == ["https://www.facebook.com/login/?next=https%3A%2F%2Fwww.facebook.com%2Fmarketplace%2F",
                     "https://www.facebook.com/marketplace/", "closed"]


def test_dashboard_facebook_login_can_be_cancelled_without_authentication(snipe_client, monkeypatch):
    from cardsnipe.browser import Browser
    from cardsnipe.facebook import FacebookMarketplace
    import dashboard.snipe_views as views

    client, _, path = snipe_client
    calls = []

    class Actions:
        def wait(self, timeout):
            assert client.post("/api/snipe/facebook/login/cancel").status_code == 202
            return True

        def clear(self):
            pass

        def set(self):
            pass

    views._scan_state.update(running=True, operation="login", source="facebook")
    monkeypatch.setattr(views, "_facebook_login_action", Actions())
    monkeypatch.setattr(Browser, "get", lambda self, url: None)
    monkeypatch.setattr(Browser, "quit", lambda self: calls.append("closed"))
    monkeypatch.setattr(FacebookMarketplace, "is_logged_in", lambda self: pytest.fail("Cancel must not verify or save sign-in"))
    views._run_facebook_login(_settings(chrome_profile_dir=path + ".chrome"))
    status = client.get("/api/snipe/scan").get_json()
    assert not status["running"] and not status["errors"] and "cancelled" in status["message"]
    assert calls == ["closed"]


def test_scanner_signin_actions_reject_missing_sessions_and_unready_window(snipe_client):
    import dashboard.snipe_views as views

    client, _, _ = snipe_client
    assert client.post("/api/snipe/facebook/login/finish").status_code == 409
    assert client.post("/api/snipe/facebook/login/cancel").status_code == 409
    assert client.post("/api/snipe/facebook/login/unknown").status_code == 400
    views._scan_state.update(running=True, operation="scan")
    assert client.post("/api/snipe/facebook/login/cancel").status_code == 409
    views._scan_state.update(operation="login", login_waiting=False)
    assert client.post("/api/snipe/facebook/login/finish").status_code == 409


@pytest.mark.parametrize("payload", [{"source": "unknown"}, ["ebay"]])
def test_invalid_scan_source_is_rejected(snipe_client, payload):
    assert snipe_client[0].post("/api/snipe/scan", json=payload).status_code == 400


def test_dashboard_scan_reports_failure_and_no_enabled_target(snipe_client, monkeypatch):
    import snipe
    import dashboard.snipe_views as views

    client, _, path = snipe_client
    monkeypatch.setattr(snipe, "_build_runner", lambda *args: (_ for _ in ()).throw(RuntimeError("Chrome unavailable")))
    views._run_dashboard_scan(_settings(chrome_profile_dir=str(path) + ".chrome"), load_watchlist(path))
    status = client.get("/api/snipe/scan").get_json()
    assert not status["running"] and status["errors"] == ["Chrome unavailable"]
    client.patch("/api/snipe/watchlist/Zard", json={"enabled": False})
    assert client.post("/api/snipe/scan").status_code == 400


def test_dashboard_detects_existing_continuous_watcher(snipe_client):
    client, _, _ = snipe_client
    with scanner_session(SnipeSettings.from_env()):
        status = client.get("/api/snipe/scan").get_json()
        assert status["watcher_running"] is True and status["running"] is False
        assert client.post("/api/snipe/scan").status_code == 409
    assert client.get("/api/snipe/scan").get_json()["watcher_running"] is False
