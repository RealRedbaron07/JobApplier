"""Application lifecycle rules and reminder timing."""

from __future__ import annotations

from datetime import datetime, timedelta


STATUSES = [
    "discovered", "interested", "resume_tailored", "applied", "follow_up_needed",
    "interview", "rejected", "offer", "archived",
]

ALLOWED_TRANSITIONS = {
    "discovered": {"interested", "resume_tailored", "archived"},
    "interested": {"resume_tailored", "applied", "archived"},
    "resume_tailored": {"applied", "interested", "archived"},
    "applied": {"follow_up_needed", "interview", "rejected", "offer", "archived"},
    "follow_up_needed": {"applied", "interview", "rejected", "offer", "archived"},
    "interview": {"follow_up_needed", "rejected", "offer", "archived"},
    "rejected": {"archived", "interested"},
    "offer": {"archived"},
    "archived": {"interested"},
}


def can_transition(current: str | None, target: str) -> bool:
    current = current or "discovered"
    return target == current or target in ALLOWED_TRANSITIONS.get(current, set())


def business_days_after(start: datetime, days: int) -> datetime:
    result = start
    remaining = days
    while remaining:
        result += timedelta(days=1)
        if result.weekday() < 5:
            remaining -= 1
    return result


def suggested_follow_up(kind: str, reference: datetime | None = None) -> datetime:
    reference = reference or datetime.now()
    if kind == "recruiter_contact":
        return business_days_after(reference, 4)
    if kind == "application":
        return business_days_after(reference, 8)
    if kind == "interview_thank_you":
        return reference + timedelta(hours=6)
    return business_days_after(reference, 5)
