"""Bounded public browser price checks for ungraded, identifiable singles."""

import re
from urllib.parse import quote_plus

from cardsnipe.matcher import detect_condition_issue, detect_grade

NUMBER = re.compile(r"(?<!\d)(\d{1,3}/\d{1,3})(?!\d)")
EXCLUDE = re.compile(r"\b(?:sealed|booster|etb|box|pack|lot|bundle|jumbo|oversized|proxy|fake|metal|reprint|custom|graded|slab|psa|cgc|bgs|tag|japanese|korean|chinese|german|french|spanish|italian|world championship)\b", re.I)
VARIANT = re.compile(r"\b(?:reverse holo|cosmos holo|non.?holo|first edition|1st edition|1st ed|shadowless|staff|prize pack|promo|"
                     r"pre-?release|stamp(?:ed)?|e-?reader|error|misprint)\b", re.I)
# Reprint sets that reuse an older card's exact number (Celebrations Classic Collection).
REPRINT_SET = re.compile(r"classic collection|celebrations", re.I)
# TCGplayer print names that are never the plain copy a seller title describes.
OTHER_PRINTINGS = re.compile(r"1st edition|reverse|cosmos|staff|stamp", re.I)


PRICE_VERSION = "plain print"


def stale_reference(value_source):
    """True for TCGplayer prices saved before print-specific pricing (they may be 1st Edition prices)."""
    return bool(value_source) and value_source.startswith("TCGplayer") and PRICE_VERSION not in value_source


def eligible(title):
    return (len(NUMBER.findall(title or "")) == 1 and not EXCLUDE.search(title) and not VARIANT.search(title)
            and not detect_grade(title) and not detect_condition_issue(title))


def _number_key(number):
    return "/".join(part.lstrip("0") or "0" for part in (number or "").lstrip("#").split("/"))


def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _name_words(name):
    # TCGplayer names can carry suffixes like "Greninja BREAK - 2016 (Cody Walinski)" or "Dodrio (34)".
    name = re.sub(r"\([^)]*\)", " ", name or "")
    return _words(name.split(" - ")[0])


def pick_product(products, title):
    """Match one product by exact card number and name; use the set to break ties.

    Sellers often leave the set out ("Miraidon 028/084 Holo"), so a unique
    number + name match is accepted. When several printings share the number
    and name, the set words in the title must pick exactly one.
    """
    number = NUMBER.search(title or "")
    if not number or not eligible(title):
        return None
    title_words = set(_words(title))
    matches = []
    reprint_seen = False
    for product in products:
        if _number_key(product.get("number")) != _number_key(number.group(1)):
            continue
        name = _name_words(product.get("name"))
        if not name or any(word not in title_words for word in name):
            continue
        if VARIANT.search(product.get("set", "") + " " + product.get("name", "")):
            continue
        if REPRINT_SET.search(product.get("set", "")) and not re.search(r"celebration", title, re.I):
            reprint_seen = True
            continue
        if product.get("price", 0) > 0:
            matches.append(product)
    if len(matches) > 1 or (reprint_seen and matches):
        # Several printings, or a reprint that shares the number: the title must name the set.
        with_set = [p for p in matches
                    if (words := _words(p.get("set", "").split(":")[-1])) and all(w in title_words for w in words)]
        matches = with_set
    return matches[0] if len(matches) == 1 else None


def search_query(title):
    """TCGplayer finds the card by its number; the full seller title usually returns nothing."""
    number = NUMBER.search(title or "")
    return number.group(1) if number else (title or "")


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


def printing_prices(text):
    """Near Mint market price per print ("Unlimited Holofoil": 39.76) from a TCGplayer product page."""
    prices = {}
    section = text.split("Near Mint Comparison Prices", 1)[-1] if "Near Mint Comparison Prices" in text else ""
    section = section.split("Price Points", 1)[0]
    for name, value in re.findall(r"([A-Za-z0-9 ]+?):\s*\$([\d,]+\.\d{2})", section):
        prices[name.strip()] = float(value.replace(",", ""))
    selected = re.search(r"Near Mint ([A-Za-z0-9 ]+?)\s*\n\s*Market Price\s*\$([\d,]+\.\d{2})", text)
    if selected:
        prices.setdefault(selected.group(1).strip(), float(selected.group(2).replace(",", "")))
    return prices


def plain_printing_price(prices):
    """Price of the plain print (Unlimited / Holofoil / Normal); None when only special prints are listed."""
    plain = {name: price for name, price in prices.items() if not OTHER_PRINTINGS.search(name) and price > 0}
    for preferred in ("Unlimited Holofoil", "Holofoil", "Unlimited", "Normal"):
        if preferred in plain:
            return plain[preferred]
    return next(iter(plain.values()), None) if len(plain) == 1 else None


def tcgplayer_market(browser, title):
    browser.get("https://www.tcgplayer.com/search/pokemon/product?productLineName=pokemon&q="
                + quote_plus(search_query(title)))
    state = lambda: browser.js("""return document.querySelector('.product-card__product') ? 'results'
      : /\\b0 results\\b|no results/i.test(document.body ? document.body.innerText : '') ? 'empty' : ''""")
    if not browser.wait_until(state, 10):
        raise RuntimeError("TCGplayer search results were unreadable; this card was not checked")
    # The page briefly says "0 results" while loading; only trust it if no products appear soon after.
    if state() == "empty" and not browser.wait_until(lambda: state() == "results", 5):
        return None
    products = browser.js("""return [...document.querySelectorAll('.product-card__product')].map(card => ({
      set: card.querySelector('.product-card__set-name')?.innerText || '',
      number: (card.querySelector('.product-card__rarity')?.innerText || '').match(/#\\d+\\/\\d+/)?.[0] || '',
      name: card.querySelector('.product-card__title')?.innerText || '',
      price: Number((card.querySelector('.product-card__market-price--value')?.innerText || '').replace(/[^0-9.]/g, '')),
      url: card.closest('a')?.href || ''
    }))""") or []
    product = pick_product(products, title)
    if not product or not product.get("url"):
        return product
    # The search card can show the 1st Edition or another print's price; read the plain print's price.
    browser.get(product["url"].split("?")[0] + "?Language=English")
    # "Price Points" only appears on product pages, so the previous search page is never parsed.
    if not browser.wait_until(lambda: "Price Points" in browser.page_text() and "Market Price" in browser.page_text(), 12):
        raise RuntimeError("TCGplayer product page was unreadable; this card was not checked")
    price = plain_printing_price(printing_prices(browser.page_text()))
    return {**product, "price": price} if price else None
