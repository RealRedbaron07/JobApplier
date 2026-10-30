"""Card sniper dashboard: read-only views over cardsnipe.db plus watchlist editing."""

from __future__ import annotations

import json
import threading
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request
from config import Config

from cardsnipe.pricing import VALUATION_VERSION, PriceService, usd_rate
from cardsnipe.discovery import (COOLDOWN_SECONDS, DISCOVERY_MODES, MAX_SEARCHES, RESULTS_PER_SEARCH,
                                 DiscoveryScanner, browser_search_links as _browser_search_links, search_plan)
from cardsnipe.runner import revalue_store, scanner_session
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import ScanRun, ScheduledBid, SeenListing, Store
from cardsnipe.watchlist import Target, load_watchlist, optional_budget, remove_target, save_watchlist, target_from_dict

snipe_bp = Blueprint("snipe", __name__)

_store: Store | None = None
_store_lock = threading.Lock()
_watchlist_lock = threading.RLock()
_scan_lock = threading.Lock()
_facebook_login_action = threading.Event()
_discovery_stop = threading.Event()
_scan_state = {"running": False, "started": None, "message": "No dashboard scan started.", "errors": []}


def get_store() -> Store:
    global _store
    with _store_lock:
        if _store is None:
            _store = Store(SnipeSettings.from_env().database_url)
    return _store


def set_store(store: Store | None) -> None:
    """Test hook."""
    global _store
    _store = store


def _settings() -> SnipeSettings:
    return SnipeSettings.from_env()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat(timespec="seconds")


def _listing_dict(row: SeenListing) -> dict:
    return {
        "id": row.id, "source": row.source, "listing_id": row.listing_id, "title": row.title,
        "price": row.price, "shipping": row.shipping, "total_price": row.total_price, "currency": row.currency,
        "url": row.url, "listing_type": row.listing_type, "end_time": _iso(row.end_time), "location": row.location,
        "discovery_at": _iso(row.discovery_at),
        "first_seen": _iso(row.first_seen), "matched_target": row.matched_target, "savings_pct": row.savings_pct,
        "last_seen": _iso(row.last_seen),
        "condition": row.condition or "",
        "promotion": row.promotion or "", "discovery_routes": json.loads(row.discovery_routes or "[]"),
        "lane": row.lane, "grade": row.grade, "tag_score": row.tag_score, "notified": bool(row.notified),
        "action": row.action, "action_detail": row.action_detail, "action_at": _iso(row.action_at),
        "market_value": row.market_value, "value_source": row.value_source, "value_bucket": row.value_bucket,
        "irregular": bool(row.irregular), "irregular_reason": row.irregular_reason,
    }


def _bid_dict(row: ScheduledBid) -> dict:
    return {
        "id": row.id, "source": row.source, "listing_id": row.listing_id, "title": row.title, "url": row.url,
        "target_name": row.target_name, "max_bid": row.max_bid, "currency": row.currency,
        "end_time": _iso(row.end_time), "fire_at": _iso(row.fire_at), "status": row.status, "result": row.result,
        "created": _iso(row.created), "updated": _iso(row.updated),
    }


def _scan_dict(row: ScanRun) -> dict:
    try:
        errors = json.loads(row.errors or "[]")
    except ValueError:
        errors = []
    return {
        "kind": row.kind or "watchlist", "budget": row.budget, "currency": row.currency,
        "id": row.id, "started": _iso(row.started), "finished": _iso(row.finished),
        "duration_seconds": row.duration_seconds, "sources": row.sources, "live": bool(row.live),
        "scanned": row.scanned, "new_listings": row.new_listings, "deals": row.deals,
        "regrade_deals": row.regrade_deals, "bids_scheduled": row.bids_scheduled, "errors": errors,
    }


def _limit(default: int = 50, maximum: int = 500) -> int:
    try:
        return max(1, min(maximum, int(request.args.get("limit", default))))
    except ValueError:
        return default


def _watchlist_data(watchlist, settings: SnipeSettings) -> dict:
    data = watchlist.to_dict()
    for item, target in zip(data["targets"], watchlist.targets):
        item["search_links"] = _browser_search_links(target.within_budget(watchlist.budget), settings)
    return data | {"path": settings.watchlist_path, "currency": settings.ebay_currency}


