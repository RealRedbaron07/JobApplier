"""Local application-funnel analytics."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


def summarize_jobs(jobs: Iterable[Any], application_records: Iterable[Any] | None = None) -> dict:
    rows = list(jobs)
    records = list(application_records or [])
    row_keys = {getattr(job, "id", None) or id(job): job for job in rows}
    statuses = Counter((getattr(job, "application_status", None) or "discovered") for job in rows)
    applied_rows = [
        job for job in rows
        if bool(getattr(job, "applied", False))
        or getattr(job, "applied_date", None)
        or (getattr(job, "application_status", None) in ("applied", "follow_up_needed", "interview", "rejected", "offer"))
    ]
    applied_keys = {getattr(job, "id", None) or id(job) for job in applied_rows}
    interview_keys = {
        getattr(job, "id", None) or id(job) for job in rows
        if (getattr(job, "application_status", None) in ("interview", "offer"))
    }
    rejected_keys = {
        getattr(job, "id", None) or id(job) for job in rows
        if getattr(job, "application_status", None) == "rejected"
    }
    offer_keys = {
        getattr(job, "id", None) or id(job) for job in rows
        if getattr(job, "application_status", None) == "offer"
    }
    for record in records:
        key = getattr(record, "job_id", None)
        if key not in row_keys:
            continue
        status = getattr(record, "application_status", None)
        if status in ("applied", "follow_up_needed", "interview", "rejected", "offer"):
            applied_keys.add(key)
        if status in ("interview", "offer"):
            interview_keys.add(key)
        if status == "rejected":
            rejected_keys.add(key)
        if status == "offer":
            offer_keys.add(key)
    applied_count = len(applied_keys)
    interviews = len(interview_keys)
    responses = len(interview_keys | rejected_keys | offer_keys)
    sources = Counter((getattr(job, "source", None) or getattr(job, "platform", None) or "manual") for job in applied_rows)
    roles = Counter((getattr(job, "resume_profile", None) or "unclassified") for job in applied_rows)
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
        applied = getattr(job, "applied_date", None)
        if applied:
            weekly[applied.strftime("%Y-W%W")] += 1
        status = getattr(job, "application_status", None) or "discovered"
        if status in ("applied", "follow_up_needed") and applied:
            aware = applied if applied.tzinfo else applied.replace(tzinfo=timezone.utc)
            stale += int(aware < now - timedelta(days=14))
        deadline = getattr(job, "deadline", None)
        if deadline and status not in ("applied", "interview", "rejected", "offer", "archived"):
            aware_deadline = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
            upcoming += int(now <= aware_deadline <= now + timedelta(days=14))
    return {
        "totals": {"jobs": len(rows), "applied": applied_count, "responses": responses, "interviews": interviews, "offers": len(offer_keys), "rejected": len(rejected_keys)},
        "rates": {
            "response_rate": round(100 * responses / applied_count, 1) if applied_count else 0,
            "interview_rate": round(100 * interviews / applied_count, 1) if applied_count else 0,
            "rejection_rate": round(100 * len(rejected_keys) / applied_count, 1) if applied_count else 0,
        },
        "funnel": [
            {"status": "discovered", "count": len(rows)},
            {"status": "interested", "count": sum(statuses[name] for name in ("interested", "resume_tailored")) + applied_count},
            {"status": "resume_tailored", "count": statuses["resume_tailored"] + applied_count},
            {"status": "applied", "count": applied_count},
            {"status": "interview", "count": interviews},
            {"status": "offer", "count": len(offer_keys)},
        ],
        "applications_per_week": sorted(weekly.items()),
        "best_sources": sources.most_common(6),
        "best_role_categories": roles.most_common(7),
        "top_missing_skills": missing.most_common(10),
        "companies": len({getattr(job, "company", "") for job in rows if getattr(job, "company", "")}),
        "companies_applied": len({getattr(job, "company", "") for job in applied_rows if getattr(job, "company", "")}),
        "stale_applications": stale,
        "upcoming_deadlines": upcoming,
    }
