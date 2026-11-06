from cardsnipe import discovery
from cardsnipe.slabs import crack_lane, raw_title, slab_eligible, slab_grade, slab_notes


def test_mid_grade_slabs_are_checked_and_tens_and_raw_promises_are_not():
    assert slab_grade("PSA 9 Charizard 4/102 Base Set") == ("PSA", 9.0)
    assert slab_eligible("BGS 8.5 Umbreon VMAX 215/203 Evolving Skies")
    assert slab_eligible("TAG 9 (945) Pikachu 58/102 Base Set")
    assert slab_eligible("CGC 9.5 Gengar 094/165 151")
    for title in ("PSA 10 Mew 151/165", "Pikachu 58/102 Base Set PSA 10 ready", "PSA 6 Charizard 4/102",
                  "PSA 9 Japanese Pikachu 001/100", "PSA 9 Charizard Base Set", "ACE 9 Pikachu 58/102"):
        assert not slab_eligible(title), title


def test_raw_title_strips_grading_words_for_raw_card_matching():
    assert raw_title("TAG 9 (945) Pikachu 58/102 Base Set Gem Mint graded slab") == "Pikachu 58/102 Base Set"
    assert raw_title("PSA 8 Charizard 4/102 Base Set") == "Charizard 4/102 Base Set"


def test_crack_when_raw_beats_slab_and_regrade_watch_only_for_upside_grades():
    assert crack_lane("PSA 9 Charizard 4/102 Base Set", 400, 500) == "crack"
    assert crack_lane("PSA 9 Charizard 4/102 Base Set", 520, 500) is None
    assert crack_lane("BGS 8.5 Umbreon VMAX 215/203 Evolving Skies", 540, 500) == "regrade"
    assert crack_lane("BGS 8 Umbreon VMAX 215/203 Evolving Skies", 540, 500) is None
    assert crack_lane("CGC 9 Gengar 094/165 151", 600, 500) is None
    assert crack_lane("PSA 9 Charizard 4/102 Base Set", 400, None) is None


def test_seller_hints_and_tag_scores_are_surfaced():
    assert slab_notes("TAG 9 (945) Pikachu 58/102 no whitening") == ["no whitening", "TAG score 945"]


def test_price_checks_interleave_slabs_with_raw_singles_and_look_up_the_raw_card(monkeypatch):
    titles = ["PSA 9 Charizard 4/102 Base Set", "Pikachu 58/102 Base Set", "BGS 8.5 Mew 151/165 151"]
    assert discovery.pick_candidates(titles, str) == [titles[0], titles[1], titles[2]]
    seen = []
    monkeypatch.setattr(discovery, "tcgplayer_market", lambda browser, title: seen.append(title) or {"price": 1})
    _, label = discovery.price_listing(None, titles[0])
    assert seen == ["Charizard 4/102 Base Set"] and "crack" in label