def _revalue_cached(settings: SnipeSettings, watchlist=None) -> dict:
    store = get_store()
    return revalue_store(store, watchlist or load_watchlist(settings.watchlist_path), PriceService(settings, store),
                         currency=settings.ebay_currency, cached_only=True)


def _payload() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Send a JSON object")
    return payload


def _edited_target(payload: dict, watchlist, previous=None):
    data = (asdict(previous) if previous else {}) | payload
    if "graded_only" in payload and "raw_ok" not in payload:
        data["raw_ok"] = not payload["graded_only"]
    target = target_from_dict(data)
    if target.max_price is None and watchlist.budget is None and not (target.card_name or target.number):
        raise ValueError("Give a card name/number for market pricing, a card budget, or a shared budget")
    if any(t is not previous and t.name.lower() == target.name.lower() for t in watchlist.targets):
        raise ValueError("A target with that name already exists. Edit it instead.")
    return target


def _run_dashboard_scan(settings, watchlist, source="all") -> None:
    from snipe import _build_runner

    browser = None
    result = {"errors": []}
    try:
        if not Config.EXTERNAL_ACCESS_ENABLED:
            raise ValueError("External scans are disabled in this local-only app")
        with scanner_session(settings) if source != "tcgplayer" else nullcontext():
            try:
                pricer = PriceService(settings, get_store())
                checked, updated, price_errors = 0, 0, []
                for target in watchlist.enabled_targets():
                    if not target.use_market or not (target.card_name or target.number):
                        continue
                    checked += 1
                    try:
                        val = pricer.refresh(target)
                        if val and val.value_usd("raw"):
                            updated += 1
                        else:
                            price_errors.append(f"TCGplayer: no unambiguous raw market reference for {target.name}")
                    except Exception as exc:
                        price_errors.append(f"TCGplayer refresh failed for {target.name}: {str(exc).splitlines()[0]}")
                message = f"TCGplayer references refreshed: {updated}/{checked}."
                errors = price_errors
                if source != "tcgplayer":
                    runner, browser = _build_runner(settings, source, watchlist)
                    report = runner.scan_once()
                    message += " " + report.summary()
                    errors += report.errors
                _revalue_cached(settings, watchlist)
                result = {"message": message, "errors": errors, "source": source,
                          "tcgplayer": {"checked": checked, "updated": updated, "kind": "market_reference"}}
            finally:
                if browser:
                    browser.quit()
    except Exception as exc:
        result = {"message": "Scan failed. " + str(exc), "errors": [str(exc)]}
    finally:
        with _scan_lock:
            _scan_state.update(result, running=False)


def _run_facebook_login(settings) -> None:
    from cardsnipe.browser import Browser
    from cardsnipe.facebook import FacebookMarketplace

    browser = None
    result = {"errors": []}
    try:
        if not (Config.EXTERNAL_ACCESS_ENABLED or Config.BROWSER_SCANS_ENABLED):
            raise ValueError("External sign-in is disabled in this local-only app")
        with scanner_session(settings):
            try:
                browser = Browser(settings)
                browser.get("https://www.facebook.com/login/?next=https%3A%2F%2Fwww.facebook.com%2Fmarketplace%2F")
                facebook = FacebookMarketplace(settings, browser)
                with _scan_lock:
                    _scan_state.update(login_waiting=True,
                                       message="Finish Facebook sign-in and any security checks in the separate scanner window. Then press Finish scanner sign-in here. The window stays open until you finish or cancel.")
                while True:
                    if not _facebook_login_action.wait(timeout=1):
                        browser.current_url()  # Detect a window the user closed without restarting it.
                        continue
                    with _scan_lock:
                        action = _scan_state.pop("login_action", None)
                        _facebook_login_action.clear()
                    if action == "cancel":
                        result = {"message": "Scanner sign-in cancelled. Your regular browser session is unchanged.", "errors": []}
                        break
                    ok = browser.wait_until(facebook.is_logged_in, timeout=12, interval=0.5)
                    if ok:
                        browser.get("https://www.facebook.com/marketplace/")
                        ok = browser.wait_until(facebook.is_logged_in, timeout=20, interval=1)
                    if ok:
                        result = {"message": "Facebook scanner session verified and saved. Its window closed after your confirmation. Run an automated Marketplace scan when ready.", "errors": []}
                        break
                    with _scan_lock:
                        _scan_state.update(login_waiting=True,
                                           message="Facebook sign-in is not verified yet. Complete sign-in and any security checks, wait for Facebook to load, then press Finish scanner sign-in again.",
                                           errors=["Scanner sign-in is not verified yet"])
            finally:
                if browser:
                    browser.quit()
    except Exception as exc:
        result = {"message": "Facebook scanner sign-in stopped before verification. " + str(exc).splitlines()[0],
                  "errors": [str(exc).splitlines()[0]]}
    finally:
        with _scan_lock:
            _scan_state.update(result, running=False, login_waiting=False)


