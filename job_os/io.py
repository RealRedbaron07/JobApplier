"""CSV/JSON import and export helpers with formula-injection protection."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Dict, Iterable

from .parser import parse_job_description
from .scoring import score_job


IMPORT_ALIASES = {
    "application_url": "job_url", "url": "job_url", "job_title": "title",
    "date_found": "discovered_date", "pay": "salary", "status": "application_status",
}

EXPORT_FIELDS = [
    "id", "company", "title", "location", "work_mode", "application_status", "fit_category",
    "match_score", "source", "job_url", "discovered_date", "applied_date", "deadline",
    "salary_min", "salary_max", "resume_profile", "resume_version_used",
    "cover_letter_version_used", "contact_name", "follow_up_date", "notes",
]


def _safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def parse_csv(content: str) -> list[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    rows = []
    for raw in reader:
        normalized = {IMPORT_ALIASES.get((key or "").strip().lower(), (key or "").strip().lower()): (value or "").strip() for key, value in raw.items()}
        if not normalized.get("title") or not normalized.get("company"):
            continue
        parsed = parse_job_description(normalized.get("description", ""), normalized)
        rows.append(parsed)
    return rows


def job_to_dict(job: Any) -> Dict[str, Any]:
    data = {}
    for field in EXPORT_FIELDS:
        value = getattr(job, field, None)
        if isinstance(value, datetime):
            value = value.isoformat()
        data[field] = value
    return data


def export_csv(jobs: Iterable[Any]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for job in jobs:
        writer.writerow({key: _safe_cell(value) for key, value in job_to_dict(job).items()})
    return output.getvalue()


def export_json(jobs: Iterable[Any], profile: Dict[str, Any] | None = None) -> str:
    payload = {"exported_at": datetime.utcnow().isoformat() + "Z", "jobs": [job_to_dict(job) for job in jobs]}
    if profile is not None:
        payload["profile"] = profile
    return json.dumps(payload, indent=2)


def prepare_import(rows: Iterable[Dict[str, Any]], profile: Dict[str, Any]) -> list[Dict[str, Any]]:
    prepared = []
    for row in rows:
        result = score_job(row, profile)
        prepared.append({**row, "score": result})
    return prepared
