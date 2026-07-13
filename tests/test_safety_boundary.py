from config import Config


def test_submission_cannot_be_enabled_by_environment():
    assert Config.AUTO_MODE is False
    assert Config.AUTO_APPLY_ENABLED is False
    assert Config.STOP_BEFORE_SUBMIT is True
    assert Config.AUTOMATION_LEVEL <= 4
