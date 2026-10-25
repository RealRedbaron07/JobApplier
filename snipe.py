#!/usr/bin/env python3
"""Pokémon card sniper for eBay + Facebook Marketplace.

  python3 snipe.py                      same as `watch` (dry-run loop)
  python3 snipe.py scan      (s)        one pass: alert on deals, simulate bids/messages
  python3 snipe.py watch     (w)        keep scanning every SNIPE_POLL_SECONDS
  python3 snipe.py watch --live         actually place eBay snipes / send FB messages
  python3 snipe.py login                open Chrome so you can sign in to eBay + Facebook once
  python3 snipe.py add       (a)        add "Moonbreon" --card "Umbreon VMAX (Alternate Art Secret)" --set "Evolving Skies" \\
                                            --number 215/203 --regrade --keywords umbreon vmax "alt art|215/203"
                                        (value comes from TCGPlayer/PriceCharting/eBay sold; --max adds a hard cap)
  python3 snipe.py remove    (rm)       remove "Moonbreon"
  python3 snipe.py value     (v)        market values per grade for every target (--refresh to refetch)
  python3 snipe.py collection (c)       sync your Collectr showcase (COLLECTR_SHOWCASE_URL) and show it
  python3 snipe.py list (l) | deals (d) | bids (b) | cancel-bid <id>

Shorter still: `make snipe`, `make live`, `make deals` ... (see `make help`).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from cardsnipe.notify import Notifier
from cardsnipe.pricing import PriceService, describe
from cardsnipe.runner import SnipeRunner
from cardsnipe.settings import SnipeSettings
from cardsnipe.store import Store
from cardsnipe.watchlist import Target, add_target, load_watchlist, remove_target


def _build_runner(settings: SnipeSettings, source_filter: str, watchlist):
    from cardsnipe.browser import Browser
    from cardsnipe.ebay import EbaySource, place_snipe
    from cardsnipe.facebook import FacebookMarketplace

    wanted = {"ebay", "facebook"} if source_filter == "all" else {source_filter}
    needs_browser = "facebook" in wanted or ("ebay" in wanted and not settings.ebay_api_enabled)
    browser = Browser(settings) if needs_browser else None

    sources = {}
    messenger = None
    if "ebay" in wanted:
        sources["ebay"] = EbaySource(settings, browser)
    if "facebook" in wanted:
        facebook = FacebookMarketplace(settings, browser)
        sources["facebook"] = facebook
        messenger = facebook.message_seller

    def bid_executor(bid):
        bid_browser = browser or Browser(settings)
        # Search-page end times are minute-granular without the API; re-read the exact countdown.
        return place_snipe(bid_browser, settings, bid.listing_id, bid.max_bid, bid.end_time,
                           settings.live, refine_end_time=not settings.ebay_api_enabled)

    store = Store(settings.database_url)
    runner = SnipeRunner(
        settings=settings,
        watchlist=watchlist,
        store=store,
        sources=sources,
        notifier=Notifier(settings),
        bid_executor=bid_executor if "ebay" in wanted else None,
        messenger=messenger,
        pricer=PriceService(settings, store, browser=browser),
    )
    return runner, browser


def _print_report(report, settings: SnipeSettings) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    mode = "LIVE" if settings.live else "dry-run"
    print(f"[{stamp}] ({mode}) {report.summary()}", flush=True)
    for error in report.errors:
        print(f"   ⚠️  {error}", flush=True)


def cmd_scan(args, settings: SnipeSettings) -> int:
    watchlist = load_watchlist(settings.watchlist_path)
    runner, browser = _build_runner(settings, args.source, watchlist)
    try:
        report = runner.scan_once()
        _print_report(report, settings)
        fired = runner.fire_due_bids()
        for bid, status, detail in fired:
            print(f"   🎯 bid #{bid.id} {status}: {detail}")
    finally:
        if browser and not args.keep_open:
            browser.quit()
    return 0


def cmd_watch(args, settings: SnipeSettings) -> int:
    watchlist = load_watchlist(settings.watchlist_path)
    runner, browser = _build_runner(settings, args.source, watchlist)
    targets = ", ".join(t.name for t in watchlist.enabled_targets()) or "(none)"
    print(f"👀 Watching {len(watchlist.enabled_targets())} targets every {settings.poll_seconds}s "
          f"[{'LIVE' if settings.live else 'dry-run'}] sources={args.source}")
    print(f"   {targets}")
    if not settings.live:
        print("   Bids and messages are simulated. Add --live to place real bids / send messages.")
    try:
        runner.watch(on_report=lambda r: _print_report(r, settings))
    except KeyboardInterrupt:
        print("\nStopping...")
        runner.stop()
    finally:
        if browser:
            browser.quit()
    return 0


def cmd_login(args, settings: SnipeSettings) -> int:
    from cardsnipe.browser import Browser

    from cardsnipe.facebook import FacebookMarketplace

    browser = Browser(settings.with_live(False))
    try:
        browser.get(f"https://www.{settings.ebay_domain}/signin/")
        print("1) Sign in to eBay in the Chrome window (waiting up to 5 min)...", flush=True)
        ebay_ok = browser.wait_until(lambda: "signin" not in browser.current_url().lower(), timeout=300, interval=2)
        print("   ✅ eBay signed in" if ebay_ok else "   ⚠️  eBay sign-in not detected", flush=True)
        facebook = FacebookMarketplace(settings, browser)
        browser.get("https://www.facebook.com/marketplace/")
        print("2) Sign in to Facebook in the same window (waiting up to 5 min)...", flush=True)
        fb_ok = facebook.ensure_logged_in(wait_seconds=300)
        print("   ✅ Facebook signed in" if fb_ok else "   ⚠️  Facebook sign-in not detected", flush=True)
    finally:
        browser.quit()
    print("Sessions saved in", settings.chrome_profile_dir)
    return 0 if (ebay_ok or fb_ok) else 1


def _fmt(value: float | None) -> str:
    return f"{value:g}" if value is not None else "market"


def cmd_add(args, settings: SnipeSettings) -> int:
    keywords = args.keywords or [w for w in args.name.lower().split() if len(w) > 2]
    if args.max is None and not (args.card or args.number):
        print("⚠️  Give --card/--set/--number so the market value can be looked up, or a hard --max cap.")
        return 1
    target = Target(
        name=args.name,
        keywords=keywords,
        max_price=args.max,
        max_bid=args.max_bid,
        min_price=args.min,
        card_name=args.card or "",
        set_name=args.set or "",
        number=args.number or "",
        bargain_pct=args.bargain,
        irregular_pct=args.irregular,
        exclude=args.exclude or [],
        graded_only=args.graded_only,
        min_grade=args.min_grade,
        raw_ok=not args.graded_only,
        sources=["ebay", "facebook"] if args.source == "all" else [args.source],
        regrade=args.regrade,
        regrade_min_grade=args.regrade_grades[0],
        regrade_max_grade=args.regrade_grades[1],
        regrade_max_price=args.regrade_max,
    )
    add_target(settings.watchlist_path, target)
    regrade = (f" regrade={target.regrade_min_grade:g}–{target.regrade_max_grade:g}"
               f"≤{_fmt(target.regrade_max_price) if target.regrade_max_price else 'raw value'}" if target.regrade else "")
    print(f"✅ Added {target.name!r}: keywords={target.keywords} min={target.min_price} max={_fmt(target.max_price)} "
          f"max_bid={target.max_bid} bargain≥{target.bargain_pct:g}%{regrade} sources={target.sources}")
    if target.card_name or target.number:
        store = Store(settings.database_url)
        val = PriceService(settings, store).valuation(target, force=True)
        print(f"   💲 {describe(val)}" if val else "   ⚠️  no market data found — add --max or check --card/--set/--number")
    return 0


def cmd_value(args, settings: SnipeSettings) -> int:
    """Show (and refresh) market valuations for the watchlist."""
    watchlist = load_watchlist(settings.watchlist_path)
    store = Store(settings.database_url)
    pricer = PriceService(settings, store)
    targets = [t for t in watchlist.targets if not args.name or t.name.lower() == args.name.lower()]
    if not targets:
        print("⚠️  No such target")
        return 1
    for target in targets:
        if not target.use_market:
            print(f"  • {target.name}: market lookups off (cap {_fmt(target.max_price)})")
            continue
        val = pricer.valuation(target, force=args.refresh)
        if val:
            age = (datetime.now(timezone.utc) - val.fetched_at).total_seconds() / 3600
            print(f"  • {target.name} ({age:.1f}h old, 1 USD = {val.fx:.3f} {val.currency})\n      {describe(val)}")
            for note in val.notes:
                print(f"      ⚠️  {note}")
        else:
            print(f"  • {target.name}: ⚠️  no market data ({target.market_query!r})")
    return 0


def cmd_revalue(args, settings: SnipeSettings) -> int:
    """Re-judge everything already seen against current market values."""
    from cardsnipe.runner import revalue_store

    store = Store(settings.database_url)
    stats = revalue_store(store, load_watchlist(settings.watchlist_path), PriceService(settings, store))
    print(f"✅ Re-judged {stats['checked']} listings: {stats['matched']} deals, {stats['unmatched']} not, "
          f"{stats['changed']} changed")
    return 0


def cmd_collection(args, settings: SnipeSettings) -> int:
    """Sync the Collectr showcase into the local DB and print it."""
    from cardsnipe.collectr import sync_collection

    url = args.url or settings.collectr_showcase_url
    if not url:
        print("⚠️  Set COLLECTR_SHOWCASE_URL in .env or pass --url")
        return 1
    store = Store(settings.database_url)
    if not args.no_sync:
        snapshot = sync_collection(store, url, settings.chrome_profile_dir)
        print(f"✅ Synced {snapshot.total_cards} cards · portfolio US${snapshot.total_value_usd:,.2f}")
    items, latest = store.collection()
    if latest:
        print(f"Portfolio ({latest.owner or 'Collectr'}): US${latest.total_value_usd:,.2f} · {latest.total_cards} cards · "
              f"synced {latest.synced_at:%m-%d %H:%M}")
    for item in items:
        change = f" ({item.change_pct:+.1f}%)" if item.change_pct is not None else ""
        print(f"  • US${item.value_usd or 0:>8.2f}{change}  {item.name} — {item.set_name} {item.number} ×{item.quantity}")
    return 0


def cmd_remove(args, settings: SnipeSettings) -> int:
    removed = remove_target(settings.watchlist_path, args.name)
    print("✅ Removed" if removed else "⚠️  No target with that name")
    return 0 if removed else 1


def cmd_list(args, settings: SnipeSettings) -> int:
    watchlist = load_watchlist(settings.watchlist_path)
    print(f"Watchlist: {settings.watchlist_path}")
    for t in watchlist.targets:
        flag = "" if t.enabled else " (disabled)"
        bid = f" bid≤{t.max_bid:g}" if t.max_bid else ""
        floor = f"{t.min_price:g}–" if t.min_price else "≤"
        cap = f"{t.max_price:g}" if t.max_price else f"value−{t.bargain_pct:g}%"
        grade = " graded-only" if t.graded_only else ""
        grade += f" ≥{t.min_grade:g}" if t.min_grade else ""
        regrade = (f" ♻️{t.regrade_min_grade:g}–{t.regrade_max_grade:g}≤{_fmt(t.regrade_max_price) if t.regrade_max_price else 'raw'}"
                   if t.regrade else "")
        card = f" [{t.market_query}]" if t.card_name or t.number else ""
        print(f"  • {t.name}{flag}: {floor}{cap}{bid}{grade}{regrade}{card} | {' + '.join(t.keywords)} | {','.join(t.sources)}")
    print(f"Global excludes: {', '.join(watchlist.global_exclude)}")
    print(f"TAG: 10 at ≥{watchlist.tag_ten_score}, near-miss within {watchlist.tag_near_margin} points (♻️ = regrade lane on)")
    return 0


def cmd_deals(args, settings: SnipeSettings) -> int:
    store = Store(settings.database_url)
    rows = store.recent_deals(args.limit)
    if not rows:
        print("No deals recorded yet.")
        return 0
    for row in rows:
        when = row.first_seen.strftime("%m-%d %H:%M") if row.first_seen else "?"
        lane = "♻️" if row.lane == "regrade" else "  "
        flag = f"⚠️({row.irregular_reason})" if row.irregular else "  "
        grade = f" [{row.grade}{f' TAG {row.tag_score}' if row.tag_score else ''}]" if row.grade or row.tag_score else ""
        value = (f" ({row.savings_pct:.0f}% under {row.value_bucket} value {row.market_value:.0f} via {row.value_source})"
                 if row.market_value else "")
        print(f"[{when}] {lane}{flag} {row.source:8} {row.currency} {row.total_price or 0:>8.2f}{grade}  {row.title[:60]}{value}  "
              f"→ {row.matched_target} ({row.action or 'seen'})\n              {row.url}")
    return 0


def cmd_bids(args, settings: SnipeSettings) -> int:
    store = Store(settings.database_url)
    rows = store.all_bids(args.limit)
    if not rows:
        print("No scheduled bids.")
        return 0
    now = datetime.now(timezone.utc)
    for b in rows:
        eta = (b.end_time - now).total_seconds() if b.end_time else None
        eta_text = f"ends in {int(eta // 60)}m{int(eta % 60):02d}s" if eta and eta > 0 else "ended"
        print(f"#{b.id:<4} {b.status:9} max {b.currency} {b.max_bid:.2f}  {eta_text:14} {b.title[:55]}"
              + (f"\n      {b.result}" if b.result else ""))
    return 0


def cmd_cancel_bid(args, settings: SnipeSettings) -> int:
    ok = Store(settings.database_url).cancel_bid(args.bid_id)
    print("✅ Cancelled" if ok else "⚠️  Bid not pending / not found")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="place real bids and send real messages")
    parser.add_argument("--source", choices=["all", "ebay", "facebook"], default="all")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", aliases=["s"], help="single pass")
    scan.add_argument("--keep-open", action="store_true", help="leave Chrome open afterwards")
    scan.set_defaults(func=cmd_scan)

    sub.add_parser("watch", aliases=["w"], help="continuous loop (default)").set_defaults(func=cmd_watch)
    sub.add_parser("login", help="sign in to eBay/Facebook once").set_defaults(func=cmd_login)

    add = sub.add_parser("add", aliases=["a"], help="add/replace a watchlist target")
    add.add_argument("name")
    add.add_argument("--card", help='exact card name for pricing, e.g. "Umbreon VMAX (Alternate Art Secret)"')
    add.add_argument("--set", help='set name for pricing, e.g. "Evolving Skies"')
    add.add_argument("--number", help="card number, e.g. 215/203")
    add.add_argument("--bargain", type=float, default=20.0, help="alert at this %% under market value (default 20)")
    add.add_argument("--irregular", type=float, default=50.0, help="flag as irregular at this %% under value (default 50)")
    add.add_argument("--max", type=float, default=None, help="hard cap on total price (optional when --card/--number given)")
    add.add_argument("--max-bid", type=float, default=None, help="snipe eBay auctions up to this amount")
    add.add_argument("--min", type=float, default=None, help="ignore Buy-It-Now/Marketplace below this (fakes)")
    add.add_argument("--keywords", nargs="*", help='all must appear; use "a|b" for alternatives')
    add.add_argument("--exclude", nargs="*")
    add.add_argument("--graded-only", action="store_true")
    add.add_argument("--min-grade", type=float, default=None)
    add.add_argument("--regrade", action="store_true",
                     help="also flag lower-graded / TAG near-miss copies under the cap (crack & regrade)")
    add.add_argument("--regrade-grades", nargs=2, type=float, default=[8.0, 9.5], metavar=("LOW", "HIGH"),
                     help="grade range for the regrade lane (default 8 9.5)")
    add.add_argument("--regrade-max", type=float, default=None, help="price cap for the regrade lane (default --max)")
    add.set_defaults(func=cmd_add)

    remove = sub.add_parser("remove", aliases=["rm"])
    remove.add_argument("name")
    remove.set_defaults(func=cmd_remove)

    sub.add_parser("list", aliases=["l"], help="show watchlist").set_defaults(func=cmd_list)

    deals = sub.add_parser("deals", aliases=["d"], help="recent matched deals")
    deals.add_argument("--limit", type=int, default=30)
    deals.set_defaults(func=cmd_deals)

    bids = sub.add_parser("bids", aliases=["b"], help="scheduled/finished snipes")
    bids.add_argument("--limit", type=int, default=50)
    bids.set_defaults(func=cmd_bids)

    cancel = sub.add_parser("cancel-bid", aliases=["cancel"])
    cancel.add_argument("bid_id", type=int)
    cancel.set_defaults(func=cmd_cancel_bid)

    value = sub.add_parser("value", aliases=["v"], help="market valuations (TCGPlayer / PriceCharting / eBay sold)")
    value.add_argument("name", nargs="?", help="only this target")
    value.add_argument("--refresh", action="store_true", help="ignore the cache")
    value.set_defaults(func=cmd_value)

    sub.add_parser("revalue", help="re-judge every seen listing against current market values").set_defaults(func=cmd_revalue)

    collection = sub.add_parser("collection", aliases=["c"], help="sync + show your Collectr showcase")
    collection.add_argument("--url", help="showcase URL (default COLLECTR_SHOWCASE_URL)")
    collection.add_argument("--no-sync", action="store_true", help="just print what is stored")
    collection.set_defaults(func=cmd_collection)
    parser.set_defaults(func=cmd_watch)  # bare `python3 snipe.py` == watch
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    settings = SnipeSettings.from_env().with_live(args.live)
    return args.func(args, settings)


if __name__ == "__main__":
    sys.exit(main())
