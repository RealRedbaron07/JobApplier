"""Company career boards are the job source. LinkedIn URLs are rejected."""

from __future__ import annotations

import pytest

from job_os.boards import Board, BoardError, Posting, add_board, classify, fetch_postings


@pytest.mark.parametrize("url,kind,token", [
    ("https://boards.greenhouse.io/shopify", "greenhouse", "shopify"),
    ("https://job-boards.greenhouse.io/embed/job_board?for=stripe", "greenhouse", "stripe"),
    ("https://jobs.lever.co/spotify", "lever", "spotify"),
    ("https://jobs.ashbyhq.com/notion", "ashby", "notion"),
    ("https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers", "workday", "td"),
])
def test_classify_public_boards(url, kind, token):
    board = classify(url)
    assert board.kind == kind and board.token == token
    if kind == "workday":
        assert board.site == "TD_Bank_Careers" and board.host == "td.wd3.myworkdayjobs.com"


def test_linkedin_is_rejected():
    with pytest.raises(BoardError, match="LinkedIn"):
        classify("https://www.linkedin.com/jobs/view/123")


def test_fetch_greenhouse_and_workday(monkeypatch):
    class Resp:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

        def raise_for_status(self):
            return None

    seen = {}

    def fake_get(self, url, params=None, timeout=0):
        seen["get"] = url
        return Resp({"jobs": [{"title": "Intern", "absolute_url": "https://boards.greenhouse.io/x/jobs/1",
                                "location": {"name": "Toronto"}, "content": "<p>Python</p>", "updated_at": "2026-10-01T00:00:00Z"}]})

    def fake_post(self, url, json=None, timeout=0):
        seen["post"] = url
        return Resp({"jobPostings": [{"title": "Co-op", "externalPath": "/job/Co-op_R1", "locationsText": "Toronto"}]})

    monkeypatch.setattr("requests.Session.get", fake_get)
    monkeypatch.setattr("requests.Session.post", fake_post)
    gh = fetch_postings(classify("https://boards.greenhouse.io/shopify"))
    assert gh[0].title == "Intern" and "Python" in gh[0].description and gh[0].platform == "greenhouse"
    wd = fetch_postings(Board("td", "https://td.wd3.myworkdayjobs.com/TD_Bank_Careers", "workday", "td",
                              host="td.wd3.myworkdayjobs.com", site="TD_Bank_Careers"))
    assert wd[0].job_url.endswith("/job/Co-op_R1") and wd[0].platform == "workday"
    assert "boards-api.greenhouse.io" in seen["get"] and "/wday/cxs/td/TD_Bank_Careers/jobs" in seen["post"]


def test_board_refresh_adds_company_postings_once(dashboard_client, monkeypatch, tmp_path):
    from config import Config

    monkeypatch.setattr(Config, "EXTERNAL_ACCESS_ENABLED", True)
    client, _, _ = dashboard_client
    monkeypatch.setenv("COMPANY_BOARDS_PATH", str(tmp_path / "boards.json"))
    added = add_board(str(tmp_path / "boards.json"), "https://jobs.lever.co/spotify", name="Spotify")
    assert added.kind == "lever"

    def fake_fetch(board, session=None, limit=50):
        return [Posting("Data Intern", "Spotify", "Toronto", "https://jobs.lever.co/spotify/abc",
                        "Fall 2026 internship. Required: Python, SQL.", "2026-10-01", "lever")]

    monkeypatch.setattr("job_os.boards.fetch_postings", fake_fetch)
    first = client.post("/api/boards/refresh")
    assert first.status_code == 200 and first.get_json()["added"] == 1
    second = client.post("/api/boards/refresh")
    assert second.get_json()["added"] == 0 and second.get_json()["skipped"] == 1
    jobs = client.get("/api/jobs").get_json()["jobs"]
    assert jobs[0]["source"] == "company_site" and jobs[0]["title"] == "Data Intern"
    assert client.post("/api/boards", json={"url": "https://www.linkedin.com/jobs/search"}).status_code == 400
