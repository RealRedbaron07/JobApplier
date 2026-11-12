"""Bounded public browser price checks for ungraded, identifiable singles."""

import re
from urllib.parse import quote_plus, urlencode

from cardsnipe.condition import TCGPLAYER_NAMES
from cardsnipe.matcher import detect_grade

NUMBER = re.compile(r"(?<!\d)(\d{1,3}/\d{1,3})(?!\d)")
STATED_NUMBER = re.compile(r"#\s*(\d{1,3})\b")
EXCLUDE = re.compile(r"\b(?:sealed|booster|etb|box|pack|lot|bundle|jumbo|oversized|proxy|fake|metal|reprint|custom|graded|slab|psa|cgc|bgs|tag|japanese|korean|chinese|german|french|spanish|italian|world championship)\b", re.I)
# Slabs from graders the crack check does not cover, and grade wording without a known company.
OTHER_SLAB = re.compile(r"\b(?:ags|pca|gma|hga|mnt|ace)\s*-?\s*(?:gem[- ]?mt|gem\s+mint|mint\+?|graded|grade)?\s*-?\s*"
                        r"(?:10|9\.5|9|8\.5|8|7)\b|\bgem[- ]?mt\b|\bmint\s*\+", re.I)
# Japanese set codes and rarities (SV2a, s8b, SM12a, AR / SAR / CHR); English uses IR / SIR.
JAPANESE = re.compile(r"\b(?:japan(?:ese)?|jpn|jp|sv\d{1,2}[a-z]|s\d{1,2}[a-z]|sm\d{1,2}[a-z+]|m\d{1,2}[a-z]|s-p|sv-p|sar|chr|csr|ssr|"
                      r"art rare|shiny treasure|blue shock|pokemiku|hatsune miku)\b", re.I)
# One listing selling several slabs or grades ("PSA 7 & 8 & 9", "Psa7. &8. &9", "PSA 7-9").
MULTI_GRADE = re.compile(r"\b(?:psa|bgs|cgc|tag|sgc)\s*-?\s*\d{1,2}(?:\.5)?\s*[.,]?\s*(?:&|and|or|/|-|,)\s*(?:psa|bgs|cgc)?\s*"
                         r"\d{1,2}(?:\.5)?\b(?!\s*/)", re.I)


def not_a_plain_listing(title):
    """Other graders, Japanese cards, and multi-slab listings: never priced as one English card."""
    title = title or ""
    return bool(OTHER_SLAB.search(title) or JAPANESE.search(title) or MULTI_GRADE.search(title))


VARIANT = re.compile(r"\b(?:reverse (?:holo\w*|foil)|rev\.? holo\w*|cosmos holo|non.?holo|first edition|1st edition|1st ed|shadowless|staff|prize pack|promo|"
                     r"pre-?release|stamp(?:ed)?|e-?reader|error|misprint)\b", re.I)
# Reprint sets that reuse an older card's exact number (Celebrations Classic Collection).
REPRINT_SET = re.compile(r"classic collection|celebrations", re.I)
# TCGplayer print names that are never the plain copy a seller title describes.
OTHER_PRINTINGS = re.compile(r"1st edition|reverse|cosmos|staff|stamp", re.I)


PRICE_VERSION = "plain print"
# Prices saved without this tag predate the PriceCharting / recent-sales cross-check.
CROSS_CHECK = "sales checked"


def stale_reference(value_source):
    """True for TCGplayer prices saved before print-specific pricing (they may be 1st Edition prices)."""
    return bool(value_source) and value_source.startswith("TCGplayer") and PRICE_VERSION not in value_source


def needs_recheck(value_source):
    """True for saved prices that should be checked again: stale, or never cross-checked against sales."""
    return stale_reference(value_source) or (bool(value_source) and CROSS_CHECK not in value_source)


def identifiable(title):
    """One card number, or no number but enough words to name a card and its set."""
    count = len(NUMBER.findall(title or ""))
    return count == 1 or (count == 0 and len(name_query(title).split()) >= 2)


def eligible(title):
    return (identifiable(title) and not EXCLUDE.search(title or "") and not VARIANT.search(title or "")
            and not detect_grade(title) and not not_a_plain_listing(title))


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
    if not eligible(title):
        return None
    if not number:
        return _pick_by_name(products, title)
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


def _pick_by_name(products, title):
    """One product whose full name and set are both in a title that has no card number.

    Marketplace sellers usually write "Base Set Magneton Holo". A "#114" in the title must agree,
    and a set with two cards of that name is left unpriced rather than guessed.
    """
    title_words = set(_words(title))
    stated = STATED_NUMBER.search(title)
    matches = []
    for product in products:
        name = _name_words(product.get("name"))
        set_name = product.get("set", "")
        set_words = _words(re.split(r":| - ", set_name)[-1])
        if not name or not set_words or set(name) <= set(set_words):
            continue  # a card named after its set ("Arceus" in Arceus) proves nothing
        if any(word not in title_words for word in name + set_words):
            continue
        if VARIANT.search(set_name + " " + product.get("name", "")) or REPRINT_SET.search(set_name):
            continue
        if stated and _number_key(product.get("number")).split("/")[0] != stated.group(1).lstrip("0"):
            continue
        if product.get("price", 0) > 0:
            matches.append(product)
    return {**matches[0], "matched_by": "name and set"} if len(matches) == 1 else None


def search_query(title):
    """TCGplayer finds the card by its number; the full seller title usually returns nothing."""
    number = NUMBER.search(title or "")
    return number.group(1) if number else (title or "")


