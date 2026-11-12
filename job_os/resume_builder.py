"""Per-job resume tailoring from the real resume, rendered to a one-page PDF.

Tailoring here is selection and ordering only. Every line on the output comes
verbatim from ``profile["resume"]`` (which mirrors the base resume PDF), plus
skills the user already approved in ``profile["skills"]`` when the posting asks
for them. Nothing is rewritten, so nothing can be invented.
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable

from config import Config
from .profile import load_profile

# Topic -> phrases. A job that talks about a topic lifts the resume lines that show it.
TOPICS: Dict[str, tuple[str, ...]] = {
    "frontend": ("frontend", "front-end", "front end", "react", "next.js", "nextjs", "ui", "ux", "navigation", "html", "css",
                 "user interface", "components", "web app", "tabs", "screen"),
    "web": ("web", "website", "wordpress", "elementor", "cms", "page", "pages", "site", "sites", "links", "seo"),
    "qa": ("qa", "quality", "test", "tests", "testing", "tested", "smoke", "bug", "bugs", "validation", "verified",
           "null checks", "regression", "debug"),
    "data": ("data", "dataset", "records", "sql", "mysql", "database", "pandas", "analytics", "analysis", "reporting",
             "features", "etl", "excel", "standardized", "laps", "simulations"),
    "ml": ("machine learning", "ml", "ai", "lightgbm", "pytorch", "model", "models", "prediction", "retraining",
           "gemini", "computer vision", "detection", "artificial intelligence"),
    "fintech": ("fintech", "finance", "financial", "trading", "trade", "wallet", "portfolio", "loan", "borrower", "bank",
                "banking", "crypto", "payments", "salary", "investment", "marketplace", "exchange", "risk"),
    "backend": ("backend", "back-end", "back end", "api", "apis", "express", "fastapi", "server", "rest", "endpoint",
                "websocket", "websockets", "database", "full stack", "full-stack"),
    "mobile": ("mobile", "react native", "ios", "android", "app store", "sign-up", "login"),
    "devops": ("ci/cd", "ci", "continuous integration", "sonarcloud", "vercel", "deploy", "deployment", "pipeline",
               "github actions", "code quality", "merged pr", "pull request", "pr"),
    "realtime": ("real-time", "real time", "realtime", "websocket", "websockets", "live", "streaming", "low latency"),
    "accessibility": ("accessibility", "a11y", "wcag", "assistive", "visually impaired"),
    "hardware": ("hardware", "embedded", "sensor", "sensors", "ultrasonic", "haptic", "raspberry pi", "arduino", "iot"),
    "research": ("research", "lab", "academic", "publication", "publications", "doi", "scientific", "university"),
    "communication": ("document", "documented", "documentation", "handoff", "stakeholder", "stakeholders", "outreach",
                      "communication", "partners", "clients", "content"),
    "leadership": ("lead", "leadership", "event", "events", "hackathon", "community", "volunteers", "coordinating",
                   "operations", "organized", "team"),
    "automation": ("automation", "automated", "scheduled", "scripts", "workflow", "workflows", "process"),
    "python": ("python", "pytest", "pandas"),
    "javascript": ("javascript", "typescript", "node", "node.js", "express", "react", "next.js"),
    "java": ("java", "spring", "jvm"),
}

# Approved profile skills that describe a practice rather than a tool; never listed as a tool.
CONCEPT_SKILLS = {
    "machine learning", "manual qa", "regression testing", "bug reporting", "ci/cd checks", "software testing",
    "automation", "debugging", "data processing", "risk management", "frontend development", "api integration",
    "accessibility", "version control", "code review", "hardware-software integration", "pull requests",
}
LANGUAGES = {"python", "java", "javascript", "typescript", "html", "css", "sql", "c++", "c#", "go", "rust", "ruby", "swift", "kotlin"}
SECTION_ORDER = ("education", "experience", "projects", "leadership", "skills")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _has(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


def _count(text: str, phrase: str) -> int:
    return len(re.findall(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text))


def job_weights(job: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, float]:
    """How strongly the posting asks for each topic and each approved skill."""
    title = _norm(job.get("title", ""))
    body = _norm(" ".join(str(job.get(key) or "") for key in ("description", "requirements", "industry")))
    required = {_norm(skill) for skill in job.get("required_skills") or []}
    preferred = {_norm(skill) for skill in job.get("preferred_skills") or []}
    weights: Dict[str, float] = {}
    for topic, phrases in TOPICS.items():
        hits = sum(min(3, _count(body, phrase)) for phrase in phrases)
        title_hits = sum(1 for phrase in phrases if _has(title, phrase))
        if hits or title_hits:
            weights[f"topic:{topic}"] = min(6.0, hits * 0.5) + title_hits * 3.0
    for skill in profile.get("skills", []):
        key = _norm(skill)
        score = 4.0 if key in required else 2.5 if key in preferred else 0.0
        score += min(2, _count(body, key)) * 0.75 + (2.0 if _has(title, key) else 0.0)
        if score:
            weights[f"skill:{key}"] = score
    return weights


def line_score(text: str, weights: Dict[str, float], extra: str = "") -> float:
    lowered = _norm(f"{text} {extra}".replace("**", ""))
    score = 0.0
    for key, weight in weights.items():
        kind, name = key.split(":", 1)
        phrases = TOPICS.get(name, ()) if kind == "topic" else (name,)
        if any(_has(lowered, phrase) for phrase in phrases):
            score += weight
    return round(score, 2)


def _matched_terms(text: str, weights: Dict[str, float]) -> list[str]:
    lowered = _norm(text.replace("**", ""))
    return [key.split(":", 1)[1] for key in weights if key.startswith("skill:") and _has(lowered, key.split(":", 1)[1])]


def tailor_resume(job: Dict[str, Any], profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Pick and order the resume content that best fits this job."""
    profile = profile or load_profile()
    base = profile.get("resume") or {}
    weights = job_weights(job, profile)

    def ranked_entries(entries: Iterable[Dict[str, Any]], keep_order: bool) -> list[Dict[str, Any]]:
        result = []
        for index, entry in enumerate(entries):
            context = f"{entry.get('title', '')} {entry.get('name', '')} {entry.get('tech', '')} {entry.get('company', '')}"
            scored = [(line_score(bullet, weights, context), position, bullet) for position, bullet in enumerate(entry.get("bullets", []))]
            ordered = sorted(scored, key=lambda item: (-item[0], item[1]))
            relevance = round(sum(item[0] for item in scored) / max(1, len(scored)) + line_score(context, weights), 2)
            result.append({**entry, "bullets": [item[2] for item in ordered], "bullet_scores": [item[0] for item in ordered],
                           "relevance": relevance, "original_index": index})
        if not keep_order:
            result.sort(key=lambda item: (-item["relevance"], item["original_index"]))
        return result

    experience = ranked_entries(base.get("experience", []), keep_order=True)  # recruiters expect reverse-chronological
    projects = ranked_entries(base.get("projects", []), keep_order=False)
    leadership = ranked_entries(base.get("leadership", []), keep_order=True)

    approved = {_norm(skill): skill for skill in profile.get("skills", [])}
    requested = [key.split(":", 1)[1] for key, weight in sorted(weights.items(), key=lambda kv: -kv[1]) if key.startswith("skill:") and weight >= 2.5]
    on_resume = {_norm(item) for group in base.get("skill_groups", []) for item in group["items"]}
    added = [approved[key] for key in requested if key in approved and key not in on_resume and key not in CONCEPT_SKILLS]
    skill_groups = []
    for group in base.get("skill_groups", []):
        items = list(group["items"])
        label = group["label"].lower()
        for skill in added:
            is_language = _norm(skill) in LANGUAGES
            if (is_language and label.startswith("language")) or (not is_language and label.startswith("tools")):
                items.append(skill)
        items.sort(key=lambda item: (-weights.get(f"skill:{_norm(item)}", 0.0), group["items"].index(item) if item in group["items"] else 99))
        skill_groups.append({"label": group["label"], "items": items})
    placed = {_norm(item) for group in skill_groups for item in group["items"]}
    if any(_norm(skill) not in placed for skill in added) and skill_groups:
        skill_groups[-1]["items"].extend(skill for skill in added if _norm(skill) not in placed)

    required = job.get("required_skills") or []
    gaps = [skill for skill in required if _norm(skill) not in approved]
    all_text = " ".join(b for section in (experience, projects, leadership) for entry in section for b in entry["bullets"])
    all_text += " " + " ".join(item for group in skill_groups for item in group["items"])
    covered = sorted({term for term in _matched_terms(all_text, weights)})
    top_topics = [key.split(":", 1)[1] for key, _ in sorted(weights.items(), key=lambda kv: -kv[1]) if key.startswith("topic:")][:6]
    return {
        "header": {key: profile.get(key, "") for key in ("name", "location", "phone", "email", "linkedin", "github", "portfolio")},
        "education": base.get("education", []),
        "experience": experience,
        "projects": projects,
        "leadership": leadership,
        "skill_groups": skill_groups,
        "report": {
            "job_focus": top_topics,
            "keywords_covered": covered,
            "skills_added_from_profile": added,
            "gaps_not_claimed": gaps,
            "project_order": [item["name"] for item in projects],
            "trimmed_bullets": [],
        },
    }


