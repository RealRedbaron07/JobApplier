"""PriceCharting cross-check: ungraded and per-grade prices plus recent sold listings.

TCGplayer's Near Mint market price can sit well above what a card actually sells
for. PriceCharting publishes, for each card, an ungraded price, a price per grade
(Grade 7 / 8 / 9 / 9.5, PSA 10), and the recent eBay and TCGplayer sales behind
them. The deal math uses these to (a) cap a raw card's value at what it recently
sold for, and (b) value a slab at its own grade's price instead of guessing from
the raw card.

Only public product pages are read, in the scanner's own browser, one card at a time.
All prices are USD.
"""

from __future__ import annotations

import re
import statistics
from datetime import date, datetime, timedelta
from urllib.parse import quote_plus

from cardsnipe.bargains import _name_words, _number_key, _words

SEARCH_URL = "https://www.pricecharting.com/search-products?type=prices&q="
SALES_DAYS = 90
MIN_SALES = 3
# PriceCharting grade rows that a slab grade maps onto. Its "Grade N" prices mix graders but are mostly PSA.
GRADE_LABELS = {7.0: "Grade 7", 8.0: "Grade 8", 9.0: "Grade 9", 9.5: "Grade 9.5"}
# Bracketed PriceCharting variants that are never the plain copy ("[Reverse Holo]", "[1st Edition]", artist decks).
_PLAIN_BRACKETS = {"", "holo"}
# TCGplayer says "EX Emerald", PriceCharting "Pokemon Emerald".
_SET_NOISE = {"pokemon", "and", "the", "tcg", "ex"}
_FOREIGN = re.compile(r"\b(?:japanese|chinese|korean|german|french|spanish|italian|portuguese)\b", re.I)
_SALE_EXCLUDE = re.compile(r"\b(?:psa|bgs|cgc|sgc|tag|ace|ags|graded|slab|lot|bundle|proxy|custom|japanese|jpn|"
                           r"reverse|1st|first edition|shadowless|staff|stamp(?:ed)?|prize pack|sealed)\b", re.I)


def _set_words(name: str) -> set[str]:
    """Comparable set words: "SWSH08: Fusion Strike" and "Pokemon Fusion Strike" both give {fusion, strike}."""
    name = (name or "").replace("&", " and ")
    name = re.split(r":| - ", name)[-1]
    return {word for word in _words(name) if word not in _SET_NOISE}


def _split_title(title: str):
    """("Gardevoir", "holo", "7") from a PriceCharting title like "Gardevoir [Holo] #7"."""
    bracket = re.search(r"\[([^\]]*)\]", title or "")
    number = re.search(r"#\s*([A-Za-z]*\d+[A-Za-z]*)", title or "")
    name = re.sub(r"\[[^\]]*\]|#\s*\S+", " ", title or "")
    return name.strip(), (bracket.group(1).strip().lower() if bracket else ""), (number.group(1) if number else "")


def pick_row(rows, product, card_number):
    """The PriceCharting row for this TCGplayer product, matched on name, number, set and print.

    rows: [{"title": "Gardevoir [Holo] #7", "set": "Pokemon Ruby & Sapphire", "url": ...}]
    product: the matched TCGplayer product ({"name", "set", "printing"}).
    Returns None unless exactly one plain-print row matches; a wrong card is worse than none.
    """
    numerator = _number_key(card_number).split("/")[0]
    name = set(_name_words(product.get("name")))
    tcg_set = _set_words(product.get("set", ""))
    holo = "holo" in (product.get("printing") or "").lower()
    matches = []
    for row in rows:
        title, bracket, number = _split_title(row.get("title", ""))
        if _number_key(number) != numerator or bracket not in _PLAIN_BRACKETS:
            continue
        if _FOREIGN.search(row.get("set", "")) or not name or not name <= set(_words(title)):
            continue
        if not tcg_set or _set_words(row.get("set", "")) != tcg_set:
            continue
        matches.append((bracket, row))
    if len(matches) > 1:
        # Same card with and without a [Holo] row (e.g. Ruby & Sapphire rares): follow TCGplayer's print.
        matches = [m for m in matches if (m[0] == "holo") == holo]
    return matches[0][1] if len(matches) == 1 else None


