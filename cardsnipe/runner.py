"""Scan loop: pull new listings per target, evaluate, alert, and schedule/fire auction snipes."""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from cardsnipe.matcher import Listing, Match, evaluate
from cardsnipe.browser import SourceUnavailable
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import ScheduledBid, Store
from cardsnipe.watchlist import Target, Watchlist, load_watchlist

logger = logging.getLogger("cardsnipe.runner")

# How early the bid page is opened before the actual confirm click.
BID_PREP_SECONDS = 25


@contextmanager
def scanner_session(settings: SnipeSettings):
    # shortcut: POSIX locking suits this local Mac app; add Windows locking if it is ported.
    import fcntl

    path = settings.chrome_profile_dir + ".scan.tmp"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another card scanner is running. Wait for it to finish or stop make snipe first.") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


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
            f"scanned {self.scanned} · new {self.new_listings} · new alerts {len(self.deals)} · "
            f"bids scheduled {self.bids_scheduled} · errors {len(self.errors)}"
        )


def revalue_store(store: Store, watchlist: Watchlist, pricer, currency: str | None = None,
                  cached_only: bool = False) -> dict:
    """Re-judge every stored listing against current market values (best match across targets)."""
    valuations = {}
    targets = watchlist.scan_targets()
    for target in targets:
        try:
            if pricer and target.use_market:
                valuations[target.name] = (pricer.valuation(target, cached_only=True) if cached_only
                                           else pricer.valuation(target))
            else:
                valuations[target.name] = None
        except Exception as exc:
            logger.warning("valuation failed for %r during revalue: %s", target.name, exc)
            valuations[target.name] = None

    def judge(listing: Listing) -> Match | None:
        if currency and listing.currency.upper() != currency.upper():
            return None
        matches = []
        for target in targets:
            match = evaluate(listing, target, watchlist.global_exclude, tag_ten_score=watchlist.tag_ten_score,
                             tag_near_margin=watchlist.tag_near_margin, valuation=valuations.get(target.name))
            if match:
                matches.append(match)
        return max(matches, key=lambda m: m.savings_pct) if matches else None

    return store.revalue(judge)


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
        pricer=None,
    ):
        self.settings = settings
        self.watchlist = watchlist
        self.store = store
        self.sources = sources
        self.notifier = notifier
        self.bid_executor = bid_executor
        self.messenger = messenger
        self.pricer = pricer  # cardsnipe.pricing.PriceService or None (cap-only mode)
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

    def _valuation(self, target: Target, report: ScanReport):
        if self.pricer is None or not target.use_market:
            return None
        try:
            return self.pricer.valuation(target)
        except Exception as exc:
            message = f"valuation failed for {target.name!r}: {exc}"
            logger.warning(message)
            report.errors.append(message)
            return None

    @staticmethod
    def _search_ceiling(target: Target, valuation) -> float | None:
        """Price filter for marketplace searches: the highest bucket value we'd ever pay for."""
        if valuation is None:
            return target.max_price
        values = [v[0] for b in ("raw", "7", "8", "9", "9.5", "10") if (v := valuation.value(b))]
        if not values:
            return target.max_price
        ceiling = max(values) * (1 - target.bargain_pct / 100.0)
        return min(ceiling, target.max_price) if target.max_price else ceiling

    def _scan_targets(self, report: ScanReport) -> None:
        targets = self.watchlist.scan_targets()
        valuations = {}
        found = {}
        unavailable = set()
        for target in targets:
            valuation = self._valuation(target, report)
            valuations[target.name] = valuation
            ceiling = self._search_ceiling(target, valuation)
            if ceiling is None:
                report.errors.append(f"{target.name!r}: no market value and no max_price — skipped")
                continue
            search_target = target.with_ceiling(ceiling)
            for name, source in self.sources.items():
                if not target.uses_source(name) or name in unavailable:
                    continue
                try:
                    listings = source.find(search_target)
                except Exception as exc:
                    message = f"{name} search failed for {target.name!r}: {exc}"
                    logger.warning(message)
                    report.errors.append(message)
                    if isinstance(exc, SourceUnavailable):
                        unavailable.add(name)
                    continue
                report.scanned += len(listings)
                for listing in listings:
                    found[listing.key] = listing
        for listing in found.values():
            self._handle_listing(listing, targets, report, valuations)

    def _handle_listing(self, listing: Listing, targets: list[Target], report: ScanReport, valuations: dict) -> None:
        def judge(allow_unverified=False):
            if (listing.currency or "").upper() != self.settings.ebay_currency:
                return []
            return [match for target in targets if (match := evaluate(
                listing, target, self.watchlist.global_exclude,
                tag_ten_score=self.watchlist.tag_ten_score, tag_near_margin=self.watchlist.tag_near_margin,
                valuation=valuations.get(target.name), allow_unverified_condition=allow_unverified,
            ))]

        matches = judge(allow_unverified=True)
        details = getattr(self.sources.get(listing.source), "details", None)
        if matches and details:
            try:
                listing = details(listing)
            except Exception as exc:
                listing.condition = "unverified"
                report.errors.append(f"{listing.source} condition check failed for {listing.listing_id}: {str(exc).splitlines()[0]}")
        matches = judge()
        match = max(matches, key=lambda m: m.savings_pct) if matches else None
        report.new_listings += int(not self.store.is_seen(listing))
        row = self.store.record_listing(listing, match)
        if not match or row.dismissed or row.notified:
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
            # Never schedule or place a bid. Auctions are not deals.
            return
        if listing.source == "facebook" and self.settings.fb_auto_message and self.messenger:
            try:
                status, detail = self.messenger(listing, self.settings.fb_message_template, self.settings.live)
            except Exception as exc:
                status, detail = "failed", str(exc)
            self.store.mark_action(listing, f"message_{status}", detail)

    # ── bidding ──────────────────────────────────────────────────────────
    def fire_due_bids(self, now: datetime | None = None) -> list[tuple[ScheduledBid, str, str]]:
        """Cancel leftover queued bids. Nothing is placed."""
        results = []
        for bid in self.store.pending_bids():
            if self.store.cancel_bid(bid.id):
                results.append((bid, "cancelled", "auctions are not bid on"))
        return results

    # ── watch ────────────────────────────────────────────────────────────
    def watch(self, on_report: Callable[[ScanReport], None] | None = None) -> None:
        self._stop.clear()
        self.fire_due_bids()
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    if not os.path.isfile(self.settings.watchlist_path):
                        raise ValueError("Watchlist file is missing")
                    self.watchlist = load_watchlist(self.settings.watchlist_path, create_example=False)
                except (OSError, ValueError) as exc:
                    logger.warning("Cannot load watchlist; skipping scan: %s", exc)
                    self._stop.wait(self.settings.poll_seconds)
                    continue
                report = self.scan_once()
                if on_report:
                    on_report(report)
                elapsed = time.monotonic() - started
                self._stop.wait(max(1.0, self.settings.poll_seconds - elapsed))
        finally:
            self._stop.set()

    def stop(self) -> None:
        self._stop.set()
