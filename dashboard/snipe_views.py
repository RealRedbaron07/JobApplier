"""Card sniper dashboard: read-only views over cardsnipe.db plus watchlist editing."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request

from cardsnipe.settings import SnipeSettings
from cardsnipe.store import ScanRun, ScheduledBid, SeenListing, Store
from cardsnipe.watchlist import Target, add_target, load_watchlist, remove_target, save_watchlist

snipe_bp = Blueprint("snipe", __name__)

_store: Store | None = None


def get_store() -> Store:
    global _store
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
        "first_seen": _iso(row.first_seen), "matched_target": row.matched_target, "savings_pct": row.savings_pct,
        "lane": row.lane, "grade": row.grade, "tag_score": row.tag_score, "notified": bool(row.notified),
        "action": row.action, "action_detail": row.action_detail, "action_at": _iso(row.action_at),
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


@snipe_bp.get("/snipe")
def snipe_page():
    settings = _settings()
    return render_template(
        "snipe.html",
        poll_seconds=settings.poll_seconds,
        ebay_mode="API" if settings.ebay_api_enabled else "Chrome",
        fb_city=settings.fb_city,
    )


@snipe_bp.get("/api/snipe/summary")
def snipe_summary():
    settings = _settings()
    summary = get_store().summary()
    summary["settings"] = {
        "poll_seconds": settings.poll_seconds, "snipe_lead_seconds": settings.snipe_lead_seconds,
        "ebay_mode": "api" if settings.ebay_api_enabled else "chrome", "ebay_domain": settings.ebay_domain,
        "fb_city": settings.fb_city, "fb_auto_message": settings.fb_auto_message,
        "watchlist_path": settings.watchlist_path,
    }
    return jsonify(summary)


@snipe_bp.get("/api/snipe/deals")
def snipe_deals():
    rows = get_store().recent_deals(
        limit=_limit(100), lane=request.args.get("lane") or None, source=request.args.get("source") or None
    )
    return jsonify({"deals": [_listing_dict(r) for r in rows]})


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
    path = _settings().watchlist_path
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        keywords = [str(k).strip() for k in payload.get("keywords", []) if str(k).strip()]
        if not name or not keywords:
            return jsonify({"error": "name and at least one keyword are required"}), 400
        try:
            max_price = float(payload.get("max_price"))
        except (TypeError, ValueError):
            return jsonify({"error": "max_price must be a number"}), 400

        def _opt(key):
            value = payload.get(key)
            return float(value) if value not in (None, "") else None

        sources = [s for s in payload.get("sources", ["ebay", "facebook"]) if s in ("ebay", "facebook")] or ["ebay", "facebook"]
        target = Target(
            name=name, keywords=keywords, max_price=max_price, max_bid=_opt("max_bid"), min_price=_opt("min_price"),
            exclude=[str(x).strip() for x in payload.get("exclude", []) if str(x).strip()],
            graded_only=bool(payload.get("graded_only")), min_grade=_opt("min_grade"),
            raw_ok=not bool(payload.get("graded_only")), sources=sources,
            regrade=bool(payload.get("regrade")),
            regrade_min_grade=_opt("regrade_min_grade") or 8.0, regrade_max_grade=_opt("regrade_max_grade") or 9.5,
            regrade_max_price=_opt("regrade_max_price"), note=str(payload.get("note", ""))[:200],
        )
        add_target(path, target)
    watchlist = load_watchlist(path)
    return jsonify(watchlist.to_dict() | {"path": path})


@snipe_bp.delete("/api/snipe/watchlist/<path:name>")
def snipe_watchlist_delete(name: str):
    path = _settings().watchlist_path
    if not remove_target(path, name):
        return jsonify({"error": "No target with that name"}), 404
    return jsonify(load_watchlist(path).to_dict())


@snipe_bp.patch("/api/snipe/watchlist/<path:name>")
def snipe_watchlist_toggle(name: str):
    """Enable/disable a target without deleting it."""
    path = _settings().watchlist_path
    watchlist = load_watchlist(path)
    payload = request.get_json(silent=True) or {}
    for target in watchlist.targets:
        if target.name.lower() == name.lower():
            if "enabled" in payload:
                target.enabled = bool(payload["enabled"])
            save_watchlist(path, watchlist)
            return jsonify(watchlist.to_dict())
    return jsonify({"error": "No target with that name"}), 404
