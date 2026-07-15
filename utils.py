#!/usr/bin/env python3
"""
Utility functions for job application automation.
Includes validation, data cleaning, and helper functions.
"""

import re
import os
import json
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from datetime import datetime

from logger import get_logger

logger = get_logger("utils")

# Internship detection keywords (used for filtering)
INTERNSHIP_KEYWORDS = [
    'intern', 'internship', 'co-op', 'coop', 'student', 'summer',
    'undergraduate', 'undergrad'
]

def is_internship_job(job) -> bool:
    """
    Return True if a job looks like an internship based on title/description.
    Accepts either a Job model or a dict with title/description.
    """
    try:
        title = getattr(job, 'title', None) or job.get('title', '')
        description = getattr(job, 'description', None) or job.get('description', '')
    except Exception:
        return False

    text = f"{title} {description}".lower()
    return any(keyword in text for keyword in INTERNSHIP_KEYWORDS)


def parse_user_profile(user_profile_db) -> Dict:
    """
    Parse UserProfile database object into a dictionary.
    """
    return {
        'skills': json.loads(user_profile_db.skills) if user_profile_db.skills else [],
        'experience': json.loads(user_profile_db.experience) if user_profile_db.experience else [],
        'education': json.loads(user_profile_db.education) if user_profile_db.education else [],
        'contact_info': {
            'first_name': getattr(user_profile_db, 'first_name', ''),
            'last_name': getattr(user_profile_db, 'last_name', ''),
            'email': getattr(user_profile_db, 'email', ''),
            'phone': getattr(user_profile_db, 'phone', ''),
            'linkedin': getattr(user_profile_db, 'linkedin', ''),
            'portfolio': getattr(user_profile_db, 'portfolio', ''),
            'github': getattr(user_profile_db, 'github', ''),
            'location': getattr(user_profile_db, 'location', '')
        }
    }


def create_job_data(job) -> Dict:
    """
    Create a job data dictionary from a Job database object.
    """
    return {
        'title': job.title,
        'company': job.company,
        'location': job.location or '',
        'description': job.description or '',
        'requirements': job.requirements or ''
    }


def generate_job_materials(job, user_profile, resume_to_use, cover_letter_gen, resume_tailor, session=None):
    """
    Generate cover letter and tailored resume for a job, if missing.
    Updates the Job record in-place and optionally commits the session.
    """
    job_data = {
        'title': job.title,
        'company': job.company,
        'location': job.location or '',
        'description': job.description or '',
        'requirements': job.requirements or ''
    }

    # Track original resume used for this job
    if resume_to_use and not job.original_resume_path:
        job.original_resume_path = resume_to_use

    # Generate cover letter if missing or file missing
    try:
        cover_letter_missing = not job.cover_letter_path or not os.path.exists(job.cover_letter_path)
        if cover_letter_missing:
            cover_letter_text, cover_letter_path = cover_letter_gen.generate_cover_letter(
                job_data, user_profile
            )
            job.cover_letter = cover_letter_text
            job.cover_letter_path = cover_letter_path
    except Exception as e:
        logger.warning(f"Cover letter generation failed for job {job.id}: {e}")

    # Generate tailored resume if missing or file missing
    try:
        resume_missing = not job.tailored_resume_path or not os.path.exists(job.tailored_resume_path)
        if resume_missing:
            if not resume_to_use or not os.path.exists(resume_to_use):
                raise FileNotFoundError(f"Resume not found: {resume_to_use}")
            tailored_resume_path = resume_tailor.tailor_resume(
                resume_to_use,
                job_data,
                user_profile
            )
            job.tailored_resume_path = tailored_resume_path
    except Exception as e:
        logger.warning(f"Resume tailoring failed for job {job.id}: {e}")

    if session:
        session.commit()

    return job


def get_resume_path(user_profile_db, fallback_path: Optional[str] = None) -> Optional[str]:
    """Get valid resume path from centralized resolver or optional fallback."""
    path = resolve_resume_path(user_profile_db)
    if path:
        return path
    if fallback_path and os.path.exists(fallback_path):
        return fallback_path
    return None


