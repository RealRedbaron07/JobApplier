from job_os.workflow import can_transition


def test_status_transitions_require_order_and_allow_real_outcomes():
    assert can_transition("discovered", "interested")
    assert can_transition("resume_tailored", "applied")
    assert can_transition("applied", "interview")
    assert can_transition("interview", "offer")
    assert not can_transition("discovered", "offer")
    assert not can_transition("archived", "applied")
