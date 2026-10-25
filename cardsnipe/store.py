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
    market_value = Column(Float)          # value for the listing's grade bucket, listing currency
    value_source = Column(String(30))     # tcgplayer / pricecharting / ebay_sold
    value_bucket = Column(String(8))
    irregular = Column(Boolean, default=False)
    irregular_reason = Column(String(80))
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


class ValuationRow(Base):
    """Cached market valuation per target (JSON payload from cardsnipe.pricing.Valuation)."""

    __tablename__ = "valuations"

    id = Column(Integer, primary_key=True)
    target_name = Column(String(200), unique=True, nullable=False)
    currency = Column(String(8))
    payload = Column(Text, nullable=False)
    fetched_at = Column(DateTime, default=utcnow)


class CollectionItem(Base):
    """A card in the user's Collectr showcase (what they can trade up from)."""

    __tablename__ = "collection_items"

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    set_name = Column(Text)
    rarity = Column(Text)
    number = Column(String(40))
    value_usd = Column(Float)
    change_usd = Column(Float)
    change_pct = Column(Float)
    quantity = Column(Integer, default=1)
    graded = Column(Boolean, default=False)
    synced_at = Column(DateTime, default=utcnow)


class CollectionSnapshot(Base):
    """Portfolio total per sync, so the dashboard can chart it over time."""

    __tablename__ = "collection_snapshots"

    id = Column(Integer, primary_key=True)
    synced_at = Column(DateTime, default=utcnow)
    source_url = Column(Text)
    owner = Column(Text)
    total_value_usd = Column(Float)
    total_cards = Column(Integer)
    total_graded = Column(Integer)


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
        self._add_missing_columns()
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _add_missing_columns(self) -> None:
        """SQLite-only forward migration: add columns that newer code expects on existing tables."""
        from sqlalchemy import inspect, text

        inspector = inspect(self.engine)
        with self.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                existing = {c["name"] for c in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name not in existing:
                        ddl = f'ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(self.engine.dialect)}'
                        conn.execute(text(ddl))

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
            self._apply_match(row, match)
            session.commit()
            return row

    @staticmethod
    def _apply_match(row: SeenListing, match: Match | None) -> None:
        if match is None:
            row.matched_target = None
            row.savings_pct = row.lane = row.grade = row.tag_score = None
            row.market_value = row.value_source = row.value_bucket = row.irregular_reason = None
            row.irregular = False
            return
        row.matched_target = match.target.name
        row.savings_pct = match.under_value_pct if match.market_value else match.savings_pct
        row.lane = match.lane
        row.grade = f"{match.grade[0]} {match.grade[1]:g}" if match.grade else None
        row.tag_score = match.tag_score
        row.market_value = match.market_value
        row.value_source = match.value_source or None
        row.value_bucket = match.value_bucket or None
        row.irregular = match.irregular
        row.irregular_reason = match.irregular_reason or None

    def revalue(self, evaluate_fn) -> dict:
        """Re-judge every stored listing with `evaluate_fn(listing) -> Match | None`.

        Used after valuations change so old cap-based matches get market numbers (or drop
        out). Alerts/actions already taken are left untouched.
        """
        from datetime import datetime as _dt

        stats = {"checked": 0, "matched": 0, "unmatched": 0, "changed": 0}
        with self.session() as session:
            for row in session.query(SeenListing).all():
                listing = Listing(
                    source=row.source, listing_id=row.listing_id, title=row.title or "", price=row.price,
                    currency=row.currency or "", url=row.url or "", listing_type=row.listing_type or "bin",
                    shipping=row.shipping, end_time=_aware(row.end_time), location=row.location or "",
                )
                before = (row.matched_target, row.market_value, row.lane, row.irregular)
                match = evaluate_fn(listing)
                self._apply_match(row, match)
                stats["checked"] += 1
                stats["matched" if match else "unmatched"] += 1
                if before != (row.matched_target, row.market_value, row.lane, row.irregular):
                    stats["changed"] += 1
            session.commit()
        return stats

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

    # ── valuations ───────────────────────────────────────────────────────
    def save_valuation(self, valuation) -> None:
        import json

        with self.session() as session:
            row = session.query(ValuationRow).filter_by(target_name=valuation.target_name).first()
            if row is None:
                row = ValuationRow(target_name=valuation.target_name)
                session.add(row)
            row.currency = valuation.currency
            row.payload = json.dumps(valuation.to_dict())
            row.fetched_at = valuation.fetched_at
            session.commit()

    def load_valuation(self, target_name: str) -> dict | None:
        import json

        with self.session() as session:
            row = session.query(ValuationRow).filter_by(target_name=target_name).first()
            return json.loads(row.payload) if row else None

    def all_valuations(self) -> list[dict]:
        import json

        with self.session() as session:
            rows = session.query(ValuationRow).order_by(ValuationRow.target_name).all()
            return [json.loads(r.payload) for r in rows]

    # ── collection (Collectr) ────────────────────────────────────────────
    def replace_collection(self, items: list[dict], total_value_usd: float | None, source_url: str,
                           owner: str = "", total_graded: int | None = None) -> CollectionSnapshot:
        now = utcnow()
        with self.session() as session:
            session.query(CollectionItem).delete()
            for item in items:
                session.add(CollectionItem(
                    name=item["name"], set_name=item.get("set_name"), rarity=item.get("rarity"),
                    number=item.get("number"), value_usd=item.get("value_usd"), change_usd=item.get("change_usd"),
                    change_pct=item.get("change_pct"), quantity=int(item.get("quantity") or 1),
                    graded=bool(item.get("graded")), synced_at=now,
                ))
            snapshot = CollectionSnapshot(
                synced_at=now, source_url=source_url, owner=owner,
                total_value_usd=total_value_usd if total_value_usd is not None
                else sum((i.get("value_usd") or 0) * int(i.get("quantity") or 1) for i in items),
                total_cards=sum(int(i.get("quantity") or 1) for i in items),
                total_graded=total_graded if total_graded is not None else sum(1 for i in items if i.get("graded")),
            )
            session.add(snapshot)
            session.commit()
            return snapshot

    def collection(self) -> tuple[list[CollectionItem], CollectionSnapshot | None]:
        with self.session() as session:
            items = session.query(CollectionItem).order_by(CollectionItem.value_usd.desc()).all()
            latest = session.query(CollectionSnapshot).order_by(CollectionSnapshot.synced_at.desc()).first()
            return items, latest

    def collection_history(self, limit: int = 90) -> list[CollectionSnapshot]:
        with self.session() as session:
            return session.query(CollectionSnapshot).order_by(CollectionSnapshot.synced_at.desc()).limit(limit).all()

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
                "irregular_total": deals_q.filter(SeenListing.irregular.is_(True)).count(),
                "valuations": session.query(func.count(ValuationRow.id)).scalar() or 0,
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