@snipe_bp.post("/api/snipe/facebook/login")
def snipe_facebook_login():
    with _scan_lock:
        settings = replace(_settings(), live=False, fb_auto_message=False, open_in_browser=False,
                           notify_macos=False, webhook_url="", headless=False)
        if _scan_state["running"]:
            return jsonify({"error": "Wait for the current scanner operation to finish first."}), 409
        try:
            with scanner_session(settings):
                pass
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        _facebook_login_action.clear()
        _scan_state.update(running=True, operation="login", source="facebook", tcgplayer=None, login_waiting=False,
                           started=_iso(datetime.now(timezone.utc)), errors=[],
                           message="Opening the separate scanner profile. Your regular Chrome login is not shared. Finish or cancel this sign-in from the dashboard.")
        threading.Thread(target=_run_facebook_login, args=(settings,), daemon=True).start()
        return jsonify(_scan_state), 202


@snipe_bp.post("/api/snipe/facebook/login/<action>")
def snipe_facebook_login_action(action: str):
    if action not in {"finish", "cancel"}:
        raise ValueError("Choose finish or cancel")
    with _scan_lock:
        if not _scan_state["running"] or _scan_state.get("operation") != "login":
            return jsonify({"error": "No scanner sign-in is open."}), 409
        if action == "finish" and not _scan_state.get("login_waiting"):
            return jsonify({"error": "Wait for the sign-in window to open or the current check to finish."}), 409
        _scan_state.update(login_action=action, login_waiting=False, errors=[],
                           message="Checking Facebook sign-in..." if action == "finish" else "Closing the scanner sign-in window...")
        _facebook_login_action.set()
        return jsonify(_scan_state), 202


@snipe_bp.route("/api/snipe/scan", methods=["GET", "POST"])
def snipe_scan():
    with _scan_lock:
        settings = _settings()
        watcher_running = False
        if not _scan_state["running"]:
            try:
                with scanner_session(settings):
                    pass
            except ValueError:
                watcher_running = True
        if request.method == "POST":
            payload = request.get_json(silent=True)
            if payload is not None and not isinstance(payload, dict):
                raise ValueError("Scan options must be a JSON object")
            source = (payload or {}).get("source", "all")
            if source not in {"all", "ebay", "facebook", "tcgplayer"}:
                raise ValueError("Choose all, ebay, facebook, or tcgplayer")
            if _scan_state["running"] or (watcher_running and source != "tcgplayer"):
                return jsonify({"error": "A card scanner is already running. Saved results reload automatically."}), 409
            settings = replace(settings, live=False, fb_auto_message=False, open_in_browser=False, notify_macos=False, webhook_url="")
            watchlist = load_watchlist(settings.watchlist_path)
            wanted = {"ebay", "facebook"} if source == "all" else {source}
            if source == "tcgplayer":
                enabled = any(t.enabled and t.use_market and (t.card_name or t.number) for t in watchlist.targets)
            else:
                enabled = any(t.uses_source(s) for t in watchlist.targets for s in wanted)
            if not enabled:
                return jsonify({"error": "Add or enable a target for the selected source in Watchlist first"}), 400
            _scan_state.update(running=True, started=_iso(datetime.now(timezone.utc)),
                               message="Refreshing TCGplayer references, then checking the selected listing sources...",
                               operation="scan", source=source, tcgplayer=None, errors=[])
            worker = threading.Thread(target=_run_dashboard_scan, args=(settings, watchlist, source), daemon=True)
            worker.start()
        return jsonify(_scan_state | {"watcher_running": watcher_running,
                                      "local_only": not (Config.EXTERNAL_ACCESS_ENABLED or Config.BROWSER_SCANS_ENABLED)}), 202 if request.method == "POST" else 200


