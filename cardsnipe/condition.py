"""Condition checks for raw singles: what the seller claims, warning signs, and condition plays.

Condition arbitrage has two sides:
- A Lightly / Moderately Played card is priced against its own condition's
  TCGplayer market price, not the Near Mint price, so played cards can still be
  real deals.
- A card listed as played (or with no condition) whose title suggests it is
  clean may be Near Mint. Its upside is the Near Mint price minus all-in cost.
  That is a "condition play": worth checking the photos, never assumed.

Everything here reads seller text only. Photos must be checked by a person.
"""

from __future__ import annotations

import re

CONDITIONS = ("NM", "LP", "MP", "HP", "DMG")
TCGPLAYER_NAMES = {"NM": "Near Mint", "LP": "Lightly Played", "MP": "Moderately Played",
                   "HP": "Heavily Played", "DMG": "Damaged"}
LABELS = {"NM": "Near Mint", "LP": "Lightly played", "MP": "Moderately played", "HP": "Heavily played",
          "DMG": "Damaged", None: "Condition unknown"}
# Share of the Near Mint price when TCGplayer has no market price for that condition.
# Unknown condition is valued as Lightly Played until photos show otherwise.
FALLBACK_SHARE = {"NM": 1.0, "LP": 0.85, "MP": 0.7, "HP": 0.5, "DMG": 0.35, None: 0.85}

_HIT_POINTS = re.compile(r"\b\d{2,3}\s*hp\b", re.I)
_NEGATED = re.compile(r"\b(?:not|no|non)[ -]?(?:near[ -]?mint|mint|nm)\b", re.I)
_NO_DAMAGE = re.compile(r"\b(?:no|zero|without|free of)\s+(?:\w+\s+){0,2}?(?:damage|whitening|scratch(?:es)?|wear|"
                        r"crease[s]?|dents?|flaws?|marks?)\b", re.I)
_CLAIMS = (
    ("DMG", re.compile(r"\b(?:damaged?|dmg|poor)\b", re.I)),
    ("HP", re.compile(r"\b(?:heavily[ -]played|heavy[ -]play|hp)\b", re.I)),
    ("MP", re.compile(r"\b(?:moderately[ -]played|moderate[ -]play|mp|very good|vg)\b", re.I)),
    ("LP", re.compile(r"\b(?:lightly[ -]played|light[ -]play|lp|excellent|ex(?:cellent)?[ -]condition|played)\b", re.I)),
    ("NM", re.compile(r"\b(?:near[ -]?mint|nm(?:/m|-?mt)?|mint|pack[ -]fresh|gem)\b", re.I)),
)
RED_FLAGS = re.compile(
    r"\b(?:crease[sd]?|creasing|bent|bend|dents?|dented|water[ -]damage|ink|writing|stain(?:ed|s)?|tears?|torn|"
    r"ripped|scratch(?:ed|es)?|whitening|edge wear|corner wear|wear|scuff(?:ed|s)?|off[ -]?cent(?:er|re)(?:ed)?|"
    r"miscut|curl(?:ed|ing)?|warp(?:ed)?|fade[d]?|binder dings?|dings?)\b", re.I)
CLEAN_HINTS = re.compile(
    r"\b(?:pack[ -]fresh|fresh (?:from|out of) (?:the )?pack|straight (?:from|out of) (?:the )?pack|"
    r"(?:sleeved|toploaded|top[ -]?loaded) (?:right away|immediately|since pulled|after pull)|never played|"
    r"no whitening|no scratches|no wear|no damage|perfect centering|well cent(?:er|re)d|clean|"
    r"psa 10 (?:potential|candidate|ready)|gem candidate|could grade|gradable|10 potential)\b", re.I)


def _clean(text: str) -> str:
    text = _HIT_POINTS.sub(" ", text or "")
    return _NEGATED.sub(" ", text)


def condition_claim(title: str, condition: str = "") -> str | None:
    """Worst condition the seller states ("NM", "LP", ...), or None when they say nothing."""
    text = _clean(f"{condition or ''} {title or ''}")
    text = _NO_DAMAGE.sub(" ", text)
    text = re.sub(r"\bnear mint or better\b", " near mint ", text, flags=re.I)
    text = re.sub(r"\b(?:never|un)[ -]?played\b", " ", text, flags=re.I)
    for claim, pattern in _CLAIMS:
        if pattern.search(text):
            return claim
    return None


def red_flags(title: str, condition: str = "") -> list[str]:
    """Damage words the seller used, ignoring "no whitening" style denials."""
    text = _NO_DAMAGE.sub(" ", _clean(f"{title or ''} {condition or ''}"))
    return sorted({match.group(0).lower() for match in RED_FLAGS.finditer(text)})


def clean_hints(title: str, condition: str = "") -> list[str]:
    return sorted({match.group(0).lower() for match in CLEAN_HINTS.finditer(f"{title or ''} {condition or ''}")})


def condition_value(nm_value: float | None, claim: str | None, checked_value: float | None = None):
    """(value, basis) for the claimed condition: TCGplayer's own price when checked, else a share of NM."""
    if not nm_value:
        return None, None
    if checked_value and claim not in (None, "NM"):
        return checked_value, claim
    share = FALLBACK_SHARE[claim]
    if share == 1.0:
        return nm_value, "NM"
    return round(nm_value * share, 2), f"{claim or 'LP'} est."
