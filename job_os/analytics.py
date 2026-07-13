"""Local application-funnel analytics."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


def summarize_jobs(jobs: Iterable[Any]) -> dict:
    rows = list(jobs)
    statuses = Counter((getattr(job, "application_status", None) or "discovered") for job in rows)
    applied_count = sum(statuses[name] for name in ("applied", "follow_up_needed", "interview", "rejected", "offer"))
    interviews = statuses["interview"] + statuses["offer"]
    responses = interviews + statuses["rejected"]
    sources = Counter((getattr(job, "source", None) or getattr(job, "platform", None) or "manual") for job in rows)
    roles = Counter((getattr(job, "resume_profile", None) or "unclassified") for job in rows)
    missing = Counter()
    weekly = defaultdict(int)
    now = datetime.now(timezone.utc)
    stale = 0
    upcoming = 0
    for job in rows:
        try:
            explanation = getattr(job, "match_explanation", None) or "{}"
            import json
            missing.update(json.loads(explanation).get("missing_skills", []))
        except (ValueError, TypeError):
            pass
        found = getattr(job, "discovered_date", None)
        if found:
            weekly[found.strftime("%Y-W%W")] += 1
        status = getattr(job, "application_status", None) or "discovered"
        if status in ("applied", "follow_up_needed") and found:
            aware = found if found.tzinfo else found.replace(tzinfo=timezone.utc)
            stale += int(aware < now - timedelta(days=14))
        deadline = getattr(job, "deadline", None)
        if deadline:
            aware_deadline = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
            upcoming += int(now <= aware_deadline <= now + timedelta(days=14))
    return {
        "totals": {"jobs": len(rows), "applied": applied_count, "responses": responses, "interviews": interviews, "offers": statuses["offer"], "rejected": statuses["rejected"]},
        "rates": {
            "response_rate": round(100 * responses / applied_count, 1) if applied_count else 0,
            "interview_rate": round(100 * interviews / applied_count, 1) if applied_count else 0,
            "rejection_rate": round(100 * statuses["rejected"] / applied_count, 1) if applied_count else 0,
        },
        "funnel": [{"status": status, "count": statuses[status]} for status in ("discovered", "interested", "resume_tailored", "applied", "follow_up_needed", "interview", "offer")],
        "applications_per_week": sorted(weekly.items()),
        "best_sources": sources.most_common(6),
        "best_role_categories": roles.most_common(7),
        "top_missing_skills": missing.most_common(10),
        "companies": len({getattr(job, "company", "") for job in rows if getattr(job, "company", "")}),
        "stale_applications": stale,
        "upcoming_deadlines": upcoming,
    }
