"""Facebook Marketplace: newest listings for a search, plus optional first-message to the seller."""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import quote_plus

from cardsnipe.browser import Browser
from cardsnipe.matcher import Listing, parse_price
from cardsnipe.settings import SnipeSettings
from cardsnipe.watchlist import Target

logger = logging.getLogger("cardsnipe.facebook")

ITEM_RE = re.compile(r"/marketplace/item/(\d+)")
PRICE_LINE_RE = re.compile(r"(CA\$|C\$|\$|free)", re.I)

EXTRACT_JS = """
const seen = new Set(); const out = [];
for (const a of document.querySelectorAll("a[href*='/marketplace/item/']")) {
  const m = a.href.match(/\\/marketplace\\/item\\/(\\d+)/);
  if (!m || seen.has(m[1])) continue;
  seen.add(m[1]);
  const img = a.querySelector('img');
  out.push({id: m[1], href: 'https://www.facebook.com/marketplace/item/' + m[1] + '/', text: a.innerText || '', img: img ? img.src : ''});
}
return out;
"""

MESSAGE_BOX_SELECTORS = [
    ("css selector", "textarea[aria-label*='essage']"),
    ("css selector", "textarea[placeholder*='essage']"),
    ("css selector", "div[role='textbox'][contenteditable='true']"),
    ("css selector", "textarea"),
]
SEND_SELECTORS = [
    ("css selector", "div[aria-label='Send'][role='button']"),
    ("css selector", "div[aria-label='Send message'][role='button']"),
    ("css selector", "button[aria-label='Send']"),
    ("xpath", "//div[@role='button' and .//span[normalize-space(text())='Send']]"),
    ("xpath", "//span[normalize-space(text())='Send message']/ancestor::div[@role='button'][1]"),
]
MESSAGE_OPENER_SELECTORS = [
    ("xpath", "//div[@role='button' and .//span[contains(normalize-space(text()), 'Message')]]"),
    ("xpath", "//a[@role='button' and .//span[contains(normalize-space(text()), 'Message')]]"),
]


class FacebookMarketplace:
    name = "facebook"

    LOGIN_RETRY_SECONDS = 600

    def __init__(self, settings: SnipeSettings, browser: Browser):
        self.settings = settings
        self.browser = browser
        self._login_failed_at: float | None = None

    # ── auth ─────────────────────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        url = self.browser.current_url().lower()
        if "login" in url or "checkpoint" in url:
            return False
        return not self.browser.js(
            "return !!document.querySelector(\"input[name='email'], form[action*='login']\");"
        )

    def ensure_logged_in(self, wait_seconds: int = 300) -> bool:
        if self.is_logged_in():
            return True
        print("\n🔐 Facebook login needed. Sign in inside the Chrome window (one time); waiting up to "
              f"{wait_seconds // 60} min...", flush=True)
        self.browser.get("https://www.facebook.com/login/")
        ok = self.browser.wait_until(self.is_logged_in, timeout=wait_seconds, interval=2)
        if ok:
            print("✅ Facebook session saved to the sniper Chrome profile.", flush=True)
        return ok

    # ── search ───────────────────────────────────────────────────────────
    def search_url(self, target: Target) -> str:
        return (
            f"https://www.facebook.com/marketplace/{self.settings.fb_city}/search"
            f"?query={quote_plus(target.search_query)}&maxPrice={int(target.max_price)}"
            f"&daysSinceListed={self.settings.fb_days_since_listed}"
            f"&sortBy=creation_time_descend&exact=false"
        )

    def _require_login(self) -> None:
        """Fail fast (no 5-minute wait) so eBay scanning keeps going; `snipe.py login` does the sign-in."""
        if self._login_failed_at and time.time() - self._login_failed_at < self.LOGIN_RETRY_SECONDS:
            raise RuntimeError("Facebook not logged in — run `make login` (retrying every 10 min)")
        if not self.is_logged_in():
            self._login_failed_at = time.time()
            raise RuntimeError("Facebook not logged in — run `make login` (retrying every 10 min)")
        self._login_failed_at = None

    def find(self, target: Target) -> list[Listing]:
        if self._login_failed_at and time.time() - self._login_failed_at < self.LOGIN_RETRY_SECONDS:
            raise RuntimeError("Facebook not logged in — run `make login` (retrying every 10 min)")
        self.browser.get(self.search_url(target))
        self._require_login()
        self.browser.wait_until(
            lambda: self.browser.js("return document.querySelectorAll(\"a[href*='/marketplace/item/']\").length > 0"),
            timeout=10,
        )
        self.browser.js("window.scrollTo(0, 1200);")
        time.sleep(0.8)
        rows = self.browser.js(EXTRACT_JS) or []
        listings = [l for l in (self._parse_card(row) for row in rows) if l]
        return listings

    def _parse_card(self, row: dict) -> Listing | None:
        lines = [ln.strip() for ln in (row.get("text") or "").split("\n") if ln.strip()]
        if not lines:
            return None
        price_idx = next((i for i, ln in enumerate(lines) if PRICE_LINE_RE.search(ln) and len(ln) < 40), None)
        price = parse_price(lines[price_idx]) if price_idx is not None else None
        remaining = [ln for i, ln in enumerate(lines) if i != price_idx]
        title = remaining[0] if remaining else lines[0]
        location = remaining[1] if len(remaining) > 1 else ""
        return Listing(
            source="facebook",
            listing_id=row["id"],
            title=title,
            price=price,
            currency="CAD",
            url=row["href"],
            listing_type="bin",
            location=location,
            image_url=row.get("img", ""),
            raw=row,
        )

    # ── messaging ────────────────────────────────────────────────────────
    def message_seller(self, listing: Listing, text: str, live: bool) -> tuple[str, str]:
        """Open the listing, replace the default message with `text`, and send (when live)."""
        self.browser.get(listing.url)
        try:
            self._require_login()
        except RuntimeError as exc:
            return "failed", str(exc)

        box = self.browser.find_first(MESSAGE_BOX_SELECTORS)
        if box is None:
            opener = self.browser.find_first(MESSAGE_OPENER_SELECTORS)
            if opener is not None:
                try:
                    with self.browser.lock:
                        opener.click()
                except Exception:
                    self.browser.js("arguments[0].click();", opener)
                self.browser.wait_until(lambda: self.browser.find_first(MESSAGE_BOX_SELECTORS) is not None, timeout=6)
                box = self.browser.find_first(MESSAGE_BOX_SELECTORS)
        if box is None:
            shot = self.browser.screenshot(f"fb_no_box_{listing.listing_id}")
            return "failed", f"message box not found (screenshot: {shot})"

        try:
            with self.browser.lock:
                box.click()
                # Clear Facebook's prefilled "Is this available?" before typing ours.
                self.browser.js(
                    "const el=arguments[0]; if ('value' in el) { el.value=''; } else { el.textContent=''; }"
                    "el.dispatchEvent(new Event('input', {bubbles:true}));", box)
                box.send_keys(text)
        except Exception as exc:
            return "failed", f"could not type message: {exc}"

        if not live:
            shot = self.browser.screenshot(f"fb_dry_run_{listing.listing_id}")
            return "dry_run", f"message typed, not sent (screenshot: {shot})"

        send = self.browser.find_first(SEND_SELECTORS)
        if send is None:
            shot = self.browser.screenshot(f"fb_no_send_{listing.listing_id}")
            return "failed", f"send button not found (screenshot: {shot})"
        try:
            with self.browser.lock:
                send.click()
        except Exception:
            self.browser.js("arguments[0].click();", send)
        time.sleep(1.0)
        return "sent", "message sent"
