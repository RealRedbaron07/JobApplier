#!/usr/bin/env python3
"""
Unified Entry Point for JobApplier.
Handles resume management, job searching, and application with final confirmation.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
import logging

from config import Config
from database.models import Session, Job, UserProfile
from scrapers.linkedin_scraper import LinkedInScraper
from matcher.job_matcher import JobMatcher
from cover_letter_generator import CoverLetterGenerator
from resume_tailor import ResumeTailor
from utils import (
    parse_user_profile, 
    generate_job_materials, 
    apply_to_job,
    format_job_summary
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("run")

def load_settings():
    """Load user settings from JSON file."""
    if os.path.exists(Config.USER_SETTINGS_FILE):
        with open(Config.USER_SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_settings(settings):
    """Save user settings to JSON file."""
    with open(Config.USER_SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

def set_resume(resume_path):
    """Set the default resume path."""
    if not os.path.exists(resume_path):
        print(f"❌ Error: File not found at {resume_path}")
        return False
    
    settings = load_settings()
    settings['resume_path'] = os.path.abspath(resume_path)
    settings['last_updated'] = datetime.now().strftime("%Y-%m-%d")
    save_settings(settings)
    print(f"✅ Default resume set to: {settings['resume_path']}")
    return True

def show_resume():
    """Show the current default resume path."""
    settings = load_settings()
    resume_path = settings.get('resume_path')
    if resume_path:
        print(f"📄 Current default resume: {resume_path}")
        if not os.path.exists(resume_path):
            print("   ⚠️  Warning: File no longer exists at this path!")
    else:
        print("❌ No default resume set. Use --set-resume to set one.")

def run_workflow(resume_override=None):
    """Run the main application workflow."""
    settings = load_settings()
    resume_path = resume_override or settings.get('resume_path')
    
    if not resume_path:
        print("❌ Error: No resume specified. Use --set-resume or --resume.")
        return
    
    if not os.path.exists(resume_path):
        print(f"❌ Error: Resume not found at {resume_path}")
        return

    print(f"\n🚀 Starting JobApplier with resume: {resume_path}")
    
    if Session is None:
        print("❌ Error: Database not initialized.")
        return

    session = Session()
    user_profile_db = session.query(UserProfile).first()
    if not user_profile_db:
        print("❌ Error: No user profile found. Please run setup_profile.py first.")
        return

    user_profile = parse_user_profile(user_profile_db)
    
    # Step 1: Scraping
    print("\n" + "="*50)
    print("🔍 STEP 1: SCRAPING JOBS")
    print("="*50)
    
    linkedin = LinkedInScraper()
    linkedin.login()
    
    matcher = JobMatcher(user_profile)
    total_found = 0
    
    # We'll search for the first few titles and locations from config
    titles = Config.JOB_TITLES[:3]
    locations = Config.LOCATIONS[:2]
    
    for title in titles:
        for loc in locations:
            print(f"   Searching for '{title}' in '{loc}'...")
            found_jobs = linkedin.search_jobs(title, loc)
            for job_data in found_jobs:
                # Check if already exists
                existing = session.query(Job).filter_by(job_url=job_data['url']).first()
                if existing:
                    continue
                
                # Get details and score
                details = linkedin.get_job_details(job_data['url'])
                job_data.update(details)
                score = matcher.calculate_match_score(job_data)
                
                job_db = Job(
                    title=job_data['title'],
                    company=job_data['company'],
                    location=job_data['location'],
                    platform=job_data['platform'],
                    job_url=job_data['url'],
                    description=job_data.get('description', ''),
                    match_score=score,
                    external_site=job_data.get('external_site', True),
                    discovered_date=datetime.now(timezone.utc),
                    applied=False
                )
                session.add(job_db)
                total_found += 1
            session.commit()
    
    linkedin.close_driver()
    print(f"✅ Found and scored {total_found} new jobs.")

    # Step 2: Filter and Review
    print("\n" + "="*50)
    print("📋 STEP 2: REVIEW MATCHES")
    print("="*50)
    
    qualifying_jobs = session.query(Job).filter(
        Job.applied == False,
        Job.match_score >= Config.MIN_MATCH_SCORE
    ).order_by(Job.match_score.desc()).limit(15).all()
    
    if not qualifying_jobs:
        print("ℹ️ No new qualifying jobs found.")
        return

    print(f"Found {len(qualifying_jobs)} jobs matching your criteria:")
    print("-" * 80)
    print(f"{'#':<3} | {'Score':<5} | {'Title':<30} | {'Company':<20} | {'Location'}")
    print("-" * 80)
    
    for i, job in enumerate(qualifying_jobs, 1):
        print(f"{i:<3} | {job.match_score:>4}% | {job.title[:30]:<30} | {job.company[:20]:<20} | {job.location}")
    print("-" * 80)

    # Step 3: Material Generation
    print("\n" + "="*50)
    print("📄 STEP 3: GENERATING MATERIALS")
    print("="*50)
    
    cover_letter_gen = CoverLetterGenerator()
    resume_tailor = ResumeTailor()
    
    for job in qualifying_jobs:
        generate_job_materials(job, user_profile, resume_path, cover_letter_gen, resume_tailor, session)
    
    print("✅ Materials generated for all selected jobs.")

    # Step 4: Final Confirmation and Apply
    print("\n" + "="*50)
    print("🎯 STEP 4: APPLY")
    print("="*50)
    
    print(f"Ready to apply to {len(qualifying_jobs)} jobs.")
    choice = input("\nApply to all? [yes/no/select]: ").lower().strip()
    
    to_apply = []
    if choice == 'yes':
        to_apply = qualifying_jobs
    elif choice == 'select':
        indices = input("Enter numbers separated by commas (e.g., 1,3,5): ").split(',')
        for idx in indices:
            try:
                i = int(idx.strip()) - 1
                if 0 <= i < len(qualifying_jobs):
                    to_apply.append(qualifying_jobs[i])
            except ValueError:
                continue
    
    if not to_apply:
        print("👋 No jobs selected. Exiting.")
        return

    print(f"\n🚀 Applying to {len(to_apply)} jobs...")
    applied_count = 0
    for job in to_apply:
        print(f"   Applying to {job.title} at {job.company}...")
        success = apply_to_job(job, user_profile, resume_path, session)
        if success:
            applied_count += 1
    
    print(f"\n✅ Finished! Successfully applied to {applied_count} jobs.")
    session.close()

def main():
    parser = argparse.ArgumentParser(description="JobApplier Unified Entry Point")
    parser.add_argument('--set-resume', type=str, help="Set the default resume path")
    parser.add_argument('--show-resume', action='store_true', help="Show the current default resume path")
    parser.add_argument('--resume', type=str, help="Use a specific resume for this run only")
    parser.add_argument('--dashboard', action='store_true', help="Start the web dashboard")
    
    args = parser.parse_args()
    
    if args.set_resume:
        set_resume(args.set_resume)
    elif args.show_resume:
        show_resume()
    elif args.dashboard:
        print("🚀 Starting dashboard...")
        # Import here to avoid circular imports if any
        from dashboard.app import app
        app.run(host=Config.DASHBOARD_HOST, port=Config.DASHBOARD_PORT, debug=True)
    else:
        # Default workflow
        # Check if first run and default resume not set
        settings = load_settings()
        if not settings.get('resume_path'):
            # Check for your specific resume as a courtesy
            default_path = "/Users/malpari/Desktop/Mustafa Alp ARI.pdf"
            if os.path.exists(default_path):
                print(f"👋 Found your resume at {default_path}")
                set_resume(default_path)
            else:
                print("👋 Welcome! Please set your resume first using: python run.py --set-resume /path/to/resume.pdf")
                return
        
        run_workflow(resume_override=args.resume)

if __name__ == "__main__":
    main()