def _run_broad_scan(settings, source):
    def progress(**state):
        with _scan_lock:
            _scan_state.update(state)

    try:
        with scanner_session(settings):
            result = DiscoveryScanner(settings, get_store(), stop=_discovery_stop, progress=progress).scan(source)
    except Exception as exc:
        result = {"message": "Broad scan failed. " + str(exc), "errors": [str(exc)]}
    with _scan_lock:
        _scan_state.update(result, running=False, finished=_iso(datetime.now(timezone.utc)))


def _discovery_status():
    _, latest = get_store().discovery_results()
    remaining = 0
    if latest and latest.finished:
        finished = latest.finished.replace(tzinfo=timezone.utc) if latest.finished.tzinfo is None else latest.finished
        remaining = max(0, COOLDOWN_SECONDS - int((datetime.now(timezone.utc) - finished).total_seconds()))
    return _scan_state | {"browser_scans_enabled": Config.BROWSER_SCANS_ENABLED, "paid_apis_enabled": False,
                          "max_searches": MAX_SEARCHES, "results_per_search": RESULTS_PER_SEARCH,
                          "cooldown_seconds": remaining}


@snipe_bp.route("/api/snipe/discovery/scan", methods=["GET", "POST"])
def snipe_discovery_scan():
    with _scan_lock:
        if request.method == "POST":
            if not Config.BROWSER_SCANS_ENABLED:
                return jsonify({"error": "Browser scans are disabled"}), 403
            source = _payload().get("source", "all")
            plan = search_plan(source)
            if _scan_state["running"]:
                return jsonify({"error": "A scan or scanner sign-in is already running."}), 409
            status = _discovery_status()
            if status["cooldown_seconds"]:
                return jsonify({"error": f"Wait {status['cooldown_seconds']} seconds before another scan.",
                                "cooldown_seconds": status["cooldown_seconds"]}), 429
            settings = _settings()
            try:
                with scanner_session(settings):
                    pass
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 409
            _discovery_stop.clear()
            _scan_state.update(running=True, operation="broad", source=source, errors=[], candidates=0,
                               scanned=0, pages_done=0, page_limit=len(plan), tcgplayer=None, login_waiting=False,
                               started=_iso(datetime.now(timezone.utc)), finished=None,
                               message="Starting broad browser searches. No card list or paid API is used…")
            threading.Thread(target=_run_broad_scan, args=(settings, source), daemon=True).start()
        return jsonify(_discovery_status()), 202 if request.method == "POST" else 200


@snipe_bp.post("/api/snipe/discovery/stop")
def snipe_discovery_stop():
    with _scan_lock:
        if not _scan_state["running"] or _scan_state.get("operation") != "broad":
            return jsonify({"error": "No broad scan is running."}), 409
        _discovery_stop.set()
        _scan_state.update(message="Stopping after the current page…")
        return jsonify(_scan_state), 202


@snipe_bp.get("/api/snipe/discovery/results")
def snipe_discovery_results():
    rows, latest = get_store().discovery_results()
    return jsonify({"listings": [_listing_dict(row) for row in rows],
                    "scan": _scan_dict(latest) if latest else None})


@snipe_bp.get("/snipe")
def snipe_page():
    settings = _settings()
    watchlist = load_watchlist(settings.watchlist_path)
    presets = [{"label": label, "query": query, "links": _browser_search_links(
        Target(name=query, keywords=[query], max_price=watchlist.budget, use_market=False), settings, mode="all",
    )} for label, query in (
        ("All Pokémon cards", "pokemon cards"), ("Singles", "pokemon singles"),
        ("All graded cards", "pokemon graded"), ("Lots & bundles", "pokemon card lot"),
        ("Collections", "pokemon collection"), ("Sealed products", "pokemon sealed"), ("Promos", "pokemon promo"),
    )]
    broad = Target(name="pokemon cards", keywords=["pokemon cards"], max_price=watchlist.budget, use_market=False)
    return render_template(
        "snipe.html",
        poll_seconds=settings.poll_seconds,
        ebay_mode="API" if settings.ebay_api_enabled else "Chrome",
        fb_city=settings.fb_city,
        currency=settings.ebay_currency,
        discovery=presets[0], discovery_presets=presets,
        discovery_modes=[{"mode": mode, "label": label, "note": note,
                          "links": _browser_search_links(broad, settings, mode=mode)}
                         for mode, label, note in DISCOVERY_MODES],
        collectr_url=settings.collectr_showcase_url,
        browser_scans_enabled=Config.BROWSER_SCANS_ENABLED,
    )