# Seller words TCGplayer's search does not help with: left in, they push the real card off the results.
SEARCH_NOISE = re.compile(r"\b(?:pok[eé]mon|tcg|cards?|holo\w*|foil|rare|wotc|wizards|of|the|coast|vintage|nintendo|"
                          r"english|unlimited|nm|lp|mp|hp|dmg|mint|near|light(?:ly)?|moderately|heavily|played|"
                          r"damaged|scratched|poor|excellent|condition|uk|(?:19|20)\d\d)\b\+?", re.I)


def name_query(title):
    """Card name and set from a seller title, for cards TCGplayer cannot find by number.

    Older cards are named just "Sabrina's Gengar" there, so searching "14/132" returns other cards.
    """
    words = SEARCH_NOISE.sub(" ", STATED_NUMBER.sub(" ", NUMBER.sub(" ", title or "")))
    return " ".join(re.sub(r"[^\w'&.-]+", " ", words).split())


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


def plain_printing(prices):
    """(print name, price) of the plain print (Unlimited / Holofoil / Normal); (None, None) when unclear."""
    plain = {name: price for name, price in prices.items() if not OTHER_PRINTINGS.search(name) and price > 0}
    for preferred in ("Unlimited Holofoil", "Holofoil", "Unlimited", "Normal"):
        if preferred in plain:
            return preferred, plain[preferred]
    return next(iter(plain.items())) if len(plain) == 1 else (None, None)


def plain_printing_price(prices):
    """Price of the plain print; None when only special prints are listed."""
    return plain_printing(prices)[1]


def sold_last_3_months(text):
    """TCGplayer's 3-month "Total Sold" count for the selected condition and print, if shown."""
    match = re.search(r"Total Sold:\s*([\d,]+)", text or "")
    return int(match.group(1).replace(",", "")) if match else None


def condition_market_price(text, condition_name, printing):
    """Market price TCGplayer shows for one condition of one print ("Lightly Played Holofoil")."""
    match = re.search(re.escape(f"{condition_name} {printing}") + r"\s*\n\s*Market Price\s*\$([\d,]+\.\d{2})", text or "")
    return float(match.group(1).replace(",", "")) if match else None


def _search_products(browser, query):
    """Product cards from one TCGplayer search page."""
    browser.get("https://www.tcgplayer.com/search/pokemon/product?productLineName=pokemon&q=" + quote_plus(query))
    state = lambda: browser.js("""return document.querySelector('.product-card__product') ? 'results'
      : /\\b0 results\\b|no results/i.test(document.body ? document.body.innerText : '') ? 'empty' : ''""")
    if not browser.wait_until(state, 10):
        raise RuntimeError("TCGplayer search results were unreadable; this card was not checked")
    # The page briefly says "0 results" while loading; only trust it if no products appear soon after.
    if state() == "empty" and not browser.wait_until(lambda: state() == "results", 5):
        return []
    return browser.js("""return [...document.querySelectorAll('.product-card__product')].map(card => ({
      set: card.querySelector('.product-card__set-name')?.innerText || '',
      number: (card.querySelector('.product-card__rarity')?.innerText || '').match(/#\\d+\\/\\d+/)?.[0] || '',
      name: card.querySelector('.product-card__title')?.innerText || '',
      price: Number((card.querySelector('.product-card__market-price--value')?.innerText || '').replace(/[^0-9.]/g, '')),
      url: card.closest('a')?.href || ''
    }))""") or []


def tcgplayer_market(browser, title, claim=None):
    """Plain-print Near Mint market price (USD) for the card in `title`.

    When the seller states a played condition (claim "LP", "MP", "HP" or "DMG"), the same
    product page is also read for that condition's market price ("condition_price").
    """
    product = None
    for query in ([search_query(title)] if NUMBER.search(title or "") else []) + [name_query(title)]:
        product = pick_product(_search_products(browser, query), title) if query else None
        if product:
            break
    if not product or not product.get("url"):
        return product
    # The search card can show the 1st Edition or another print's price; read the plain print's price.
    browser.get(product["url"].split("?")[0] + "?Language=English")
    # "Price Points" only appears on product pages, so the previous search page is never parsed.
    if not browser.wait_until(lambda: "Price Points" in browser.page_text() and "Market Price" in browser.page_text(), 12):
        raise RuntimeError("TCGplayer product page was unreadable; this card was not checked")
    # The comparison block ("Unlimited Holofoil: $..") loads after the rest of the page; the default
    # selected print can be 1st Edition, so wait for a plain print's price before giving up.
    browser.wait_until(lambda: plain_printing(printing_prices(browser.page_text()))[1], 8)
    text = browser.page_text()
    printing, price = plain_printing(printing_prices(text))
    if not price:
        return None
    result = {**product, "price": price, "printing": printing, "sold_3m": sold_last_3_months(text),
              "condition": claim, "condition_price": None}
    name = TCGPLAYER_NAMES.get(claim)
    if name and claim != "NM":
        browser.get(product["url"].split("?")[0] + "?" + urlencode(
            {"Language": "English", "Condition": name, "Printing": printing}))
        # The Near Mint page never shows "<condition> <print> / Market Price", so a stale page cannot match.
        # No price within the wait leaves condition_price empty; the deal math then uses a share of Near Mint.
        found = lambda: condition_market_price(browser.page_text(), name, printing)
        if browser.wait_until(lambda: found() is not None, 8):
            result["condition_price"] = found()
    return result