def parse_money(text):
    match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", text or "")
    return float(match.group(1).replace(",", "")) if match else None


def parse_guide(pairs):
    """{"Ungraded": 184.96, "Grade 9": 1539.86, "PSA 10": ...} from the full price guide rows."""
    guide = {}
    for label, price in pairs or []:
        value = parse_money(price)
        if value:
            guide[(label or "").strip()] = value
    return guide


def recent_sales(rows, today: date | None = None, days: int = SALES_DAYS):
    """(median, count) of recent ungraded sales, skipping graded, lot, foreign and other-print titles.

    rows: [["2026-11-04", "Charizard EX 100/106 Flashfire", "$300.00"], ...]
    """
    today = today or date.today()
    cutoff = today - timedelta(days=days)
    prices = []
    for sold, title, price in rows or []:
        try:
            when = datetime.strptime((sold or "").strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        value = parse_money(price)
        if when < cutoff or not value or _SALE_EXCLUDE.search(title or ""):
            continue
        prices.append(value)
    if len(prices) < MIN_SALES:
        return None, len(prices)
    return round(statistics.median(prices), 2), len(prices)


_SEARCH_JS = """return [...document.querySelectorAll('#games_table tbody tr')].map(tr => ({
  title: tr.querySelector('td.title a')?.innerText.trim() || '',
  set: tr.querySelector('td.console')?.innerText.trim() || '',
  url: tr.querySelector('td.title a')?.href || ''}))"""
_PRODUCT_JS = """const h1 = document.querySelector('h1#product_name') || document.querySelector('h1');
const set = h1?.querySelector('a')?.innerText.trim() || '';
const guide = [...document.querySelectorAll('#full-prices tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))
  .filter(cells => cells.length >= 2).map(cells => [cells[0], cells[1]]);
const box = [...document.querySelectorAll('div.completed-auctions-used')].find(d => d.querySelector('tbody tr'));
const sales = box ? [...box.querySelectorAll('tbody tr')].map(tr => [
  tr.querySelector('td.date')?.innerText.trim() || '', tr.querySelector('td.title')?.innerText.trim() || '',
  tr.querySelector('td.numeric')?.innerText.trim() || '']) : [];
return {title: h1 ? h1.innerText.replace(set, '').trim() : '', set, guide, sales, url: location.href.split('?')[0]};"""


def pricecharting_lookup(browser, product, card_number, grade: float | None = None):
    """PriceCharting prices (USD) for a matched TCGplayer product, or None when no exact row matches.

    Returns {"url", "ungraded", "graded" (price for `grade`, if given), "sales_median", "sales_count"}.
    """
    if not product or not product.get("name") or not card_number:
        return None
    query = f"{' '.join(_name_words(product['name']))} {card_number}"
    browser.get(SEARCH_URL + quote_plus(query))
    ready = lambda: browser.js("return !!(document.querySelector('#games_table') || document.querySelector('#full-prices'))")
    if not browser.wait_until(ready, 10):
        return None
    if not browser.js("return !!document.querySelector('#full-prices')"):
        row = pick_row(browser.js(_SEARCH_JS) or [], product, card_number)
        if not row or not row.get("url"):
            return None
        browser.get(row["url"])
        if not browser.wait_until(lambda: browser.js("return !!document.querySelector('#full-prices')"), 10):
            return None
    page = browser.js(_PRODUCT_JS) or {}
    # A search that jumps straight to a product must still be the same card, set and print.
    if not pick_row([{"title": page.get("title", ""), "set": page.get("set", ""), "url": page.get("url")}],
                    product, card_number):
        return None
    guide = parse_guide(page.get("guide"))
    median, count = recent_sales(page.get("sales"))
    label = GRADE_LABELS.get(grade) if grade is not None else None
    return {"url": page.get("url"), "ungraded": guide.get("Ungraded"),
            "graded": guide.get(label) if label else None, "grade_label": label,
            "sales_median": median, "sales_count": count}
