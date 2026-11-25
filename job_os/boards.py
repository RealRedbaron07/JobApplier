"""Read public company career boards. LinkedIn is not a source: its posts go stale.

Supported public list endpoints (no login, no application, no form fill):
  Greenhouse  https://boards.greenhouse.io/{token}  or job-boards.greenhouse.io/{token}
  Lever       https://jobs.lever.co/{token}
  Ashby       https://jobs.ashbyhq.com/{token}
  Workday     https://{tenant}.wdN.myworkdayjobs.com/{site}
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
from urllib.parse import urlparse

import requests

UA = "JobApplier/1.0 (local career-board reader; +https://github.com/RealRedbaron07/JobApplier)"

# Workday boards hold hundreds of jobs; search them with early-career terms instead of paging everything.
WORKDAY_SEARCH_TERMS = ("intern", "co-op", "student", "new grad", "developer", "data analyst")
WORKDAY_PAGE = 20
MAX_AGE_DAYS = 14

EARLY_CAREER = re.compile(r"\b(?:intern(?:ship)?s?|co-?op|student|new\s+grad(?:uate)?|graduate|junior|jr\.?|entry[- ]level|"
                          r"summer\s+\d{4}|winter\s+\d{4}|fall\s+\d{4}|analyst\s+i\b|developer\s+i\b|scientist\s+i\b|engineer\s+i\b)\b", re.I)
# Branch, sales and advisory roles crowd bank boards but are not tech/early-career targets.
NON_TARGET = re.compile(r"\b(?:personal\s+banking|mortgage|client\s+associate|branch|teller|financial\s+(?:advisor|adviser|planner)|"
                        r"insurance\s+advisor|wealth\s+advisor|sales|relationship\s+manager|account\s+manager|registered)\b", re.I)
SENIOR_TITLE = re.compile(r"\b(?:senior|sr\.?|staff|principal|lead|director|manager|head|vp|vice\s+president|chief)\b", re.I)
ROLE_WORDS = re.compile(r"\b(?:developer|engineer(?:ing)?|software|programmer|data|analyst|analytics|qa|quality|test(?:ing|er)?|"
                        r"web|front[- ]?end|back[- ]?end|full[- ]?stack|ai|machine\s+learning|ml|automation|technical|technology|"
                        r"it|bi|reporting|cloud|devops|security|cyber|product)\b", re.I)
SENIOR = re.compile(r"\b(?:senior|sr\.?|staff|principal|lead|manager|director|head|vp|vice\s+president|chief|architect|"
                    r"advisor|adviser|specialist|consultant\s+ii+|ii+|iv)\b", re.I)

# Public boards checked when no board list has been saved yet. Remove any you do not want.
STARTER_BOARDS = (
    ("TD", "https://td.wd3.myworkdayjobs.com/TD_Bank_Careers"),
    ("RBC", "https://rbc.wd3.myworkdayjobs.com/RBCGLOBAL1"),
    ("BMO", "https://bmo.wd3.myworkdayjobs.com/External"),
    ("CIBC", "https://cibc.wd3.myworkdayjobs.com/search"),
    ("Manulife", "https://manulife.wd3.myworkdayjobs.com/MFCJH_Jobs"),
    ("Sun Life", "https://sunlife.wd3.myworkdayjobs.com/Experienced-Jobs"),
    ("Wealthsimple", "https://jobs.ashbyhq.com/wealthsimple"),
    ("Cohere", "https://jobs.ashbyhq.com/cohere"),
    ("1Password", "https://jobs.ashbyhq.com/1password"),
    ("Benevity", "https://jobs.ashbyhq.com/benevity"),
    ("KOHO", "https://jobs.ashbyhq.com/koho"),
    ("Faire", "https://boards.greenhouse.io/faire"),
    ("Wattpad", "https://jobs.lever.co/wattpad"),
)


class BoardError(ValueError):
    pass


@dataclass
class Board:
    name: str
    url: str
    kind: str
    token: str
    host: str = ""
    site: str = ""


@dataclass
class Posting:
    title: str
    company: str
    location: str
    job_url: str
    description: str
    posted_date: str | None
    platform: str


def _strip_html(html: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", html or "")
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"[^\S\n]+", " ", unescape(text))).strip()


def classify(url: str) -> Board:
    """Turn a career-page URL into a board. Rejects LinkedIn and unknown hosts."""
    raw = (url or "").strip()
    if not raw:
        raise BoardError("Paste the company's career board URL.")
    if not raw.startswith("http"):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]
    if "linkedin.com" in host:
        raise BoardError("LinkedIn listings go stale. Add the company's own career site (Workday, Greenhouse, Lever, or Ashby).")
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io"} and parts:
        token = parts[-1] if parts[0] != "embed" else ""
        if parts[:2] == ["embed", "job_board"]:
            token = ""
        if "for=" in (parsed.query or ""):
            token = dict(p.split("=", 1) for p in parsed.query.split("&") if "=" in p).get("for", "")
        if not token or token in {"embed", "job_board"}:
            raise BoardError("Could not read the Greenhouse board name from that URL.")
        return Board(name=token, url=raw, kind="greenhouse", token=token)
    if host == "jobs.lever.co" and parts:
        return Board(name=parts[0], url=raw, kind="lever", token=parts[0])
    if host == "jobs.ashbyhq.com" and parts:
        return Board(name=parts[0], url=raw, kind="ashby", token=parts[0])
    wd = re.match(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", host)
    if wd and parts:
        locales = {"en-us", "en-ca", "fr-ca", "en-gb"}
        site_parts = [p for p in parts if p.lower() not in locales]
        if not site_parts:
            raise BoardError("Could not read the Workday site name from that URL.")
        return Board(name=wd.group(1), url=raw, kind="workday", token=wd.group(1), host=host, site=site_parts[-1])
    raise BoardError("Use a Greenhouse, Lever, Ashby, or Workday career board URL.")


def _iso(epoch_ms: int | None) -> str | None:
    if not epoch_ms:
        return None
    try:
        return datetime.fromtimestamp(int(epoch_ms) / 1000, timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def workday_posted_date(text: str | None, today: date | None = None) -> str | None:
    """'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago' / 'Posted 30+ Days Ago' -> ISO date."""
    today = today or datetime.now(timezone.utc).date()
    value = (text or "").lower()
    if "today" in value:
        return today.isoformat()
    if "yesterday" in value:
        return (today - timedelta(days=1)).isoformat()
    match = re.search(r"(\d+)\+?\s*days?", value)
    return (today - timedelta(days=int(match.group(1)))).isoformat() if match else None


def is_relevant(title: str) -> bool:
    """Early-career and junior technical roles; never senior, branch or sales roles."""
    title = title or ""
    if NON_TARGET.search(title):
        return False
    if EARLY_CAREER.search(title):
        return not SENIOR_TITLE.search(title)
    return bool(ROLE_WORDS.search(title)) and not SENIOR.search(title)


def is_recent(posted: str | None, max_age_days: int = MAX_AGE_DAYS, today: date | None = None) -> bool:
    """Unknown dates are kept (some boards omit them); known dates must be within max_age_days."""
    if not posted:
        return True
    try:
        when = date.fromisoformat(posted[:10])
    except ValueError:
        return True
    return ((today or datetime.now(timezone.utc).date()) - when).days <= max_age_days


def workday_detail(board: Board, posting: Posting, session: requests.Session) -> Posting:
    """Fill a Workday posting's description and exact start date from its public detail page."""
    path = posting.job_url.split(f"/{board.site}", 1)[-1]
    resp = session.get(f"https://{board.host}/wday/cxs/{board.token}/{board.site}{path}", timeout=20)
    resp.raise_for_status()
    info = (resp.json() or {}).get("jobPostingInfo") or {}
    posting.description = _strip_html(info.get("jobDescription") or "") or posting.description
    posting.posted_date = (info.get("startDate") or "")[:10] or posting.posted_date
    posting.location = info.get("location") or posting.location
    return posting


