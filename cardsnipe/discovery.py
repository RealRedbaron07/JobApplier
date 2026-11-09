"""One bounded, read-only browser scan across broad Pokémon searches."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cardsnipe.browser import Browser, SourceUnavailable
from cardsnipe.bargains import (CROSS_CHECK, NUMBER, PRICE_VERSION, bank_of_canada_usd_cad, eligible, needs_recheck,
                                tcgplayer_market)
from cardsnipe.ebay import EbayWeb
from cardsnipe.facebook import FacebookMarketplace
from cardsnipe.condition import condition_claim
from cardsnipe.deals import AUCTION_WINDOW_MINUTES, assess, is_bargain, minutes_left
from cardsnipe.pricecharting import pricecharting_lookup
from cardsnipe.slabs import raw_title, slab_eligible, slab_grade
from cardsnipe.watchlist import Target

MAX_SEARCHES = 10
RESULTS_PER_SEARCH = 60
COOLDOWN_SECONDS = 60
PAGE_INTERVAL_SECONDS = 2
MAX_RUN_SECONDS = 240
PRICE_CHECKS_PER_RUN = 40
SLAB_CHECKS_PER_RUN = 20
EBAY_MIN_PRICE = 15.0  # CAD, fixed-price listings only
PRICE_CHECK_SECONDS = 720  # each card now reads TCGplayer and PriceCharting
AUCTION_PRICE_SECONDS = 180  # the first pricing pass, so the other searches still get their turn


def priceable(title):
    """Raw single or mid-grade slab that a TCGplayer raw price can be compared with."""
    return eligible(title) or slab_eligible(title)


def price_listing(browser, title, condition=""):
    """TCGplayer raw NM market price for this card, cross-checked on PriceCharting.

    Slabs are looked up by their raw card, plus PriceCharting's price for the slab's grade.
    Raw singles listed as played also get that condition's TCGplayer market price.
    PriceCharting adds the ungraded price and the median of recent sales; if it has no exact
    match the TCGplayer price is still used, and the label says the sales check found nothing.
    """
    slab = slab_grade(title) if slab_eligible(title) else None
    if slab:
        product = tcgplayer_market(browser, raw_title(title))
        label = f"TCGplayer raw NM (crack check, {PRICE_VERSION})"
    else:
        product = tcgplayer_market(browser, title, condition_claim(title, condition))
        label = f"TCGplayer {PRICE_VERSION}"
    if product and product.get("price"):
        number = NUMBER.search(title or "")
        try:
            product["pricecharting"] = pricecharting_lookup(browser, product, number.group(1) if number else "",
                                                            grade=slab[1] if slab else None,
                                                            company=slab[0] if slab else "")
        except Exception:
            product["pricecharting"] = None
        label += f" + PriceCharting, {CROSS_CHECK}" if product["pricecharting"] else f", {CROSS_CHECK}: no PriceCharting match"
    return product, label


def cross_check_cad(product, fx):
    """PriceCharting values converted to CAD for storage."""
    pc = (product or {}).get("pricecharting") or {}
    cad = lambda usd: round(usd * fx, 2) if usd else None
    return {"pc_value": cad(pc.get("ungraded")), "sales_value": cad(pc.get("sales_median")),
            "sales_count": pc.get("sales_count"), "graded_value": cad(pc.get("graded")), "pc_url": pc.get("url")}


def save_price(store, row_id, product, label, fx):
    """Store the CAD prices from one check. Returns the NM value, or None if unmatched."""
    value = round(product["price"] * fx, 2) if product else None
    played = product.get("condition_price") if product else None
    if not store.set_discovery_price(row_id, value, f"{label} · BoC FX {fx:g}" if value else "",
                                     condition_value=round(played * fx, 2) if played else None,
                                     sold_3m=product.get("sold_3m") if product else None,
                                     cross_check=cross_check_cad(product, fx)):
        return False, None
    return True, value


def _assess(item, value, condition_value, check):
    return assess(title=item.title, source=item.source, listing_type=item.listing_type, price=item.price,
                  shipping=item.shipping, total_price=item.total_price, value=value if priceable(item.title) else None,
                  slab=slab_grade(item.title) if slab_eligible(item.title) else None,
                  condition=getattr(item, "condition", "") or "", checked_condition_value=condition_value,
                  sales_value=check.get("sales_value"), graded_value=check.get("graded_value"),
                  end_time=getattr(item, "end_time", None))


def verdict(item, value):
    """Deal verdict for a saved row priced at `value` (CAD raw NM).

    Titles the current rules no longer price (other graders, Japanese, multi-slab) get no verdict,
    even if an older run saved a price for them.
    """
    check = {"sales_value": getattr(item, "sales_value", None), "graded_value": getattr(item, "graded_value", None)}
    return _assess(item, value, getattr(item, "condition_value", None), check)


def counts_as_bargain(item, value, product=None, fx=1.0):
    if value is None:
        return False
    return is_bargain(_assess(item, value, _played_cad(product, fx), cross_check_cad(product, fx)))


def _played_cad(product, fx):
    played = product.get("condition_price") if product else None
    return round(played * fx, 2) if played else None


# Rarity words that make a card worth a price check; plain commons rarely clear $5 profit.
VALUABLE = re.compile(r"\b(?:holo|foil|ex|gx|v|vmax|vstar|break|prime|lv\.?\s?x|legend|star|delta|"
                      r"full art|alt(?:ernate)? art|secret|gold|rainbow|shiny|radiant|trainer gallery|"
                      r"illustration rare|special illustration|sir|ir|ultra rare|hyper rare|amazing rare|"
                      r"wotc|vintage|neo|base set|jungle|fossil|team rocket|gym)\b", re.I)
LOW_RARITY = re.compile(r"\b(?:common|uncommon|energy)\b", re.I)


def check_priority(title, price=None):
    """Lower sorts first: rare-looking cards before plain ones, pricier listings first within each."""
    title = title or ""
    tier = 2 if LOW_RARITY.search(title) and not VALUABLE.search(title) else 0 if VALUABLE.search(title) else 1
    return tier, -(price or 0)


def pick_candidates(items, title_of, price_of=None):
    """Up to PRICE_CHECKS_PER_RUN raw singles plus SLAB_CHECKS_PER_RUN slabs, most promising first.

    Plain commons and uncommons are checked last: a $0.20 card listed at $15 shipped used to use up
    the whole budget before any holo or slab was priced.
    """
    if price_of is not None:
        items = sorted(items, key=lambda item: check_priority(title_of(item), price_of(item)))
    raw = [item for item in items if eligible(title_of(item))][:PRICE_CHECKS_PER_RUN]
    slabs = [item for item in items if slab_eligible(title_of(item))][:SLAB_CHECKS_PER_RUN]
    picked = []
    for pair in zip(slabs, raw):  # interleave so a short time budget still covers both kinds
        picked.extend(pair)
    longer = slabs if len(slabs) > len(raw) else raw
    return picked + longer[min(len(slabs), len(raw)):]


# Auctions are priced only when they end within this many minutes: a little past the bargain window so
# a card priced now is still on the list as it enters its final hour.
AUCTION_PRICE_MINUTES = AUCTION_WINDOW_MINUTES + 30


def auction_order(items, title_of, now=None):
    """(auctions worth pricing soonest-ending first, buy-now items). Auctions that ended, have no end
    time, or end after AUCTION_PRICE_MINUTES are dropped: they cannot become a bargain in time."""
    auctions, others = [], []
    for item in items:
        if getattr(item, "listing_type", "") != "auction":
            others.append(item)
            continue
        left = minutes_left(getattr(item, "end_time", None), now)
        if left is not None and 0 < left <= AUCTION_PRICE_MINUTES and (
                eligible(title_of(item)) or slab_eligible(title_of(item))):
            auctions.append((left, item))
    return [item for _, item in sorted(auctions, key=lambda pair: pair[0])], others


def order_checks(items, title_of, price_of=None, now=None):
    """Price auctions about to end first (they expire), then the best buy-now candidates."""
    auctions, others = auction_order(items, title_of, now)
    return auctions + pick_candidates(others, title_of, price_of)


DISCOVERY_MODES = (
    ("all", "All listings", "Every buying format, newest first"),
    ("sale", "Sales & coupons", "Seller promotions and marked reductions"),
    ("auction", "Auctions ending soon", "Browse current bids; final prices can rise"),
    ("offers", "Accepts offers", "Listings where you can negotiate"),
)


def browser_search_links(target, settings, *, mode="bin"):
    ebay = urlsplit(EbayWeb(settings, None).search_url(target.search_query, target.max_price, limit=None))
    params = dict(parse_qsl(ebay.query))
    if mode != "bin":
        params.pop("LH_BIN", None)
        if mode == "sale":
            params["LH_SaleItems"] = "1"
        elif mode == "auction":
            params.update(LH_Auction="1", _sop="1")
        elif mode == "offers":
            params["LH_BO"] = "1"
        elif mode != "all":
            raise ValueError("Unknown browser search mode")
    if mode != "auction" and target.max_price is None:
        # Fixed-price singles under this are bulk; auctions keep low current bids, which is where the finds are.
        params["_udlo"] = f"{EBAY_MIN_PRICE:.2f}"
    return {"ebay": urlunsplit(ebay._replace(query=urlencode(params))),
            "facebook": FacebookMarketplace(settings, None).search_url(target, all_dates=True)}


def search_plan(source="all"):
    """Searches aimed at listings that can be priced and can be under value.

    Sealed product is never priced, and "pokemon cards" newest-first is mostly bulk commons
    (and often an eBay server error), so the plan targets slabs, holos and chase cards instead.
    Auctions ending soonest with low bids produced the real finds.
    """
    if not isinstance(source, str) or source not in {"all", "ebay", "facebook"}:
        raise ValueError("Choose all, ebay, or facebook")
    # Auctions run first and are priced straight away: most are first seen with minutes left.
    searches = [("ebay", "auction", "psa 9 pokemon"), ("ebay", "auction", "psa 8 pokemon"),
                ("ebay", "auction", "pokemon holo rare")]
    searches += [("facebook", "all", query) for query in
                 ("pokemon single card", "pokemon graded card", "pokemon holo card")]
    searches += [("ebay", "all", "pokemon psa 7 8 9"), ("ebay", "all", "pokemon illustration rare"),
                 ("ebay", "offers", "pokemon holo"), ("ebay", "sale", "pokemon card holo")]
    return [item for item in searches if source == "all" or item[0] == source][:MAX_SEARCHES]


LOT_RE = re.compile(
    r"\b(?:lots?|bulk|binders?)\b|\bcards?\s+(?:bundle|collection)s?\b|"
    r"\bcollection(?:s|\s+of|\s+sale)?\b|\b(?:cards|singles|sets)\b|"
    r"\b(?:card\s+hits|single\s+packs|looking\s+to\s+trade|looking\s+for|buying|"
    r"trade\s+or\s+buy|can\s+sell\s+in\s+singles)\b", re.I)
CARD_NUMBER_RE = re.compile(r"\b\d{1,3}/\d{1,3}\b")


def is_lot_listing(title: str) -> bool:
    title = title or ""
    if re.search(r"\b(?:ultra\s+premium\s+collection|special\s+collection|booster\s+bundle)\b", title, re.I):
        return False
    if CARD_NUMBER_RE.search(title) and not re.search(r"\b(?:lots?|bulk|binders?|collection)\b", title, re.I):
        return False
    return bool(LOT_RE.search(title))


def is_discovery_candidate(listing) -> bool:
    # Marketplace $0/$1 offers commonly advertise variable per-card prices.
    if is_lot_listing(listing.title):
        return False
    if listing.source == "facebook":
        if listing.price is not None and listing.price <= 1:
            return False
        if re.search(r"\bpre[ -]?orders?\b", listing.title, re.I):
            return False
        if re.fullmatch(r"(?:pok[eé]mon\s+)?cards?(?:\s+for\s+sale)?", listing.title.strip(), re.I):
            return False
        if re.fullmatch(r"pok[eé]mon\s+(?:vintage|card\s+english\s*&\s*japanese)", listing.title.strip(), re.I):
            return False
        if re.fullmatch(r"[\w .'-]+,\s*[A-Z]{2}", listing.title.strip()):
            return False
    return True


def promotion_text(listing):
    lines = (listing.raw.get("text") or "").splitlines()
    return " · ".join(line.strip() for line in lines if re.search(
        r"\bcoupon\b|\d+\s*%\s*off|\bprice (?:drop|reduc)|\bwas\s*[$£€]", line, re.I))[:400]


class DiscoveryScanner:
    def __init__(self, settings, store, *, stop=None, progress=None):
        # API keys and side effects are never passed to this browser-only scanner.
        self.settings = replace(settings, ebay_app_id="", ebay_cert_id="", ebay_domain="ebay.ca", live=False,
                                fb_auto_message=False, notify_macos=False, open_in_browser=False,
                                webhook_url="", ebay_sold_comps=False)
        self.store = store
        self.stop = stop or threading.Event()
        self.progress = progress or (lambda **state: None)

    def scan(self, source="all"):
        from config import Config

        if not Config.BROWSER_SCANS_ENABLED:
            raise ValueError("Browser scans are disabled")
        plan = search_plan(source)
        started = datetime.now(timezone.utc)
        deadline = time.monotonic() + MAX_RUN_SECONDS
        browser = Browser(self.settings)
        ebay, facebook = EbayWeb(self.settings, browser), FacebookMarketplace(self.settings, browser)
        found, unavailable, errors, failures, active = {}, set(), [], {}, set()
        scanned = pages = new = saved = priced = bargains = 0
        stopped = False
        fx = None

        def flush(limit=PRICE_CHECK_SECONDS):
            """Save everything found so far, then price what has not been priced yet."""
            nonlocal new, saved, priced, bargains, fx
            fresh = [entry for entry in found.values() if "row_id" not in entry]
            for entry in fresh:
                listing = entry["listing"]
                new += int(not self.store.is_seen(listing))
                row = self.store.record_listing(listing, None, discovery_at=started,
                                                discovery_routes=entry["routes"], promotion=promotion_text(listing))
                entry["row_id"] = row.id
                entry["price_checked_at"] = None if needs_recheck(row.value_source) else row.price_checked_at
                saved += int(not row.dismissed)
                if not row.dismissed:
                    active.add(listing.key)
                entry["saved_routes"] = len(entry["routes"])
            for entry in found.values():  # seen again by a later search after its first save
                if entry not in fresh and len(entry["routes"]) != entry["saved_routes"]:
                    self.store.record_listing(entry["listing"], None, discovery_at=started,
                                              discovery_routes=entry["routes"],
                                              promotion=promotion_text(entry["listing"]))
                    entry["saved_routes"] = len(entry["routes"])
            candidates = order_checks([entry["listing"] for entry in fresh
                                       if entry["listing"].key in active and not entry["price_checked_at"]
                                       and entry["listing"].currency == "CAD"
                                       and priceable(entry["listing"].title)
                                       and entry["listing"].total_price is not None and entry["listing"].price > 1],
                                      lambda listing: listing.title, lambda listing: listing.total_price)
            if not candidates or self.stop.is_set():
                return
            until = time.monotonic() + limit
            try:
                fx = fx or bank_of_canada_usd_cad(browser)
                if fx is None:
                    errors.append("price check: Bank of Canada USD/CAD rate was not readable; no comparisons made")
                    return
                for listing in candidates:
                    if self.stop.is_set() or time.monotonic() >= until:
                        break
                    self.progress(message=f"Checking exact card prices: {priced} priced so far…",
                                  priced=priced, bargains=bargains)
                    if self.stop.wait(PAGE_INTERVAL_SECONDS):
                        break
                    try:
                        product, label = price_listing(browser, listing.title, listing.condition)
                        stored, value = save_price(self.store, found[listing.key]["row_id"], product, label, fx)
                        if stored:
                            priced += int(value is not None)
                            bargains += int(counts_as_bargain(listing, value, product, fx))
                    except Exception as exc:
                        errors.append(f"price check for {listing.title!r}: {str(exc).splitlines()[0]}")
            except Exception as exc:
                errors.append(f"price check: {str(exc).splitlines()[0]}")

        try:
            for index, (name, mode, query) in enumerate(plan):
                if name in unavailable:
                    continue
                if self.stop.is_set() or time.monotonic() >= deadline:
                    stopped = True
                    break
                if pages and self.stop.wait(PAGE_INTERVAL_SECONDS):
                    stopped = True
                    break
                self.progress(message=f"Searching {name}: {query} ({mode})…", pages_done=pages,
                              page_limit=len(plan), scanned=scanned, candidates=len(found))
                target = Target(name=query, keywords=[query], use_market=False)
                pages += 1
                try:
                    if name == "ebay":
                        url = browser_search_links(target, self.settings, mode=mode)["ebay"]
                        listings = ebay.search_page(url, "auction" if mode == "auction" else "all", RESULTS_PER_SEARCH)
                    else:
                        listings = facebook.find(target, all_dates=True)[:RESULTS_PER_SEARCH]
                    listings = listings[:RESULTS_PER_SEARCH]
                    failures[name] = 0
                    scanned += len(listings)
                    for listing in listings:
                        if listing.currency != self.settings.ebay_currency:
                            continue
                        if not is_discovery_candidate(listing):
                            continue
                        entry = found.setdefault(listing.key, {"listing": listing, "routes": []})
                        route_mode = "search-bar retry (unfiltered)" if name == "ebay" and getattr(ebay, "used_home_search", False) else mode
                        route = f"{route_mode}: {query}"
                        if route not in entry["routes"]:
                            entry["routes"].append(route)
                except Exception as exc:
                    errors.append(f"{name} {query!r} ({mode}): {str(exc).splitlines()[0]}")
                    failures[name] = failures.get(name, 0) + 1
                    # Stop account/verification blocks immediately; tolerate one transient query failure.
                    if isinstance(exc, SourceUnavailable) or failures[name] >= 2:
                        unavailable.add(name)
                self.progress(pages_done=pages, scanned=scanned, candidates=len(found), errors=list(errors))
                if mode == "auction" and (index + 1 == len(plan) or plan[index + 1][1] != "auction"):
                    # Price auctions now; waiting for the other searches costs minutes they do not have.
                    began = time.monotonic()
                    flush(AUCTION_PRICE_SECONDS)
                    deadline += time.monotonic() - began
            flush()
        finally:
            browser.quit()
            self.store.record_scan(started=started, finished=datetime.now(timezone.utc),
                                   sources=sorted({name for name, _, _ in plan}), live=False,
                                   scanned=scanned, new_listings=new, deals=bargains, regrade_deals=0,
                                   bids_scheduled=0, errors=errors, kind="broad", budget=None,
                                   currency=self.settings.ebay_currency)
        stopped = stopped or self.stop.is_set()
        return {"message": f"{'Stopped' if stopped else 'Finished'}: {saved} candidates saved from {pages} searches. {priced} exact singles priced, {bargains} possible bargains. {len(errors)} errors.",
                "scanned": scanned, "new_listings": new, "candidates": saved, "pages_done": pages,
                "page_limit": len(plan), "priced": priced, "bargains": bargains, "errors": errors, "stopped": stopped}


def price_saved_singles(settings, store, stop=None, progress=None):
    """Check the next batch of saved exact singles through public browser pages."""
    rows, _ = store.discovery_results()
    candidates = [row for row in rows if (row.price_checked_at is None or needs_recheck(row.value_source))
                  and row.currency == "CAD"
                  and row.total_price is not None and row.price > 1 and priceable(row.title)]
    # Never-checked first, then priced finds that still lack the sales cross-check (deals first).
    candidates.sort(key=lambda row: (row.price_checked_at is not None, check_priority(row.title, row.total_price),
                                     row.source != "facebook"))
    candidates = order_checks(candidates, lambda row: row.title)
    if not candidates:
        return {"message": "No unchecked exact singles remain in saved finds.", "checked": 0, "priced": 0,
                "bargains": 0, "errors": []}
    browser = Browser(settings)
    checked = priced = bargains = 0
    errors = []
    deadline = time.monotonic() + PRICE_CHECK_SECONDS
    try:
        fx = bank_of_canada_usd_cad(browser)
        if fx is None:
            return {"message": "Bank of Canada rate was unreadable. No listings were marked checked.",
                    "checked": 0, "priced": 0, "bargains": 0, "errors": ["USD/CAD rate unavailable"]}
        for row in candidates:
            if (stop is not None and stop.is_set()) or time.monotonic() >= deadline:
                break
            if progress:
                progress(message=f"Checking saved singles: {checked}/{len(candidates)} checked…", checked=checked,
                         priced=priced, bargains=bargains)
            try:
                product, label = price_listing(browser, row.title, row.condition)
                saved, value = save_price(store, row.id, product, label, fx)
                if saved:
                    checked += 1
                    priced += int(value is not None)
                    bargains += int(counts_as_bargain(row, value, product, fx))
            except Exception as exc:
                errors.append(f"{row.title!r}: {str(exc).splitlines()[0]}")
                if len(errors) >= 5:
                    break
    finally:
        browser.quit()
    return {"message": f"Checked {checked} saved singles. {priced} exact prices, {bargains} possible bargains. {len(errors)} errors.",
            "checked": checked, "priced": priced, "bargains": bargains, "errors": errors}
