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
