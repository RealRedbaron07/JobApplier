"""eBay: listing discovery (Browse API or Chrome fallback) and last-seconds auction bidding."""

from __future__ import annotations

import base64
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from cardsnipe.browser import Browser, SourceUnavailable
from cardsnipe.matcher import Listing, extract_time_left_line, parse_price, parse_time_left
from cardsnipe.settings import SnipeSettings
from cardsnipe.watchlist import Target

logger = logging.getLogger("cardsnipe.ebay")

ITEM_ID_RE = re.compile(r"/itm/(?:[^/]+/)?(\d{9,15})")
LEGACY_ID_RE = re.compile(r"v1\|(\d+)\|")


def _iso_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


class EbayBrowseAPI:
    """Official Buy Browse API with client-credentials OAuth. Fast and reliable."""

    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    SCOPE = "https://api.ebay.com/oauth/api_scope"

    def __init__(self, settings: SnipeSettings):
        self.settings = settings
        self._token: str | None = None
        self._token_expiry = 0.0

    def _get_token(self) -> str:
        import requests

        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        credentials = f"{self.settings.ebay_app_id}:{self.settings.ebay_cert_id}".encode()
        response = requests.post(
            self.TOKEN_URL,
            headers={
                "Authorization": "Basic " + base64.b64encode(credentials).decode(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": self.SCOPE},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + float(payload.get("expires_in", 7200))
        return self._token

    def search(self, query: str, max_price: float, buying_option: str, limit: int) -> list[Listing]:
        import requests

        buying = "FIXED_PRICE|BEST_OFFER" if buying_option == "bin" else "AUCTION"
        sort = "newlyListed" if buying_option == "bin" else "endingSoonest"
        params = {
            "q": query,
            "category_ids": "183454",
            "limit": str(limit),
            "sort": sort,
            "filter": f"buyingOptions:{{{buying}}},price:[..{max_price:.2f}],priceCurrency:{self.settings.ebay_currency}",
        }
        response = requests.get(
            self.SEARCH_URL,
            params=params,
            headers={
                "Authorization": f"Bearer {self._get_token()}",
                "X-EBAY-C-MARKETPLACE-ID": self.settings.ebay_marketplace,
                "Accept": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        return [self._to_listing(item) for item in response.json().get("itemSummaries", [])]

    def _to_listing(self, item: dict) -> Listing:
        options = item.get("buyingOptions", [])
        is_auction = "AUCTION" in options and "FIXED_PRICE" not in options
        price_block = item.get("currentBidPrice") if is_auction else item.get("price")
        price_block = price_block or item.get("price") or {}
        shipping = None
        for option in item.get("shippingOptions", []) or []:
            cost = option.get("shippingCost") or {}
            if cost.get("value") is not None and cost.get("currency") == price_block.get("currency"):
                amount = float(cost["value"])
                shipping = min(shipping, amount) if shipping is not None else amount
        location = item.get("itemLocation") or {}
        raw_id = item.get("itemId", "")
        legacy = item.get("legacyItemId") or (LEGACY_ID_RE.search(raw_id).group(1) if LEGACY_ID_RE.search(raw_id) else raw_id)
        condition = item.get("condition", "")
        for descriptor in item.get("conditionDescriptors", []) or []:
            condition += " " + " ".join(v.get("content", "") for v in descriptor.get("values", []) if isinstance(v, dict))
        return Listing(
            source="ebay",
            listing_id=str(legacy),
            title=item.get("title", ""),
            price=float(price_block["value"]) if price_block.get("value") is not None else None,
            currency=price_block.get("currency", self.settings.ebay_currency),
            url=item.get("itemWebUrl", f"https://www.{self.settings.ebay_domain}/itm/{legacy}"),
            listing_type="auction" if is_auction else "bin",
            shipping=shipping,
            end_time=_iso_to_dt(item.get("itemEndDate")),
            location=", ".join(v for v in (location.get("city"), location.get("country")) if v),
            condition=condition.strip(),
            image_url=(item.get("image") or {}).get("imageUrl", ""),
            bid_count=item.get("bidCount"),
            raw=item,
        )

    def details(self, listing: Listing) -> Listing:
        import requests

        response = requests.get(
            "https://api.ebay.com/buy/browse/v1/item/get_item_by_legacy_id",
            params={"legacy_item_id": listing.listing_id},
            headers={"Authorization": f"Bearer {self._get_token()}",
                     "X-EBAY-C-MARKETPLACE-ID": self.settings.ebay_marketplace}, timeout=15,
        )
        response.raise_for_status()
        item = response.json()
        detailed = self._to_listing(item)
        detailed.listing_id = listing.listing_id
        if not detailed.condition:
            detailed.condition = "unverified"
        if item.get("estimatedAvailabilities") and not any(
            a.get("estimatedAvailabilityStatus") == "IN_STOCK" for a in item["estimatedAvailabilities"]
        ):
            detailed.price = None
        return detailed


class EbayWeb:
    """Chrome fallback that reads the public search page. Slower; markup may change."""

    EXTRACT_JS = """
    const seen = new Set(); const out = [];
    for (const a of document.querySelectorAll("a[href*='/itm/']")) {
      const m = a.href.match(/\\/itm\\/(?:[^/]+\\/)?(\\d{9,15})/);
      if (!m || seen.has(m[1])) continue;
      const card = a.closest('li') || a.closest("[class*='s-card']") || a.closest("[class*='s-item']") || a.parentElement;
      const text = card ? card.innerText : a.innerText;
      if (!text || text.length < 10) continue;
      seen.add(m[1]);
      const img = card ? card.querySelector('img') : null;
      const timeEl = card ? card.querySelector("[class*='time-left'], [class*='time_left']") : null;
      const titleEl = card ? card.querySelector(".s-card__title, .s-item__title, [role='heading']") : null;
      const priceEl = card ? card.querySelector(".s-card__price, .s-item__price") : null;
      out.push({id: m[1], href: a.href.split('?')[0], text, img: img ? img.src : '',
                timeLeft: timeEl ? timeEl.innerText : '', title: titleEl ? titleEl.innerText : '',
                price: priceEl ? priceEl.innerText : ''});
    }
    return out;
    """

    def __init__(self, settings: SnipeSettings, browser: Browser):
        self.settings = settings
        self.browser = browser

    def search_url(self, query: str, max_price: float | None, buying_option: str = "bin", limit: int | None = 60) -> str:
        sort = "10" if buying_option == "bin" else "1"  # newly listed / ending soonest
        kind = "LH_BIN=1" if buying_option == "bin" else "LH_Auction=1"
        return (
            f"https://www.{self.settings.ebay_domain}/sch/i.html?_nkw={quote_plus(query)}"
            f"&_sop={sort}&{kind}"
            + (f"&_ipg={min(limit, 120)}" if limit is not None else "")
            + (f"&_udhi={max_price:.2f}" if max_price is not None else "")
        )

    def search(self, query: str, max_price: float, buying_option: str, limit: int) -> list[Listing]:
        url = self.search_url(query, max_price, buying_option, limit)
        return self.search_page(url, buying_option, limit)

    def search_page(self, url: str, buying_option: str, limit: int) -> list[Listing]:
        self.used_home_search = False
        query = dict(parse_qsl(urlsplit(url).query)).get("_nkw", "")
        for attempt in range(2):
            if attempt and callable(getattr(self.browser, "find_first", None)):
                self.browser.get(f"https://www.{self.settings.ebay_domain}/")
                search_box = None

                def search_ready():
                    nonlocal search_box
                    search_box = self.browser.find_first([("css selector", "input#gh-ac, input[name='_nkw']")])
                    return search_box is not None

                if not self.browser.wait_until(search_ready, timeout=10):
                    raise RuntimeError("eBay's homepage search bar did not load. This search was not completed.")
                search_box.clear()
                search_box.send_keys(query)
                search_box.send_keys("\ue007")  # Enter submits eBay's normal search form.
                self.used_home_search = True
            else:
                self.browser.get(url)
            self.browser.wait_until(
                lambda: self.browser.js("return document.querySelectorAll(\"a[href*='/itm/']\").length > 0 || "
                                        "/something went wrong on our end|no exact matches|no results|0 results|verify you are|security check|captcha/i.test(document.body?.innerText || '')"),
                timeout=12,
            )
            rows = self.browser.js(self.EXTRACT_JS) or []
            body = " ".join(self.browser.page_text().lower().split()) if not rows else ""
            if rows or "something went wrong on our end" not in body or attempt == 1:
                break
            logger.warning("Temporary eBay server error; retrying the same query through the normal search bar once")
            # Budgets are still enforced by the matcher when eBay's optional filters fail.
            parts = urlsplit(url)
            params = dict(parse_qsl(parts.query))
            params.pop("_ipg", None)
            params.pop("_udhi", None)
            url = urlunsplit(parts._replace(query=urlencode(params)))
            time.sleep(2)
        if not rows:
            if not any(marker in body for marker in ("0 results", "no results", "no exact matches")):
                title = self.browser.js("return document.title") or ""
                current = self.browser.current_url()
                self.browser.screenshot("ebay_search_unreadable")
                logger.warning("Unreadable eBay search: title=%r url=%s body=%r", title, current, body[:700])
                if "something went wrong on our end" in body:
                    raise RuntimeError("eBay server error persisted after one retry. This search was not completed.")
                if any(word in body for word in ("verify you're", "verify you are", "security check", "captcha")):
                    raise SourceUnavailable("eBay requires verification in the scanner Chrome window. This search was not completed.")
                if "sign in" in title.lower() or "signin" in current.lower():
                    raise SourceUnavailable("eBay sign-in is required in the scanner Chrome profile. Use the scanner sign-in controls.")
                raise RuntimeError(f"eBay page did not expose readable results ({title or 'untitled page'}). This search was not completed.")
        listings = []
        for row in rows[:limit]:
            listing = self._parse_card(row, buying_option)
            if listing is None:
                continue
            # A Buy-It-Now search still picks up auctions that also show a bid count.
            # Those are watched only when an auction search was requested, and never bid on from here.
            if buying_option == "bin" and listing.listing_type == "auction":
                continue
            listings.append(listing)
        return listings

    @staticmethod
    def price_currency(text: str, default: str) -> str:
        for pattern, currency in ((r"\b(?:US\s*\$|USD\b)", "USD"),
                                  (r"\b(?:C\s*\$|CA\s*\$|CAD\b)", "CAD"),
                                  (r"\b(?:AU\s*\$|A\s*\$|AUD\b)", "AUD"),
                                  (r"£|\bGBP\b", "GBP"), (r"€|\bEUR\b", "EUR")):
            if re.search(pattern, text, re.I):
                return currency
        return default

    def _parse_card(self, row: dict, buying_option: str) -> Listing | None:
        lines = [ln.strip() for ln in row["text"].split("\n") if ln.strip()]
        if not lines:
            return None
        title_lines = (row.get("title") or row["text"]).splitlines()
        title = next((ln.strip() for ln in title_lines if ln.strip().lower() not in {
            "new listing", "sponsored", "opens in a new window or tab"
        } and not ln.startswith(("C $", "US $", "$"))), lines[0])
        price_line = row.get("price") or next((ln for ln in lines if re.search(r"(C\s?\$|US\s?\$|\$|£|€)\s?\d", ln)), "")
        # A variation range does not identify the asking price of the requested card.
        ranged_price = bool(re.search(r"\bto\b|\s[-–]\s", price_line, re.I))
        if ranged_price and buying_option != "all":
            return None
        currency = self.price_currency(price_line, self.settings.ebay_currency)
        shipping_line = next((ln for ln in lines if "shipping" in ln.lower() or "delivery" in ln.lower()), "")
        time_line = row.get("timeLeft") or extract_time_left_line(lines)
        bids_line = next((ln for ln in lines if re.search(r"\b\d+\s+bids?\b", ln.lower())), "")
        shipping = None
        if shipping_line:
            amount = r"((?:(?:US|CA|C|AU|A)\s*)?[$£€]\s*\d[\d,]*(?:\.\d{1,2})?)"
            charge = re.search(amount + r"\s*(?:shipping|delivery)", shipping_line, re.I)
            charge = charge or re.search(r"(?:shipping|delivery)\s*:?\s*" + amount, shipping_line, re.I)
            if charge and self.price_currency(charge.group(1), currency) == currency:
                shipping = parse_price(charge.group(1))
            elif re.search(r"\bfree(?:\s+[\w-]+){0,3}\s+(?:shipping|delivery)\b", shipping_line, re.I):
                shipping = 0.0
        bid_count = int(re.search(r"(\d+)\s+bids?", bids_line.lower()).group(1)) if bids_line else None
        return Listing(
            source="ebay",
            listing_id=row["id"],
            title=title,
            price=None if ranged_price else parse_price(price_line),
            currency=currency,
            url=row["href"],
            listing_type="auction" if (buying_option == "auction" or bids_line) else "bin",
            shipping=shipping,
            end_time=parse_time_left(time_line),
            image_url=row.get("img", ""),
            condition=next((ln for ln in lines if re.match(
                r"(?:condition\s*:?\s*)?(near mint|lightly played|moderately played|heavily played|damaged|pre-owned)\b",
                ln, re.I)), ""),
            bid_count=bid_count,
            raw=row,
        )

    def details(self, listing: Listing) -> Listing:
        """Read the seller's condition, which search cards often reduce to 'Pre-Owned'."""
        self.browser.get(listing.url)
        self.browser.wait_until(lambda: bool(self.browser.js(
            "return document.querySelector('.x-item-condition-text') || document.querySelector('.x-item-title');"
        )), timeout=10)
        condition = self.browser.js(
            "return document.querySelector('.x-item-condition-text')?.innerText || '';"
        ) or ""
        body = self.browser.page_text()
        if not condition:
            found = re.search(r"(?:^|\n)Condition:\s*\n([^\n]+)", body, re.I)
            condition = found.group(1).strip() if found else ""
        listing.condition = condition.strip() or "unverified"
        if re.search(r"this listing (?:has ended|sold)|this item is no longer available|the item you selected is unavailable", body, re.I):
            listing.price = None
        return listing


class EbaySource:
    """Finds Buy-It-Now deals and ending-soon auctions for a target."""

    name = "ebay"

    def __init__(self, settings: SnipeSettings, browser: Browser | None):
        self.settings = settings
        if settings.ebay_api_enabled:
            self.client = EbayBrowseAPI(settings)
            self.mode = "api"
        else:
            if browser is None:
                raise ValueError("Chrome browser required for eBay when API keys are not configured")
            self.client = EbayWeb(settings, browser)
            self.mode = "web"

    def find(self, target: Target) -> list[Listing]:
        # Buy-It-Now only. Auctions are not searched and are never bid on.
        return self.client.search(target.search_query, target.max_price, "bin", self.settings.ebay_max_results)

    def details(self, listing: Listing) -> Listing:
        return self.client.details(listing)


# ── bidding ──────────────────────────────────────────────────────────────────

CONFIRM_SELECTORS = [
    ("css selector", "button[data-testid='ux-call-to-action']"),
    ("css selector", "#confirm_button"),
    ("css selector", "button[name='confirm']"),
    ("xpath", "//button[contains(normalize-space(.), 'Confirm bid')]"),
    ("xpath", "//button[contains(normalize-space(.), 'Confirm')]"),
    ("xpath", "//input[@type='submit' and contains(@value, 'Confirm')]"),
]
LOGIN_MARKERS = ("signin.ebay", "/signin", "userid", "sign in to your account")
SUCCESS_MARKERS = ("you're the highest bidder", "you are the highest bidder", "bid confirmed",
                   "you've been outbid", "you have been outbid", "congratulations", "you won")


def bid_page_url(settings: SnipeSettings, item_id: str, amount: float) -> str:
    return f"https://offer.{settings.ebay_domain}/ws/eBayISAPI.dll?MakeBid&item={item_id}&maxbid={amount:.2f}"


TIMER_JS = """
const sel = "[class*='timer'], [class*='time-left'], [class*='timeLeft'], [class*='countdown']";
for (const el of document.querySelectorAll(sel)) {
  const t = (el.innerText || '').trim();
  if (/\\d+\\s*[dhms]\\b/i.test(t)) return t;
}
return '';
"""


def refresh_end_time(browser: Browser, settings: SnipeSettings, item_id: str) -> datetime | None:
    """Read the item page countdown (second precision close to the end) for an exact end time.

    Search-page times are minute-granular, so we re-read right before sniping.
    """
    try:
        browser.get(f"https://www.{settings.ebay_domain}/itm/{item_id}")
        browser.wait_until(lambda: bool(browser.js(TIMER_JS)), timeout=6)
        text = browser.js(TIMER_JS) or ""
        return parse_time_left(text)
    except Exception as exc:
        logger.debug("could not refresh end time for %s: %s", item_id, exc)
        return None


def place_snipe(browser: Browser, settings: SnipeSettings, item_id: str, max_bid: float,
                end_time: datetime | None, live: bool, refine_end_time: bool = True) -> tuple[str, str]:
    """Open the bid confirmation page early, then confirm `snipe_lead_seconds` before the end.

    Returns (status, detail). status: placed | skipped | failed.
    Dry-run never opens the bid page.
    """
    if not live:
        return "skipped", "dry-run does not open or confirm a bid"
    if refine_end_time:
        exact = refresh_end_time(browser, settings, item_id)
        if exact is not None:
            end_time = exact
    url = bid_page_url(settings, item_id, max_bid)
    try:
        browser.get(url)
    except Exception as exc:
        return "failed", f"could not open bid page: {exc}"

    current = browser.current_url().lower()
    body = browser.page_text().lower()
    if any(marker in current or marker in body for marker in LOGIN_MARKERS):
        browser.screenshot(f"login_required_{item_id}")
        return "failed", "eBay login required — run `python3 snipe.py login` and sign in once"

    confirm = browser.find_first(CONFIRM_SELECTORS)
    if confirm is None:
        shot = browser.screenshot(f"no_confirm_{item_id}")
        return "failed", f"confirm button not found on bid page (screenshot: {shot})"

    if end_time is not None:
        fire_at = end_time.timestamp() - settings.snipe_lead_seconds
        while True:
            remaining = fire_at - time.time()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.25))

    if not live:
        shot = browser.screenshot(f"dry_run_{item_id}")
        return "dry_run", f"would have confirmed {max_bid:.2f} (screenshot: {shot})"

    try:
        with browser.lock:
            confirm.click()
    except Exception:
        try:
            browser.js("arguments[0].click();", confirm)
        except Exception as exc:
            return "failed", f"confirm click failed: {exc}"

    browser.wait_until(lambda: any(m in browser.page_text().lower() for m in SUCCESS_MARKERS), timeout=8)
    text = browser.page_text().lower()
    shot = browser.screenshot(f"result_{item_id}")
    if any(m in text for m in SUCCESS_MARKERS):
        return "placed", f"bid submitted ({shot})"
    return "placed", f"confirm clicked; result unclear — check eBay (screenshot: {shot})"
