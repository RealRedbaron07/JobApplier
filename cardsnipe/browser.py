"""One shared Chrome window (persistent profile) used for eBay fallback, bidding, and Facebook."""

from __future__ import annotations

import logging
import os
import threading
import time

from cardsnipe.settings import SnipeSettings

logger = logging.getLogger("cardsnipe.browser")


class Browser:
    """Lazy Selenium Chrome session. All calls are serialized through one lock."""

    def __init__(self, settings: SnipeSettings):
        self.settings = settings
        self.lock = threading.RLock()
        self._driver = None

    @property
    def driver(self):
        with self.lock:
            if self._driver is None:
                self._driver = self._start()
            return self._driver

    def _start(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        os.makedirs(self.settings.chrome_profile_dir, exist_ok=True)
        options.add_argument(f"--user-data-dir={self.settings.chrome_profile_dir}")
        options.add_argument("--window-size=1400,1000")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=en-CA")
        if self.settings.headless:
            options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)  # Selenium Manager resolves chromedriver
        driver.set_page_load_timeout(45)
        logger.info("Chrome started with profile %s", self.settings.chrome_profile_dir)
        return driver

    def get(self, url: str) -> None:
        with self.lock:
            self.driver.get(url)

    def js(self, script: str, *args):
        with self.lock:
            return self.driver.execute_script(script, *args)

    def current_url(self) -> str:
        with self.lock:
            return self.driver.current_url

    def page_text(self) -> str:
        try:
            return self.js("return document.body ? document.body.innerText : '';") or ""
        except Exception:
            return ""

    def wait_until(self, predicate, timeout: float, interval: float = 0.5) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return True
            except Exception:
                pass
            time.sleep(interval)
        return False

    def screenshot(self, name: str) -> str | None:
        try:
            os.makedirs(self.settings.screenshot_dir, exist_ok=True)
            path = os.path.join(self.settings.screenshot_dir, f"{int(time.time())}_{name}.png")
            with self.lock:
                self.driver.save_screenshot(path)
            return path
        except Exception as exc:
            logger.debug("screenshot failed: %s", exc)
            return None

    def find_first(self, selectors: list[tuple[str, str]]):
        """Return the first displayed, enabled element matching any (by, value) selector.

        `by` is a Selenium locator string such as "css selector" or "xpath".
        """
        with self.lock:
            for by, value in selectors:
                try:
                    for element in self.driver.find_elements(by, value):
                        if element.is_displayed() and element.is_enabled():
                            return element
                except Exception:
                    continue
        return None

    def quit(self) -> None:
        with self.lock:
            if self._driver is not None:
                try:
                    self._driver.quit()
                except Exception:
                    pass
                self._driver = None
