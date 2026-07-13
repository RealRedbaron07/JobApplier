from job_os.parser import parse_job_description
from job_os.profile import load_profile
from job_os.scoring import score_job


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
