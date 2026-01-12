#!/usr/bin/env python3
"""
Main entry point for job scraping and discovery.
This script searches for jobs, scores them, and saves to database.
Run apply_jobs.py or auto_apply.py to apply to discovered jobs.
"""

from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.glassdoor_scraper import GlassdoorScraper
from resume_parser.parser import ResumeParser
from matcher.job_matcher import JobMatcher
from database.models import Session, Job, UserProfile
from config import Config
from logger import get_logger, LogContext
from utils import validate_job_data, clean_job_data, deduplicate_jobs, format_job_summary
import json
from datetime import datetime, timezone
import signal
import sys
import traceback

# Initialize logger
logger = get_logger("main")

# Global variables for cleanup
current_session = None
current_scrapers = []

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully with proper logging."""
    logger.warning("Interrupt received - stopping job search...")
    
    # Close all browser instances
    for scraper in current_scrapers:
        try:
            scraper.close_driver()
            logger.info(f"Closed {scraper.__class__.__name__} browser")
        except Exception as e:
            logger.debug(f"Error closing scraper: {e}")
    
    # Commit any pending database changes
    if current_session:
        try:
            current_session.commit()
            current_session.close()
            logger.info("Database changes saved")
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    logger.info("Program stopped safely. Your progress is saved!")
    print("\n✅ Run 'python3 main.py' to continue searching.")
    sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)

def main():
    global current_session, current_scrapers
    
    logger.info("=" * 50)
    logger.info("JOB APPLIER BOT - Starting job search")
    logger.info("=" * 50)
    
    print("\n" + "=" * 50)
    print("STEP 1: Finding and scoring jobs (most recent first)")
    print("STEP 2: You have 15 min to review (python3 review_ui.py)")
    print("STEP 3: After 15 min, auto-applies to good matches")
    print("\n💡 TIP: Press Ctrl+C anytime to stop safely")
    print("=" * 50)
    
    # Initialize database session
    if Session is None:
        logger.error("Database not initialized")
        return 1
    
    current_session = Session()
    
    # Check if user profile exists
    user_profile_db = current_session.query(UserProfile).first()
    
    if not user_profile_db:
        logger.error("No user profile found. Please run: python3 setup_profile.py")
        return 1
    
    logger.info(f"Loaded user profile for {user_profile_db.first_name or 'user'}")
    
    # Parse user profile
    user_profile = {
        'skills': json.loads(user_profile_db.skills) if user_profile_db.skills else [],
        'experience': json.loads(user_profile_db.experience) if user_profile_db.experience else [],
        'education': json.loads(user_profile_db.education) if user_profile_db.education else [],
        'contact_info': {},
        'resume_path': user_profile_db.resume_path
    }
    
    # Initialize scrapers
    scrapers = []
    
    logger.info("[1/3] Initializing scrapers...")
    
    # LinkedIn
    if Config.LINKEDIN_EMAIL and Config.LINKEDIN_EMAIL != '':
        try:
            linkedin = LinkedInScraper()
            scrapers.append(('LinkedIn', linkedin, True))
            logger.info("LinkedIn scraper ready")
        except Exception as e:
            logger.error(f"LinkedIn scraper failed: {e}")
    else:
        logger.info("LinkedIn credentials not configured (optional)")
    
    # Indeed
    try:
        indeed = IndeedScraper()
        scrapers.append(('Indeed', indeed, False))
        logger.info("Indeed scraper ready")
    except Exception as e:
        logger.error(f"Indeed scraper failed: {e}")
    
    # Glassdoor
    try:
        glassdoor = GlassdoorScraper()
        scrapers.append(('Glassdoor', glassdoor, False))
        logger.info("Glassdoor scraper ready")
    except Exception as e:
        logger.error(f"Glassdoor scraper failed: {e}")
    
    if not scrapers:
        logger.error("No scrapers available - cannot continue")
        return 1
    
    # Initialize matcher
    logger.info("[2/3] Initializing job matcher...")
    matcher = JobMatcher(user_profile)
    logger.info("Job matcher ready (no API key needed)")
    
    # Search for jobs
    logger.info("[3/3] Searching for jobs (recent first)...")
    print("💡 Press Ctrl+C to stop at any time")
    print("=" * 50)
    
    total_jobs_found = 0
    new_jobs_added = 0
    invalid_jobs_skipped = 0
    search_start_time = datetime.now(timezone.utc)
    
    for platform_name, scraper, needs_login in scrapers:
        current_scrapers.append(scraper)  # Track for cleanup
        
        try:
            with LogContext(logger, f"Scraping {platform_name}"):
                scraper.login()
                
                # Check for rate limiting
                if scraper.is_rate_limited():
                    logger.warning(f"{platform_name} is rate limiting - waiting...")
                    scraper.handle_rate_limit(Config.RATE_LIMIT_WAIT_MINUTES)
                
                for title in Config.JOB_TITLES:
                    for location in Config.LOCATIONS:
                        logger.info(f"Searching: {title} in {location}")
                        
                        try:
                            jobs = scraper.search_jobs(title, location)
                            logger.info(f"Found {len(jobs)} jobs")
                            total_jobs_found += len(jobs)
                            
                            # Clean and validate jobs
                            for job_data in jobs:
                                # Clean the data
                                job_data = clean_job_data(job_data)
                                
                                # Validate job data
                                is_valid, issues = validate_job_data(job_data)
                                if not is_valid:
                                    logger.debug(f"Skipping invalid job: {issues}")
                                    invalid_jobs_skipped += 1
                                    continue
                                
                                # Check if job already exists
                                existing = current_session.query(Job).filter_by(
                                    job_url=job_data['url']
                                ).first()
                                if existing:
                                    continue
                                
                                # Get job details
                                try:
                                    details = scraper.get_job_details(job_data['url'])
                                    job_data.update(details)
                                except Exception as e:
                                    logger.debug(f"Could not get details for {job_data['title']}: {e}")
                                    job_data['description'] = ''
                                
                                # Calculate match score
                                match_score = matcher.calculate_match_score(job_data)
                                
                                # Save with search timestamp
                                job_db = Job(
                                    title=job_data['title'],
                                    company=job_data['company'],
                                    location=job_data.get('location', ''),
                                    platform=job_data.get('platform', platform_name.lower()),
                                    job_url=job_data['url'],
                                    description=job_data.get('description', ''),
                                    match_score=match_score,
                                    external_site=job_data.get('external_site', True),
                                    discovered_date=search_start_time,
                                    applied=False,
                                    application_status=None
                                )
                                
                                current_session.add(job_db)
                                new_jobs_added += 1
                                
                                if match_score >= Config.MIN_MATCH_SCORE:
                                    logger.info(f"⭐ {format_job_summary(job_data)}")
                                else:
                                    logger.debug(f"• {format_job_summary(job_data)} (below threshold)")
                            
                            # Commit after each search to save progress
                            current_session.commit()
                            logger.info(f"Saved {len(jobs)} jobs to database")
                            
                        except Exception as e:
                            logger.error(f"Error searching {title} in {location}: {e}")
                            logger.debug(traceback.format_exc())
                            continue
        
        except Exception as e:
            logger.error(f"Error with {platform_name}: {e}")
            logger.debug(traceback.format_exc())
        finally:
            try:
                scraper.close_driver()
                current_scrapers.remove(scraper)
            except Exception:
                pass
    
    current_session.close()
    current_session = None
    
    # Summary
    logger.info("=" * 50)
    logger.info("JOB SEARCH COMPLETED")
    logger.info("=" * 50)
    logger.info(f"Total jobs found: {total_jobs_found}")
    logger.info(f"New jobs added: {new_jobs_added}")
    logger.info(f"Invalid jobs skipped: {invalid_jobs_skipped}")
    
    print("\n" + "=" * 50)
    print("✅ Job search completed!")
    print(f"Total jobs found: {total_jobs_found}")
    print(f"New jobs added: {new_jobs_added}")
    print("=" * 50)
    print(f"\n⏰ Search started at: {search_start_time.strftime('%H:%M:%S')}")
    print(f"⏰ Auto-apply deadline: {search_start_time.strftime('%H:%M:%S')} + 15 min")
    print("\n📋 Next steps:")
    print("1. Quick! Review jobs: python3 review_ui.py")
    print("2. Or wait 15 min, then run: python3 auto_apply_pending.py")
    print("=" * 50)
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code or 0)
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}")
        logger.debug(traceback.format_exc())
        sys.exit(1)