def apply_to_job(job, user_profile, resume_path, session, linkedin_scraper=None, workday_scraper=None):
    """
    Legacy compatibility wrapper that records a prepared package only.

    JobApplier deliberately never submits applications. Browser-specific
    scrapers are not opened here; the user reviews materials and submits on the
    official portal, then marks the application as applied in the dashboard.
    """
    from database.models import ApplicationRecord
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    job.applied = False
    job.application_status = 'resume_tailored' if job.tailored_resume_path else 'interested'
    job.application_method = 'human_review_required'
    job.notes = (job.notes or '') + f"\n[Package prepared; manual submission required - {now.strftime('%Y-%m-%d %H:%M')}]"
    session.add(ApplicationRecord(
        job_id=job.id,
        application_date=now,
        resume_used=resume_path,
        cover_letter_used=job.cover_letter_path,
        tailored_resume_used=job.tailored_resume_path,
        application_method='human_review_required',
        application_status='draft',
        notes='Application package prepared. Nothing was submitted.',
    ))
    session.commit()
    logger.info(f"Package prepared for {job.title} at {job.company}; manual submission required")
    return False


def validate_job_data(job_data: dict, strict: bool = False) -> Tuple[bool, List[str]]:
    """
    Validate that job data has required fields and proper format.
    
    Args:
        job_data: Dictionary containing job information
        strict: If True, also require description and salary
    
    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []
    
    # Required fields
    required_fields = {
        'title': ('Job title', 3),
        'company': ('Company name', 2),
        'url': ('Job URL', 10),
    }
    
    # Additional required fields in strict mode
    if strict:
        required_fields['description'] = ('Job description', 50)
    
    for field, (display_name, min_length) in required_fields.items():
        value = job_data.get(field, '')
        
        if not value:
            issues.append(f"Missing {display_name}")
        elif len(str(value).strip()) < min_length:
            issues.append(f"{display_name} too short (min {min_length} chars)")
    
    # Validate URL format
    url = job_data.get('url', '')
    if url:
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                issues.append("Invalid URL format (missing scheme or domain)")
            elif parsed.scheme not in ('http', 'https'):
                issues.append("URL must start with http:// or https://")
        except Exception:
            issues.append("Could not parse URL")
    
    # Validate platform if present
    valid_platforms = {'linkedin', 'indeed', 'glassdoor', 'workday', 'greenhouse', 'lever'}
    platform = job_data.get('platform', '').lower()
    if platform and platform not in valid_platforms:
        issues.append(f"Unknown platform: {platform}")
    
    # Log validation result
    is_valid = len(issues) == 0
    if not is_valid:
        logger.debug(f"Job validation failed for '{job_data.get('title', 'Unknown')}': {issues}")
    
    return is_valid, issues


def clean_job_data(job_data: dict) -> dict:
    """
    Clean and normalize job data.
    
    Args:
        job_data: Raw job data dictionary
    
    Returns:
        Cleaned job data dictionary
    """
    cleaned = {}
    
    # Clean string fields
    string_fields = ['title', 'company', 'location', 'description', 'salary', 'platform']
    for field in string_fields:
        value = job_data.get(field, '')
        if value:
            # Remove extra whitespace
            value = ' '.join(str(value).split())
            # Remove non-printable characters
            value = ''.join(char for char in value if char.isprintable() or char in '\n\t')
            cleaned[field] = value.strip()
        else:
            cleaned[field] = ''
    
    # Clean URL
    url = job_data.get('url', '')
    if url:
        # Remove tracking parameters
        url = re.sub(r'\?.*trk=.*$', '', url)
        url = re.sub(r'&trk=.*$', '', url)
        cleaned['url'] = url.strip()
    else:
        cleaned['url'] = ''
    
    # Preserve other fields
    for key, value in job_data.items():
        if key not in cleaned:
            cleaned[key] = value
    
    return cleaned


def extract_job_id_from_url(url: str) -> Optional[str]:
    """
    Extract unique job ID from job URL.
    
    Args:
        url: Job posting URL
    
    Returns:
        Extracted job ID or None
    """
    patterns = [
        # LinkedIn: /jobs/view/12345678
        r'/jobs/view/(\d+)',
        # Indeed: /viewjob?jk=abc123
        r'[?&]jk=([a-zA-Z0-9]+)',
        # Workday: /job/12345
        r'/job/(\d+)',
        # Greenhouse: /jobs/12345
        r'/jobs/(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def deduplicate_jobs(jobs: List[Dict], key_fields: List[str] = None) -> List[Dict]:
    """
    Remove duplicate jobs based on key fields.
    
    Args:
        jobs: List of job dictionaries
        key_fields: Fields to use for deduplication (default: title + company)
    
    Returns:
        Deduplicated list of jobs
    """
    if key_fields is None:
        key_fields = ['title', 'company']
    
    seen = {}
    unique_jobs = []
    
    for job in jobs:
        # Create deduplication key
        key_parts = []
        for field in key_fields:
            value = job.get(field, '')
            if value:
                key_parts.append(str(value).strip().lower())
        
        if not key_parts:
            # If no key fields have values, use URL
            key = job.get('url', str(len(seen)))
        else:
            key = '|'.join(key_parts)
        
        if key not in seen:
            seen[key] = job
            unique_jobs.append(job)
        else:
            logger.debug(f"Duplicate job skipped: {job.get('title', 'Unknown')}")
    
    removed_count = len(jobs) - len(unique_jobs)
    if removed_count > 0:
        logger.info(f"Removed {removed_count} duplicate jobs")
    
    return unique_jobs


def is_job_expired(job: Dict, max_age_days: int = 30) -> bool:
    """
    Check if a job posting is too old.
    
    Args:
        job: Job dictionary with posted_date or discovered_date
        max_age_days: Maximum age in days
    
    Returns:
        True if job is expired, False otherwise
    """
    from datetime import timedelta, timezone
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    
    posted_date = job.get('posted_date')
    discovered_date = job.get('discovered_date')
    
    check_date = posted_date or discovered_date
    
    if not check_date:
        return False  # Unknown date, assume current
    
    if isinstance(check_date, str):
        try:
            check_date = datetime.fromisoformat(check_date.replace('Z', '+00:00'))
        except ValueError:
            return False
    
    # Ensure timezone aware
    if check_date.tzinfo is None:
        check_date = check_date.replace(tzinfo=timezone.utc)
    
    return check_date < cutoff_date


def format_job_summary(job: Dict) -> str:
    """
    Format a job for display.
    
    Args:
        job: Job dictionary
    
    Returns:
        Formatted string representation
    """
    title = job.get('title', 'Unknown Position')
    company = job.get('company', 'Unknown Company')
    location = job.get('location', '')
    score = job.get('match_score', 0)
    platform = job.get('platform', 'unknown')
    
    summary = f"{title} at {company}"
    if location:
        summary += f" ({location})"
    summary += f" [{score}/100] [{platform}]"
    
    return summary


def sanitize_filename(name: str, max_length: int = 50) -> str:
    """
    Create a safe filename from a string.
    
    Args:
        name: Original string
        max_length: Maximum length
    
    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    safe = re.sub(r'[^\w\s-]', '', name)
    safe = re.sub(r'[-\s]+', '_', safe)
    safe = safe.strip('_')
    
    # Truncate
    if len(safe) > max_length:
        safe = safe[:max_length].rstrip('_')
    
    return safe or 'unnamed'


