from job_os.parser import parse_job_description
from job_os.profile import load_profile
from job_os.scoring import score_job
from datetime import date


def test_strong_candidate_specific_match_scores_above_senior_role():
    profile = load_profile("/path/that/does/not/exist.json")
    intern = parse_job_description(
        "Paid Summer 2026 software developer internship in Toronto. Required TypeScript, Next.js, Git and manual testing. Fintech team.",
        {"title": "Software Developer Intern", "company": "Example", "location": "Toronto, ON"},
    )
    senior = parse_job_description(
        "Senior platform engineer. 5+ years required. Go, Kubernetes and AWS production operations.",
        {"title": "Senior Platform Engineer", "company": "Example", "location": "California"},
    )
    intern_score = score_job(intern, profile)
    senior_score = score_job(senior, profile)
    assert intern_score["overall_score"] > senior_score["overall_score"]
    assert intern_score["resume_profile"] in {"general_software", "qa_testing", "fintech"}
    assert senior_score["category"] in {"low_priority", "skip", "maybe"}


def test_payment_request_caps_score_and_blocks():
    parsed = parse_job_description("Software internship. Pay a training fee before your interview. Python and React required.", {"title": "Intern", "company": "Suspicious"})
    result = score_job(parsed)
    assert result["overall_score"] <= 15
    assert any(flag["code"] == "payment_request" for flag in result["safety_flags"])


def test_us_only_authorization_and_future_ontario_wage_are_flagged():
    parsed = parse_job_description(
        "Fall 2026 internship. Must be authorized to work in the United States without sponsorship. Pay $17.75 per hour. Python required.",
        {"title": "Software Intern", "company": "US Example", "location": "New York, NY"},
    )
    result = score_job(parsed, as_of=date(2026, 7, 15))
    codes = {flag["code"] for flag in result["safety_flags"]}
    assert "outside_canada_authorization" in codes
    assert "below_minimum_wage" in codes


def test_role_substrings_do_not_turn_retail_into_applied_ai():
    parsed = parse_job_description("Retail operations student position.", {"title": "Retail Operations Intern", "company": "Shop"})
    result = score_job(parsed)
    assert result["resume_profile"] != "applied_ai_automation"
    assert result["overall_score"] < 68
