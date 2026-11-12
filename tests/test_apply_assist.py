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
    assert "Submit yourself" in FILL_SCRIPT


def test_fill_refuses_when_stop_before_submit_is_off(monkeypatch, tmp_path):
    from config import Config
    import pytest

    monkeypatch.setattr(Config, "STOP_BEFORE_SUBMIT", False)
    with pytest.raises(RuntimeError):
        apply_assist.fill_application("https://example.com", str(tmp_path / "r.pdf"), {})
