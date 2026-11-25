import re

from job_os import apply_assist
from job_os.apply_assist import FILL_SCRIPT, RESUME_INPUT_SCRIPT, application_url, detect_ats, field_values
from job_os.profile import load_profile


def test_ats_detection_and_direct_form_urls():
    lever = "https://jobs.lever.co/wattpad/0f5b4c1e-1111-2222-3333-444455556666"
    ashby = "https://jobs.ashbyhq.com/cohere/0f5b4c1e-1111-2222-3333-444455556666"
    assert detect_ats(lever) == "lever" and application_url(lever) == lever + "/apply"
    assert detect_ats(ashby) == "ashby" and application_url(ashby) == ashby + "/application"
    assert detect_ats("https://td.wd3.myworkdayjobs.com/TD_Bank_Careers/job/x") == "workday"
    assert detect_ats("https://job-boards.greenhouse.io/faire/jobs/123") == "greenhouse"
    assert detect_ats("https://evilgreenhouse.io.example.com/x") == "generic"


def test_field_values_come_from_profile():
    profile = load_profile("/missing/profile.json")
    values = field_values(profile, {"cover_letter": "Hello"})
    assert values["first_name"] == "Mustafa" and values["last_name"] == "ARI"
    assert values["work_authorized"] == "Yes" and values["sponsorship"] == "No"
    assert values["school"] == "York University" and values["graduation_year"] == "2029"
    assert values["cover_letter"] == "Hello"


def test_unclear_authorization_is_left_blank():
    profile = load_profile("/missing/profile.json")
    profile["work_authorization"] = "Ask me"
    values = field_values(profile)
    assert values["work_authorized"] == "" and values["sponsorship"] == ""


def test_page_scripts_never_submit_or_press_buttons():
    for script in (FILL_SCRIPT, RESUME_INPUT_SCRIPT):
        assert not re.search(r"\.submit\(|requestSubmit|button[^'\"]*\.click|form\.", script)
    # Checkboxes (consent, terms) are skipped outright.
    assert "'checkbox'" in FILL_SCRIPT
    assert "Submit yourself" in apply_assist.BANNER_SCRIPT


def test_fill_refuses_when_stop_before_submit_is_off(monkeypatch, tmp_path):
    from config import Config
    import pytest

    monkeypatch.setattr(Config, "STOP_BEFORE_SUBMIT", False)
    with pytest.raises(RuntimeError):
        apply_assist.fill_application("https://example.com", str(tmp_path / "r.pdf"), {})


def test_screening_answers_come_from_profile_and_job():
    profile = load_profile("/missing/profile.json")
    values = field_values(profile, {"why_company": "Because", "availability": "Summer 2027"}, {"company": "Shopify"})
    assert values["relocate"] == "Yes" and values["student"] == "Yes"
    assert values["previously_employed"] == "No" and values["why_company"] == "Because"
    # A company on the resume is never answered "No" for previous employment.
    assert field_values(profile, {}, {"company": "Venture for Canada"})["previously_employed"] == ""
    assert field_values(profile)["previously_employed"] == ""


def test_dropdown_step_only_reads_options():
    assert not re.search(r"\.submit\(|requestSubmit|\.click\(", apply_assist.COMBO_OPTIONS_SCRIPT)
    assert "[role=option]" in apply_assist.COMBO_OPTIONS_SCRIPT


def test_current_company_comes_from_the_job_marked_present():
    values = field_values(load_profile("/missing/profile.json"))
    assert values["current_company"] == "M4 & Aging Lab, York University"
    assert values["current_title"] == "Research Assistant"


def test_embedded_form_is_followed_only_by_host_and_only_without_a_form_of_its_own():
    # A Google sign-in helper iframe carries "greenhouse.io" in its query string; it must not be followed.
    assert "new URL(frame.src" in apply_assist.IFRAME_SCRIPT and ".hostname" in apply_assist.IFRAME_SCRIPT
    assert "own >= 3" in apply_assist.IFRAME_SCRIPT


def test_hidden_validation_inputs_are_not_visible_to_the_filler():
    assert "opacity" in FILL_SCRIPT and "r.width > 2" in FILL_SCRIPT
