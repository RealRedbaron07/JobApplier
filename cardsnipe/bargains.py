"""Bounded public browser price checks for ungraded, identifiable singles."""

import re
from urllib.parse import quote_plus

from cardsnipe.matcher import detect_grade

NUMBER = re.compile(r"(?<!\d)(\d{1,3}/\d{1,3})(?!\d)")
EXCLUDE = re.compile(r"\b(?:sealed|booster|etb|box|pack|lot|bundle|jumbo|oversized|proxy|fake|metal|reprint|custom|graded|slab|psa|cgc|bgs|tag|japanese|korean|chinese|german|french|spanish|italian|world championship)\b", re.I)
VARIANT = re.compile(r"\b(?:reverse holo|cosmos holo|non.?holo|first edition|1st edition|shadowless|staff|prize pack|promo)\b", re.I)


def eligible(title):
    return len(NUMBER.findall(title or "")) == 1 and not EXCLUDE.search(title) and not VARIANT.search(title) and not detect_grade(title)


def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def pick_product(products, title):
    """Require one exact number, name and set in the seller title."""
    number = NUMBER.search(title or "")
    if not number or not eligible(title):
        return None
    title_words = _words(title)
    matches = []
    for product in products:
        if product.get("number", "").lstrip("#") != number.group(1):
            continue
        name = _words(product.get("name"))
        set_name = _words(product.get("set", "").split(":")[-1])
        if not name or not set_name or any(word not in title_words for word in name):
            continue
        if not all(word in title_words for word in set_name):
            continue
        if VARIANT.search(product.get("set", "") + " " + product.get("name", "")):
            continue
        if product.get("price", 0) > 0:
            matches.append(product)
    return matches[0] if len(matches) == 1 else None


def bank_of_canada_usd_cad(browser):
    browser.get("https://www.bankofcanada.ca/rates/exchange/daily-exchange-rates/")
    text = browser.page_text()
    lines = [line for line in text.splitlines() if line.startswith("US dollar\t")]
    if len(lines) != 1:
        return None
    try:
        rate = float(lines[0].split("\t")[-1])
    except ValueError:
        return None
    return rate if 0.5 < rate < 3 else None


def tcgplayer_market(browser, title):
    browser.get("https://www.tcgplayer.com/search/pokemon/product?productLineName=pokemon&q=" + quote_plus(title))
    browser.wait_until(lambda: bool(browser.js("return document.querySelector('.product-card__product')")), 8)
    products = browser.js("""return [...document.querySelectorAll('.product-card__product')].map(card => ({
      set: card.querySelector('.product-card__set-name')?.innerText || '',
      number: (card.querySelector('.product-card__rarity')?.innerText || '').match(/#\\d+\\/\\d+/)?.[0] || '',
      name: card.querySelector('.product-card__title')?.innerText || '',
      price: Number((card.querySelector('.product-card__market-price--value')?.innerText || '').replace(/[^0-9.]/g, '')),
      url: card.closest('a')?.href || ''
    }))""") or []
    return pick_product(products, title)
