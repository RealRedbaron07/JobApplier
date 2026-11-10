from cardsnipe.bargains import eligible, pick_product


def test_only_clear_single_cards_get_browser_price_checks():
    assert eligible("Pokemon Lugia VSTAR 139/195 Silver Tempest")
    assert eligible("Lugia VSTAR Silver Tempest")  # no number: only priced if name and set pick one card
    for title in ("Any Pokémon card", "PSA 10 Lugia VSTAR 139/195 Silver Tempest",
                  "Lugia VSTAR 139/195 Japanese Silver Tempest", "Lugia VSTAR 139/195 reverse holo Silver Tempest",
                  "Lugia VSTAR 139/195 211/195 Silver Tempest", "Lugia VSTAR 139/195 jumbo Silver Tempest",
                  ):
        assert not eligible(title)
    # Played and damaged copies are priced at their own condition, so they are checked too.
    assert eligible("Lugia VSTAR 139/195 Silver Tempest LP") and eligible("Lugia VSTAR 139/195 Silver Tempest damaged")


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


def test_plain_print_price_ignores_first_edition_and_reverse_prices():
    from cardsnipe.bargains import plain_printing_price, printing_prices, stale_reference
    text = ("Near Mint Comparison Prices\nMarket prices for alternative printings and conditions\n"
            "1st Edition Holofoil:\t$123.59\tUnlimited Holofoil:\t$39.76\nPrice Points \n"
            "Near Mint Unlimited Holofoil\nMarket Price\t$39.76\n")
    assert plain_printing_price(printing_prices(text)) == 39.76
    assert plain_printing_price({"Holofoil": 5.0, "Reverse Holofoil": 9.0}) == 5.0
    assert plain_printing_price({"1st Edition Holofoil": 120.0}) is None
    assert stale_reference("TCGplayer browser · BoC FX 1.4") and not stale_reference("TCGplayer plain print · BoC FX 1.4")
    assert not stale_reference("") and not stale_reference("manual")


def test_reprint_only_results_are_not_priced_as_the_original():
    reprint = {"name": "Rocket's Zapdos", "number": "#15/132", "set": "Celebrations: Classic Collection", "price": 2.99}
    assert pick_product([reprint], "Rocket's Zapdos 15/132 Gym Challenge Holo") is None
    assert pick_product([reprint], "Rocket's Zapdos 15/132 Celebrations Classic Collection") == reprint


def test_condition_price_is_read_for_the_plain_print():
    from cardsnipe.bargains import condition_market_price, plain_printing, sold_last_3_months
    text = ("Near Mint Comparison Prices\nHolofoil:\t$6.39\nPrice Points \nLightly Played Holofoil\n"
            "Market Price\t$5.74\nMost Recent Sale\t$6.99\nTotal Sold:\t111\tAvg. Daily Sold:\t1\n")
    assert condition_market_price(text, "Lightly Played", "Holofoil") == 5.74
    assert condition_market_price(text, "Lightly Played", "Reverse Holofoil") is None
    assert sold_last_3_months(text) == 111
    assert plain_printing({"1st Edition Holofoil": 120.0, "Unlimited Holofoil": 40.0}) == ("Unlimited Holofoil", 40.0)
