#!/usr/bin/env python3
"""
Full Automation Entry Point for Job Applications.
Runs the complete cycle: scrape → match → generate materials → apply
No user interaction required when AUTO_MODE=true.
"""

import sys
import os
import json
import traceback
from datetime import datetime, timezone, timedelta

from database.models import Session, Job, UserProfile, ApplicationRecord
from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.glassdoor_scraper import GlassdoorScraper
from scrapers.workday_scraper import WorkdayScraper
from resume_parser.parser import ResumeParser
from matcher.job_matcher import JobMatcher
from cover_letter_generator import CoverLetterGenerator
from resume_tailor import ResumeTailor
from config import Config
from logger import get_logger, LogContext
from utils import validate_job_data, clean_job_data, format_job_summary
from sqlalchemy import or_, and_

# Initialize logger
logger = get_logger("auto_apply")


def log(message: str, level: str = "INFO"):
    """Compatibility wrapper for old log calls - routes to new logger."""
    level_map = {
        "INFO": logger.info,
        "SUCCESS": logger.info,
        "WARNING": logger.warning,
        "ERROR": logger.error,
        "STEP": logger.info,
    }
    log_func = level_map.get(level, logger.info)
    log_func(message)


def scrape_jobs(session, user_profile: dict) -> int:
    """Scrape jobs from all configured platforms using a single browser."""
    log("Starting job scraping...", "STEP")
    
    # Check for WAIT_FOR_LOGIN mode
    wait_for_login = os.getenv('WAIT_FOR_LOGIN', 'true').lower() == 'true'  # Default to True
    
    total_new_jobs = 0
    search_start_time = datetime.now(timezone.utc)
    
    # Initialize matcher
    matcher = JobMatcher(user_profile)
    
    # Only scrape LinkedIn for now (most reliable for internships)
    if Config.LINKEDIN_EMAIL or wait_for_login:
        try:
            log("Initializing LinkedIn scraper...")
            linkedin = LinkedInScraper()
            
            # This will now wait for manual login if WAIT_FOR_LOGIN=true
            linkedin.login()
            
            # Search for jobs
            for title in Config.JOB_TITLES[:3]:  # Limit for speed
                for location in Config.LOCATIONS[:2]:  # Limit for speed
                    log(f"Searching: {title} in {location}")
                    try:
                        jobs = linkedin.search_jobs(title, location)
                        log(f"Found {len(jobs)} jobs")
                        
                        for job_data in jobs:
                            # Check if already exists
                            existing = session.query(Job).filter_by(job_url=job_data['url']).first()
                            if existing:
                                continue
                            
                            # Get details
                            try:
                                details = linkedin.get_job_details(job_data['url'])
                                job_data.update(details)
                            except:
                                job_data['description'] = ''
                            
                            # Calculate score
                            match_score = matcher.calculate_match_score(job_data)
                            
                            # Save
                            job_db = Job(
                                title=job_data['title'],
                                company=job_data['company'],
                                location=job_data['location'],
                                platform=job_data['platform'],
                                job_url=job_data['url'],
                                description=job_data.get('description', ''),
                                match_score=match_score,
                                external_site=job_data.get('external_site', True),
                                discovered_date=search_start_time,
                                applied=False
                            )
                            session.add(job_db)
                            total_new_jobs += 1
                            
                            if match_score >= Config.MIN_MATCH_SCORE:
                                log(f"  ⭐ {job_data['title']} at {job_data['company']} - Score: {match_score}")
                        
                        session.commit()
                    except Exception as e:
                        log(f"Error searching {title}: {e}", "WARNING")
                        continue
            
            linkedin.close_driver()
        except Exception as e:
            log(f"LinkedIn scraping failed: {e}", "ERROR")
    else:
        log("Skipping LinkedIn (no credentials and WAIT_FOR_LOGIN=false)", "WARNING")
    
    log(f"Scraped {total_new_jobs} new jobs", "SUCCESS")
    return total_new_jobs


