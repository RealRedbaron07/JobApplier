"""Environment-driven settings for the card sniper."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(ROOT_DIR, path)


@dataclass(frozen=True)
class SnipeSettings:
    watchlist_path: str
    database_url: str
    poll_seconds: int
    snipe_lead_seconds: int
    ebay_app_id: str
    ebay_cert_id: str
    ebay_marketplace: str
    ebay_domain: str
    ebay_currency: str
    ebay_max_results: int
    fb_city: str
    fb_days_since_listed: int
    fb_auto_message: bool
    fb_message_template: str
    chrome_profile_dir: str
    headless: bool
    notify_macos: bool
    open_in_browser: bool
    max_opens_per_scan: int
    max_notifications_per_scan: int
    webhook_url: str
    screenshot_dir: str
    # Set by the CLI. False = simulate bids/messages, alerts still fire.
    live: bool = False

    @property
    def ebay_api_enabled(self) -> bool:
        return bool(self.ebay_app_id and self.ebay_cert_id)

    def with_live(self, live: bool) -> "SnipeSettings":
        return replace(self, live=live)

    @classmethod
    def from_env(cls) -> "SnipeSettings":
        return cls(
            watchlist_path=_abs(os.getenv("SNIPE_WATCHLIST", "data/cardsnipe_watchlist.json")),
            database_url=os.getenv("SNIPE_DATABASE_URL", "sqlite:///" + os.path.join(ROOT_DIR, "cardsnipe.db")),
            poll_seconds=max(10, _env_int("SNIPE_POLL_SECONDS", 45)),
            snipe_lead_seconds=max(2, _env_int("SNIPE_LEAD_SECONDS", 6)),
            ebay_app_id=os.getenv("EBAY_APP_ID", "").strip(),
            ebay_cert_id=os.getenv("EBAY_CERT_ID", "").strip(),
            ebay_marketplace=os.getenv("EBAY_MARKETPLACE", "EBAY_CA").strip() or "EBAY_CA",
            ebay_domain=os.getenv("EBAY_DOMAIN", "ebay.ca").strip() or "ebay.ca",
            ebay_currency=os.getenv("EBAY_CURRENCY", "CAD").strip().upper() or "CAD",
            ebay_max_results=min(200, max(10, _env_int("EBAY_MAX_RESULTS", 60))),
            fb_city=os.getenv("FB_CITY", "toronto").strip().lower() or "toronto",
            fb_days_since_listed=max(1, _env_int("FB_DAYS_SINCE_LISTED", 1)),
            fb_auto_message=_env_bool("FB_AUTO_MESSAGE", False),
            fb_message_template=os.getenv("FB_MESSAGE_TEMPLATE", "Hi! Is this still available?").strip(),
            chrome_profile_dir=_abs(os.getenv("SNIPE_CHROME_PROFILE", "chrome_profile_cardsnipe")),
            headless=_env_bool("SNIPE_HEADLESS", False),
            notify_macos=_env_bool("SNIPE_NOTIFY_MACOS", True),
            open_in_browser=_env_bool("SNIPE_OPEN_IN_BROWSER", True),
            max_opens_per_scan=max(0, _env_int("SNIPE_MAX_OPEN_PER_SCAN", 3)),
            max_notifications_per_scan=max(0, _env_int("SNIPE_MAX_NOTIFY_PER_SCAN", 5)),
            webhook_url=os.getenv("SNIPE_WEBHOOK_URL", "").strip(),
            screenshot_dir=_abs(os.getenv("SNIPE_SCREENSHOT_DIR", os.path.join("data", "cardsnipe_screens"))),
        )
