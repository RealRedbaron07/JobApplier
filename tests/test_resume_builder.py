from job_os.parser import parse_job_description
from job_os.profile import load_profile
from job_os.resume_builder import build_tailored_resume, render_html, tailor_resume, trim_one_bullet


def _bullets(profile):
    resume = profile["resume"]
    return {b for section in ("experience", "projects", "leadership") for entry in resume[section] for b in entry["bullets"]}


def _job(text, title):
    return parse_job_description(text, {"title": title, "company": "Example"})


def test_tailored_resume_uses_only_resume_lines_and_keeps_roles_chronological():
    profile = load_profile("/missing/profile.json")
    tailored = tailor_resume(_job("Required: React, TypeScript, CSS. Build frontend UI components.", "Frontend Developer Intern"), profile)
    used = {b for section in ("experience", "projects", "leadership") for entry in tailored[section] for b in entry["bullets"]}
    assert used == _bullets(profile)
    assert [e["dates"] for e in tailored["experience"]] == [e["dates"] for e in profile["resume"]["experience"]]


def test_bullets_and_projects_follow_the_posting():
    profile = load_profile("/missing/profile.json")
    frontend = tailor_resume(_job("Required: React, TypeScript. Frontend navigation and UI.", "Frontend Developer Intern"), profile)
    level_up = next(e for e in frontend["experience"] if e["title"].startswith("Software Developer Intern /"))
    assert "navigation" in level_up["bullets"][0]
    ml = tailor_resume(_job("Machine learning co-op. Required: Python, PyTorch. Train models on data.", "ML Engineer Co-op"), profile)
    assert ml["projects"][0]["name"] == "MalpariBot"
    realtime = tailor_resume(_job("Real-time systems intern. Required: FastAPI, WebSockets. Low latency streaming.", "Backend Intern"), profile)
    assert realtime["projects"][0]["name"] == "Lightning Response"


def test_missing_skills_are_reported_not_added():
    profile = load_profile("/missing/profile.json")
    tailored = tailor_resume(_job("Required: Python, AWS, Kubernetes, SQL.", "Data Intern"), profile)
    listed = {item for group in tailored["skill_groups"] for item in group["items"]}
    assert "AWS" not in listed and "Kubernetes" not in listed
    assert {"AWS", "Kubernetes"} <= set(tailored["report"]["gaps_not_claimed"])
    assert "SQL" in listed and "SQL" in tailored["report"]["skills_added_from_profile"]


def test_practice_skills_are_never_listed_as_tools():
    profile = load_profile("/missing/profile.json")
    tailored = tailor_resume(_job("Required: Machine Learning, Software Testing, Python.", "ML Intern"), profile)
    listed = {item for group in tailored["skill_groups"] for item in group["items"]}
    assert "Machine Learning" not in listed and "Software Testing" not in listed


def test_render_keeps_bold_and_escapes_text():
    profile = load_profile("/missing/profile.json")
    tailored = tailor_resume(_job("Python", "Intern"), profile)
    page = render_html(tailored)
    assert "<b>Best Accessibility Hack</b>" in page
    assert "M4 &amp; Aging Lab" in page and "**" not in page


def test_build_trims_until_one_page(tmp_path):
    profile = load_profile("/missing/profile.json")
    calls = []

    def renderer(path):
        calls.append(path)
        return b"%PDF"

    import job_os.resume_builder as builder

    pages = iter([2, 2, 2, 1])
    original = builder.pdf_page_count
    builder.pdf_page_count = lambda data: next(pages)
    try:
        built = build_tailored_resume(5, _job("Python", "Intern"), profile, str(tmp_path), renderer)
    finally:
        builder.pdf_page_count = original
    assert built["pages"] == 1
    assert len(built["report"]["trimmed_bullets"]) == 2
    assert built["pdf_path"].endswith("Mustafa_Alp_ARI_Resume.pdf")
    assert len(calls) == 4


def test_trim_stops_when_every_entry_has_one_bullet():
    profile = load_profile("/missing/profile.json")
    tailored = tailor_resume(_job("Python", "Intern"), profile)
    while trim_one_bullet(tailored):
        pass
    assert all(len(e["bullets"]) == 1 for s in ("experience", "projects", "leadership") for e in tailored[s])
