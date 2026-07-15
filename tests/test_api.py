from __future__ import annotations

import io
import json
from pathlib import Path

from database.models import ApplicationRecord, FollowUp, Job


JOB = {
    "title": "QA Analyst Co-op",
    "company": "Example",
    "location": "Toronto, ON",
    "job_url": "https://example.com/jobs/qa-coop",
    "posting_date": "2026-07-10",
    "description": (
        "Fall 2026 paid co-op. Required:\nPython\nSQL\nAWS\n"
        "Preferred:\nPower BI\nHybrid Toronto. Pay $17.75 per hour."
    ),
}


def _create(client):
    response = client.post("/api/jobs", json=JOB)
    assert response.status_code == 201
    return response.get_json()["job"]


def test_dashboard_shell_renders_supported_workflows(dashboard_client):
    client, _, _ = dashboard_client
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for label in ("Dashboard", "Add job", "Application tracker", "Resume tailor", "Follow-ups", "Contacts", "Analytics", "Settings & profile"):
        assert label in html
    assert "Create reviewed handoff" in html
    assert "Nothing is auto-submitted" in html


def test_end_to_end_package_is_draft_only(dashboard_client):
    client, session_factory, _ = dashboard_client
    job = _create(client)
    assert client.get("/api/health").get_json()["auto_submit"] is False
    assert client.post(f"/api/jobs/{job['id']}/tailor", json={"resume_profile": "qa_testing"}).status_code == 200
    answers = client.post(f"/api/jobs/{job['id']}/answers", json={})
    assert answers.status_code == 200
    assert answers.get_json()["safety_report"]["passed"] is True
    package = client.post(f"/api/jobs/{job['id']}/prepare", json={})
    assert package.status_code == 200
    assert "nothing was submitted" in package.get_json()["message"].lower()
    assert client.post("/api/apply/batch").status_code == 403
    with session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored.applied is False
        assert stored.application_status == "resume_tailored"


def test_mark_applied_requires_confirmation_and_is_idempotent(dashboard_client):
    client, session_factory, _ = dashboard_client
    job = _create(client)
    assert client.patch(f"/api/jobs/{job['id']}", json={"application_status": "interested"}).status_code == 200
    refused = client.patch(f"/api/jobs/{job['id']}", json={"application_status": "applied"})
    assert refused.status_code == 409
    confirmed = client.patch(
        f"/api/jobs/{job['id']}",
        json={"application_status": "applied", "confirm_submission": True, "resume_version_used": "reviewed.tex"},
    )
    assert confirmed.status_code == 200
    assert client.patch(f"/api/jobs/{job['id']}", json={"application_status": "applied"}).status_code == 200
    with session_factory() as session:
        assert session.query(ApplicationRecord).count() == 1
        assert session.query(FollowUp).count() == 1
        assert session.get(Job, job["id"]).resume_version_used == "reviewed.tex"


