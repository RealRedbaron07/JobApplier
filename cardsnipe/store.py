"""SQLite persistence for seen listings and scheduled bids (separate from the job DB)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from cardsnipe.matcher import Listing, Match

Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class SeenListing(Base):
    __tablename__ = "seen_listings"
    __table_args__ = (UniqueConstraint("source", "listing_id", name="uq_source_listing"),)

    id = Column(Integer, primary_key=True)
    source = Column(String(20), nullable=False)
    listing_id = Column(String(80), nullable=False)
    title = Column(Text)
    price = Column(Float)
    shipping = Column(Float)
    total_price = Column(Float)
    currency = Column(String(8))
    url = Column(Text)
    listing_type = Column(String(20))
    end_time = Column(DateTime)
    location = Column(String(255))
    first_seen = Column(DateTime, default=utcnow)
    matched_target = Column(String(255))
    savings_pct = Column(Float)
    lane = Column(String(20))
    grade = Column(String(20))
    tag_score = Column(Integer)
    notified = Column(Boolean, default=False)
    action = Column(String(40))
    action_detail = Column(Text)
    action_at = Column(DateTime)


class ScheduledBid(Base):
    __tablename__ = "scheduled_bids"

    id = Column(Integer, primary_key=True)
    source = Column(String(20), default="ebay")
    listing_id = Column(String(80), nullable=False)
    title = Column(Text)
    url = Column(Text)
    target_name = Column(String(255))
    max_bid = Column(Float, nullable=False)
    currency = Column(String(8))
    end_time = Column(DateTime, nullable=False)
    fire_at = Column(DateTime, nullable=False)
    status = Column(String(20), default="pending")  # pending|firing|placed|dry_run|failed|cancelled
    result = Column(Text)
    created = Column(DateTime, default=utcnow)
    updated = Column(DateTime, default=utcnow)


class ScanRun(Base):
    """One pass over the watchlist — history for the dashboard and health checks."""

    __tablename__ = "scan_runs"

    id = Column(Integer, primary_key=True)
    started = Column(DateTime, default=utcnow)
    finished = Column(DateTime)
    duration_seconds = Column(Float)
    sources = Column(String(80))
    live = Column(Boolean, default=False)
    scanned = Column(Integer, default=0)
    new_listings = Column(Integer, default=0)
    deals = Column(Integer, default=0)
    regrade_deals = Column(Integer, default=0)
    bids_scheduled = Column(Integer, default=0)
    errors = Column(Text, default="[]")


class Store:
    def __init__(self, database_url: str):
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            self.engine = create_engine(
                "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
        else:
            self.engine = create_engine(database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self):
        return self._session_factory()

    # ── listings ──────────────────────────────────────────────────────────
    def is_seen(self, listing: Listing) -> bool:
        with self.session() as session:
            return session.query(SeenListing.id).filter_by(
                source=listing.source, listing_id=listing.listing_id
            ).first() is not None

    def record_listing(self, listing: Listing, match: Match | None) -> SeenListing:
        with self.session() as session:
            row = session.query(SeenListing).filter_by(
                source=listing.source, listing_id=listing.listing_id
            ).first()
            if row is None:
                row = SeenListing(source=listing.source, listing_id=listing.listing_id)
                session.add(row)
            row.title = listing.title
            row.price = listing.price
            row.shipping = listing.shipping
            row.total_price = listing.total_price
            row.currency = listing.currency
            row.url = listing.url
            row.listing_type = listing.listing_type
            row.end_time = listing.end_time
            row.location = listing.location
            if match:
                row.matched_target = match.target.name
                row.savings_pct = match.savings_pct
                row.lane = match.lane
                row.grade = f"{match.grade[0]} {match.grade[1]:g}" if match.grade else None
                row.tag_score = match.tag_score
            session.commit()
            return row

    def mark_action(self, listing: Listing, action: str, detail: str = "", notified: bool | None = None) -> None:
        with self.session() as session:
            row = session.query(SeenListing).filter_by(
                source=listing.source, listing_id=listing.listing_id
            ).first()
            if row is None:
                return
            row.action = action
            row.action_detail = detail[:2000] if detail else detail
            row.action_at = utcnow()
            if notified is not None:
                row.notified = notified
            session.commit()

    def recent_deals(self, limit: int = 30, lane: str | None = None, source: str | None = None) -> list[SeenListing]:
        with self.session() as session:
            query = session.query(SeenListing).filter(SeenListing.matched_target.isnot(None))
            if lane:
                query = query.filter(SeenListing.lane == lane)
            if source:
                query = query.filter(SeenListing.source == source)
            return query.order_by(SeenListing.first_seen.desc()).limit(limit).all()

    def recent_listings(self, limit: int = 100, source: str | None = None) -> list[SeenListing]:
        with self.session() as session:
            query = session.query(SeenListing)
            if source:
                query = query.filter(SeenListing.source == source)
            return query.order_by(SeenListing.first_seen.desc()).limit(limit).all()

    # ── scan history ─────────────────────────────────────────────────────
    def record_scan(self, started: datetime, finished: datetime, sources: list[str], live: bool,
                    scanned: int, new_listings: int, deals: int, regrade_deals: int,
                    bids_scheduled: int, errors: list[str]) -> ScanRun:
        import json

        with self.session() as session:
            run = ScanRun(
                started=started, finished=finished,
                duration_seconds=(finished - started).total_seconds(),
                sources=",".join(sources), live=live, scanned=scanned, new_listings=new_listings,
                deals=deals, regrade_deals=regrade_deals, bids_scheduled=bids_scheduled,
                errors=json.dumps(errors[:20]),
            )
            session.add(run)
            session.commit()
            return run

    def recent_scans(self, limit: int = 50) -> list[ScanRun]:
        with self.session() as session:
            return session.query(ScanRun).order_by(ScanRun.started.desc()).limit(limit).all()

    def summary(self) -> dict:
        """Headline numbers for the dashboard."""
        from datetime import timedelta

        from sqlalchemy import func

        day_ago = utcnow() - timedelta(hours=24)
        with self.session() as session:
            deals_q = session.query(SeenListing).filter(SeenListing.matched_target.isnot(None))
            by_source = dict(
                session.query(SeenListing.source, func.count(SeenListing.id))
                .filter(SeenListing.matched_target.isnot(None)).group_by(SeenListing.source).all()
            )
            by_target = dict(
                session.query(SeenListing.matched_target, func.count(SeenListing.id))
                .filter(SeenListing.matched_target.isnot(None)).group_by(SeenListing.matched_target).all()
            )
            bid_status = dict(
                session.query(ScheduledBid.status, func.count(ScheduledBid.id)).group_by(ScheduledBid.status).all()
            )
            last_scan = session.query(ScanRun).order_by(ScanRun.started.desc()).first()
            return {
                "listings_seen": session.query(func.count(SeenListing.id)).scalar() or 0,
                "listings_seen_24h": session.query(func.count(SeenListing.id))
                .filter(SeenListing.first_seen >= day_ago).scalar() or 0,
                "deals_total": deals_q.count(),
                "deals_24h": deals_q.filter(SeenListing.first_seen >= day_ago).count(),
                "regrade_total": deals_q.filter(SeenListing.lane == "regrade").count(),
                "messages_sent": session.query(func.count(SeenListing.id))
                .filter(SeenListing.action == "message_sent").scalar() or 0,
                "deals_by_source": by_source,
                "deals_by_target": by_target,
                "bids_by_status": bid_status,
                "scans_total": session.query(func.count(ScanRun.id)).scalar() or 0,
                "last_scan": {
                    "started": last_scan.started.isoformat() if last_scan and last_scan.started else None,
                    "duration_seconds": last_scan.duration_seconds if last_scan else None,
                    "scanned": last_scan.scanned if last_scan else 0,
                    "deals": last_scan.deals if last_scan else 0,
                    "errors": last_scan.errors if last_scan else "[]",
                    "live": bool(last_scan.live) if last_scan else False,
                } if last_scan else None,
            }

    # ── bids ──────────────────────────────────────────────────────────────
    def schedule_bid(self, match: Match, max_bid: float, fire_at: datetime) -> ScheduledBid | None:
        listing = match.listing
        with self.session() as session:
            existing = session.query(ScheduledBid).filter(
                ScheduledBid.listing_id == listing.listing_id,
                ScheduledBid.status.in_(["pending", "firing"]),
            ).first()
            if existing:
                return None
            bid = ScheduledBid(
                source=listing.source,
                listing_id=listing.listing_id,
                title=listing.title,
                url=listing.url,
                target_name=match.target.name,
                max_bid=max_bid,
                currency=listing.currency,
                end_time=listing.end_time,
                fire_at=fire_at,
            )
            session.add(bid)
            session.commit()
            return bid

    def pending_bids(self) -> list[ScheduledBid]:
        with self.session() as session:
            rows = session.query(ScheduledBid).filter_by(status="pending").order_by(ScheduledBid.fire_at).all()
            for row in rows:
                row.fire_at = _aware(row.fire_at)
                row.end_time = _aware(row.end_time)
            return rows

    def all_bids(self, limit: int = 50) -> list[ScheduledBid]:
        with self.session() as session:
            rows = session.query(ScheduledBid).order_by(ScheduledBid.created.desc()).limit(limit).all()
            for row in rows:
                row.fire_at = _aware(row.fire_at)
                row.end_time = _aware(row.end_time)
            return rows

    def claim_bid(self, bid_id: int) -> bool:
        """Atomically move a bid from pending to firing so it cannot fire twice."""
        with self.session() as session:
            updated = (
                session.query(ScheduledBid)
                .filter_by(id=bid_id, status="pending")
                .update({"status": "firing", "updated": utcnow()})
            )
            session.commit()
            return updated == 1

    def finish_bid(self, bid_id: int, status: str, result: str = "") -> None:
        with self.session() as session:
            bid = session.get(ScheduledBid, bid_id)
            if bid is None:
                return
            bid.status = status
            bid.result = result[:2000] if result else result
            bid.updated = utcnow()
            session.commit()

    def cancel_bid(self, bid_id: int) -> bool:
        with self.session() as session:
            bid = session.get(ScheduledBid, bid_id)
            if bid is None or bid.status not in {"pending"}:
                return False
            bid.status = "cancelled"
            bid.updated = utcnow()
            session.commit()
            return True