@snipe_bp.get("/api/snipe/summary")
def snipe_summary():
    settings = _settings()
    _revalue_cached(settings)
    summary = get_store().summary()
    summary["settings"] = {
        "poll_seconds": settings.poll_seconds, "snipe_lead_seconds": settings.snipe_lead_seconds,
        "ebay_mode": "browser" if Config.BROWSER_SCANS_ENABLED else "disabled" if not Config.EXTERNAL_ACCESS_ENABLED else "api" if settings.ebay_api_enabled else "chrome",
        "ebay_domain": settings.ebay_domain, "external_access_enabled": Config.EXTERNAL_ACCESS_ENABLED,
        "browser_scans_enabled": Config.BROWSER_SCANS_ENABLED,
        "fb_city": settings.fb_city, "fb_auto_message": settings.fb_auto_message and Config.EXTERNAL_ACCESS_ENABLED,
        "watchlist_path": settings.watchlist_path, "currency": settings.ebay_currency,
        "collectr_url": settings.collectr_showcase_url,
    }
    return jsonify(summary)


@snipe_bp.get("/api/snipe/deals")
def snipe_deals():
    _revalue_cached(_settings())
    rows = get_store().recent_deals(
        limit=_limit(100), lane=request.args.get("lane") or None, source=request.args.get("source") or None
    )
    return jsonify({"deals": [_listing_dict(r) for r in rows]})


@snipe_bp.delete("/api/snipe/listings/<int:row_id>")
def snipe_dismiss_listing(row_id: int):
    """Drop an unrelated posting. It stays seen, so the next scan will not add it again."""
    if not get_store().dismiss_listing(row_id):
        return jsonify({"error": "Listing not found."}), 404
    return jsonify({"message": "Removed"})


@snipe_bp.get("/api/snipe/listings")
def snipe_listings():
    rows = get_store().recent_listings(limit=_limit(100), source=request.args.get("source") or None)
    return jsonify({"listings": [_listing_dict(r) for r in rows]})


@snipe_bp.get("/api/snipe/bids")
def snipe_bids():
    return jsonify({"bids": [_bid_dict(r) for r in get_store().all_bids(_limit(100))]})


@snipe_bp.post("/api/snipe/bids/<int:bid_id>/cancel")
def snipe_cancel_bid(bid_id: int):
    if not get_store().cancel_bid(bid_id):
        return jsonify({"error": "Bid is not pending or does not exist."}), 404
    return jsonify({"message": f"Bid #{bid_id} cancelled"})


@snipe_bp.get("/api/snipe/scans")
def snipe_scans():
    return jsonify({"scans": [_scan_dict(r) for r in get_store().recent_scans(_limit(50, 500))]})


@snipe_bp.route("/api/snipe/watchlist", methods=["GET", "POST"])
def snipe_watchlist():
    settings = _settings()
    with _watchlist_lock:
        watchlist = load_watchlist(settings.watchlist_path)
        if request.method == "POST":
            watchlist.targets.append(_edited_target(_payload(), watchlist))
            save_watchlist(settings.watchlist_path, watchlist)
            _revalue_cached(settings, watchlist)
        return jsonify(_watchlist_data(watchlist, settings))


@snipe_bp.get("/api/snipe/discovery")
def snipe_discovery():
    raw = request.args.get("query", "")
    if len(raw) > 160 or any(ord(char) < 32 for char in raw):
        raise ValueError("Use search keywords between 1 and 160 characters")
    query = raw.strip() or "pokemon cards"
    settings = _settings()
    watchlist = load_watchlist(settings.watchlist_path)
    target = Target(name=query, keywords=[query], max_price=watchlist.budget, use_market=False)
    return jsonify({
        "query": target.search_query, "budget": watchlist.budget, "currency": settings.ebay_currency,
        "search_links": _browser_search_links(target, settings, mode="all"),
        "search_modes": {mode: _browser_search_links(target, settings, mode=mode)
                         for mode, _, _ in DISCOVERY_MODES},
    })


