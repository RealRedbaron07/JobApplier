#!/usr/bin/env python3
"""Local-first Flask API and dashboard for the JobApplier operating system."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, render_template, request
from sqlalchemy import asc, desc, or_

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config
from database.models import ApplicationRecord, Contact, FollowUp, Job, Session, TailoredDraft
from job_os.analytics import summarize_jobs
from job_os.drafts import generate_application_answers, recruiter_message
from job_os.io import export_csv, export_json, parse_csv, parse_json_backup
from job_os.parser import parse_iso_date, parse_job_description
from job_os.profile import load_profile, save_profile
from job_os.scoring import score_job
from job_os.tailoring import PROFILE_PRIORITIES, create_tailoring_plan, save_latex_draft, validate_draft
from job_os.workflow import STATUSES, can_transition, suggested_follow_up


from dashboard.snipe_views import snipe_bp  # noqa: E402 - needs ROOT on sys.path

app = Flask(__name__)
app.config.update(JSON_SORT_KEYS=False, MAX_CONTENT_LENGTH=4 * 1024 * 1024)
app.register_blueprint(snipe_bp)


@app.before_request
def local_request_boundary():
    """Reject DNS-rebinding hosts and cross-site mutations of private local data."""
    if not _is_loopback_peer(request.remote_addr):
        return jsonify({"error": "JobApplier accepts loopback requests only."}), 403
    hostname = urlparse(f"//{request.host}").hostname
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        return jsonify({"error": "JobApplier accepts loopback requests only."}), 403
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return jsonify({"error": "Cross-site changes to local JobApplier data are blocked."}), 403
        origin = request.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != request.host:
                return jsonify({"error": "Cross-origin changes to local JobApplier data are blocked."}), 403


def _is_loopback_peer(value: str | None) -> bool:
    """Accept direct IPv4/IPv6 loopback peers, including mapped IPv4."""
    if not value:
        return False
    try:
        address = ip_address(value)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_loopback or bool(mapped and mapped.is_loopback)


@app.after_request
def privacy_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.errorhandler(ValueError)
def invalid_value(error):
    return jsonify({"error": str(error)}), 400


def _automation_level() -> int:
    try:
        return min(4, max(0, int(load_profile().get("automation_level", Config.AUTOMATION_LEVEL))))
    except (TypeError, ValueError):
        return 3


def _level_error(required: int):
    current = _automation_level()
    if current >= required:
        return None
    return jsonify({
        "error": f"Automation level {required} is required for this action; the current local profile is level {current}.",
        "current_level": current,
        "required_level": required,
    }), 403


def _external_url(value: str | None, field: str = "URL") -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError(f"{field} must be a valid HTTP(S) URL.")
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{field} must be a valid HTTP(S) URL without embedded credentials.")
    return value.strip()


def _path_reference(value: str | None, field: str) -> str | None:
    """Validate a local path as inert tracker metadata; no file is opened here."""
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 500 or "\x00" in value:
        raise ValueError(f"{field} must be a local path of at most 500 characters.")
    return value


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    parsed = _json_load(value, [])
    return parsed if isinstance(parsed, list) else []


def _json_load(value, fallback):
    try:
        return json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback


def _iso(value):
    return value.isoformat() if value else None


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _optional_int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _optional_float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _claim_relevant_content(value):
    """Remove analysis metadata that describes gaps/warnings rather than candidate claims."""
    if isinstance(value, dict):
        metadata = {"base_resume_warning", "keyword_gaps", "keyword_gap_rule", "safety_report", "risks", "missing_skills"}
        return {key: _claim_relevant_content(item) for key, item in value.items() if key not in metadata}
    if isinstance(value, list):
        return [_claim_relevant_content(item) for item in value]
    return value


def _job_dict(job: Job, detail: bool = False) -> dict:
    explanation = _json_load(job.match_explanation, {})
    data = {
        "id": job.id, "title": job.title, "company": job.company, "location": job.location,
        "work_mode": job.work_mode or "unknown", "source": job.source or job.platform or "manual",
        "job_url": job.job_url or "", "application_url": job.job_url or "",
        "job_type": job.job_type or "unspecified", "posted_date": _iso(job.posted_date),
        "application_status": job.application_status or "discovered", "applied": bool(job.applied),
        "allowed_statuses": [status for status in STATUSES if can_transition(job.application_status, status)],
        "match_score": job.match_score or 0, "fit_category": job.fit_category or "maybe",
        "resume_profile": job.resume_profile or explanation.get("resume_profile", "general_software"),
        "suggested_project": job.suggested_project or explanation.get("project_to_emphasize", "JobApplier"),
        "discovered_date": _iso(job.discovered_date), "applied_date": _iso(job.applied_date),
        "deadline": _iso(job.deadline), "follow_up_date": _iso(job.follow_up_date),
        "salary": job.salary, "salary_min": job.salary_min, "salary_max": job.salary_max,
        "salary_unit": job.salary_unit, "salary_currency": job.salary_currency,
        "next_action": job.next_action or explanation.get("strategy", "Review the posting."),
        "safety_flags": _json_load(job.safety_flags, []),
    }
    if detail:
        data.update({
            "description": job.description or "", "notes": job.notes or "", "term_length": job.term_length,
            "start_date": job.start_date, "required_skills": _json_load(job.required_skills, []),
            "preferred_skills": _json_load(job.preferred_skills, []), "tech_stack": _json_load(job.tech_stack, []),
            "work_authorization": job.work_authorization, "sponsorship": job.sponsorship,
            "coop_eligible": job.coop_eligible, "industry": job.industry,
            "seniority_level": job.seniority_level, "required_documents": _json_load(job.required_documents, []),
            "login_portal": job.login_portal, "application_effort": job.application_effort,
            "score_breakdown": _json_load(job.score_breakdown, {}), "match_explanation": explanation,
            "resume_version_used": job.resume_version_used, "cover_letter_version_used": job.cover_letter_version_used,
            "contact_name": job.contact_name, "contact_details": job.contact_details,
            "tailored_resume_path": job.tailored_resume_path,
        })
    return data


def _apply_score(job: Job, parsed: dict, result: dict) -> None:
    job.match_score = result["overall_score"]
    job.fit_category = result["category"]
    job.score_breakdown = json.dumps(result["breakdown"])
    job.match_explanation = json.dumps(result)
    job.safety_flags = json.dumps(result["safety_flags"])
    job.resume_profile = result["resume_profile"]
    job.suggested_project = result["project_to_emphasize"]
    job.next_action = result["strategy"]


def _new_job(parsed: dict, profile: dict, preserve_tracking: bool = False, score_enabled: bool = True) -> Job:
    result = score_job(parsed, profile) if score_enabled else {
        "overall_score": 0, "category": "not_scored", "breakdown": {},
        "matched_skills": [], "missing_skills": [], "why_it_fits": ["Manual tracking mode; this role has not been scored."],
        "risks": ["Enable automation level 1 to parse and score this posting."],
        "resume_profile": "general_software", "project_to_emphasize": "JobApplier",
        "strategy": "Review and track manually.", "safety_flags": [],
    }
    status = parsed.get("application_status") if preserve_tracking else "discovered"
    status = status if status in STATUSES else "discovered"
    discovered = parse_iso_date(parsed.get("discovered_date")) if preserve_tracking else None
    applied_date = parse_iso_date(parsed.get("applied_date")) if preserve_tracking else None
    job = Job(
        title=parsed["title"], company=parsed["company"], location=parsed.get("location"),
        platform=parsed.get("platform") or parsed.get("source", "manual"), source=parsed.get("source", "manual"),
        job_url=_external_url(parsed.get("job_url"), "Application URL"), description=parsed.get("description"),
        requirements=parsed.get("requirements"), job_type=parsed.get("job_type"),
        posted_date=parse_iso_date(parsed.get("posting_date") or parsed.get("posted_date")),
        work_mode=parsed.get("work_mode"), term_length=parsed.get("term_length"),
        start_date=parsed.get("start_date"), required_skills=json.dumps(_json_list(parsed.get("required_skills"))),
        preferred_skills=json.dumps(_json_list(parsed.get("preferred_skills"))), tech_stack=json.dumps(_json_list(parsed.get("tech_stack"))),
        work_authorization=parsed.get("work_authorization"), sponsorship=parsed.get("sponsorship"),
        coop_eligible=None if parsed.get("coop_eligible") in (None, "") else _as_bool(parsed.get("coop_eligible")), industry=parsed.get("industry"),
        seniority_level=parsed.get("seniority_level"), deadline=parse_iso_date(parsed.get("deadline")),
        salary=parsed.get("salary"), salary_min=_optional_float(parsed.get("salary_min")), salary_max=_optional_float(parsed.get("salary_max")),
        salary_unit=parsed.get("salary_unit"), salary_currency=parsed.get("salary_currency"),
        application_effort=parsed.get("application_effort"), required_documents=json.dumps(_json_list(parsed.get("required_documents"))),
        login_portal=parsed.get("login_portal"), notes=parsed.get("notes", ""),
        application_status=status, applied=(bool(applied_date) or _as_bool(parsed.get("applied"))) if preserve_tracking else False,
        discovered_date=discovered or datetime.now(timezone.utc), applied_date=applied_date,
        application_method=parsed.get("application_method"), application_notes=parsed.get("application_notes"),
        follow_up_date=parse_iso_date(parsed.get("follow_up_date")) if preserve_tracking else None,
        resume_version_used=parsed.get("resume_version_used"), cover_letter_version_used=parsed.get("cover_letter_version_used"),
        contact_name=parsed.get("contact_name"), contact_details=parsed.get("contact_details"),
        cover_letter=parsed.get("cover_letter"),
        cover_letter_path=_path_reference(parsed.get("cover_letter_path"), "Cover-letter path"),
        tailored_resume_path=_path_reference(parsed.get("tailored_resume_path"), "Tailored-resume path"),
        original_resume_path=_path_reference(parsed.get("original_resume_path"), "Original-resume path"),
        external_site=_as_bool(parsed.get("external_site")),
        external_url=_external_url(parsed.get("external_url"), "External application URL"),
    )
    _apply_score(job, parsed, result)
    if preserve_tracking:
        job.application_status = status
        if parsed.get("match_score") not in (None, ""):
            try:
                job.match_score = min(100, max(0, int(float(parsed["match_score"]))))
            except (TypeError, ValueError):
                pass
        job.fit_category = parsed.get("fit_category") or job.fit_category
        job.resume_profile = parsed.get("resume_profile") or job.resume_profile
        job.next_action = parsed.get("next_action") or job.next_action
        job.suggested_project = parsed.get("suggested_project") or job.suggested_project
        for field, fallback in (("score_breakdown", {}), ("match_explanation", {}), ("safety_flags", [])):
            value = parsed.get(field)
            if value not in (None, ""):
                setattr(job, field, value if isinstance(value, str) else json.dumps(value))
    return job


def _existing_restore_job(session, item: dict) -> Job | None:
    """Find the job represented by a backup without merging distinct postings."""
    if item.get("job_url"):
        return session.query(Job).filter_by(job_url=item["job_url"]).first()
    discovered = parse_iso_date(item.get("discovered_date"))
    if not discovered:
        return None
    return session.query(Job).filter_by(
        title=item.get("title"), company=item.get("company"),
        location=item.get("location"), discovered_date=discovered,
    ).first()


@app.get("/")
def index():
    return render_template("index.html", automation_level=_automation_level())


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "local_first": True, "auto_submit": False, "automation_level": _automation_level()})


@app.route("/api/profile", methods=["GET", "PUT"])
@app.route("/api/settings", methods=["GET", "POST"])
def profile_settings():
    if request.method in ("PUT", "POST"):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Profile update must be a JSON object."}), 400
        for field in ("linkedin", "github", "portfolio"):
            if field in payload:
                payload[field] = _external_url(payload[field], field.replace("_", " ").title())
        profile = save_profile(payload)
        return jsonify({"message": "Profile saved locally", "profile": profile})
    return jsonify(load_profile())


@app.post("/api/jobs/parse")
def parse_preview():
    blocked = _level_error(1)
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or not isinstance(payload.get("description", ""), str):
        return jsonify({"error": "Job payload must be an object with text description."}), 400
    parsed = parse_job_description(payload.get("description", ""), payload)
    return jsonify({"parsed": parsed, "score": score_job(parsed, load_profile())})


@app.route("/api/jobs", methods=["GET", "POST"])
def jobs_collection():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Job payload must be a JSON object."}), 400
        if not payload.get("description") and not payload.get("title"):
            return jsonify({"error": "Provide a title or pasted job description."}), 400
        if not isinstance(payload.get("description", ""), str):
            return jsonify({"error": "Job description must be text."}), 400
        for field in ("title", "company", "location", "source", "job_url", "work_mode", "job_type", "term_length", "start_date", "industry", "seniority_level", "notes", "login_portal"):
            if field in payload and payload[field] not in (None, "") and not isinstance(payload[field], str):
                return jsonify({"error": f"{field} must be text."}), 400
        level = _automation_level()
        parsed = parse_job_description(payload.get("description", ""), payload) if level >= 1 else {
            **payload,
            "title": payload.get("title") or "Untitled opportunity",
            "company": payload.get("company") or "Unknown company",
            "required_skills": [], "preferred_skills": [], "tech_stack": [],
            "required_documents": [], "source": payload.get("source") or "manual",
        }
        session = Session()
        try:
            if parsed.get("job_url"):
                existing = session.query(Job).filter_by(job_url=parsed["job_url"]).first()
                if existing:
                    return jsonify({"error": "That application URL is already tracked.", "job_id": existing.id}), 409
            job = _new_job(parsed, load_profile(), score_enabled=level >= 1)
            session.add(job)
            session.commit()
            action = "added and scored" if level >= 1 else "added for manual tracking"
            return jsonify({"message": f"Job {action}", "job": _job_dict(job, True)}), 201
        finally:
            session.close()

    session = Session()
    try:
        query = session.query(Job)
        status = request.args.get("status")
        category = request.args.get("category")
        search = request.args.get("search", "").strip()
        if status and status != "all":
            query = query.filter(Job.application_status == status)
        if category and category != "all":
            query = query.filter(Job.fit_category == category)
        if search:
            query = query.filter(or_(Job.title.ilike(f"%{search}%"), Job.company.ilike(f"%{search}%"), Job.location.ilike(f"%{search}%")))
        sort = request.args.get("sort", "match_score")
        sortable = {
            "match_score": Job.match_score, "discovered_date": Job.discovered_date,
            "posted_date": Job.posted_date, "deadline": Job.deadline,
            "applied_date": Job.applied_date, "company": Job.company, "title": Job.title,
        }
        if sort not in sortable:
            return jsonify({"error": "Unsupported sort field."}), 400
        column = sortable[sort]
        order = request.args.get("order", "desc")
        if order not in {"asc", "desc"}:
            return jsonify({"error": "Order must be asc or desc."}), 400
        query = query.order_by(desc(column).nullslast() if order == "desc" else asc(column).nullslast())
        try:
            limit = min(500, max(1, int(request.args.get("limit", 200))))
        except (TypeError, ValueError):
            return jsonify({"error": "Limit must be an integer from 1 through 500."}), 400
        rows = query.limit(limit).all()
        return jsonify({"jobs": [_job_dict(job) for job in rows], "count": len(rows)})
    finally:
        session.close()


@app.route("/api/jobs/<int:job_id>", methods=["GET", "PATCH", "DELETE"])
def job_detail(job_id: int):
    session = Session()
    try:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        if request.method == "DELETE":
            job.application_status = "archived"
            session.commit()
            return jsonify({"message": "Job archived"})
        if request.method == "PATCH":
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                return jsonify({"error": "Job update must be a JSON object."}), 400
            target = payload.get("application_status")
            current = job.application_status or "discovered"
            if target and target not in STATUSES:
                return jsonify({"error": "Unknown application status."}), 400
            if target and not can_transition(current, target):
                return jsonify({"error": f"Invalid status transition: {current} -> {target}"}), 409
            if target == "applied" and target != current and payload.get("confirm_submission") is not True:
                return jsonify({"error": "Confirm that you personally submitted the application before marking it applied.", "confirmation_required": True}), 409
            editable = (
                "notes", "deadline", "follow_up_date", "contact_name", "contact_details",
                "login_portal", "salary_min", "salary_max", "salary_unit", "salary_currency",
                "resume_version_used", "cover_letter_version_used", "source", "job_url",
            )
            for field in editable:
                if field not in payload:
                    continue
                value = payload[field]
                if field in ("deadline", "follow_up_date"):
                    value = parse_iso_date(value)
                elif field == "job_url":
                    value = _external_url(value, "Application URL")
                elif field in ("salary_min", "salary_max") and value not in (None, ""):
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        return jsonify({"error": f"{field} must be numeric."}), 400
                setattr(job, field, value)
            if target and target != current:
                job.application_status = target
                if target == "applied":
                    job.applied = True
                    job.applied_date = job.applied_date or datetime.now(timezone.utc)
                    job.follow_up_date = job.follow_up_date or suggested_follow_up("application", job.applied_date)
                    session.add(ApplicationRecord(
                        job_id=job.id, application_date=job.applied_date,
                        resume_used=job.resume_version_used, cover_letter_used=job.cover_letter_version_used,
                        tailored_resume_used=job.tailored_resume_path, application_status="applied",
                        application_method="human_confirmed", follow_up_date=job.follow_up_date,
                        notes="User explicitly confirmed submission outside JobApplier.",
                    ))
                    existing_follow_up = session.query(FollowUp).filter_by(job_id=job.id, follow_up_type="application", status="pending").first()
                    if not existing_follow_up:
                        session.add(FollowUp(
                            job_id=job.id, follow_up_type="application", due_date=job.follow_up_date,
                            status="pending", message_draft=recruiter_message(
                                "application_follow_up",
                                {"name": job.contact_name or "Hiring Team", "company": job.company, "role": job.title},
                                _job_dict(job, True),
                            ),
                        ))
                elif target in ("discovered", "interested", "resume_tailored"):
                    job.applied = False
                elif job.applied and target in ("follow_up_needed", "interview", "rejected", "offer", "archived"):
                    session.add(ApplicationRecord(
                        job_id=job.id, application_date=datetime.now(timezone.utc),
                        application_status=target, application_method="status_event",
                        notes="Tracker status updated by the user.",
                    ))
            session.commit()
            return jsonify({"message": "Job updated", "job": _job_dict(job, True)})
        return jsonify(_job_dict(job, True))
    finally:
        session.close()


@app.post("/api/jobs/<int:job_id>/rescore")
def rescore_job(job_id: int):
    blocked = _level_error(1)
    if blocked:
        return blocked
    session = Session()
    try:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        parsed = parse_job_description(job.description or "", _job_dict(job, True))
        result = score_job(parsed, load_profile())
        job.required_skills = json.dumps(parsed["required_skills"])
        job.preferred_skills = json.dumps(parsed["preferred_skills"])
        job.tech_stack = json.dumps(parsed["tech_stack"])
        _apply_score(job, parsed, result)
        session.commit()
        return jsonify({"message": "Job rescored", "score": result})
    finally:
        session.close()


@app.post("/api/jobs/<int:job_id>/tailor")
def tailor_job(job_id: int):
    blocked = _level_error(2)
    if blocked:
        return blocked
    session = Session()
    try:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        profile = load_profile()
        job_data = _job_dict(job, True)
        scoring = _json_load(job.match_explanation, score_job(job_data, profile))
        selected = (request.get_json(silent=True) or {}).get("resume_profile") or job.resume_profile
        if selected not in PROFILE_PRIORITIES:
            return jsonify({"error": "Unknown resume profile."}), 400
        plan = create_tailoring_plan(job_data, scoring, profile, selected)
        path = save_latex_draft(job.id, plan.pop("latex"))
        plan["latex_path"] = path
        draft = TailoredDraft(job_id=job.id, draft_type="resume_tailoring", resume_profile=plan["resume_profile"], content=json.dumps(plan), file_path=path, review_status="draft", safety_report=json.dumps(plan["safety_report"]))
        session.add(draft)
        job.resume_profile = plan["resume_profile"]
        job.tailored_resume_path = path
        if can_transition(job.application_status, "resume_tailored"):
            job.application_status = "resume_tailored"
        session.commit()
        return jsonify({"message": "Tailoring draft created; human review required", "draft_id": draft.id, "plan": plan})
    finally:
        session.close()


@app.post("/api/jobs/<int:job_id>/answers")
def draft_answers(job_id: int):
    blocked = _level_error(2)
    if blocked:
        return blocked
    session = Session()
    try:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        profile = load_profile()
        answers = generate_application_answers(_job_dict(job, True), profile)
        safety_report = validate_draft("\n".join(answers.values()), profile)
        draft = TailoredDraft(job_id=job.id, draft_type="application_answers", content=json.dumps(answers), review_status="draft", safety_report=json.dumps(safety_report))
        session.add(draft)
        session.commit()
        return jsonify({"message": "Editable answer drafts created", "draft_id": draft.id, "answers": answers, "safety_report": safety_report})
    finally:
        session.close()


@app.post("/api/jobs/<int:job_id>/prepare")
def prepare_package(job_id: int):
    """Prepare materials only. This endpoint never opens or submits an application."""
    blocked = _level_error(3)
    if blocked:
        return blocked
    session = Session()
    try:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        profile = load_profile()
        job_data = _job_dict(job, True)
        scoring = _json_load(job.match_explanation, score_job(job_data, profile))
        plan = create_tailoring_plan(job_data, scoring, profile, job.resume_profile)
        latex_path = save_latex_draft(job.id, plan.pop("latex"))
        answers = generate_application_answers(job_data, profile)
        answer_safety = validate_draft("\n".join(answers.values()), profile)
        combined_safety = {
            "passed": bool(plan["safety_report"]["passed"] and answer_safety["passed"]),
            "violations": plan["safety_report"]["violations"] + answer_safety["violations"],
            "requires_human_review": True,
        }
        package_draft = TailoredDraft(job_id=job.id, draft_type="application_package", resume_profile=plan["resume_profile"], content=json.dumps({"tailoring": plan, "answers": answers}), file_path=latex_path, review_status="draft", safety_report=json.dumps(combined_safety))
        session.add(package_draft)
        job.tailored_resume_path = latex_path
        job.application_status = "resume_tailored" if can_transition(job.application_status, "resume_tailored") else job.application_status
        job.next_action = "Review the LaTeX draft and answers, complete the checklist, then submit manually on the official portal."
        session.commit()
        return jsonify({"message": "Application package prepared; nothing was submitted", "draft_id": package_draft.id, "latex_path": latex_path, "tailoring": plan, "answers": answers, "safety_report": combined_safety, "checklist": ["Verify company and role details", "Review every resume claim", "Resolve safety warnings", "Confirm work authorization answer", "Check one-page PDF output", "Submit manually on the official portal", "Return and mark the job applied"]})
    finally:
        session.close()


@app.post("/api/jobs/<int:job_id>/handoff")
def application_handoff(job_id: int):
    """Level-4 handoff: expose a reviewed link and checklist, never fill or submit."""
    blocked = _level_error(4)
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    if payload.get("confirm_reviewed") is not True:
        return jsonify({"error": "Confirm that you reviewed the prepared package before creating a handoff."}), 409
    session = Session()
    try:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        application_url = _external_url(job.job_url, "Application URL")
        if not application_url:
            return jsonify({"error": "Add the employer's official application URL before creating a handoff."}), 409
        package = session.query(TailoredDraft).filter_by(job_id=job.id, draft_type="application_package").order_by(desc(TailoredDraft.created_date)).first()
        if not package:
            return jsonify({"error": "Prepare and review an application package first."}), 409
        if package.review_status != "reviewed":
            return jsonify({"error": "Save the latest application package as reviewed before creating a handoff."}), 409
        safety_report = _json_load(package.safety_report, {})
        if not safety_report.get("passed"):
            return jsonify({"error": "Resolve the package safety warnings before handoff.", "safety_report": safety_report}), 409
        job.next_action = "Open the reviewed handoff link, complete every portal field yourself, submit manually, then return and mark applied."
        session.commit()
        return jsonify({
            "message": "Reviewed handoff ready; no form was opened, filled, or submitted",
            "application_url": application_url,
            "draft_id": package.id,
            "human_actions": [
                "Open the official employer URL", "Authenticate yourself if required",
                "Answer and verify every portal question", "Upload only reviewed files",
                "Handle any CAPTCHA yourself", "Submit with your own final action",
                "Return to JobApplier and explicitly mark applied",
            ],
        })
    finally:
        session.close()


@app.get("/api/jobs/<int:job_id>/drafts")
def list_drafts(job_id: int):
    session = Session()
    try:
        drafts = session.query(TailoredDraft).filter_by(job_id=job_id).order_by(desc(TailoredDraft.created_date)).all()
        return jsonify({"drafts": [{"id": d.id, "type": d.draft_type, "profile": d.resume_profile, "content": _json_load(d.content, d.content), "file_path": d.file_path, "review_status": d.review_status, "safety_report": _json_load(d.safety_report, {}), "created_date": _iso(d.created_date)} for d in drafts]})
    finally:
        session.close()


@app.patch("/api/drafts/<int:draft_id>")
def update_draft(draft_id: int):
    blocked = _level_error(2)
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or "content" not in payload:
        return jsonify({"error": "Draft content is required."}), 400
    content = payload["content"]
    serialized = json.dumps(content) if isinstance(content, (dict, list)) else str(content)
    claim_content = _claim_relevant_content(content)
    claim_text = json.dumps(claim_content) if isinstance(claim_content, (dict, list)) else str(claim_content)
    safety_report = validate_draft(claim_text, load_profile())
    if not safety_report["passed"]:
        return jsonify({"error": "Draft contains unsupported claims and was not saved.", "safety_report": safety_report}), 409
    review_status = payload.get("review_status", "draft")
    if review_status not in {"draft", "reviewed"}:
        return jsonify({"error": "Review status must be draft or reviewed."}), 400
    session = Session()
    try:
        draft = session.get(TailoredDraft, draft_id)
        if not draft:
            return jsonify({"error": "Draft not found"}), 404
        if draft.draft_type == "application_package" and (not isinstance(content, dict) or not isinstance(content.get("tailoring"), dict) or not isinstance(content.get("answers"), dict)):
            return jsonify({"error": "Application packages must retain both tailoring and answers sections."}), 400
        if draft.draft_type == "application_answers" and not isinstance(content, dict):
            return jsonify({"error": "Application-answer drafts must be a keyed answer object."}), 400
        draft.content = serialized
        draft.review_status = review_status
        draft.safety_report = json.dumps(safety_report)
        draft.updated_date = datetime.now(timezone.utc)
        session.commit()
        return jsonify({"message": "Edited draft saved locally", "safety_report": safety_report})
    finally:
        session.close()


@app.post("/api/import/csv")
def import_csv_route():
    content = request.files["file"].read().decode("utf-8-sig") if "file" in request.files else (request.get_json(silent=True) or {}).get("csv", "")
    level = _automation_level()
    rows = parse_csv(content, parse_enabled=level >= 1)
    session = Session()
    created = 0
    skipped = 0
    try:
        for item in rows:
            if item.get("job_url") and session.query(Job).filter_by(job_url=item["job_url"]).first():
                skipped += 1
                continue
            session.add(_new_job(item, load_profile(), preserve_tracking=True, score_enabled=level >= 1))
            created += 1
        session.commit()
        return jsonify({"message": "CSV import complete", "created": created, "skipped_duplicates": skipped})
    finally:
        session.close()


@app.post("/api/import/json")
def import_json_route():
    if "file" in request.files:
        content = request.files["file"].read().decode("utf-8-sig")
    else:
        supplied = request.get_json(silent=True)
        content = json.dumps(supplied) if isinstance(supplied, dict) else ""
    level = _automation_level()
    backup = parse_json_backup(content, parse_enabled=False)
    if backup.get("profile"):
        try:
            level = min(level, max(0, min(4, int(backup["profile"].get("automation_level", level)))))
        except (TypeError, ValueError):
            pass
    if level >= 1:
        backup = parse_json_backup(content, parse_enabled=True)
    if backup.get("profile"):
        restored_profile = dict(backup["profile"])
        for field in ("linkedin", "github", "portfolio"):
            if field in restored_profile:
                restored_profile[field] = _external_url(restored_profile[field], field.replace("_", " ").title())
        save_profile(restored_profile)
    profile = load_profile()
    session = Session()
    created = skipped = 0
    job_map: dict[int, int] = {}
    contact_map: dict[int, int] = {}
    try:
        for item in backup["jobs"]:
            existing = _existing_restore_job(session, item)
            if existing:
                skipped += 1
                old_job_id = _optional_int(item.get("id"))
                if old_job_id is not None:
                    job_map[old_job_id] = existing.id
                continue
            job = _new_job(item, profile, preserve_tracking=True, score_enabled=level >= 1)
            session.add(job)
            session.flush()
            old_job_id = _optional_int(item.get("id"))
            if old_job_id is not None:
                job_map[old_job_id] = job.id
            created += 1
        for raw in backup.get("contacts", []):
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            existing = None
            if raw.get("email"):
                existing = session.query(Contact).filter_by(email=raw["email"]).first()
            if not existing:
                existing = session.query(Contact).filter_by(name=raw["name"], company=raw.get("company")).first()
            if existing:
                contact = existing
            else:
                contact = Contact(
                    name=str(raw["name"])[:255], company=raw.get("company"), role=raw.get("role"),
                    email=raw.get("email"), linkedin=_external_url(raw.get("linkedin"), "LinkedIn URL"),
                    last_contact_date=parse_iso_date(raw.get("last_contact_date")), notes=raw.get("notes"),
                    follow_up_needed=_as_bool(raw.get("follow_up_needed")),
                    relationship_strength=raw.get("relationship_strength") or "new",
                )
                session.add(contact)
                session.flush()
            old_contact_id = _optional_int(raw.get("id"))
            if old_contact_id is not None:
                contact_map[old_contact_id] = contact.id
        for raw in backup.get("follow_ups", []):
            if not isinstance(raw, dict):
                continue
            mapped_job = job_map.get(_optional_int(raw.get("job_id")))
            mapped_contact = contact_map.get(_optional_int(raw.get("contact_id")))
            due = parse_iso_date(raw.get("due_date"))
            if not due:
                continue
            follow_up_values = {
                "job_id": mapped_job, "contact_id": mapped_contact,
                "follow_up_type": raw.get("follow_up_type") or "application",
                "due_date": due, "status": raw.get("status") or "pending",
                "message_draft": raw.get("message_draft"),
            }
            if not session.query(FollowUp.id).filter_by(**follow_up_values).first():
                session.add(FollowUp(**follow_up_values))
        for raw in backup.get("application_records", []):
            if not isinstance(raw, dict) or raw.get("job_id") is None:
                continue
            mapped_job = job_map.get(_optional_int(raw.get("job_id")))
            if not mapped_job:
                continue
            restored_job = session.get(Job, mapped_job)
            application_values = {
                "job_id": mapped_job,
                "application_date": parse_iso_date(raw.get("application_date")) or restored_job.applied_date or restored_job.discovered_date,
                "resume_used": raw.get("resume_used"), "cover_letter_used": raw.get("cover_letter_used"),
                "tailored_resume_used": raw.get("tailored_resume_used"),
                "application_method": raw.get("application_method"), "application_status": raw.get("application_status"),
                "follow_up_date": parse_iso_date(raw.get("follow_up_date")), "notes": raw.get("notes"),
            }
            if not session.query(ApplicationRecord.id).filter_by(**application_values).first():
                session.add(ApplicationRecord(**application_values))
        for raw in backup.get("drafts", []):
            if not isinstance(raw, dict) or raw.get("job_id") is None or not raw.get("content"):
                continue
            mapped_job = job_map.get(_optional_int(raw.get("job_id")))
            if not mapped_job:
                continue
            restored_content = raw["content"] if isinstance(raw["content"], str) else json.dumps(raw["content"])
            draft_type = raw.get("draft_type") if raw.get("draft_type") in {"resume_tailoring", "application_answers", "application_package", "restored_draft"} else "restored_draft"
            if session.query(TailoredDraft.id).filter_by(
                job_id=mapped_job, draft_type=draft_type,
                resume_profile=raw.get("resume_profile"), content=restored_content,
            ).first():
                continue
            file_path = None
            file_content = raw.get("file_content")
            if isinstance(file_content, str) and len(file_content.encode("utf-8")) <= 1_000_000:
                file_safety = validate_draft(file_content, profile)
                if file_safety["passed"]:
                    file_path = save_latex_draft(mapped_job, file_content)
            parsed_content = _json_load(restored_content, restored_content)
            relevant_content = _claim_relevant_content(parsed_content)
            relevant_text = json.dumps(relevant_content) if isinstance(relevant_content, (dict, list)) else str(relevant_content)
            restored_safety = validate_draft(relevant_text, profile)
            restored_status = raw.get("review_status") if raw.get("review_status") in {"draft", "reviewed"} else "draft"
            if not restored_safety["passed"]:
                restored_status = "draft"
            session.add(TailoredDraft(
                job_id=mapped_job, draft_type=draft_type,
                resume_profile=raw.get("resume_profile"), content=restored_content,
                file_path=file_path, review_status=restored_status,
                safety_report=json.dumps(restored_safety),
            ))
            if file_path:
                restored_job = session.get(Job, mapped_job)
                if restored_job:
                    restored_job.tailored_resume_path = file_path
        session.commit()
        return jsonify({
            "message": "Local JSON backup restored",
            "created_jobs": created, "skipped_duplicate_jobs": skipped,
            "profile_restored": bool(backup.get("profile")),
        })
    finally:
        session.close()


@app.get("/api/export")
def export_route():
    session = Session()
    try:
        jobs = session.query(Job).order_by(desc(Job.discovered_date)).all()
        format_name = request.args.get("format", "csv")
        if format_name == "json":
            content = export_json(
                jobs, load_profile(), session.query(Contact).all(), session.query(FollowUp).all(),
                session.query(TailoredDraft).all(), session.query(ApplicationRecord).all(),
            )
            return Response(content, mimetype="application/json", headers={"Content-Disposition": "attachment; filename=jobapplier_backup.json"})
        if format_name == "summary":
            return jsonify(summarize_jobs(jobs, session.query(ApplicationRecord).all()))
        return Response(export_csv(jobs), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=jobapplier_tracker.csv"})
    finally:
        session.close()


@app.route("/api/contacts", methods=["GET", "POST"])
def contacts_collection():
    session = Session()
    try:
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            if not payload.get("name"):
                return jsonify({"error": "Contact name is required"}), 400
            contact = Contact(
                name=str(payload["name"]).strip()[:255], company=payload.get("company"), role=payload.get("role"),
                email=payload.get("email"), linkedin=_external_url(payload.get("linkedin"), "LinkedIn URL"),
                notes=payload.get("notes"), relationship_strength=payload.get("relationship_strength", "new"),
                follow_up_needed=payload.get("follow_up_needed") is True,
                last_contact_date=parse_iso_date(payload.get("last_contact_date")),
            )
            session.add(contact)
            session.commit()
            return jsonify({"message": "Contact added", "id": contact.id}), 201
        contacts = session.query(Contact).order_by(desc(Contact.last_contact_date).nullslast(), Contact.name).all()
        return jsonify({"contacts": [{"id": c.id, "name": c.name, "company": c.company, "role": c.role, "email": c.email, "linkedin": c.linkedin, "notes": c.notes, "relationship_strength": c.relationship_strength, "follow_up_needed": c.follow_up_needed, "last_contact_date": _iso(c.last_contact_date)} for c in contacts]})
    finally:
        session.close()


@app.route("/api/contacts/<int:contact_id>", methods=["PATCH", "DELETE"])
def contact_detail(contact_id: int):
    session = Session()
    try:
        contact = session.get(Contact, contact_id)
        if not contact:
            return jsonify({"error": "Contact not found"}), 404
        if request.method == "DELETE":
            if session.query(FollowUp).filter_by(contact_id=contact.id, status="pending").first():
                return jsonify({"error": "Complete or remove pending follow-ups before deleting this contact."}), 409
            session.delete(contact)
            session.commit()
            return jsonify({"message": "Contact deleted"})
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({"error": "Contact update must be a JSON object."}), 400
        for field in ("name", "company", "role", "email", "notes", "relationship_strength"):
            if field in payload:
                setattr(contact, field, payload[field])
        if "linkedin" in payload:
            contact.linkedin = _external_url(payload["linkedin"], "LinkedIn URL")
        if "last_contact_date" in payload:
            contact.last_contact_date = parse_iso_date(payload["last_contact_date"])
        if "follow_up_needed" in payload:
            contact.follow_up_needed = payload["follow_up_needed"] is True
        session.commit()
        return jsonify({"message": "Contact updated"})
    finally:
        session.close()


@app.post("/api/contacts/<int:contact_id>/message")
def contact_message(contact_id: int):
    session = Session()
    try:
        contact = session.get(Contact, contact_id)
        if not contact:
            return jsonify({"error": "Contact not found"}), 404
        payload = request.get_json(silent=True) or {}
        job = session.get(Job, payload.get("job_id")) if payload.get("job_id") else None
        data = {column.name: getattr(contact, column.name) for column in Contact.__table__.columns}
        return jsonify({"message": recruiter_message(payload.get("kind", "application_follow_up"), data, _job_dict(job, True) if job else None), "review_required": True})
    finally:
        session.close()


@app.route("/api/follow-ups", methods=["GET", "POST"])
def followups_collection():
    session = Session()
    try:
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                return jsonify({"error": "Follow-up must be a JSON object."}), 400
            due = parse_iso_date(payload.get("due_date")) or suggested_follow_up(payload.get("type", "application"))
            job = session.get(Job, payload.get("job_id")) if payload.get("job_id") else None
            contact = session.get(Contact, payload.get("contact_id")) if payload.get("contact_id") else None
            if payload.get("job_id") and not job:
                return jsonify({"error": "Selected job does not exist."}), 400
            if payload.get("contact_id") and not contact:
                return jsonify({"error": "Selected contact does not exist."}), 400
            if not job and not contact:
                return jsonify({"error": "Choose a job or contact for the reminder."}), 400
            duplicate = session.query(FollowUp).filter_by(
                job_id=job.id if job else None, contact_id=contact.id if contact else None,
                follow_up_type=payload.get("type", "application"), status="pending",
            ).first()
            if duplicate:
                return jsonify({"error": "A pending reminder of this type already exists.", "follow_up_id": duplicate.id}), 409
            contact_data = {"name": contact.name, "company": contact.company, "role": contact.role} if contact else {"name": "Hiring Team", "company": job.company if job else "the company"}
            message_kind = {
                "interview_thank_you": "thank_you", "referral": "referral_request",
                "rejection_networking": "rejection_networking",
            }.get(payload.get("type"), "application_follow_up")
            message = payload.get("message_draft") or recruiter_message(message_kind, contact_data, _job_dict(job, True) if job else None)
            followup = FollowUp(job_id=payload.get("job_id"), contact_id=payload.get("contact_id"), follow_up_type=payload.get("type", "application"), due_date=due, message_draft=message, status="pending")
            session.add(followup)
            if job and (not job.follow_up_date or due < job.follow_up_date):
                job.follow_up_date = due
            if contact:
                contact.follow_up_needed = True
            session.commit()
            return jsonify({"message": "Follow-up reminder created", "id": followup.id}), 201
        items = session.query(FollowUp).order_by(asc(FollowUp.due_date)).all()
        return jsonify({"follow_ups": [{
            "id": item.id, "job_id": item.job_id, "contact_id": item.contact_id,
            "type": item.follow_up_type, "due_date": _iso(item.due_date),
            "status": item.status, "message_draft": item.message_draft,
        } for item in items]})
    finally:
        session.close()


@app.route("/api/follow-ups/<int:follow_up_id>", methods=["PATCH", "DELETE"])
def followup_detail(follow_up_id: int):
    session = Session()
    try:
        followup = session.get(FollowUp, follow_up_id)
        if not followup:
            return jsonify({"error": "Follow-up not found"}), 404
        if request.method == "DELETE":
            session.delete(followup)
            session.commit()
            return jsonify({"message": "Follow-up deleted"})
        payload = request.get_json(silent=True) or {}
        status = payload.get("status")
        if status and status not in {"pending", "completed", "dismissed"}:
            return jsonify({"error": "Unknown follow-up status."}), 400
        if status:
            followup.status = status
        if "due_date" in payload:
            due = parse_iso_date(payload["due_date"])
            if not due:
                return jsonify({"error": "Due date is invalid."}), 400
            followup.due_date = due
        if "message_draft" in payload:
            followup.message_draft = str(payload["message_draft"])
        if followup.contact_id and status in {"completed", "dismissed"}:
            contact = session.get(Contact, followup.contact_id)
            if contact and not session.query(FollowUp).filter(
                FollowUp.contact_id == contact.id, FollowUp.status == "pending", FollowUp.id != followup.id,
            ).first():
                contact.follow_up_needed = False
        session.commit()
        return jsonify({"message": "Follow-up updated"})
    finally:
        session.close()


@app.get("/api/analytics")
@app.get("/api/stats")
def analytics():
    session = Session()
    try:
        return jsonify(summarize_jobs(session.query(Job).all(), session.query(ApplicationRecord).all()))
    finally:
        session.close()


@app.post("/api/seed-demo")
def seed_demo():
    examples = [
        {"title": "Software Developer Intern", "company": "Northstar Demo", "location": "Toronto, ON", "source": "demo", "job_url": "https://demo.invalid/northstar-intern", "description": "Summer 2026 paid internship. Required: TypeScript, React, Git. Next.js preferred. Hybrid Toronto. No sponsorship available."},
        {"title": "QA Analyst Co-op", "company": "Maple Quality Demo", "location": "Remote Canada", "source": "demo", "job_url": "https://demo.invalid/maple-qa-coop", "description": "8 month co-op starting Fall 2026. Manual testing, regression testing, SQL, Selenium and bug reporting. Remote in Canada."},
        {"title": "Senior Platform Engineer", "company": "Example Systems", "location": "Vancouver, BC", "source": "demo", "job_url": "https://demo.invalid/senior-platform", "description": "Senior role requiring 5+ years, AWS, Kubernetes, Go, and production operations."},
    ]
    session = Session()
    level = _automation_level()
    try:
        for example in examples:
            parsed = parse_job_description(example["description"], example) if level >= 1 else {
                **example, "required_skills": [], "preferred_skills": [], "tech_stack": [], "required_documents": [],
            }
            if not session.query(Job).filter_by(job_url=parsed["job_url"]).first():
                session.add(_new_job(parsed, load_profile(), score_enabled=level >= 1))
        session.commit()
        return jsonify({"message": "Three demo jobs added"}), 201
    finally:
        session.close()


# Legacy routes are retained as explicit safety responses.
@app.post("/api/apply/batch")
def disabled_batch_apply():
    return jsonify({"error": "Blind or batch submission is disabled. Use each job's Prepare package action, review it, and submit manually."}), 403


@app.post("/api/search/start")
def restricted_search():
    return jsonify({"error": "Protected-board scraping is disabled in the dashboard. Add jobs manually, paste text, import CSV, or use an official API integration."}), 403


if __name__ == "__main__":
    if Config.DASHBOARD_HOST not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Refusing to expose private job data: DASHBOARD_HOST must be loopback-only.")
    print(f"JobApplier: http://{Config.DASHBOARD_HOST}:{Config.DASHBOARD_PORT}")
    print("Local-first. Application submission is always manual.")
    app.run(host=Config.DASHBOARD_HOST, port=Config.DASHBOARD_PORT, debug=False)
