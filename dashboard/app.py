#!/usr/bin/env python3
"""Local-first Flask API and dashboard for the JobApplier operating system."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request
from sqlalchemy import asc, desc, or_

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config
from database.models import ApplicationRecord, Contact, FollowUp, Job, Session, TailoredDraft
from job_os.analytics import summarize_jobs
from job_os.drafts import generate_application_answers, recruiter_message
from job_os.io import export_csv, export_json, parse_csv, prepare_import
from job_os.parser import parse_iso_date, parse_job_description
from job_os.profile import load_profile, save_profile
from job_os.scoring import score_job
from job_os.tailoring import create_tailoring_plan, save_latex_draft
from job_os.workflow import STATUSES, can_transition, suggested_follow_up


app = Flask(__name__)
app.config.update(JSON_SORT_KEYS=False, MAX_CONTENT_LENGTH=4 * 1024 * 1024)


def _json_load(value, fallback):
    try:
        return json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback


def _iso(value):
    return value.isoformat() if value else None


def _job_dict(job: Job, detail: bool = False) -> dict:
    explanation = _json_load(job.match_explanation, {})
    data = {
        "id": job.id, "title": job.title, "company": job.company, "location": job.location,
        "work_mode": job.work_mode or "unknown", "source": job.source or job.platform or "manual",
        "job_url": job.job_url or "", "application_url": job.job_url or "",
        "application_status": job.application_status or "discovered", "applied": bool(job.applied),
        "match_score": job.match_score or 0, "fit_category": job.fit_category or "maybe",
        "resume_profile": job.resume_profile or explanation.get("resume_profile", "general_software"),
        "suggested_project": job.suggested_project or explanation.get("project_to_emphasize", "JobApplier"),
        "discovered_date": _iso(job.discovered_date), "applied_date": _iso(job.applied_date),
        "deadline": _iso(job.deadline), "follow_up_date": _iso(job.follow_up_date),
        "salary_min": job.salary_min, "salary_max": job.salary_max,
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


def _new_job(parsed: dict, profile: dict) -> Job:
    result = score_job(parsed, profile)
    job = Job(
        title=parsed["title"], company=parsed["company"], location=parsed.get("location"),
        platform=parsed.get("source", "manual"), source=parsed.get("source", "manual"),
        job_url=parsed.get("job_url") or None, description=parsed.get("description"),
        work_mode=parsed.get("work_mode"), term_length=parsed.get("term_length"),
        start_date=parsed.get("start_date"), required_skills=json.dumps(parsed.get("required_skills", [])),
        preferred_skills=json.dumps(parsed.get("preferred_skills", [])), tech_stack=json.dumps(parsed.get("tech_stack", [])),
        work_authorization=parsed.get("work_authorization"), sponsorship=parsed.get("sponsorship"),
        coop_eligible=parsed.get("coop_eligible"), industry=parsed.get("industry"),
        seniority_level=parsed.get("seniority_level"), deadline=parse_iso_date(parsed.get("deadline")),
        salary_min=parsed.get("salary_min"), salary_max=parsed.get("salary_max"),
        application_effort=parsed.get("application_effort"), required_documents=json.dumps(parsed.get("required_documents", [])),
        login_portal=parsed.get("login_portal"), notes=parsed.get("notes", ""),
        application_status="discovered", applied=False, discovered_date=datetime.now(timezone.utc),
    )
    _apply_score(job, parsed, result)
    return job


@app.get("/")
def index():
    return render_template("index.html", automation_level=Config.AUTOMATION_LEVEL)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "local_first": True, "auto_submit": False, "automation_level": Config.AUTOMATION_LEVEL})


@app.route("/api/profile", methods=["GET", "PUT"])
@app.route("/api/settings", methods=["GET", "POST"])
def profile_settings():
    if request.method in ("PUT", "POST"):
        profile = save_profile(request.get_json(silent=True) or {})
        return jsonify({"message": "Profile saved locally", "profile": profile})
    return jsonify(load_profile())


@app.post("/api/jobs/parse")
def parse_preview():
    payload = request.get_json(silent=True) or {}
    parsed = parse_job_description(payload.get("description", ""), payload)
    return jsonify({"parsed": parsed, "score": score_job(parsed, load_profile())})


@app.route("/api/jobs", methods=["GET", "POST"])
def jobs_collection():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        if not payload.get("description") and not payload.get("title"):
            return jsonify({"error": "Provide a title or pasted job description."}), 400
        parsed = parse_job_description(payload.get("description", ""), payload)
        session = Session()
        try:
            if parsed.get("job_url"):
                existing = session.query(Job).filter_by(job_url=parsed["job_url"]).first()
                if existing:
                    return jsonify({"error": "That application URL is already tracked.", "job_id": existing.id}), 409
            job = _new_job(parsed, load_profile())
            session.add(job)
            session.commit()
            return jsonify({"message": "Job added and scored", "job": _job_dict(job, True)}), 201
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
        column = getattr(Job, sort, Job.match_score)
        query = query.order_by(desc(column).nullslast() if request.args.get("order", "desc") == "desc" else asc(column).nullslast())
        rows = query.limit(min(500, int(request.args.get("limit", 200)))).all()
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
            target = payload.get("application_status")
            current = job.application_status or "discovered"
            if target and not can_transition(current, target):
                return jsonify({"error": f"Invalid status transition: {current} -> {target}"}), 409
            editable = ("notes", "deadline", "follow_up_date", "contact_name", "contact_details", "login_portal", "salary_min", "salary_max")
            for field in editable:
                if field not in payload:
                    continue
                value = payload[field]
                if field in ("deadline", "follow_up_date"):
                    value = parse_iso_date(value)
                setattr(job, field, value)
            if target:
                job.application_status = target
                if target == "applied":
                    job.applied = True
                    job.applied_date = job.applied_date or datetime.now(timezone.utc)
                    job.follow_up_date = job.follow_up_date or suggested_follow_up("application", job.applied_date)
                    session.add(ApplicationRecord(job_id=job.id, application_date=job.applied_date, application_status="applied", application_method="human_confirmed", notes="User confirmed submission outside JobApplier."))
                elif target in ("discovered", "interested", "resume_tailored"):
                    job.applied = False
            session.commit()
            return jsonify({"message": "Job updated", "job": _job_dict(job, True)})
        return jsonify(_job_dict(job, True))
    finally:
        session.close()


@app.post("/api/jobs/<int:job_id>/rescore")
def rescore_job(job_id: int):
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
    session = Session()
    try:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        profile = load_profile()
        job_data = _job_dict(job, True)
        scoring = _json_load(job.match_explanation, score_job(job_data, profile))
        selected = (request.get_json(silent=True) or {}).get("resume_profile") or job.resume_profile
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
    session = Session()
    try:
        job = session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        answers = generate_application_answers(_job_dict(job, True), load_profile())
        draft = TailoredDraft(job_id=job.id, draft_type="application_answers", content=json.dumps(answers), review_status="draft", safety_report=json.dumps({"passed": True, "requires_human_review": True}))
        session.add(draft)
        session.commit()
        return jsonify({"message": "Editable answer drafts created", "draft_id": draft.id, "answers": answers})
    finally:
        session.close()


@app.post("/api/jobs/<int:job_id>/prepare")
def prepare_package(job_id: int):
    """Prepare materials only. This endpoint never opens or submits an application."""
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
        session.add(TailoredDraft(job_id=job.id, draft_type="application_package", resume_profile=plan["resume_profile"], content=json.dumps({"tailoring": plan, "answers": answers}), file_path=latex_path, review_status="draft", safety_report=json.dumps(plan["safety_report"])))
        job.tailored_resume_path = latex_path
        job.application_status = "resume_tailored" if can_transition(job.application_status, "resume_tailored") else job.application_status
        job.next_action = "Review the LaTeX draft and answers, complete the checklist, then submit manually on the official portal."
        session.commit()
        return jsonify({"message": "Application package prepared; nothing was submitted", "latex_path": latex_path, "tailoring": plan, "answers": answers, "checklist": ["Verify company and role details", "Review every resume claim", "Resolve safety warnings", "Confirm work authorization answer", "Check one-page PDF output", "Submit manually on the official portal", "Return and mark the job applied"]})
    finally:
        session.close()


@app.get("/api/jobs/<int:job_id>/drafts")
def list_drafts(job_id: int):
    session = Session()
    try:
        drafts = session.query(TailoredDraft).filter_by(job_id=job_id).order_by(desc(TailoredDraft.created_date)).all()
        return jsonify({"drafts": [{"id": d.id, "type": d.draft_type, "profile": d.resume_profile, "content": _json_load(d.content, d.content), "file_path": d.file_path, "review_status": d.review_status, "created_date": _iso(d.created_date)} for d in drafts]})
    finally:
        session.close()


@app.post("/api/import/csv")
def import_csv_route():
    content = request.files["file"].read().decode("utf-8-sig") if "file" in request.files else (request.get_json(silent=True) or {}).get("csv", "")
    rows = prepare_import(parse_csv(content), load_profile())
    session = Session()
    created = 0
    skipped = 0
    try:
        for item in rows:
            if item.get("job_url") and session.query(Job).filter_by(job_url=item["job_url"]).first():
                skipped += 1
                continue
            session.add(_new_job(item, load_profile()))
            created += 1
        session.commit()
        return jsonify({"message": "CSV import complete", "created": created, "skipped_duplicates": skipped})
    finally:
        session.close()


@app.get("/api/export")
def export_route():
    session = Session()
    try:
        jobs = session.query(Job).order_by(desc(Job.discovered_date)).all()
        format_name = request.args.get("format", "csv")
        if format_name == "json":
            return Response(export_json(jobs), mimetype="application/json", headers={"Content-Disposition": "attachment; filename=jobapplier_export.json"})
        if format_name == "summary":
            return jsonify(summarize_jobs(jobs))
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
            contact = Contact(name=payload["name"], company=payload.get("company"), role=payload.get("role"), email=payload.get("email"), linkedin=payload.get("linkedin"), notes=payload.get("notes"), relationship_strength=payload.get("relationship_strength", "new"), follow_up_needed=bool(payload.get("follow_up_needed")))
            session.add(contact)
            session.commit()
            return jsonify({"message": "Contact added", "id": contact.id}), 201
        contacts = session.query(Contact).order_by(desc(Contact.last_contact_date).nullslast(), Contact.name).all()
        return jsonify({"contacts": [{"id": c.id, "name": c.name, "company": c.company, "role": c.role, "email": c.email, "linkedin": c.linkedin, "notes": c.notes, "relationship_strength": c.relationship_strength, "follow_up_needed": c.follow_up_needed, "last_contact_date": _iso(c.last_contact_date)} for c in contacts]})
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
            due = parse_iso_date(payload.get("due_date")) or suggested_follow_up(payload.get("type", "application"))
            job = session.get(Job, payload.get("job_id")) if payload.get("job_id") else None
            contact = session.get(Contact, payload.get("contact_id")) if payload.get("contact_id") else None
            contact_data = {"name": contact.name, "company": contact.company, "role": contact.role} if contact else {"name": "Hiring Team", "company": job.company if job else "the company"}
            message_kind = {"interview_thank_you": "thank_you", "referral": "referral_request"}.get(payload.get("type"), "application_follow_up")
            message = payload.get("message_draft") or recruiter_message(message_kind, contact_data, _job_dict(job, True) if job else None)
            followup = FollowUp(job_id=payload.get("job_id"), contact_id=payload.get("contact_id"), follow_up_type=payload.get("type", "application"), due_date=due, message_draft=message, status="pending")
            session.add(followup)
            session.commit()
            return jsonify({"message": "Follow-up reminder created", "id": followup.id}), 201
        items = session.query(FollowUp).order_by(asc(FollowUp.due_date)).all()
        return jsonify({"follow_ups": [{"id": item.id, "job_id": item.job_id, "contact_id": item.contact_id, "type": item.follow_up_type, "due_date": _iso(item.due_date), "status": item.status, "message_draft": item.message_draft} for item in items]})
    finally:
        session.close()


@app.get("/api/analytics")
@app.get("/api/stats")
def analytics():
    session = Session()
    try:
        return jsonify(summarize_jobs(session.query(Job).all()))
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
    try:
        for example in examples:
            parsed = parse_job_description(example["description"], example)
            if not session.query(Job).filter_by(job_url=parsed["job_url"]).first():
                session.add(_new_job(parsed, load_profile()))
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
    print(f"JobApplier: http://{Config.DASHBOARD_HOST}:{Config.DASHBOARD_PORT}")
    print("Local-first. Application submission is always manual.")
    app.run(host=Config.DASHBOARD_HOST, port=Config.DASHBOARD_PORT, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
