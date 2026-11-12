from datetime import date

import pytest

from cardsnipe.deals import assess, is_bargain
from cardsnipe.pricecharting import parse_guide, pick_row, recent_sales

GARDEVOIR_ROWS = [
    {"title": "Gardevoir [Holo] #7", "set": "Pokemon Ruby & Sapphire", "url": "rs-holo"},
    {"title": "Gardevoir #7", "set": "Pokemon Secret Wonders", "url": "sw"},
    {"title": "Gardevoir [Reverse Holo] #7", "set": "Pokemon Ruby & Sapphire", "url": "rs-rev"},
    {"title": "Gardevoir #7", "set": "Pokemon Ruby & Sapphire", "url": "rs"},
    {"title": "Gardevoir [Reverse Holo] #7", "set": "Pokemon Secret Wonders", "url": "sw-rev"},
    {"title": "Gardevoir [Kevin Nguyen] #7", "set": "Pokemon Ruby & Sapphire", "url": "wcd"},
]


def test_pricecharting_row_must_match_set_number_name_and_print():
    secret_wonders = {"name": "Gardevoir", "set": "Secret Wonders", "printing": "Holofoil"}
    assert pick_row(GARDEVOIR_ROWS, secret_wonders, "7/132")["url"] == "sw"
    ruby = {"name": "Gardevoir", "set": "EX Ruby & Sapphire", "printing": "Holofoil"}
    assert pick_row(GARDEVOIR_ROWS, ruby, "7/109")["url"] == "rs-holo"
    assert pick_row(GARDEVOIR_ROWS, {**ruby, "printing": "Normal"}, "7/109")["url"] == "rs"
    # Same number in another set is never borrowed.
    assert pick_row(GARDEVOIR_ROWS, {"name": "Gardevoir", "set": "Base Set", "printing": "Holofoil"}, "7/102") is None


def test_pricecharting_set_names_normalise_tcgplayer_prefixes():
    rows = [{"title": "Baltoy #144", "set": "Pokemon Fusion Strike", "url": "a"},
            {"title": "Baltoy [Reverse Holo] #144", "set": "Pokemon Fusion Strike", "url": "b"},
            {"title": "Charizard EX #100", "set": "Pokemon Flashfire", "url": "c"},
            {"title": "Koffing #109", "set": "Pokemon Scarlet & Violet 151", "url": "d"},
            {"title": "Mewtwo #9", "set": "Pokemon Japanese Melee Pokemon Scramble", "url": "jp"}]
    assert pick_row(rows, {"name": "Baltoy", "set": "SWSH08: Fusion Strike", "printing": "Normal"}, "144/264")["url"] == "a"
    assert pick_row(rows, {"name": "Charizard EX (100 Full Art)", "set": "XY - Flashfire"}, "100/106")["url"] == "c"
    assert pick_row(rows, {"name": "Koffing", "set": "SV: Scarlet & Violet 151"}, "109/165")["url"] == "d"
    assert pick_row(rows, {"name": "Mewtwo", "set": "Melee Pokemon Scramble"}, "9/100") is None


def test_price_guide_and_recent_sales():
    guide = parse_guide([["Ungraded", "$184.96"], ["Grade 9", "$1,539.86"], ["TAG 10", "-"]])
    assert guide == {"Ungraded": 184.96, "Grade 9": 1539.86}
    rows = [["2026-11-04", "Charizard EX 100/106 Flashfire", "$300.00"],
            ["2026-11-01", "Charizard EX 100/106 LP-MP", "$140.00"],
            ["2026-10-31", "Charizard EX 100/106 PSA 9", "$1,500.00"],
            ["2026-10-29", "Charizard EX 100/106 lot of 3", "$400.00"],
            ["2026-10-28", "Charizard EX 100/106", "$175.00"],
            ["2026-05-01", "Charizard EX 100/106", "$90.00"]]
    assert recent_sales(rows, today=date(2026, 11, 7)) == (175.0, 3)
    assert recent_sales(rows[:2], today=date(2026, 11, 7)) == (None, 2)


def raw(value, total, sales=None, title="Pinsir 9/64 Jungle Holo NM", **kw):
    return assess(title=title, source="facebook", listing_type="bin", price=total, shipping=0,
                  total_price=total, value=value, condition="", sales_value=sales, **kw)


def test_recent_sales_cap_a_tcgplayer_price_the_card_does_not_sell_for():
    # TCGplayer NM $60 but it sells around $28: $40 is not a bargain.
    capped = raw(60, 40, sales=28)
    assert capped["basis"] == "sales" and capped["resale_value"] == 28 and capped["tier"] is None
    assert any("under TCGplayer" in flag for flag in capped["flags"])
    assert raw(60, 40)["tier"] == "strong"
    # Sales above TCGplayer never raise the value.
    assert raw(60, 40, sales=90)["resale_value"] == 60


def slab(total, raw_value, graded=None, title="1999 Pokemon Fossil Kabutops 9/62 Holo PSA 8", source="facebook"):
    return assess(title=title, source=source, listing_type="bin", price=total, shipping=0, total_price=total,
                  value=raw_value, slab=("PSA", 8.0) if "PSA" in title else ("CGC", 9.0), graded_value=graded)


def test_psa_slab_under_its_grade_price_is_a_slab_deal():
    deal = slab(60, 30, graded=100)
    assert deal["lane"] == "slab" and deal["tier"] == "strong" and deal["basis"] == "graded"
    assert deal["profit"] == 40 and is_bargain(deal)
    assert slab(90, 30, graded=100)["lane"] is None


def test_no_crack_when_the_slab_sells_for_more_than_the_raw_card():
    # Raw NM $200 makes a $100 PSA 8 look like a crack, but PSA 8s sell for $240: sell it as a slab instead.
    assert slab(100, 200)["lane"] == "crack"
    assert slab(100, 200, graded=240)["lane"] == "slab"
    assert slab(160, 200, graded=190)["lane"] is None  # cracked 8 ≈ 180 < 190 as a slab, and 160 > 80% of 190


def test_other_graders_only_show_the_grade_price_as_a_reference():
    deal = slab(60, 30, graded=100, title="Kabutops 9/62 Fossil CGC 9")
    assert deal["lane"] != "slab" and any("PriceCharting grade 9" in flag for flag in deal["flags"])


def test_graded_value_uses_the_median_of_the_same_graders_sales():
    from cardsnipe.pricecharting import graded_sales
    rows = [["2026-11-06", "2009 POKEMON PLATINUM #7 DIALGA G-HOLO PSA 9", "$579.28"],
            ["2026-10-26", "Dialga G 7/127 Platinum PSA 9", "$810.00"],
            ["2026-10-21", "Dialga G Platinum 7/127 CGC 9 Mint", "$45.99"],
            ["2026-10-12", "Dialga G 7/127 Platinum PSA 9", "$2,000.00"],
            ["2026-10-04", "PSA 9 2009 Platinum Dialga G 7/127", "$140.00"],
            ["2026-09-28", "Dialga G 7/127 Platinum PSA 9", "$610.00"],
            ["2026-09-17", "Dialga G 7/127 Platinum PSA 9 Mint", "$381.15"],
            ["2026-05-01", "Dialga G 7/127 Platinum PSA 9", "$99.00"]]
    assert graded_sales(rows, "PSA", today=date(2026, 11, 9)) == (594.64, 6)
    assert graded_sales(rows, "CGC", today=date(2026, 11, 9)) == (None, 1)