def trim_one_bullet(tailored: Dict[str, Any]) -> bool:
    """Drop the least relevant bullet from an entry that has more than one. Returns False if nothing can go."""
    candidates = []
    for section in ("projects", "experience", "leadership"):
        for entry in tailored[section]:
            if len(entry["bullets"]) > 1:
                candidates.append((entry["bullet_scores"][-1], section, entry))
    if not candidates:
        return False
    _, _, entry = min(candidates, key=lambda item: item[0])
    removed = entry["bullets"].pop()
    entry["bullet_scores"].pop()
    tailored["report"]["trimmed_bullets"].append(removed.replace("**", ""))
    return True


def _link(url: str) -> str:
    shown = re.sub(r"^https?://(www\.)?", "", url or "").rstrip("/")
    return f'<a href="{html.escape(url)}">{html.escape(shown)}</a>' if url else ""


def _rich(text: str) -> str:
    """Escape a bullet and turn **marked** spans into bold, as on the base resume."""
    parts = html.escape(text).split("**")
    return "".join(f"<b>{part}</b>" if index % 2 else part for index, part in enumerate(parts))


def _entry(left: str, right: str, sub_left: str, sub_right: str, bullets: list[str]) -> str:
    items = "".join(f"<li>{_rich(b)}</li>" for b in bullets)
    sub = f'<div class="row sub"><span>{sub_left}</span><span>{sub_right}</span></div>' if (sub_left or sub_right) else ""
    return f'<div class="entry"><div class="row"><span class="b">{left}</span><span>{right}</span></div>{sub}<ul>{items}</ul></div>'


