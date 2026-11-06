from cardsnipe.bargains import eligible, pick_product


def test_only_clear_single_cards_get_browser_price_checks():
    assert eligible("Pokemon Lugia VSTAR 139/195 Silver Tempest")
    for title in ("Lugia VSTAR Silver Tempest", "PSA 10 Lugia VSTAR 139/195 Silver Tempest",
                  "Lugia VSTAR 139/195 Japanese Silver Tempest", "Lugia VSTAR 139/195 reverse holo Silver Tempest",
                  "Lugia VSTAR 139/195 211/195 Silver Tempest", "Lugia VSTAR 139/195 jumbo Silver Tempest",
                  "Lugia VSTAR 139/195 Silver Tempest LP", "Lugia VSTAR 139/195 Silver Tempest damaged"):
        assert not eligible(title)


def test_product_requires_unique_name_number_and_set():
    title = "Pokemon Lugia VSTAR 139/195 Silver Tempest"
    exact = {"name": "Lugia VSTAR", "number": "#139/195", "set": "SWSH12: Silver Tempest", "price": 6.94}
    wrong = {**exact, "set": "Prize Pack Series Cards", "price": 26.49}
    assert pick_product([wrong, exact], title) == exact
    assert pick_product([exact, exact], title) is None
    assert pick_product([wrong], title) is None


def test_product_matches_without_set_in_title_and_searches_by_number():
    from cardsnipe.bargains import search_query
    title = "Pokemon Cards Miraidon 028/084 Holo"
    product = {"name": "Miraidon", "number": "#028/084", "set": "SV: Some Set", "price": 1.5}
    assert pick_product([product], title) == product
    assert search_query("Trade or Sell Pokemon Greninja BREAK 41/122 XY BREAKpoint Card") == "41/122"


def test_reprints_need_set_words_to_break_ties_and_suffixes_are_ignored():
    title = "Greninja BREAK 41/122 XY BREAKpoint"
    original = {"name": "Greninja BREAK", "number": "#41/122", "set": "XY - BREAKpoint", "price": 35.3}
    reprint = {"name": "Greninja BREAK", "number": "#41/122", "set": "ME: 30th Celebration Classic Collection", "price": 10}
    worlds = {"name": "Greninja BREAK - 2016 (Cody Walinski)", "number": "#41/122", "set": "World Championship Decks", "price": 10}
    assert pick_product([worlds, reprint, original], title) == original
    assert pick_product([reprint, original], "Greninja BREAK 41/122") is None


def test_leading_zeros_in_card_numbers_still_match():
    product = {"name": "Dodrio", "number": "#034/064", "set": "Jungle", "price": 4.8}
    assert pick_product([product], "Pokemon Jungle Dodrio 34/64 Trading Card") == product