def fetch_postings(board: Board, session: requests.Session | None = None, limit: int = 200,
                   terms: tuple[str, ...] = WORKDAY_SEARCH_TERMS) -> list[Posting]:
    """Public postings from one board, newest first."""
    postings = _fetch_postings(board, session, limit, terms)
    return sorted(postings, key=lambda post: post.posted_date or "", reverse=True)


def _fetch_postings(board: Board, session: requests.Session | None, limit: int, terms: tuple[str, ...]) -> list[Posting]:
    http = session or requests.Session()
    http.headers.setdefault("User-Agent", UA)
    if board.kind == "greenhouse":
        resp = http.get(f"https://boards-api.greenhouse.io/v1/boards/{board.token}/jobs", params={"content": "true"}, timeout=20)
        resp.raise_for_status()
        rows = resp.json().get("jobs") or []
        return [Posting(
            title=row.get("title") or "Untitled", company=board.name, location=(row.get("location") or {}).get("name") or "",
            job_url=row.get("absolute_url") or "", description=_strip_html(row.get("content") or ""),
            posted_date=(row.get("first_published") or row.get("updated_at") or "")[:10] or None, platform="greenhouse",
        ) for row in rows[:limit] if row.get("absolute_url")]
    if board.kind == "lever":
        resp = http.get(f"https://api.lever.co/v0/postings/{board.token}", params={"mode": "json"}, timeout=20)
        resp.raise_for_status()
        rows = resp.json() if isinstance(resp.json(), list) else []
        return [Posting(
            title=row.get("text") or "Untitled", company=board.name,
            location=(row.get("categories") or {}).get("location") or "",
            job_url=row.get("hostedUrl") or "", description=row.get("descriptionPlain") or _strip_html(row.get("description") or ""),
            posted_date=_iso(row.get("createdAt")), platform="lever",
        ) for row in rows[:limit] if row.get("hostedUrl")]
    if board.kind == "ashby":
        resp = http.get(f"https://api.ashbyhq.com/posting-api/job-board/{board.token}", timeout=20)
        resp.raise_for_status()
        rows = (resp.json() or {}).get("jobs") or []
        return [Posting(
            title=row.get("title") or "Untitled", company=board.name, location=row.get("location") or "",
            job_url=row.get("jobUrl") or "", description=_strip_html(row.get("descriptionHtml") or ""),
            posted_date=(row.get("publishedAt") or "")[:10] or None, platform="ashby",
        ) for row in rows[:limit] if row.get("jobUrl")]
    if board.kind == "workday":
        postings, seen = [], set()
        for term in terms or ("",):
            resp = http.post(
                f"https://{board.host}/wday/cxs/{board.token}/{board.site}/jobs",
                json={"appliedFacets": {}, "limit": WORKDAY_PAGE, "offset": 0, "searchText": term},
                timeout=20,
            )
            resp.raise_for_status()
            for row in (resp.json() or {}).get("jobPostings") or []:
                path = row.get("externalPath") or ""
                if not path or path in seen:
                    continue
                seen.add(path)
                postings.append(Posting(
                    title=row.get("title") or "Untitled", company=board.name, location=row.get("locationsText") or "",
                    job_url=f"https://{board.host}/{board.site}{path}", description="",
                    posted_date=workday_posted_date(row.get("postedOn")), platform="workday",
                ))
        return postings[:limit]
    raise BoardError(f"Unknown board type {board.kind}")