def generate_materials(session, jobs: list, user_profile: dict, resume_path: str) -> list:
    """Generate cover letters and tailored resumes for all jobs."""
    log(f"Generating application materials for {len(jobs)} jobs...", "STEP")
    
    cover_letter_gen = CoverLetterGenerator()
    resume_tailor = ResumeTailor()
    processed = []
    
    for i, job in enumerate(jobs, 1):
        log(f"[{i}/{len(jobs)}] Processing: {job.title} at {job.company}")
        
        try:
            job_data = {
                'title': job.title,
                'company': job.company,
                'location': job.location or '',
                'description': job.description or '',
                'requirements': job.requirements or ''
            }
            
            # Generate cover letter
            if not job.cover_letter_path:
                try:
                    cover_letter_text, cover_letter_path = cover_letter_gen.generate_cover_letter(
                        job_data, user_profile
                    )
                    job.cover_letter = cover_letter_text
                    job.cover_letter_path = cover_letter_path
                except Exception as e:
                    log(f"  Cover letter failed: {e}", "WARNING")
            
            # Tailor resume
            if not job.tailored_resume_path and resume_path:
                try:
                    tailored_resume_path = resume_tailor.tailor_resume(
                        resume_path,
                        job_data,
                        user_profile
                    )
                    job.tailored_resume_path = tailored_resume_path
                except Exception as e:
                    log(f"  Resume tailoring failed: {e}", "WARNING")
            
            session.commit()
            processed.append(job)
            
        except Exception as e:
            log(f"  Error processing job: {e}", "ERROR")
            continue
    
    log(f"Generated materials for {len(processed)} jobs", "SUCCESS")
    return processed


def apply_to_jobs(session, jobs: list, user_profile_db, resume_path: str) -> tuple:
    """Apply to all processed jobs automatically."""
    log(f"Starting automatic application to {len(jobs)} jobs...", "STEP")
    
    applied_count = 0
    manual_count = 0
    
    for i, job in enumerate(jobs, 1):
        log(f"[{i}/{len(jobs)}] Applying: {job.title} at {job.company}")
        
        try:
            job_url_lower = job.job_url.lower()
            is_workday = 'myworkdayjobs.com' in job_url_lower or 'workday.com' in job_url_lower
            is_greenhouse = 'greenhouse.io' in job_url_lower
            is_lever = 'lever.co' in job_url_lower
            
            success = False
            application_method = 'manual'
            
            # Try automated application for supported platforms
            if is_workday or is_greenhouse or is_lever:
                try:
                    workday_scraper = WorkdayScraper()
                    workday_scraper.login()
                    
                    user_info = {
                        'email': getattr(user_profile_db, 'email', '') or '',
                        'phone': getattr(user_profile_db, 'phone', '') or '',
                        'first_name': getattr(user_profile_db, 'first_name', '') or '',
                        'last_name': getattr(user_profile_db, 'last_name', '') or ''
                    }
                    
                    if user_info['email']:
                        resume_for_app = job.tailored_resume_path or resume_path
                        success = workday_scraper.apply_to_job(
                            job.job_url,
                            user_info,
                            resume_for_app,
                            job.cover_letter_path
                        )
                        
                        if success:
                            application_method = 'auto'
                    
                    workday_scraper.close_driver()
                except Exception as e:
                    log(f"  Automation failed: {e}", "WARNING")
            
            # Record application
            now = datetime.now(timezone.utc)
            
            if success:
                job.applied = True
                job.applied_date = now
                job.application_status = 'applied'
                job.notes = (job.notes or '') + f"\n[Auto-applied on {now.strftime('%Y-%m-%d %H:%M')}]"
                applied_count += 1
                log(f"  Applied successfully!", "SUCCESS")
            else:
                job.notes = (job.notes or '') + f"\n[Manual application required - {now.strftime('%Y-%m-%d %H:%M')}]"
                manual_count += 1
                log(f"  Marked for manual application")
            
            # Create application record
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
            
        except Exception as e:
            log(f"  Error: {e}", "ERROR")
            continue
    
    log(f"Applied: {applied_count}, Manual: {manual_count}", "SUCCESS")
    return applied_count, manual_count


