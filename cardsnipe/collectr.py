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

from cardsnipe.matcher import detect_grade, parse_price, trusted_value_bucket
from cardsnipe.watchlist import Target

logger = logging.getLogger("cardsnipe.collectr")

MONEY_RE = re.compile(r"^[+-]?\$[\d,]+(?:\.\d{1,2})?$")
PCT_RE = re.compile(r"^\(([+-]?[\d.]+)%\)$")
QTY_RE = re.compile(r"^Qty:\s*(\d+)$", re.I)
CARD_NUMBER_RE = re.compile(r"^#?[A-Z]*\d+[A-Z0-9]*(?:/[A-Z0-9]+)?$", re.I)
CONDITION_RE = re.compile(r"\b(Near Mint|Lightly Played|Moderately Played|Heavily Played|Damaged|Mint)\b", re.I)
GRADE_HINT_RE = re.compile(r"\b(PSA|CGC|BGS|SGC|TAG|ACE)\s*\d", re.I)

# Collectr set names that price sites spell differently.
SET_ALIASES = {
    "sun & moon base set": "Sun & Moon", "sword & shield base set": "Sword & Shield",
    "scarlet & violet base set": "Scarlet & Violet", "xy base set": "XY",
    "miscellaneous cards & products": "",  # promos: let the number + name find it
}


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
        if not CARD_NUMBER_RE.fullmatch(number):
            continue
        following = []
        for value in lines[i + 2:i + 16]:
            following.append(value)
            if QTY_RE.match(value):
                break
        price_index = next((j for j, value in enumerate(following) if MONEY_RE.match(value)), None)
        if price_index is None:
            continue
        price_line = following[price_index]
        details = " ".join(following[:price_index])
        condition = CONDITION_RE.search(details)
        item = {
            "name": name, "set_name": set_name, "rarity": rarity, "number": number,
            "value_usd": parse_price(price_line), "change_usd": None, "change_pct": None, "quantity": 1,
            "graded": bool(GRADE_HINT_RE.search(name)) or "graded" in rarity.lower(),
            "condition": condition.group(1) if condition else None,
            "finish": details.split("•")[-1].strip() if "•" in details else None,
        }
        for follow in following[price_index + 1:price_index + 7]:
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


def parse_showcase_import(text: str) -> ShowcaseResult:
    """Validate a complete, manually copied USD showcase before replacing local data."""
    if not isinstance(text, str) or not text.strip() or len(text) > 1_000_000:
        raise ValueError("Paste the full Collectr page text (up to 1 MB).")
    if re.search(r"(?:CA|AU|A|C|NZ|HK|S)\$|[€£¥]", text):
        raise ValueError("Choose USD on Collectr before copying. CAD and other currencies cannot be stored as USD.")
    result = parse_showcase_text(text)
    if not result.items or result.total_cards is None or result.total_value_usd is None:
        raise ValueError("No complete portfolio found. Copy the full Collectr page in USD, including totals and every card.")
    quantities = sum(bool(QTY_RE.fullmatch(line.strip())) for line in text.splitlines())
    if quantities != len(result.items) or result.total_cards != sum(item["quantity"] for item in result.items):
        raise ValueError("The card quantities do not match Collectr's total. Clear filters and load every card before copying.")
    if any(item["quantity"] < 1 or item["value_usd"] is None for item in result.items):
        raise ValueError("Every imported card needs a positive quantity and a displayed price.")
    total = sum(item["value_usd"] * item["quantity"] for item in result.items)
    if abs(total - result.total_value_usd) > max(0.05, len(result.items) * 0.01):
        raise ValueError("The card prices do not match the portfolio total. Copy the unfiltered Cards Only portfolio.")
    return result


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


def market_target(item: dict) -> Target:
    """Watchlist-style target for a Collectr item so PriceService can value it."""
    name = re.sub(r"\(\s*\d+\s*\)", " ", item["name"])          # Collectr's "(21)" disambiguator
    name = re.sub(r"\s+", " ", name).strip()
    set_name = item.get("set_name") or ""
    set_name = SET_ALIASES.get(set_name.lower(), set_name)
    number = item.get("number") or ""
    label = " ".join(p for p in (name, set_name, number) if p)
    return Target(name=f"collection: {label}", keywords=[name], card_name=name, set_name=set_name, number=number)


def item_bucket(item: dict) -> str | None:
    """Price bucket for an owned card. None when the slab isn't a grade we have sales for."""
    grade = detect_grade(item.get("grade") or item["name"])
    if grade is None and (item.get("graded") or item.get("grade")):
        return None
    return trusted_value_bucket(grade)


def value_items(items: list[dict], pricer, force: bool = False) -> list[dict]:
    """Attach our market value to each item.

    Collectr is never the value. Its raw figure is ignored (it is not NM). Its graded
    figure is kept only as `collectr_usd` so it can be glanced at, and is not used for
    the portfolio or for deal math.
    """
    for item in items:
        bucket = item_bucket(item)
        item["market_bucket"] = bucket
        item["market_value_usd"] = item["market_source"] = None
        item["collectr_usd"] = item.get("value_usd") if bucket != "raw" else None
        if bucket == "raw" and (item.get("condition") or "").lower() not in {"near mint", "mint"}:
            continue
        try:
            val = pricer.valuation(market_target(item), force=force)
        except Exception as exc:  # one bad card must not block the sync
            logger.warning("collection valuation failed for %r: %s", item["name"], exc)
            val = None
        found = val.value_usd(bucket) if val and bucket else None
        if found:
            item["market_value_usd"], item["market_source"] = found
    return items


def sync_collection(store, url: str, profile_dir: str, pricer=None):
    """Fetch the showcase, value it with our sources and replace the stored collection."""
    result = fetch_showcase(url, profile_dir)
    if not result.items and result.total_value_usd is None:
        raise RuntimeError("Collectr showcase rendered nothing — is the profile public?")
    items = value_items(result.items, pricer) if pricer else result.items
    return store.replace_collection(items, result.total_value_usd, url, owner=result.owner,
                                    total_graded=result.total_graded)


def revalue_collection(store, pricer, force: bool = False):
    """Re-price what is already stored (no Collectr fetch). Returns the new snapshot or None."""
    rows, latest = store.collection()
    if not rows:
        return None
    items = [{
        "name": r.name, "set_name": r.set_name, "rarity": r.rarity, "number": r.number, "value_usd": r.value_usd,
        "change_usd": r.change_usd, "change_pct": r.change_pct, "quantity": r.quantity, "graded": r.graded, "grade": r.grade,
        "condition": r.condition, "finish": r.finish,
    } for r in rows]
    value_items(items, pricer, force=force)
    return store.replace_collection(items, latest.total_value_usd if latest else None,
                                    latest.source_url if latest else "", owner=latest.owner if latest else "",
                                    total_graded=latest.total_graded if latest else None)