def default_path() -> str:
    return os.path.abspath(os.getenv("COMPANY_BOARDS_PATH", os.path.join("data", "company_boards.json")))


def board_from_dict(data: dict) -> Board:
    return Board(
        name=data.get("name") or data.get("token") or "Company", url=data["url"], kind=data["kind"],
        token=data.get("token") or "", host=data.get("host") or "", site=data.get("site") or "",
    )


def starter_boards() -> list[dict]:
    boards = []
    for name, url in STARTER_BOARDS:
        board = classify(url)
        boards.append({"name": name, "url": board.url, "kind": board.kind, "token": board.token,
                       "host": board.host, "site": board.site})
    return boards


def load_boards(path: str) -> list[dict]:
    """Saved boards; the starter list until the user saves their own (an empty saved list stays empty)."""
    if not os.path.exists(path):
        return starter_boards()
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return list(data.get("boards") or [])


def save_boards(path: str, boards: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"boards": boards}, handle, indent=2)


def add_board(path: str, url: str, name: str = "") -> Board:
    board = classify(url)
    if name.strip():
        board.name = name.strip()
    boards = [b for b in load_boards(path) if b.get("url") != board.url]
    boards.append({
        "name": board.name, "url": board.url, "kind": board.kind, "token": board.token,
        "host": board.host, "site": board.site,
    })
    save_boards(path, boards)
    return board


def remove_board(path: str, url: str) -> bool:
    boards = load_boards(path)
    kept = [b for b in boards if b.get("url") != url]
    save_boards(path, kept)
    return len(kept) != len(boards)
