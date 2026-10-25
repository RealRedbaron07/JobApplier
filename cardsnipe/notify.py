"""Deal alerts: console, macOS notification, open-in-browser, optional webhook."""

from __future__ import annotations

import logging
import platform
import subprocess

from cardsnipe.matcher import Match
from cardsnipe.settings import SnipeSettings

logger = logging.getLogger("cardsnipe.notify")


def _applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class Notifier:
    def __init__(self, settings: SnipeSettings):
        self.settings = settings
        self.is_mac = platform.system().lower() == "darwin"
        self._opened = 0
        self._notified = 0
        self._suppressed = 0

    def begin_scan(self) -> None:
        """Reset per-scan caps so one big first scan cannot open dozens of tabs."""
        self._opened = 0
        self._notified = 0
        self._suppressed = 0

    def end_scan(self) -> None:
        if self._suppressed and self.settings.notify_macos and self.is_mac:
            self._macos("Card sniper", f"{self._suppressed} more deals this scan — run: python3 snipe.py deals")
        self._suppressed = 0

    def deal(self, match: Match) -> None:
        line = match.headline
        print(f"\n🔥 {line}\n   {match.listing.url}", flush=True)
        if self.settings.notify_macos and self.is_mac:
            if self._notified < self.settings.max_notifications_per_scan:
                self._notified += 1
                self._macos(
                    title=f"Card deal: {match.target.name[:40]}",
                    body=f"{match.listing.currency} {match.total_price:.2f} · {match.listing.title[:90]}",
                )
            else:
                self._suppressed += 1
        if self.settings.open_in_browser and self.is_mac and self._opened < self.settings.max_opens_per_scan:
            self._opened += 1
            self._open(match.listing.url)
        if self.settings.webhook_url:
            self._webhook(f"🔥 {line}\n{match.listing.url}")

    def info(self, title: str, body: str) -> None:
        print(f"ℹ️  {title}: {body}", flush=True)
        if self.settings.notify_macos and self.is_mac:
            self._macos(title, body)
        if self.settings.webhook_url:
            self._webhook(f"{title}: {body}")

    def _macos(self, title: str, body: str) -> None:
        script = (
            f'display notification "{_applescript_string(body)}" '
            f'with title "{_applescript_string(title)}" sound name "Glass"'
        )
        try:
            subprocess.run(["osascript", "-e", script], check=False, timeout=5, capture_output=True)
        except Exception as exc:  # notifications are best-effort
            logger.debug("macOS notification failed: %s", exc)

    def _open(self, url: str) -> None:
        try:
            subprocess.run(["open", url], check=False, timeout=5, capture_output=True)
        except Exception as exc:
            logger.debug("open URL failed: %s", exc)

    def _webhook(self, content: str) -> None:
        try:
            import requests

            requests.post(self.settings.webhook_url, json={"content": content, "text": content}, timeout=5)
        except Exception as exc:
            logger.debug("webhook failed: %s", exc)