@snipe_bp.patch("/api/snipe/budget")
def snipe_budget():
    settings = _settings()
    payload = _payload()
    if "budget" not in payload:
        raise ValueError("A budget is required. Use null to clear it.")
    with _watchlist_lock:
        watchlist = load_watchlist(settings.watchlist_path)
        watchlist.budget = optional_budget(payload["budget"])
        save_watchlist(settings.watchlist_path, watchlist)
        _revalue_cached(settings, watchlist)
        return jsonify(_watchlist_data(watchlist, settings))


@snipe_bp.get("/api/snipe/valuations")
def snipe_valuations():
    settings = _settings()
    watchlist = load_watchlist(settings.watchlist_path)
    cached = {v["target_name"]: v for v in get_store().all_valuations()}
    rows = []
    for target in watchlist.targets:
        valuation = cached.get(target.name)
        if valuation and (valuation.get("market_query") != target.market_query
                          or valuation.get("currency") != settings.ebay_currency
                          or valuation.get("schema_version") != VALUATION_VERSION):
            valuation = None
        stale = bool(valuation and (datetime.now(timezone.utc) - datetime.fromisoformat(valuation["fetched_at"])).total_seconds()
                     >= settings.price_ttl_hours * 3600)
        rows.append({
            "target": target.name, "market_query": target.market_query, "use_market": target.use_market,
            "max_price": target.max_price, "bargain_pct": target.bargain_pct, "irregular_pct": target.irregular_pct,
            "valuation": valuation, "stale": stale,
            "effective_budget": target.within_budget(watchlist.budget).max_price,
        })
    return jsonify({"valuations": rows, "currency": settings.ebay_currency,
                    "local_only": not Config.EXTERNAL_ACCESS_ENABLED})


@snipe_bp.post("/api/snipe/valuations/refresh")
def snipe_valuations_refresh():
    settings = _settings()
    watchlist = load_watchlist(settings.watchlist_path)
    wanted = (request.args.get("target") or "").lower()
    pricer = PriceService(settings, get_store())
    refreshed, failed = [], []
    for target in watchlist.targets:
        if wanted and target.name.lower() != wanted:
            continue
        if not target.use_market:
            continue
        try:
            (refreshed if pricer.refresh(target) else failed).append(target.name)
        except Exception as exc:
            failed.append(f"{target.name}: {exc}")
    stats = _revalue_cached(settings, watchlist)
    return jsonify({"refreshed": refreshed, "failed": failed, "revalued": stats})


@snipe_bp.post("/api/snipe/revalue")
def snipe_revalue():
    from cardsnipe.runner import revalue_store

    settings = _settings()
    store = get_store()
    stats = revalue_store(store, load_watchlist(settings.watchlist_path), PriceService(settings, store),
                         currency=settings.ebay_currency, cached_only=not Config.EXTERNAL_ACCESS_ENABLED)
    return jsonify(stats | {"message": f"Re-judged {stats['checked']} listings · {stats['matched']} deals · {stats['changed']} changed"})


@snipe_bp.get("/api/snipe/collection")
def snipe_collection():
    settings = _settings()
    items, latest = get_store().collection()
    history = get_store().collection_history()
    fx = (usd_rate(settings.ebay_currency, settings.usd_rate_fallback) if Config.EXTERNAL_ACCESS_ENABLED
          else 1.0 if settings.ebay_currency == "USD" else settings.usd_rate_fallback)
    return jsonify({
        "configured_url": settings.collectr_showcase_url,
        "currency": settings.ebay_currency, "fx": fx,
        "fx_estimated": not Config.EXTERNAL_ACCESS_ENABLED and settings.ebay_currency != "USD",
        "local_only": not Config.EXTERNAL_ACCESS_ENABLED,
        "automatic_sync": False,
        "snapshot": {
            "synced_at": _iso(latest.synced_at), "owner": latest.owner, "source_url": latest.source_url,
            "total_value_usd": latest.total_value_usd, "market_value_usd": latest.market_value_usd,
            "unvalued_items": latest.unvalued_items or 0,
            "total_cards": latest.total_cards, "total_graded": latest.total_graded,
        } if latest else None,
        "items": [{
            "id": i.id, "name": i.name, "set_name": i.set_name, "rarity": i.rarity, "number": i.number,
            "value_usd": i.value_usd, "change_usd": i.change_usd, "change_pct": i.change_pct,
            "quantity": i.quantity, "graded": bool(i.graded), "grade": i.grade,
            "condition": i.condition, "finish": i.finish,
            "market_value_usd": i.market_value_usd, "market_source": i.market_source, "market_bucket": i.market_bucket,
        } for i in items],
        "history": [{"synced_at": _iso(h.synced_at), "total_value_usd": h.total_value_usd,
                     "market_value_usd": h.market_value_usd, "total_cards": h.total_cards}
                    for h in reversed(history)],
    })


