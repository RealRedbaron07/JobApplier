from job_os.parser import parse_job_description
from job_os.profile import load_profile
from job_os.scoring import score_job
from job_os.tailoring import create_tailoring_plan, validate_draft


def test_tailoring_never_promotes_unknown_skill():
    profile = load_profile("/missing/profile.json")
    job = parse_job_description("AI internship requiring Python, AWS and Kubernetes.", {"title": "Applied AI Intern", "company": "Example"})
    score = score_job(job, profile)
    plan = create_tailoring_plan(job, score, profile)
    assert "AWS" in plan["keyword_gaps"]
    assert "AWS" not in plan["skills_to_move_higher"]
    assert "Kubernetes" not in plan["skills_to_move_higher"]
    assert plan["safety_report"]["passed"] is True


def test_claim_guard_rejects_malparibot_overclaim():
    report = validate_draft("Deployed profitable live trading with real-money broker orders.")
    assert report["passed"] is False
    assert {item["code"] for item in report["violations"]} >= {"live_trading", "profitability"}


def test_claim_guard_rejects_unknown_skills_gpa_and_graduation():
    report = validate_draft("I am an expert in AWS, Kubernetes, Go, and Rust. GPA: 3.5. Expected graduation May 2028.")
    codes = {item["code"] for item in report["violations"]}
    assert {"unsupported_skill", "unsupported_gpa", "graduation_mismatch"}.issubset(codes)


def test_claim_guard_rejects_unknown_skill_outside_parser_catalog():
    report = validate_draft("I am proficient in MadeUpLang.")
    assert report["passed"] is False
    assert any(item["code"] == "unsupported_skill" for item in report["violations"])


def test_generated_facts_follow_profile_customization():
    from job_os.drafts import generate_application_answers

    profile = load_profile("/missing/profile.json")
    profile["work_authorization"] = "Custom verified authorization statement"
    profile["graduation"] = "December 2030"
    profile["education"] = [{"institution": "Verified University", "degree": "Verified Degree", "minor": "Verified Minor"}]
    answers = generate_application_answers({"title": "Intern", "company": "Example"}, profile)
    assert answers["work_authorization"] == "Custom verified authorization statement"
    plan = create_tailoring_plan({"title": "Intern", "company": "Example", "required_skills": []}, {"matched_skills": [], "missing_skills": [], "resume_profile": "general_software", "project_to_emphasize": "JobApplier"}, profile)
    assert "Verified University" in plan["latex"]
    assert "December 2030" in plan["latex"]
    assert "currently configured value is December 2030" in plan["base_resume_warning"]


def test_resume_drafts_are_versioned(tmp_path):
    from job_os.tailoring import save_latex_draft

    first = save_latex_draft(7, "first", str(tmp_path))
    second = save_latex_draft(7, "second", str(tmp_path))
    assert first != second


def test_latex_drafts_reject_file_and_shell_commands(tmp_path):
    from job_os.tailoring import save_latex_draft
    import pytest

    with pytest.raises(ValueError):
        save_latex_draft(7, r"\immediate\write18{touch /tmp/unsafe}", str(tmp_path))
