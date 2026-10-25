"""Scan loop: pull new listings per target, evaluate, alert, and schedule/fire auction snipes."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from cardsnipe.matcher import Listing, Match, evaluate
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import ScheduledBid, Store
from cardsnipe.watchlist import Target, Watchlist

logger = logging.getLogger("cardsnipe.runner")

# How early the bid page is opened before the actual confirm click.
BID_PREP_SECONDS = 25


class Source(Protocol):
    name: str

    def find(self, target: Target) -> list[Listing]: ...


@dataclass
class ScanReport:
    scanned: int = 0
    new_listings: int = 0
    deals: list[Match] = field(default_factory=list)
    bids_scheduled: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scanned {self.scanned} · new {self.new_listings} · deals {len(self.deals)} · "
            f"bids scheduled {self.bids_scheduled} · errors {len(self.errors)}"
        )


def bid_fire_time(end_time: datetime, settings: SnipeSettings) -> datetime:
    """When the scheduler should start the snipe (open the page, then wait for the lead window)."""
    return end_time - timedelta(seconds=settings.snipe_lead_seconds + BID_PREP_SECONDS)


class SnipeRunner:
    def __init__(
        self,
        settings: SnipeSettings,
        watchlist: Watchlist,
        store: Store,
        sources: dict[str, Source],
        notifier,
        bid_executor: Callable[[ScheduledBid], tuple[str, str]] | None = None,
        messenger: Callable[[Listing, str, bool], tuple[str, str]] | None = None,
    ):
        self.settings = settings
        self.watchlist = watchlist
        self.store = store
        self.sources = sources
        self.notifier = notifier
        self.bid_executor = bid_executor
        self.messenger = messenger
        self._stop = threading.Event()

    # ── scanning ─────────────────────────────────────────────────────────
    def scan_once(self) -> ScanReport:
        report = ScanReport()
        started = datetime.now(timezone.utc)
        begin = getattr(self.notifier, "begin_scan", None)
        if begin:
            begin()
        try:
            self._scan_targets(report)
        finally:
            end = getattr(self.notifier, "end_scan", None)
            if end:
                end()
            try:
                self.store.record_scan(
                    started=started, finished=datetime.now(timezone.utc),
                    sources=list(self.sources), live=self.settings.live,
                    scanned=report.scanned, new_listings=report.new_listings, deals=len(report.deals),
                    regrade_deals=sum(1 for m in report.deals if m.lane == "regrade"),
                    bids_scheduled=report.bids_scheduled, errors=report.errors,
                )
            except Exception as exc:
                logger.warning("could not record scan: %s", exc)
        return report

    def _scan_targets(self, report: ScanReport) -> None:
        for target in self.watchlist.enabled_targets():
            for name, source in self.sources.items():
                if not target.uses_source(name):
                    continue
                try:
                    listings = source.find(target)
                except Exception as exc:
                    message = f"{name} search failed for {target.name!r}: {exc}"
                    logger.warning(message)
                    report.errors.append(message)
                    continue
                report.scanned += len(listings)
                for listing in listings:
                    self._handle_listing(listing, target, report)

    def _handle_listing(self, listing: Listing, target: Target, report: ScanReport) -> None:
        if self.store.is_seen(listing):
            return
        match = evaluate(
            listing, target, self.watchlist.global_exclude,
            tag_ten_score=self.watchlist.tag_ten_score, tag_near_margin=self.watchlist.tag_near_margin,
        )
        self.store.record_listing(listing, match)
        report.new_listings += 1
        if not match:
            return
        report.deals.append(match)
        try:
            self.notifier.deal(match)
            self.store.mark_action(listing, "alerted", notified=True)
        except Exception as exc:
            logger.warning("notify failed: %s", exc)
        self._act(match, report)

    def _act(self, match: Match, report: ScanReport) -> None:
        listing = match.listing
        if listing.source == "ebay" and listing.listing_type == "auction":
            if match.target.max_bid and listing.end_time:
                now = datetime.now(timezone.utc)
                if listing.end_time <= now + timedelta(seconds=self.settings.snipe_lead_seconds + 3):
                    self.store.mark_action(listing, "skipped", "auction ends too soon to snipe")
                    return
                # A past fire_at simply fires on the next scheduler tick.
                fire_at = bid_fire_time(listing.end_time, self.settings)
                bid = self.store.schedule_bid(match, match.target.max_bid, fire_at)
                if bid:
                    report.bids_scheduled += 1
                    self.store.mark_action(
                        listing, "bid_scheduled",
                        f"max {match.target.max_bid:.2f} at {fire_at.isoformat(timespec='seconds')}",
                    )
            return
        if listing.source == "facebook" and self.settings.fb_auto_message and self.messenger:
            try:
                status, detail = self.messenger(listing, self.settings.fb_message_template, self.settings.live)
            except Exception as exc:
                status, detail = "failed", str(exc)
            self.store.mark_action(listing, f"message_{status}", detail)

    # ── bidding ──────────────────────────────────────────────────────────
    def fire_due_bids(self, now: datetime | None = None) -> list[tuple[ScheduledBid, str, str]]:
        """Execute every pending bid whose fire_at has arrived. Returns (bid, status, detail)."""
        now = now or datetime.now(timezone.utc)
        results = []
        for bid in self.store.pending_bids():
            if bid.fire_at > now:
                continue
            if bid.end_time and bid.end_time < now:
                self.store.finish_bid(bid.id, "failed", "auction already ended")
                continue
            if not self.store.claim_bid(bid.id):
                continue
            if self.bid_executor is None:
                status, detail = "failed", "no bid executor configured"
            else:
                try:
                    status, detail = self.bid_executor(bid)
                except Exception as exc:
                    status, detail = "failed", f"executor error: {exc}"
            self.store.finish_bid(bid.id, status, detail)
            results.append((bid, status, detail))
            try:
                self.notifier.info(f"Snipe {status}: {bid.title[:50]}", detail[:140])
            except Exception:
                pass
        return results

    def _bid_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.fire_due_bids()
            except Exception as exc:
                logger.warning("bid loop error: %s", exc)
            self._stop.wait(0.5)

    # ── watch ────────────────────────────────────────────────────────────
    def watch(self, on_report: Callable[[ScanReport], None] | None = None) -> None:
        self._stop.clear()
        bid_thread = threading.Thread(target=self._bid_loop, name="cardsnipe-bids", daemon=True)
        bid_thread.start()
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                report = self.scan_once()
                if on_report:
                    on_report(report)
                elapsed = time.monotonic() - started
                self._stop.wait(max(1.0, self.settings.poll_seconds - elapsed))
        finally:
            self._stop.set()
            bid_thread.join(timeout=2)

    def stop(self) -> None:
        self._stop.set()