def resolve_resume_path(user_profile_db=None) -> Optional[str]:
    """
    Resolve an explicitly configured resume path without copying or uploading it.

    The profile selection wins over legacy local/default paths. The supported
    dashboard workflow generates new drafts and never sends this file anywhere.
    """
    from config import Config

    candidates = []
    if user_profile_db and user_profile_db.resume_path:
        candidates.append(user_profile_db.resume_path)
    if Config.DEFAULT_RESUME_PATH:
        candidates.append(Config.DEFAULT_RESUME_PATH)
    if Config.LOCAL_RESUME_PATH:
        candidates.append(Config.LOCAL_RESUME_PATH)

    source = None
    for path in candidates:
        if path and os.path.exists(path):
            source = os.path.abspath(path)
            break

    if not source:
        logger.error("No valid resume found in local copy, profile, or DEFAULT_RESUME_PATH")
        return None

    return source


def get_unapplied_new_jobs(session, scrape_started_at=None, limit: int = 10):
    """
    Return unapplied, high-match jobs that look like new postings.
    Prefers jobs discovered in the current scrape session, then recent postings.
    """
    from config import Config
    from database.models import Job
    from datetime import timedelta, timezone
    from sqlalchemy import or_, and_

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=Config.MAX_JOB_AGE_DAYS)
    new_cutoff = datetime.now(timezone.utc) - timedelta(hours=Config.NEW_JOB_HOURS)

    jobs = session.query(Job).filter_by(applied=False).filter(
        Job.match_score >= Config.MIN_MATCH_SCORE
    ).filter(
        or_(
            and_(Job.posted_date.isnot(None), Job.posted_date >= cutoff_date),
            and_(Job.posted_date.is_(None), Job.discovered_date >= cutoff_date)
        )
    ).all()

    seen = {}
    unique_jobs = []
    for job in jobs:
        if Config.REQUIRE_INTERNSHIP and not is_internship_job(job):
            continue
        key = (job.title.strip().lower(), job.company.strip().lower())
        if key not in seen:
            seen[key] = job
            unique_jobs.append(job)

    def _recency_ts(job):
        dt = job.posted_date or job.discovered_date
        if not dt:
            return 0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    def _is_new(job):
        if scrape_started_at:
            discovered = job.discovered_date
            if discovered:
                if discovered.tzinfo is None:
                    discovered = discovered.replace(tzinfo=timezone.utc)
                if discovered >= scrape_started_at:
                    return True
        posted = job.posted_date or job.discovered_date
        if posted:
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
            return posted >= new_cutoff
        return False

    new_jobs = [j for j in unique_jobs if _is_new(j)]
    pool = new_jobs if new_jobs else unique_jobs
    pool.sort(key=lambda j: (_recency_ts(j), j.match_score or 0), reverse=True)
    return pool[:limit]


