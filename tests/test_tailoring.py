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
