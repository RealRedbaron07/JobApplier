#!/usr/bin/env python3
"""Pokémon card sniper for eBay + Facebook Marketplace.

  python3 snipe.py                      same as `watch` (dry-run loop)
  python3 snipe.py scan      (s)        one pass: alert on deals, simulate bids/messages
  python3 snipe.py watch     (w)        keep scanning every SNIPE_POLL_SECONDS
  python3 snipe.py watch --live         actually place eBay snipes / send FB messages
  python3 snipe.py login                open Chrome so you can sign in to eBay + Facebook once
  python3 snipe.py add       (a)        add "Umbreon VMAX Alt Art" --min 250 --max 550 --max-bid 600 --regrade \\
                                            --keywords umbreon vmax "alt art|215/203"
  python3 snipe.py remove    (rm)       remove "Umbreon VMAX Alt Art"
  python3 snipe.py list (l) | deals (d) | bids (b) | cancel-bid <id>

Shorter still: `make snipe`, `make live`, `make deals` ... (see `make help`).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from cardsnipe.notify import Notifier
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

    runner = SnipeRunner(
        settings=settings,
        watchlist=watchlist,
        store=Store(settings.database_url),
        sources=sources,
        notifier=Notifier(settings),
        bid_executor=bid_executor if "ebay" in wanted else None,
        messenger=messenger,
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


def cmd_add(args, settings: SnipeSettings) -> int:
    keywords = args.keywords or [w for w in args.name.lower().split() if len(w) > 2]
    target = Target(
        name=args.name,
        keywords=keywords,
        max_price=args.max,
        max_bid=args.max_bid,
        min_price=args.min,
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
               f"≤{(target.regrade_max_price or target.max_price):g}" if target.regrade else "")
    print(f"✅ Added {target.name!r}: keywords={target.keywords} min={target.min_price} max={target.max_price:g} "
          f"max_bid={target.max_bid}{regrade} sources={target.sources}")
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
        grade = " graded-only" if t.graded_only else ""
        grade += f" ≥{t.min_grade:g}" if t.min_grade else ""
        regrade = (f" ♻️{t.regrade_min_grade:g}–{t.regrade_max_grade:g}≤{(t.regrade_max_price or t.max_price):g}"
                   if t.regrade else "")
        print(f"  • {t.name}{flag}: {floor}{t.max_price:g}{bid}{grade}{regrade} | {' + '.join(t.keywords)} | {','.join(t.sources)}")
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
        grade = f" [{row.grade}{f' TAG {row.tag_score}' if row.tag_score else ''}]" if row.grade or row.tag_score else ""
        print(f"[{when}] {lane} {row.source:8} {row.currency} {row.total_price or 0:>8.2f}{grade}  {row.title[:60]}  "
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
    add.add_argument("--max", type=float, required=True, help="max total price (incl. shipping)")
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