def main(dry_run: bool = False):
    """Main automation loop."""
    print("\n" + "=" * 70)
    print("🚀 JOB APPLIER - FULL AUTOMATION MODE")
    print("=" * 70)
    
    if dry_run:
        log("DRY RUN MODE - No actual applications will be made", "WARNING")
    
    # Check database
    if Session is None:
        log("Database not initialized", "ERROR")
        return 1
    
    session = Session()
    
    # Check user profile
    user_profile_db = session.query(UserProfile).first()
    if not user_profile_db:
        log("No user profile found. Run: python3 setup_profile.py", "ERROR")
        session.close()
        return 1
    
    user_profile = {
        'skills': json.loads(user_profile_db.skills) if user_profile_db.skills else [],
        'experience': json.loads(user_profile_db.experience) if user_profile_db.experience else [],
        'education': json.loads(user_profile_db.education) if user_profile_db.education else [],
        'contact_info': {}
    }
    
    resume_path = user_profile_db.resume_path
    if not resume_path or not os.path.exists(resume_path):
        log(f"Resume not found: {resume_path}", "ERROR")
        session.close()
        return 1
    
    log(f"Using resume: {resume_path}")
    
    # Step 1: Scrape new jobs
    print("\n" + "-" * 70)
    log("STEP 1: SCRAPING JOBS", "STEP")
    print("-" * 70)
    
    if not dry_run:
        scrape_jobs(session, user_profile)
    else:
        log("Skipping scraping in dry run mode")
    
    # Step 2: Get qualifying jobs
    print("\n" + "-" * 70)
    log("STEP 2: FILTERING QUALIFYING JOBS", "STEP")
    print("-" * 70)
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=Config.MAX_JOB_AGE_DAYS)
    
    jobs = session.query(Job).filter_by(
        applied=False
    ).filter(
        Job.match_score >= Config.MIN_MATCH_SCORE
    ).filter(
        or_(
            and_(Job.posted_date.isnot(None), Job.posted_date >= cutoff_date),
            and_(Job.posted_date.is_(None), Job.discovered_date >= cutoff_date)
        )
    ).order_by(Job.match_score.desc()).limit(20).all()
    
    # Deduplicate by title+company
    seen = {}
    unique_jobs = []
    for job in jobs:
        key = (job.title.strip().lower(), job.company.strip().lower())
        if key not in seen:
            seen[key] = job
            unique_jobs.append(job)
    
    jobs = unique_jobs[:10]  # Limit to 10
    
    log(f"Found {len(jobs)} qualifying jobs")
    
    if not jobs:
        log("No jobs to process", "WARNING")
        session.close()
        return 0
    
    for i, job in enumerate(jobs, 1):
        print(f"  {i}. [{job.match_score}/100] {job.title} at {job.company}")
    
    # Step 3: Generate materials
    print("\n" + "-" * 70)
    log("STEP 3: GENERATING APPLICATION MATERIALS", "STEP")
    print("-" * 70)
    
    if not dry_run:
        processed = generate_materials(session, jobs, user_profile, resume_path)
    else:
        log("Skipping material generation in dry run mode")
        processed = jobs
    
    # Step 4: Apply
    print("\n" + "-" * 70)
    log("STEP 4: APPLYING TO JOBS", "STEP")
    print("-" * 70)
    
    if not dry_run:
        applied, manual = apply_to_jobs(session, processed, user_profile_db, resume_path)
    else:
        log("Would apply to the following jobs:")
        for job in processed:
            print(f"  • {job.title} at {job.company} - {job.job_url}")
        applied, manual = 0, len(processed)
    
    # Summary
    print("\n" + "=" * 70)
    log("AUTOMATION COMPLETE", "SUCCESS")
    print("=" * 70)
    print(f"  ✅ Auto-applied: {applied}")
    print(f"  📋 Manual needed: {manual}")
    print(f"\n  Run 'python3 dashboard/app.py' to view dashboard")
    print("=" * 70 + "\n")
    
    session.close()
    return 0


if __name__ == "__main__":
    dry_run = '--dry-run' in sys.argv
    sys.exit(main(dry_run=dry_run))
