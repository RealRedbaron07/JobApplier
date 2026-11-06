import pytest

from cardsnipe.bargains import eligible
from cardsnipe.deals import assess, crack_multiplier, is_bargain, max_buy
from cardsnipe.slabs import crack_lane, slab_eligible


def deal(value, total, source="facebook", listing_type="bin", title="Deoxys 4/110 Holon Phantoms", slab=None):
    return assess(title=title, source=source, listing_type=listing_type, price=total, shipping=0,
                  total_price=total, value=value, slab=slab)


def test_a_few_cents_under_market_is_not_a_bargain():
    assert deal(100, 99)["tier"] is None and not is_bargain(deal(100, 99))
    assert deal(100, 80)["tier"] == "good" and deal(100, 70)["tier"] == "strong"
    assert is_bargain(deal(202.39, 110))


def test_small_spreads_need_minimum_profit():
    # 70% under value but only $3 profit: cheap bulk, not a find.
    assert deal(4.3, 1.3)["tier"] is None


def test_ebay_hst_is_part_of_the_all_in_cost():
    verdict = deal(100, 75, source="ebay")
    assert verdict["all_in"] == pytest.approx(84.75) and verdict["tier"] is None
    assert deal(100, 75, source="facebook")["tier"] == "good"
    assert any("HST" in flag for flag in verdict["flags"])


def test_auctions_get_a_max_bid_and_do_not_count_as_bargains():
    verdict = deal(94.96, 38.5, source="ebay", listing_type="auction")
    assert verdict["auction"] and not is_bargain(verdict)
    assert verdict["max_buy"] == pytest.approx(max_buy(94.96, "ebay"))
    assert verdict["max_buy"] * 1.13 <= 94.96 * 0.8 + 0.01


def test_too_cheap_finds_are_flagged_for_verification():
    assert any("too cheap" in flag for flag in deal(100, 20)["flags"])
    assert not any("too cheap" in flag for flag in deal(100, 65)["flags"])


def test_cracked_slab_value_depends_on_grade_and_clean_claims():
    assert crack_multiplier(9) == 1.0 and crack_multiplier(8) == 0.9 and crack_multiplier(7) == 0.8
    assert crack_multiplier(7, "PSA 7 Charizard 4/102 no whitening") == pytest.approx(0.9)
    # PSA 7 slab at $70 vs raw NM $80: raw is higher, but a cracked 7 sells around $64.
    assert crack_lane("PSA 7 Charizard 4/102 Base Set", 70, 80) is None
    assert crack_lane("PSA 9 Charizard 4/102 Base Set", 70, 80) == "crack"
    # eBay HST can erase a thin crack spread.
    assert crack_lane("PSA 9 Charizard 4/102 Base Set", 400, 460) == "crack"
    assert crack_lane("PSA 9 Charizard 4/102 Base Set", 400, 460, source="ebay") is None


def test_other_graders_japanese_and_multi_slab_titles_are_not_price_checked():
    for title in ("Pokemon Go Mewtwo VSTAR 086/078 AGS Mint+ 9.5 Full Art Holo",
                  "Snorlax VMAX 206/202 PCA Mint+ 9.5 FA Holo Rare",
                  "Zeraora VSTAR 055/159 AGS GEM-MT 10 Holo Rare",
                  "Pikachu AR SV2a Pokemon Card 151 173/165",
                  "Mew 011/025 Celebrations Holo Psa7. &8. &9"):
        assert not eligible(title) and not slab_eligible(title), title
    assert not slab_eligible("Pikachu AR Psa9 SV2a Pokemon Card 151 173/165")
    assert not slab_eligible("PSA 9 Japanese Pikachu 001/100")
    # A card number right after the grade is not a second grade.
    assert slab_eligible("PSA 9 - 4/102 Charizard Base Set")
    assert eligible("Prime Catcher ACE SPEC 157/162 Temporal Forces")