@snipe_bp.post("/api/snipe/collection/import")
def snipe_collection_import():
    from cardsnipe.collectr import parse_showcase_import

    payload = _payload()
    result = parse_showcase_import(payload.get("text"))
    if payload.get("confirm") is not True:
        return jsonify({"preview": True, "owner": result.owner, "items": result.items,
                        "total_cards": result.total_cards, "total_value_usd": result.total_value_usd})
    settings = _settings()
    _, latest = get_store().collection()
    source_url = settings.collectr_showcase_url or (latest.source_url if latest else "")
    snapshot = get_store().replace_collection(result.items, result.total_value_usd, source_url,
                                             owner=result.owner, total_graded=result.total_graded)
    return jsonify({"message": f"Imported {snapshot.total_cards} cards. Collectr figures are saved references; independent prices need verification.",
                    "local_only": True, "total_cards": snapshot.total_cards})


def _snapshot_message(snapshot) -> str:
    ours = f"ours US${snapshot.market_value_usd:,.2f}" if snapshot.market_value_usd else "nothing priced yet"
    unvalued = f" · {snapshot.unvalued_items} unpriced" if snapshot.unvalued_items else ""
    return f"{snapshot.total_cards} cards · {ours} · Collectr US${snapshot.total_value_usd or 0:,.2f}{unvalued}"


@snipe_bp.post("/api/snipe/collection/sync")
def snipe_collection_sync():
    from cardsnipe.collectr import sync_collection

    settings = _settings()
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url") or settings.collectr_showcase_url).strip()
    if not url.startswith("https://app.getcollectr.com/"):
        return jsonify({"error": "Set COLLECTR_SHOWCASE_URL to your https://app.getcollectr.com/showcase/... link"}), 400
    try:
        snapshot = sync_collection(get_store(), url, settings.chrome_profile_dir, pricer=PriceService(settings, get_store()))
    except Exception as exc:
        return jsonify({"error": f"Collectr sync failed: {exc}"}), 502
    return jsonify({"message": "Synced · " + _snapshot_message(snapshot)})


@snipe_bp.post("/api/snipe/collection/revalue")
def snipe_collection_revalue():
    """Re-price the stored collection with our sources (no Collectr fetch)."""
    from cardsnipe.collectr import revalue_collection

    settings = _settings()
    force = request.args.get("force") in ("1", "true")
    snapshot = revalue_collection(get_store(), PriceService(settings, get_store()), force=force)
    if snapshot is None:
        return jsonify({"error": "Nothing synced yet — press Sync now first"}), 400
    return jsonify({"message": "Re-priced · " + _snapshot_message(snapshot)})


@snipe_bp.delete("/api/snipe/watchlist/<path:name>")
def snipe_watchlist_delete(name: str):
    settings = _settings()
    with _watchlist_lock:
        if not remove_target(settings.watchlist_path, name):
            return jsonify({"error": "No target with that name"}), 404
        _revalue_cached(settings)
        return jsonify(_watchlist_data(load_watchlist(settings.watchlist_path), settings))


@snipe_bp.patch("/api/snipe/watchlist/<path:name>")
def snipe_watchlist_edit(name: str):
    settings = _settings()
    payload = _payload()
    with _watchlist_lock:
        watchlist = load_watchlist(settings.watchlist_path)
        for index, target in enumerate(watchlist.targets):
            if target.name.lower() == name.lower():
                watchlist.targets[index] = _edited_target(payload, watchlist, previous=target)
                save_watchlist(settings.watchlist_path, watchlist)
                _revalue_cached(settings, watchlist)
                return jsonify(_watchlist_data(watchlist, settings))
    return jsonify({"error": "No target with that name"}), 404
