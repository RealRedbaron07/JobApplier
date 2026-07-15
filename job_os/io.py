"""CSV/JSON import and export helpers with formula-injection protection."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from config import Config
from .parser import parse_job_description
from .scoring import score_job


IMPORT_ALIASES = {
    "application_url": "job_url", "url": "job_url", "job_title": "title",
    "date_found": "discovered_date", "pay": "salary", "status": "application_status",
}

EXPORT_FIELDS = [
    "id", "company", "title", "location", "work_mode", "application_status", "fit_category",
    "match_score", "source", "job_url", "discovered_date", "applied_date", "deadline",
    "posted_date", "job_type", "term_length", "start_date", "salary", "salary_min",
    "salary_max", "salary_unit", "salary_currency", "resume_profile", "resume_version_used",
    "cover_letter_version_used", "contact_name", "contact_details", "follow_up_date",
    "required_documents", "login_portal", "notes",
]

JSON_JOB_FIELDS = [
    "id", "title", "company", "location", "platform", "job_url", "description", "requirements",
    "salary", "salary_min", "salary_max", "salary_unit", "salary_currency", "job_type",
    "posted_date", "discovered_date", "work_mode", "term_length", "start_date",
    "required_skills", "preferred_skills", "work_authorization", "sponsorship", "coop_eligible",
    "tech_stack", "industry", "seniority_level", "deadline", "source", "required_documents",
    "login_portal", "fit_category", "match_score", "score_breakdown", "match_explanation",
    "safety_flags", "resume_profile", "suggested_project", "next_action", "application_effort",
    "application_status", "applied", "applied_date", "application_method", "application_notes",
    "notes", "contact_name", "contact_details", "follow_up_date", "resume_version_used",
    "cover_letter_version_used", "tailored_resume_path", "original_resume_path",
    "cover_letter", "cover_letter_path", "external_site", "external_url",
]

TRACKER_IMPORT_FIELDS = {
    "id", "application_status", "fit_category", "match_score", "discovered_date", "applied_date",
    "posted_date", "deadline", "follow_up_date", "resume_profile", "resume_version_used",
    "cover_letter_version_used", "contact_name", "contact_details", "application_method",
    "application_notes", "applied", "next_action", "suggested_project",
    "score_breakdown", "match_explanation", "safety_flags",
}

LIST_FIELDS = {"required_skills", "preferred_skills", "tech_stack", "required_documents"}
JSON_TEXT_FIELDS = {
    "title", "company", "location", "platform", "job_url", "description", "requirements",
    "salary", "salary_unit", "salary_currency", "job_type", "work_mode", "term_length",
    "start_date", "work_authorization", "sponsorship", "industry", "seniority_level",
    "source", "login_portal", "fit_category", "resume_profile", "suggested_project",
    "next_action", "application_effort", "application_status", "application_method",
    "application_notes", "notes", "contact_name", "contact_details", "resume_version_used",
    "cover_letter_version_used", "tailored_resume_path", "original_resume_path",
    "cover_letter", "cover_letter_path", "external_url",
}


def _safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip()[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def parse_csv(content: str, parse_enabled: bool = True) -> list[Dict[str, Any]]:
    if not isinstance(content, str):
        raise ValueError("CSV import must be text.")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    rows = []
    for raw in reader:
        normalized = {IMPORT_ALIASES.get((key or "").strip().lower(), (key or "").strip().lower()): (value or "").strip() for key, value in raw.items()}
        if not normalized.get("title") or not normalized.get("company"):
            continue
        parsed = (
            parse_job_description(normalized.get("description", ""), normalized)
            if parse_enabled else
            {**normalized, "required_skills": [], "preferred_skills": [], "tech_stack": [], "required_documents": []}
        )
        for field in TRACKER_IMPORT_FIELDS:
            if normalized.get(field) not in (None, ""):
                parsed[field] = normalized[field]
        for field in LIST_FIELDS:
            if not normalized.get(field):
                continue
            try:
                value = json.loads(normalized[field])
                if isinstance(value, list):
                    parsed[field] = value
            except (TypeError, json.JSONDecodeError):
                parsed[field] = [item.strip() for item in normalized[field].split("|") if item.strip()]
        rows.append(parsed)
    return rows


def _record_to_dict(record: Any, fields: Iterable[str]) -> Dict[str, Any]:
    data = {}
    for field in fields:
        value = record.get(field) if isinstance(record, dict) else getattr(record, field, None)
        if isinstance(value, datetime):
            value = value.isoformat()
        data[field] = value
    return data


def job_to_dict(job: Any, detailed: bool = False) -> Dict[str, Any]:
    return _record_to_dict(job, JSON_JOB_FIELDS if detailed else EXPORT_FIELDS)


def export_csv(jobs: Iterable[Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for job in jobs:
        row = {}
        for key, value in job_to_dict(job).items():
            if isinstance(value, (list, dict)):
                value = json.dumps(value)
            row[key] = _safe_cell(value)
        writer.writerow(row)
    return output.getvalue()


def export_json(
    jobs: Iterable[Any],
    profile: Dict[str, Any] | None = None,
    contacts: Iterable[Any] | None = None,
    follow_ups: Iterable[Any] | None = None,
    drafts: Iterable[Any] | None = None,
    application_records: Iterable[Any] | None = None,
) -> str:
    payload = {
        "schema_version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "jobs": [job_to_dict(job, detailed=True) for job in jobs],
    }
    if profile is not None:
        payload["profile"] = profile
    if contacts is not None:
        payload["contacts"] = [_record_to_dict(item, (
            "id", "name", "company", "role", "email", "linkedin", "last_contact_date",
            "notes", "follow_up_needed", "relationship_strength",
        )) for item in contacts]
    if follow_ups is not None:
        payload["follow_ups"] = [_record_to_dict(item, (
            "id", "job_id", "contact_id", "follow_up_type", "due_date", "status",
            "message_draft", "created_date",
        )) for item in follow_ups]
    if drafts is not None:
        payload["drafts"] = []
        draft_root = Path(Config.DRAFTS_DIR).resolve()
        for item in drafts:
            draft = _record_to_dict(item, (
                "id", "job_id", "draft_type", "resume_profile", "content", "file_path",
                "review_status", "safety_report", "created_date", "updated_date",
            ))
            raw_path = draft.get("file_path")
            if raw_path:
                try:
                    path = Path(raw_path).resolve()
                    if path.suffix.lower() == ".tex" and draft_root in path.parents and path.is_file() and path.stat().st_size <= 1_000_000:
                        draft["file_content"] = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    pass
            payload["drafts"].append(draft)
    if application_records is not None:
        payload["application_records"] = [_record_to_dict(item, (
            "id", "job_id", "application_date", "resume_used", "cover_letter_used",
            "tailored_resume_used", "application_method", "application_status",
            "follow_up_date", "notes",
        )) for item in application_records]
    return json.dumps(payload, indent=2)


def parse_json_backup(content: str, parse_enabled: bool = True) -> Dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("JSON import must be text.")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("The selected file is not valid JSON.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs", []), list):
        raise ValueError("JSON backup must be an object with a jobs list.")
    jobs = []
    for raw in payload.get("jobs", []):
        if not isinstance(raw, dict) or not isinstance(raw.get("title"), str) or not raw["title"].strip() or not isinstance(raw.get("company"), str) or not raw["company"].strip():
            continue
        for field in JSON_TEXT_FIELDS:
            if raw.get(field) not in (None, "") and not isinstance(raw[field], str):
                raise ValueError(f"JSON backup field {field} must be text when present.")
        parsed = (
            parse_job_description(raw.get("description", ""), raw)
            if parse_enabled else
            {**raw, "required_skills": [], "preferred_skills": [], "tech_stack": [], "required_documents": []}
        )
        # A backup is authoritative for fields it already contains. Parsing may
        # fill gaps, but it must not silently discard tracker data or local draft
        # references during a round trip.
        for field in JSON_JOB_FIELDS:
            if field in raw and raw[field] not in (None, ""):
                parsed[field] = raw[field]
        for field in TRACKER_IMPORT_FIELDS:
            if raw.get(field) not in (None, ""):
                parsed[field] = raw[field]
        for field in LIST_FIELDS:
            value = raw.get(field)
            if value in (None, ""):
                continue
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = [item.strip() for item in value.split("|") if item.strip()]
            if isinstance(value, list):
                parsed[field] = value
        jobs.append(parsed)
    return {
        "schema_version": payload.get("schema_version", 1),
        "jobs": jobs,
        "profile": payload.get("profile") if isinstance(payload.get("profile"), dict) else None,
        "contacts": payload.get("contacts", []) if isinstance(payload.get("contacts", []), list) else [],
        "follow_ups": payload.get("follow_ups", []) if isinstance(payload.get("follow_ups", []), list) else [],
        "drafts": payload.get("drafts", []) if isinstance(payload.get("drafts", []), list) else [],
        "application_records": payload.get("application_records", []) if isinstance(payload.get("application_records", []), list) else [],
    }


def prepare_import(rows: Iterable[Dict[str, Any]], profile: Dict[str, Any]) -> list[Dict[str, Any]]:
    prepared = []
    for row in rows:
        result = score_job(row, profile)
        prepared.append({**row, "score": result})
    return prepared
