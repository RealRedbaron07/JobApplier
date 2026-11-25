from datetime import datetime

import pytest

from job_os.workflow import business_days_after, can_transition


def test_status_transitions_require_order_and_allow_real_outcomes():
    assert can_transition("discovered", "interested")
    assert can_transition("resume_tailored", "applied")
    assert can_transition("applied", "interview")
    assert can_transition("interview", "offer")
    assert not can_transition("discovered", "offer")
    assert not can_transition("archived", "applied")


def test_negative_business_day_offset_is_rejected():
    with pytest.raises(ValueError):
        business_days_after(datetime(2026, 7, 15), -1)


def test_answers_quote_the_posting_instead_of_a_placeholder():
    from job_os.drafts import company_fact, generate_application_answers

    job = {"company": "Acme", "title": "Dev Intern", "description": "Acme builds tools that help our customers ship faster. You will write tests. Requirements: experience with Rust."}
    assert company_fact(job).startswith("Acme builds tools")
    answers = generate_application_answers(job)
    assert "Before using this" not in answers["cover_letter"] and "Acme builds tools" in answers["why_company"]
    assert "Rust" not in answers["cover_letter"]
    bare = generate_application_answers({"company": "Acme", "title": "Dev", "description": "You will write tests."})
    assert "Before using this draft" in bare["cover_letter"]