def render_html(tailored: Dict[str, Any], scale: float = 1.0) -> str:
    """Render a resume page that matches the base PDF's layout (Times, ruled section heads)."""
    h = tailored["header"]
    e = html.escape
    sep = "&nbsp; | &nbsp;"
    contact_1 = sep.join(x for x in (e(h.get("location", "").replace(", Canada", "")), e(h.get("phone", "")), _link_mail(h.get("email", ""))) if x)
    contact_2 = sep.join(x for x in (_link(h.get("linkedin", "")), _link(h.get("github", "")), _link(h.get("portfolio", ""))) if x)
    education = "".join(
        f'<div class="entry"><div class="row"><span class="b">{e(ed.get("institution", ""))}</span><span>{e(ed.get("location", ""))}</span></div>'
        f'<div class="row sub"><span>{e(ed.get("degree", ""))}</span><span>{e(ed.get("dates", ""))}</span></div></div>'
        for ed in tailored["education"]
    )
    experience = "".join(_entry(e(x["title"]), e(x.get("dates", "")), e(x.get("company", "")), e(x.get("location", "")), x["bullets"]) for x in tailored["experience"])
    projects = "".join(_entry(f'{e(p["name"])} | {e(p.get("tech", ""))}', e(p.get("dates", "")), "", "", p["bullets"]) for p in tailored["projects"])
    leadership = "".join(_entry(e(x["title"]), e(x.get("dates", "")), e(x.get("company", "")), e(x.get("location", "")), x["bullets"]) for x in tailored["leadership"])
    skills = "".join(f'<div class="skill"><span class="b">{e(g["label"])}:</span> {e(", ".join(g["items"]))}</div>' for g in tailored["skill_groups"])
    sections = [("Education", education), ("Experience", experience), ("Projects", projects),
                ("Leadership &amp; Campus Involvement", leadership), ("Technical Skills", skills)]
    body = "".join(f'<h2>{title}</h2>{content}' for title, content in sections if content)
    base_pt = round(10.0 * scale, 2)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(h.get('name', 'Resume'))} Resume</title><style>
