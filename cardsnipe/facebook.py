"""Facebook Marketplace: newest listings for a search, plus optional first-message to the seller."""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import quote_plus, urlsplit

from cardsnipe.browser import Browser, SourceUnavailable
from cardsnipe.matcher import Listing, parse_price
from cardsnipe.settings import SnipeSettings
from cardsnipe.watchlist import Target

logger = logging.getLogger("cardsnipe.facebook")

ITEM_RE = re.compile(r"/marketplace/item/(\d+)")
PRICE_LINE_RE = re.compile(r"^(?:(?:CA|C|US|AU)?\s*\$\s*\d|free(?:\s|$))", re.I)


def _no_results(text: str) -> bool:
    # Match Facebook's Turkish dotted and dotless I consistently.
    text = " ".join(text.casefold().replace("\u0307", "").replace("ı", "i").split())
    if any(marker in text for marker in ("security check", "captcha", "something went wrong", "temporarily blocked")):
        return False
    return any(marker in text for marker in (
        "no results", "no listings found", "couldn't find any results",
        "ilan bulunamadi", "sonuç bulunamadi",
    ))


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
        self._login_failed_message = ""

    # ── auth ─────────────────────────────────────────────────────────────
    def is_logged_in(self) -> bool:
        url = urlsplit(self.browser.current_url())
        host = (url.hostname or "").lower()
        if url.scheme != "https" or not (host == "facebook.com" or host.endswith(".facebook.com")):
            return False
        if any(part in url.path.lower() for part in ("login", "checkpoint", "two_factor", "two_step", "auth_platform", "recover", "confirmemail")):
            return False
        if not self.browser.has_cookie("c_user") or not self.browser.has_cookie("xs"):
            return False
        return bool(self.browser.js("""
            return document.readyState === 'complete'
                && !!document.querySelector("[role='navigation'], nav")
                && !document.querySelector("input[name='email'], input[name='pass'], form[action*='login'], form[action*='checkpoint']");
        """))

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
    def search_url(self, target: Target, *, all_dates: bool = False) -> str:
        return (
            f"https://www.facebook.com/marketplace/{self.settings.fb_city}/search"
            f"?query={quote_plus(target.search_query)}"
            + (f"&daysSinceListed={self.settings.fb_days_since_listed}" if not all_dates else "")
            + "&sortBy=creation_time_descend&exact=false"
            + (f"&maxPrice={target.max_price:.2f}" if target.max_price is not None else "")
        )

    def _require_login(self) -> None:
        """Fail fast (no 5-minute wait) so eBay scanning keeps going; `snipe.py login` does the sign-in."""
        if self._login_failed_at and time.time() - self._login_failed_at < self.LOGIN_RETRY_SECONDS:
            raise SourceUnavailable(self._login_failed_message)
        if not self.browser.has_cookie("c_user") or not self.browser.has_cookie("xs"):
            message = "No Facebook login is saved in the scanner's separate Chrome profile. Use Sign in to separate scanner profile, then Finish scanner sign-in. Your regular browser login is separate."
        elif not self.browser.wait_until(self.is_logged_in, timeout=12, interval=0.5):
            message = "Facebook session cookies are saved, but the scanner could not verify a loaded signed-in page. Check that window for a login, security check, or loading error."
        else:
            self._login_failed_at = None
            self._login_failed_message = ""
            return
        self._login_failed_at = time.time()
        self._login_failed_message = message
        raise SourceUnavailable(message)

    def find(self, target: Target, *, all_dates: bool = False) -> list[Listing]:
        if self._login_failed_at and time.time() - self._login_failed_at < self.LOGIN_RETRY_SECONDS:
            raise SourceUnavailable(self._login_failed_message)
        self.browser.get(self.search_url(target, all_dates=all_dates))
        self._require_login()
        self.browser.wait_until(
            lambda: self.browser.js("return document.querySelectorAll(\"a[href*='/marketplace/item/']\").length > 0")
                    or _no_results(self.browser.page_text()),
            timeout=10,
        )
        self.browser.js("window.scrollTo(0, 1200);")
        time.sleep(0.8)
        rows = self.browser.js(EXTRACT_JS) or []
        if not rows:
            self._require_login()
            body = self.browser.page_text()
            if not _no_results(body):
                self.browser.screenshot("facebook_search_unreadable")
                logger.warning("Unreadable Marketplace search: url=%s body=%r", self.browser.current_url(), body[:1200])
                raise RuntimeError("Marketplace did not return readable listings. Check Facebook access in the scanner Chrome profile.")
        listings = [l for l in (self._parse_card(row) for row in rows) if l]
        return listings

    def _parse_card(self, row: dict) -> Listing | None:
        lines = [ln.strip() for ln in (row.get("text") or "").split("\n") if ln.strip()]
        if not lines:
            return None
        price_idx = next((i for i, ln in enumerate(lines) if PRICE_LINE_RE.search(ln) and len(ln) < 40), None)
        price = parse_price(lines[price_idx]) if price_idx is not None else None
        if price_idx is not None and re.search(r"\bto\b|\s[-–]\s", lines[price_idx], re.I):
            return None
        remaining = [ln for ln in lines if not PRICE_LINE_RE.search(ln) and ln.lower() not in {"just listed", "new listing", "sponsored"}]
        title = remaining[0] if remaining else lines[0]
        location = remaining[1] if len(remaining) > 1 else ""
        from cardsnipe.ebay import EbayWeb

        return Listing(
            source="facebook",
            listing_id=row["id"],
            title=title,
            price=price,
            currency=EbayWeb.price_currency(lines[price_idx], "CAD") if price_idx is not None else "CAD",
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
