"""Card sniper dashboard: scan history persistence + /snipe API over an in-memory store."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from cardsnipe.matcher import Listing
from cardsnipe.runner import SnipeRunner
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import Store
from cardsnipe.watchlist import Target, Watchlist, save_watchlist

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

    store = Store("sqlite://")
    views.set_store(store)
    watchlist_path = str(tmp_path / "watchlist.json")
    save_watchlist(watchlist_path, Watchlist(targets=[ZARD]))
    monkeypatch.setenv("SNIPE_WATCHLIST", watchlist_path)
    dashboard_app.app.config.update(TESTING=True)
    yield dashboard_app.app.test_client(), store, watchlist_path
    views.set_store(None)


def _populate(store: Store) -> None:
    end_time = datetime.now(timezone.utc) + timedelta(hours=1)
    runner = SnipeRunner(
        settings=_settings(),
        watchlist=Watchlist(targets=[ZARD]),
        store=store,
        sources={
            "ebay": Source([
                _listing(),
                _listing(listing_id="2", title="PSA 9 Charizard VMAX 074/073", price=150.0, listing_type="auction", end_time=end_time),
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
    assert first.bids_scheduled == 1 and first.sources == "ebay,facebook" and first.live is False
    assert "Facebook not logged in" in first.errors
    assert second.new_listings == 0 and second.deals == 0
    assert first.duration_seconds is not None and first.duration_seconds >= 0

    summary = store.summary()
    assert summary["scans_total"] == 2 and summary["deals_total"] == 2 and summary["regrade_total"] == 1
    assert summary["listings_seen"] == 3 and summary["deals_by_source"] == {"ebay": 2}
    assert summary["deals_by_target"] == {"Zard": 2} and summary["bids_by_status"] == {"pending": 1}
    assert summary["last_scan"]["scanned"] == 3


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
    assert len(regrade) == 1 and regrade[0]["grade"] == "PSA 9" and regrade[0]["listing_type"] == "auction"
    assert client.get("/api/snipe/deals?source=facebook").get_json()["deals"] == []

    listings = client.get("/api/snipe/listings").get_json()["listings"]
    assert len(listings) == 3 and sum(1 for l in listings if l["matched_target"]) == 2

    bids = client.get("/api/snipe/bids").get_json()["bids"]
    assert len(bids) == 1 and bids[0]["status"] == "pending" and bids[0]["max_bid"] == 270
    assert client.post(f"/api/snipe/bids/{bids[0]['id']}/cancel").status_code == 200
    assert client.get("/api/snipe/bids").get_json()["bids"][0]["status"] == "cancelled"
    assert client.post(f"/api/snipe/bids/{bids[0]['id']}/cancel").status_code == 404

    scans = client.get("/api/snipe/scans").get_json()["scans"]
    assert len(scans) == 2 and scans[1]["deals"] == 2 and scans[1]["errors"][0].startswith("facebook")


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