@page {{ size: letter; margin: 0.42in 0.5in 0.4in 0.5in; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: "TeX Gyre Termes", "Times New Roman", Times, serif; font-size: {base_pt}pt; line-height: 1.18; color: #000; }}
a {{ color: #000; text-decoration: none; }}
header {{ text-align: center; margin-bottom: 2pt; }}
header h1 {{ font-size: {round(17.4 * scale, 2)}pt; margin: 0 0 2pt; font-weight: bold; }}
header div {{ font-size: {round(9.5 * scale, 2)}pt; }}
h2 {{ font-size: {round(11.3 * scale, 2)}pt; font-weight: bold; margin: {round(7 * scale, 1)}pt 0 {round(2.5 * scale, 1)}pt; padding-bottom: 1pt; border-bottom: 0.6pt solid #000; }}
.entry {{ margin-bottom: {round(3 * scale, 1)}pt; }}
.row {{ display: flex; justify-content: space-between; gap: 12pt; }}
.row.sub {{ font-style: italic; font-size: {round(9.5 * scale, 2)}pt; }}
.b {{ font-weight: bold; }}
ul {{ margin: 1pt 0 0; padding-left: 13pt; }}
li {{ font-size: {round(9.6 * scale, 2)}pt; margin: 0 0 0.8pt; text-align: justify; }}
.skill {{ font-size: {round(9.5 * scale, 2)}pt; margin-bottom: 0.8pt; }}
</style></head><body><header><h1>{e(h.get('name', ''))}</h1><div>{contact_1}</div><div>{contact_2}</div></header>{body}</body></html>"""


def _link_mail(email: str) -> str:
    return f'<a href="mailto:{html.escape(email)}">{html.escape(email)}</a>' if email else ""


def chrome_pdf(html_path: str) -> bytes:
    """Print a local HTML file to PDF with headless Chrome (already used elsewhere in this app)."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.print_page_options import PrintOptions

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(Path(html_path).resolve().as_uri())
        print_options = PrintOptions()
        print_options.page_width = 21.59
        print_options.page_height = 27.94
        print_options.margin_top = print_options.margin_bottom = print_options.margin_left = print_options.margin_right = 0
        print_options.background = True
        return base64.b64decode(driver.print_page(print_options))
    finally:
        driver.quit()


def pdf_page_count(data: bytes) -> int:
    import io
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return len(pdf.pages)


def resume_filename(profile: Dict[str, Any]) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", profile.get("name") or "Resume").strip("_")
    return f"{name}_Resume.pdf"


def build_tailored_resume(
    job_id: int,
    job: Dict[str, Any],
    profile: Dict[str, Any] | None = None,
    directory: str | None = None,
    renderer: Callable[[str], bytes] | None = None,
) -> Dict[str, Any]:
    """Tailor, render, and keep the result to one page. Returns paths and the tailoring report."""
    profile = profile or load_profile()
    renderer = renderer or chrome_pdf
    tailored = tailor_resume(job, profile)
    target = Path(directory or Config.DRAFTS_DIR) / f"job_{int(job_id)}"
    target.mkdir(parents=True, exist_ok=True)
    html_path = target / "resume.html"
    pdf_path = target / resume_filename(profile)
    pages = 0
    data = b""
    # Shrink type a touch first, then drop the least relevant bullets until it fits on one page.
    for attempt in range(8):
        scale = 1.0 if attempt == 0 else 0.97 if attempt == 1 else 0.95
        html_path.write_text(render_html(tailored, scale), encoding="utf-8")
        data = renderer(str(html_path))
        pages = pdf_page_count(data)
        if pages <= 1 or (attempt >= 1 and not trim_one_bullet(tailored)):
            break
    pdf_path.write_bytes(data)
    tailored["report"]["pages"] = pages
    return {"pdf_path": str(pdf_path), "html_path": str(html_path), "pages": pages, "report": tailored["report"], "resume": tailored}