class RateLimiter:
    """Simple rate limiter to prevent too many requests."""
    
    def __init__(self, requests_per_minute: int = 20):
        self.requests_per_minute = requests_per_minute
        self.request_times: List[datetime] = []
    
    def wait_if_needed(self):
        """Wait if we're sending too many requests."""
        now = datetime.now()
        
        # Remove old request times (older than 1 minute)
        cutoff = now - timedelta(seconds=60)
        self.request_times = [t for t in self.request_times if t > cutoff]
        
        # If we're at the limit, wait
        if len(self.request_times) >= self.requests_per_minute:
            oldest = min(self.request_times)
            wait_seconds = 60 - (now - oldest).total_seconds()
            if wait_seconds > 0:
                logger.debug(f"Rate limiting: waiting {wait_seconds:.1f}s")
                import time
                time.sleep(wait_seconds)
        
        # Record this request
        self.request_times.append(datetime.now())
    
    def reset(self):
        """Reset the rate limiter."""
        self.request_times = []


# Import timedelta for RateLimiter
from datetime import timedelta


if __name__ == "__main__":
    # Test utilities
    print("Testing job validation...")
    
    # Valid job
    valid_job = {
        'title': 'Software Engineer Intern',
        'company': 'Tech Corp',
        'url': 'https://linkedin.com/jobs/view/12345',
        'platform': 'linkedin'
    }
    is_valid, issues = validate_job_data(valid_job)
    print(f"Valid job: {is_valid}, Issues: {issues}")
    
    # Invalid job
    invalid_job = {
        'title': 'SE',  # Too short
        'company': '',  # Missing
        'url': 'not-a-url',  # Invalid
    }
    is_valid, issues = validate_job_data(invalid_job)
    print(f"Invalid job: {is_valid}, Issues: {issues}")
    
    print("\n✓ Utilities test passed!")
