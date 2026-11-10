"""Crack-and-regrade checks for graded slabs found by broad scans.

A mid-grade slab (PSA 7-9, BGS 8-9.5, CGC/TAG/SGC 7-9.5) sometimes sells for
less than a raw copy of the same card. Cracking it out and selling raw, or
resubmitting a clean copy, can then pay off. A cracked card sells in about its
grade's condition, so a PSA 7 is valued below a Near Mint raw copy (see
cardsnipe.deals). This module only decides which slabs to check and how to
describe the result; it never buys anything.
"""

from __future__ import annotations

import re

from cardsnipe.bargains import identifiable, JAPANESE, MULTI_GRADE, NUMBER, OTHER_SLAB, VARIANT
from cardsnipe.deals import assess
from cardsnipe.matcher import GRADE_RE, detect_clean_hints, detect_condition_issue, detect_grade, detect_tag_score

# Grade ranges worth checking per grading company. 10s are excluded: they are
# priced as 10s, never below raw.
GRADE_RANGES = {"PSA": (7.0, 9.0), "BGS": (8.0, 9.5), "CGC": (7.0, 9.5), "TAG": (7.0, 9.5), "SGC": (7.0, 9.5)}

LANGUAGE_OR_PRODUCT = re.compile(
    r"\b(?:sealed|booster|etb|box|pack|lot|bundle|jumbo|oversized|proxy|fake|metal|reprint|custom|"
    r"korean|chinese|german|french|spanish|italian|world championship)\b", re.I)
SLAB_WORDS = re.compile(r"\b(?:graded|slab(?:bed)?|gem\s*mint|mint|pristine|cert(?:ified)?|beckett|authentic)\b", re.I)
COMPANY_WORDS = re.compile(r"\b(?:psa|bgs|cgc|tag|sgc)\b", re.I)


def slab_grade(title: str):
    """(company, grade) when the title is a slab worth a crack check, else None."""
    grade = detect_grade(title or "")
    if not grade:
        return None
    company, value = grade
    low, high = GRADE_RANGES.get(company, (None, None))
    if low is None or not low <= value <= high:
        return None
    return company, value


def slab_eligible(title: str) -> bool:
    title = title or ""
    return (slab_grade(title) is not None and identifiable(raw_title(title))
            and not LANGUAGE_OR_PRODUCT.search(title) and not JAPANESE.search(title)
            and not MULTI_GRADE.search(title) and not OTHER_SLAB.search(title)
            and not VARIANT.search(title) and not detect_condition_issue(title))


def raw_title(title: str) -> str:
    """The seller title with grading words removed, so raw-card matching can run on it."""
    text = GRADE_RE.sub(" ", title or "")
    text = SLAB_WORDS.sub(" ", text)
    text = COMPANY_WORDS.sub(" ", text)
    text = re.sub(r"\(\s*\d{3,4}\s*\)|\b\d{3,4}\s*/\s*1000\b", " ", text)  # TAG point scores
    return re.sub(r"\s+", " ", text).strip()


def crack_lane(title: str, slab_total: float | None, raw_value: float | None, source: str = "facebook",
               listing_type: str = "bin"):
    """'crack' when the cracked-out card is worth clearly more than the slab's all-in cost,
    'regrade' for a high BGS/CGC/TAG/SGC grade priced near raw, else None."""
    grade = slab_grade(title)
    if not grade or slab_total is None or not raw_value:
        return None
    return assess(title=title, source=source, listing_type=listing_type, price=slab_total, shipping=0,
                  total_price=slab_total, value=raw_value, slab=grade)["lane"]


def slab_notes(title: str) -> list[str]:
    """Seller hints that matter for a crack decision ("no whitening", TAG score)."""
    notes = [hint for hint in detect_clean_hints(title or "") if hint not in {"mint", "gem"}]
    score = detect_tag_score(title or "")
    if score:
        notes.append(f"TAG score {score}")
    return notes
