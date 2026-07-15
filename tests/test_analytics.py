from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from job_os.analytics import summarize_jobs


def test_applications_per_week_and_staleness_use_applied_date():
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(
        id=1,
        company="Example",
        source="company_site",
        platform=None,
        resume_profile="qa_testing",
        application_status="applied",
        applied=True,
        applied_date=now - timedelta(days=15),
        discovered_date=now - timedelta(days=80),
        deadline=None,
        match_explanation="{}",
    )
    summary = summarize_jobs([job])
    assert summary["applications_per_week"] == [(job.applied_date.strftime("%Y-W%W"), 1)]
    assert summary["stale_applications"] == 1
    assert summary["companies_applied"] == 1