def test_profile_level_is_enforced_without_losing_private_fields(dashboard_client):
    client, _, _ = dashboard_client
    profile = client.get("/api/profile").get_json()
    profile["skills"].append("Confirmed Private Skill")
    profile["private_note"] = "keep me"
    assert client.put("/api/profile", json=profile).status_code == 200
    saved = client.put("/api/profile", json={"automation_level": 0, "location": "Toronto"})
    assert saved.status_code == 200
    restored = client.get("/api/profile").get_json()
    assert "Confirmed Private Skill" in restored["skills"]
    assert restored["private_note"] == "keep me"
    assert client.post("/api/jobs/parse", json={"description": "Python internship"}).status_code == 403
    manual = client.post("/api/jobs", json={"title": "Manual", "company": "Only", "description": "Track only", "coop_eligible": "false", "salary_min": "not known"})
    assert manual.status_code == 201
    assert manual.get_json()["job"]["fit_category"] == "not_scored"
    assert manual.get_json()["job"]["coop_eligible"] is False
    assert manual.get_json()["job"]["salary_min"] is None
    csv_text = "title,company,description\nLevel Zero,Manual Co,Required: AWS and Terraform\n"
    imported = client.post(
        "/api/import/csv",
        data={"file": (io.BytesIO(csv_text.encode()), "manual.csv")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 200
    imported_job = next(item for item in client.get("/api/jobs").get_json()["jobs"] if item["title"] == "Level Zero")
    assert imported_job["fit_category"] == "not_scored"
    assert client.get(f"/api/jobs/{imported_job['id']}").get_json()["required_skills"] == []


def test_url_and_query_validation_return_client_errors(dashboard_client):
    client, _, _ = dashboard_client
    bad = client.post(
        "/api/jobs",
        json={"title": "Bad", "company": "URL", "description": "Internship", "job_url": "javascript:alert(1)"},
    )
    assert bad.status_code == 400
    assert client.get("/api/jobs?limit=nope").status_code == 400
    assert client.get("/api/jobs?sort=__table__").status_code == 400
    assert client.get("/api/jobs?order=sideways").status_code == 400
    assert client.post("/api/jobs/parse", json={"description": {"not": "text"}}).status_code == 400
    assert client.post("/api/jobs", json={"title": {"not": "text"}, "company": "Example"}).status_code == 400


def test_local_host_and_cross_site_mutation_boundaries(dashboard_client):
    client, _, _ = dashboard_client
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 403
    assert client.get(
        "/api/health", environ_overrides={"REMOTE_ADDR": "203.0.113.10"}
    ).status_code == 403
    assert client.post("/api/seed-demo", headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/seed-demo", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_csv_and_json_backup_preserve_tracker_state(dashboard_client):
    client, _, _ = dashboard_client
    csv_text = (
        "title,company,application_url,status,date_found,description\n"
        "Developer Intern,CSV Co,https://example.com/csv,interested,2026-06-01T10:00:00,Python internship\n"
    )
    imported = client.post(
        "/api/import/csv",
        data={"file": (io.BytesIO(csv_text.encode()), "jobs.csv")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 200
    row = client.get("/api/jobs").get_json()["jobs"][0]
    assert row["application_status"] == "interested"
    assert row["discovered_date"].startswith("2026-06-01")
    backup_response = client.get("/api/export?format=json")
    backup = json.loads(backup_response.data)
    assert backup["schema_version"] == 1
    assert backup["profile"]["name"] == "Mustafa Alp ARI"
    assert backup["jobs"][0]["description"]
    restored = client.post(
        "/api/import/json",
        data={"file": (io.BytesIO(backup_response.data), "backup.json")},
        content_type="multipart/form-data",
    )
    assert restored.status_code == 200
    assert restored.get_json()["skipped_duplicate_jobs"] == 1


def test_draft_edits_are_saved_only_after_claim_check(dashboard_client):
    client, session_factory, _ = dashboard_client
    job = _create(client)
    created = client.post(f"/api/jobs/{job['id']}/answers", json={}).get_json()
    rejected = client.patch(
        f"/api/drafts/{created['draft_id']}",
        json={"content": {"why_role": "I am proficient in MadeUpLang."}, "review_status": "reviewed"},
    )
    assert rejected.status_code == 409
    accepted = client.patch(
        f"/api/drafts/{created['draft_id']}",
        json={"content": {"why_role": "I want to deepen my verified software testing experience."}, "review_status": "reviewed"},
    )
    assert accepted.status_code == 200
    with session_factory() as session:
        from database.models import TailoredDraft
        assert session.get(TailoredDraft, created["draft_id"]).review_status == "reviewed"


def test_level_four_handoff_is_reviewed_and_never_applies(dashboard_client):
    client, session_factory, _ = dashboard_client
    job = _create(client)
    client.put("/api/profile", json={"automation_level": 4})
    prepared = client.post(f"/api/jobs/{job['id']}/prepare", json={})
    assert prepared.status_code == 200
    assert client.post(f"/api/jobs/{job['id']}/handoff", json={}).status_code == 409
    package = prepared.get_json()
    assert client.patch(
        f"/api/drafts/{package['draft_id']}",
        json={"content": {"tailoring": package["tailoring"], "answers": package["answers"]}, "review_status": "reviewed"},
    ).status_code == 200
    handoff = client.post(f"/api/jobs/{job['id']}/handoff", json={"confirm_reviewed": True})
    assert handoff.status_code == 200
    assert handoff.get_json()["application_url"] == JOB["job_url"]
    with session_factory() as session:
        assert session.get(Job, job["id"]).applied is False
        assert session.query(ApplicationRecord).count() == 0


def test_json_backup_embeds_and_restores_safe_latex(dashboard_client):
    client, session_factory, _ = dashboard_client
    job = _create(client)
    tailored = client.post(f"/api/jobs/{job['id']}/tailor", json={"resume_profile": "qa_testing"}).get_json()
    source = Path(tailored["plan"]["latex_path"])
    original = source.read_text(encoding="utf-8")
    backup_response = client.get("/api/export?format=json")
    backup = backup_response.get_json()
    assert backup["drafts"][0]["file_content"] == original
    with session_factory() as session:
        from database.models import TailoredDraft
        session.query(TailoredDraft).delete()
        session.query(Job).delete()
        session.commit()
    restored = client.post(
        "/api/import/json",
        data={"file": (io.BytesIO(backup_response.data), "backup.json")},
        content_type="multipart/form-data",
    )
    assert restored.status_code == 200
    with session_factory() as session:
        from database.models import TailoredDraft
        draft = session.query(TailoredDraft).one()
        assert draft.file_path
        assert Path(draft.file_path).read_text(encoding="utf-8") == original


def test_json_backup_round_trips_legacy_job_fields(dashboard_client):
    client, session_factory, tmp_path = dashboard_client
    job = _create(client)
    expected = {
        "cover_letter": "Reviewed local draft",
        "cover_letter_path": str(tmp_path / "cover-letter.docx"),
        "tailored_resume_path": str(tmp_path / "reviewed-resume.tex"),
        "original_resume_path": str(tmp_path / "base-resume.pdf"),
        "external_url": "https://example.com/portal/application",
    }
    with session_factory() as session:
        stored = session.get(Job, job["id"])
        for field, value in expected.items():
            setattr(stored, field, value)
        stored.external_site = True
        stored.platform = "manual-portal"
        session.commit()
    backup_response = client.get("/api/export?format=json")
    with session_factory() as session:
        session.query(Job).delete()
        session.commit()
    assert client.post(
        "/api/import/json",
        data={"file": (io.BytesIO(backup_response.data), "backup.json")},
        content_type="multipart/form-data",
    ).status_code == 200
    with session_factory() as session:
        restored = session.query(Job).one()
        for field, value in expected.items():
            assert getattr(restored, field) == value
        assert restored.external_site is True
        assert restored.platform == "manual-portal"


def test_json_restore_is_idempotent_for_url_less_jobs_and_history(dashboard_client):
    client, session_factory, _ = dashboard_client
    created = client.post(
        "/api/jobs",
        json={"title": "Data Co-op", "company": "No URL Co", "description": "Paid SQL internship in Toronto"},
    ).get_json()["job"]
    assert client.post(f"/api/jobs/{created['id']}/answers", json={}).status_code == 200
    assert client.patch(f"/api/jobs/{created['id']}", json={"application_status": "interested"}).status_code == 200
    assert client.patch(
        f"/api/jobs/{created['id']}",
        json={"application_status": "applied", "confirm_submission": True},
    ).status_code == 200
    backup_response = client.get("/api/export?format=json")
    with session_factory() as session:
        before = (
            session.query(Job).count(), session.query(FollowUp).count(),
            session.query(ApplicationRecord).count(),
        )
        from database.models import TailoredDraft
        draft_count = session.query(TailoredDraft).count()
    for _ in range(2):
        restored = client.post(
            "/api/import/json",
            data={"file": (io.BytesIO(backup_response.data), "backup.json")},
            content_type="multipart/form-data",
        )
        assert restored.status_code == 200
        assert restored.get_json()["skipped_duplicate_jobs"] == 1
    with session_factory() as session:
        from database.models import TailoredDraft
        assert (
            session.query(Job).count(), session.query(FollowUp).count(),
            session.query(ApplicationRecord).count(), session.query(TailoredDraft).count(),
        ) == (*before, draft_count)


def test_json_false_values_do_not_become_true(dashboard_client):
    client, _, _ = dashboard_client
    backup = {
        "jobs": [{"id": 9, "title": "Manual Job", "company": "Boolean Co", "job_url": "https://example.com/boolean", "applied": "false"}],
        "contacts": [{"id": 8, "name": "Recruiter", "follow_up_needed": "false"}],
    }
    response = client.post("/api/import/json", json=backup)
    assert response.status_code == 200
    job = client.get("/api/jobs").get_json()["jobs"][0]
    assert job["applied"] is False
    contact = client.get("/api/contacts").get_json()["contacts"][0]
    assert contact["follow_up_needed"] is False


def test_json_restore_rechecks_draft_claims_and_review_status(dashboard_client):
    client, session_factory, _ = dashboard_client
    backup = {
        "jobs": [{"id": 4, "title": "Intern", "company": "Restore Co", "job_url": "https://example.com/restore"}],
        "drafts": [{
            "job_id": 4, "draft_type": "application_package", "review_status": "reviewed",
            "content": {"answers": {"why_role": "I am proficient in MadeUpLang."}},
            "safety_report": {"passed": True, "violations": []},
        }],
    }
    assert client.post("/api/import/json", json=backup).status_code == 200
    with session_factory() as session:
        from database.models import TailoredDraft
        draft = session.query(TailoredDraft).one()
        assert draft.review_status == "draft"
        assert json.loads(draft.safety_report)["passed"] is False
