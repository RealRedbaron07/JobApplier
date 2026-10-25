"""Import the user's Collectr showcase (public profile page) so the dashboard knows what
they own and can show trade-up math. Collectr renders client-side, so this loads the
page in headless Chrome and parses the rendered text — no login needed for a public
showcase.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass

from cardsnipe.matcher import parse_price

logger = logging.getLogger("cardsnipe.collectr")

MONEY_RE = re.compile(r"^[+-]?\$[\d,]+(?:\.\d{1,2})?$")
PCT_RE = re.compile(r"^\(([+-]?[\d.]+)%\)$")
QTY_RE = re.compile(r"^Qty:\s*(\d+)$", re.I)
GRADE_HINT_RE = re.compile(r"\b(PSA|CGC|BGS|SGC|TAG|ACE)\s*\d", re.I)


@dataclass
class ShowcaseResult:
    owner: str
    total_value_usd: float | None
    total_cards: int | None
    total_graded: int | None
    items: list[dict]


def parse_showcase_text(text: str) -> ShowcaseResult:
    """Parse the rendered showcase body text.

    Each card renders as:  name / set / rarity / • / number / $price / ±$change / (±pct%) / Qty: n
    Header has "Estimated Portfolio Value" / $X, "Total Cards" / n, "Total Graded" / n.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    owner = ""
    total_value = total_cards = total_graded = None
    for i, line in enumerate(lines):
        if line == "Estimated Portfolio Value" and i + 1 < len(lines):
            total_value = parse_price(lines[i + 1])
            if i >= 1 and not owner:
                owner = lines[i - 1]
        elif line == "Total Cards" and i + 1 < len(lines) and lines[i + 1].isdigit():
            total_cards = int(lines[i + 1])
        elif line == "Total Graded" and i + 1 < len(lines) and lines[i + 1].isdigit():
            total_graded = int(lines[i + 1])

    items: list[dict] = []
    for i, line in enumerate(lines):
        if line != "•" or i < 3 or i + 2 >= len(lines):
            continue
        name, set_name, rarity = lines[i - 3], lines[i - 2], lines[i - 1]
        number = lines[i + 1]
        price_line = lines[i + 2]
        if not MONEY_RE.match(price_line):
            continue
        item = {
            "name": name, "set_name": set_name, "rarity": rarity, "number": number,
            "value_usd": parse_price(price_line), "change_usd": None, "change_pct": None, "quantity": 1,
            "graded": bool(GRADE_HINT_RE.search(name)) or "graded" in rarity.lower(),
        }
        for follow in lines[i + 3:i + 7]:
            if MONEY_RE.match(follow) and item["change_usd"] is None:
                sign = -1 if follow.startswith("-") else 1
                item["change_usd"] = sign * (parse_price(follow.lstrip("+-")) or 0)
            elif (m := PCT_RE.match(follow)):
                item["change_pct"] = float(m.group(1))
            elif (m := QTY_RE.match(follow)):
                item["quantity"] = int(m.group(1))
                break
        items.append(item)
    return ShowcaseResult(owner=owner, total_value_usd=total_value, total_cards=total_cards,
                          total_graded=total_graded, items=items)


def fetch_showcase(url: str, profile_dir: str, wait_seconds: int = 25) -> ShowcaseResult:
    """Load the showcase in a headless Chrome (separate profile) and parse it."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,4000")
    options.add_argument(f"--user-data-dir={os.path.join(profile_dir, 'collectr')}")
    options.add_argument("--disable-notifications")
    driver = webdriver.Chrome(options=options)
    try:
        driver.set_page_load_timeout(45)
        driver.get(url)
        deadline = time.time() + wait_seconds
        text = ""
        while time.time() < deadline:
            text = driver.find_element("tag name", "body").text
            if "Qty:" in text and "Estimated Portfolio Value" in text and "animate-pulse" not in driver.page_source:
                break
            time.sleep(1)
        # Scroll in case the grid lazy-loads.
        for _ in range(6):
            driver.execute_script("window.scrollBy(0, 2500)")
            time.sleep(0.6)
        text = driver.find_element("tag name", "body").text
    finally:
        driver.quit()
    result = parse_showcase_text(text)
    logger.info("collectr: %s cards, portfolio $%s", len(result.items), result.total_value_usd)
    return result


def sync_collection(store, url: str, profile_dir: str):
    """Fetch the showcase and replace the stored collection. Returns the snapshot row."""
    result = fetch_showcase(url, profile_dir)
    if not result.items and result.total_value_usd is None:
        raise RuntimeError("Collectr showcase rendered nothing — is the profile public?")
    return store.replace_collection(result.items, result.total_value_usd, url, owner=result.owner,
                                    total_graded=result.total_graded)
