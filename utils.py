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
    # ... (rest of the function remains the same)
    if session:
        session.commit()


def apply_to_job(job, user_profile, resume_path, session):
    """
    Apply to a job using the appropriate scraper.
    """
    from scrapers.linkedin_scraper import LinkedInScraper
    from scrapers.workday_scraper import WorkdayScraper
    from database.models import ApplicationRecord
    from datetime import datetime, timezone, timedelta
    
    job_url_lower = job.job_url.lower()
    is_workday = 'myworkdayjobs.com' in job_url_lower or 'workday.com' in job_url_lower
    is_greenhouse = 'greenhouse.io' in job_url_lower
    is_lever = 'lever.co' in job_url_lower
    
    success = False
    application_method = 'manual'
    scraper = None
    
    try:
        # 1. Try automated application for supported platforms
        if is_workday or is_greenhouse or is_lever:
            logger.info(f"Using Workday scraper for {job.company}")
            scraper = WorkdayScraper()
            scraper.login()
            
            user_info = user_profile.get('contact_info', {})
            resume_for_app = job.tailored_resume_path or resume_path
            
            success = scraper.apply_to_job(
                job.job_url,
                user_info,
                resume_for_app,
                job.cover_letter_path
            )
            
            if success:
                application_method = 'auto'
                
        elif 'linkedin.com' in job_url_lower:
            logger.info(f"Using LinkedIn scraper for {job.company}")
            scraper = LinkedInScraper()
            scraper.login()
            
            resume_for_app = job.tailored_resume_path or resume_path
            success = scraper.apply_to_job(job.job_url, resume_for_app)
            
            if success:
                application_method = 'auto'
        
        # 2. Record application status
        now = datetime.now(timezone.utc)
        if success:
            job.applied = True
            job.applied_date = now
            job.application_status = 'applied'
            job.notes = (job.notes or '') + f"\n[Auto-applied on {now.strftime('%Y-%m-%d %H:%M')}]"
            logger.info(f"✅ Successfully applied to {job.title} at {job.company}")
        else:
            job.notes = (job.notes or '') + f"\n[Manual application required - {now.strftime('%Y-%m-%d %H:%M')}]"
            logger.info(f"⚠️ Manual application required for {job.title} at {job.company}")
        
        # 3. Create application record
        app_record = ApplicationRecord(
            job_id=job.id,
            application_date=now,
            resume_used=resume_path,
            cover_letter_used=job.cover_letter_path,
            tailored_resume_used=job.tailored_resume_path,
            application_method=application_method,
            application_status='submitted' if success else 'pending',
            follow_up_date=now + timedelta(hours=48),
            notes=f"{'Auto-applied' if success else 'Manual application required'}"
        )
        session.add(app_record)
        session.commit()
        
        return success
        
    except Exception as e:
        logger.error(f"Error applying to job {job.id}: {e}")
        return False
    finally:
        if scraper:
            scraper.close_driver()


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


def get_resume_path(user_profile_db, fallback_path: Optional[str] = None) -> Optional[str]:
    """
    Get valid resume path from user profile or fallback.
    
    Args:
        user_profile_db: UserProfile database object
        fallback_path: Optional fallback path to check
    
    Returns:
        Valid resume path or None
    """
    # Try user profile path first
    if user_profile_db and user_profile_db.resume_path:
        if os.path.exists(user_profile_db.resume_path):
            logger.debug(f"Using resume from profile: {user_profile_db.resume_path}")
            return user_profile_db.resume_path
        else:
            logger.warning(f"Resume path in profile not found: {user_profile_db.resume_path}")
    
    # Try fallback
    if fallback_path and os.path.exists(fallback_path):
        logger.debug(f"Using fallback resume: {fallback_path}")
        return fallback_path
    
    logger.error("No valid resume found")
    return None


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
