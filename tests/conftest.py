from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config import Config
from database.models import Base


@pytest.fixture
def dashboard_client(tmp_path, monkeypatch):
    import dashboard.app as dashboard_app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    isolated_session = sessionmaker(bind=engine)
    monkeypatch.setattr(dashboard_app, "Session", isolated_session)
    monkeypatch.setattr(Config, "PROFILE_PATH", str(tmp_path / "candidate_profile.json"))
    monkeypatch.setattr(Config, "DRAFTS_DIR", str(tmp_path / "drafts"))
    dashboard_app.app.config.update(TESTING=True)
    yield dashboard_app.app.test_client(), isolated_session, tmp_path
    engine.dispose()
