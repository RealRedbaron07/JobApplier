"""One bounded, read-only browser scan across broad Pokémon searches."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cardsnipe.browser import Browser, SourceUnavailable
from cardsnipe.bargains import bank_of_canada_usd_cad, eligible, tcgplayer_market
from cardsnipe.ebay import EbayWeb
from cardsnipe.facebook import FacebookMarketplace
from cardsnipe.matcher import detect_condition_issue
from cardsnipe.watchlist import Target

MAX_SEARCHES = 8
RESULTS_PER_SEARCH = 60
COOLDOWN_SECONDS = 60
PAGE_INTERVAL_SECONDS = 2
MAX_RUN_SECONDS = 180
PRICE_CHECKS_PER_RUN = 40
PRICE_CHECK_SECONDS = 360
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
    return {"ebay": urlunsplit(ebay._replace(query=urlencode(params))),
            "facebook": FacebookMarketplace(settings, None).search_url(target, all_dates=True)}


def search_plan(source="all"):
    if not isinstance(source, str) or source not in {"all", "ebay", "facebook"}:
        raise ValueError("Choose all, ebay, or facebook")
    searches = [("facebook", "all", query) for query in
                ("pokemon single card", "pokemon graded card", "pokemon sealed")]
    searches += [("ebay", mode, "pokemon cards") for mode in ("sale", "all", "auction", "offers")]
    searches += [("ebay", "all", "pokemon sealed")]
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
        try:
            for name, mode, query in plan:
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
            for entry in found.values():
                listing = entry["listing"]
                new += int(not self.store.is_seen(listing))
                row = self.store.record_listing(listing, None, discovery_at=started,
                                                discovery_routes=entry["routes"], promotion=promotion_text(listing))
                entry["row_id"] = row.id
                entry["price_checked_at"] = row.price_checked_at
                saved += int(not row.dismissed)
                if not row.dismissed:
                    active.add(listing.key)
            # Price a bounded set from this pass; saved finds can be checked separately.
            candidates = [entry["listing"] for entry in found.values()
                          if entry["listing"].key in active and not entry["price_checked_at"]
                          and entry["listing"].currency == "CAD"
                          and eligible(entry["listing"].title)
                          and not detect_condition_issue(entry["listing"].condition)
                          and entry["listing"].total_price is not None and entry["listing"].price > 1]
            # Pricing gets its own time budget so a slow search phase does not starve it.
            deadline = time.monotonic() + PRICE_CHECK_SECONDS
            if candidates and not self.stop.is_set():
                try:
                    fx = bank_of_canada_usd_cad(browser)
                    if fx is None:
                        errors.append("price check: Bank of Canada USD/CAD rate was not readable; no comparisons made")
                    else:
                        for listing in candidates[:PRICE_CHECKS_PER_RUN]:
                            if self.stop.is_set() or time.monotonic() >= deadline:
                                break
                            self.progress(message=f"Checking exact card prices: {priced} priced so far…",
                                          priced=priced, bargains=bargains)
                            if self.stop.wait(PAGE_INTERVAL_SECONDS):
                                break
                            try:
                                product = tcgplayer_market(browser, listing.title)
                                value = round(product["price"] * fx, 2) if product else None
                                if self.store.set_discovery_price(found[listing.key]["row_id"], value,
                                                                  f"TCGplayer browser · BoC FX {fx:g}" if value else ""):
                                    priced += int(value is not None)
                                    bargains += int(value is not None and value > listing.total_price)
                            except Exception as exc:
                                errors.append(f"price check for {listing.title!r}: {str(exc).splitlines()[0]}")
                except Exception as exc:
                    errors.append(f"price check: {str(exc).splitlines()[0]}")
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
    candidates = [row for row in rows if row.price_checked_at is None and row.currency == "CAD"
                  and row.total_price is not None and row.price > 1 and eligible(row.title)
                  and not detect_condition_issue(row.condition)]
    candidates.sort(key=lambda row: row.source != "facebook")
    candidates = candidates[:PRICE_CHECKS_PER_RUN]
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
                product = tcgplayer_market(browser, row.title)
                value = round(product["price"] * fx, 2) if product else None
                if store.set_discovery_price(row.id, value, f"TCGplayer browser · BoC FX {fx:g}" if value else ""):
                    checked += 1
                    priced += int(value is not None)
                    bargains += int(value is not None and value > row.total_price)
            except Exception as exc:
                errors.append(f"{row.title!r}: {str(exc).splitlines()[0]}")
                if len(errors) >= 5:
                    break
    finally:
        browser.quit()
    return {"message": f"Checked {checked} saved singles. {priced} exact prices, {bargains} possible bargains. {len(errors)} errors.",
            "checked": checked, "priced": priced, "bargains": bargains, "errors": errors}
