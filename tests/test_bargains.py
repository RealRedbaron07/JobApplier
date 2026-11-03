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
