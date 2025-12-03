#!/usr/bin/env python3
"""
Apply to approved jobs.
This script will attempt to apply to jobs that have been approved for application.
"""

import sys
import os
from database.models import Session, Job, UserProfile, ApplicationRecord
from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.workday_scraper import WorkdayScraper
from selenium.webdriver.common.by import By
from config import Config
from datetime import datetime, timezone, timedelta
from sqlalchemy import or_, and_
import json
from cover_letter_generator import CoverLetterGenerator
from resume_tailor import ResumeTailor

def apply_to_jobs():
    """Apply to approved jobs."""
    print("=" * 70)
    print("Job Application Bot")
    print("=" * 70)
    
    if Session is None:
        print("\n❌ Error: Database not initialized")
        print("Please check your database configuration.")
        return
    
    session = Session()
    
    # Get user profile
    user_profile_db = session.query(UserProfile).first()
    if not user_profile_db:
        print("\n❌ No user profile found. Please run: python3 setup_profile.py")
        session.close()
        return
    
    # Get default resume path (optional - can be overridden per job)
    default_resume_path = None
    if user_profile_db.resume_path and os.path.exists(user_profile_db.resume_path):
        default_resume_path = user_profile_db.resume_path
        print(f"\n📄 Default resume found: {default_resume_path}")
        print("   (You can use a different resume for each job)")
    else:
        print("\n⚠️  No default resume in profile. You'll need to provide one for each job.")
    
    # Get jobs to apply to
    # Filter by: not applied, match score, date (MAX_JOB_AGE_DAYS), and remove duplicates
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=Config.MAX_JOB_AGE_DAYS)
    
    # Query jobs with date filtering (use posted_date if available, otherwise discovered_date)
    jobs_query = session.query(Job).filter_by(
        applied=False
    ).filter(
        Job.match_score >= Config.MIN_MATCH_SCORE
    ).filter(
        # Filter by date: use posted_date if available, otherwise discovered_date
        or_(
            and_(Job.posted_date.isnot(None), Job.posted_date >= cutoff_date),
            and_(Job.posted_date.is_(None), Job.discovered_date >= cutoff_date)
        )
    )
    
    # Get all candidates first
    all_candidates = jobs_query.order_by(Job.match_score.desc()).all()
    
    # Remove duplicates (same title+company, case-insensitive)
    seen_jobs = {}
    jobs_to_apply = []
    for job in all_candidates:
        # Create a unique key from title and company (case-insensitive)
        job_key = (job.title.strip().lower(), job.company.strip().lower())
        
        # If we haven't seen this title+company combination, add it
        if job_key not in seen_jobs:
            seen_jobs[job_key] = job
            jobs_to_apply.append(job)
    
    # Limit to top 10 after deduplication
    jobs_to_apply = jobs_to_apply[:10]
    
    if not jobs_to_apply:
        print("\nNo jobs to apply to.")
        print("Jobs need to have:")
        print(f"  - Match score >= {Config.MIN_MATCH_SCORE}")
        print("  - Not already applied")
        print(f"  - Posted/discovered within last {Config.MAX_JOB_AGE_DAYS} days")
        print("  - Unique (no duplicate title+company)")
        print("\nRun 'python3 main.py' to find more jobs, or 'python3 review_ui.py' to review existing ones.")
        session.close()
        return
    
    print(f"\nFound {len(jobs_to_apply)} jobs to apply to (after filtering by date and removing duplicates)")
    
    # Ask for resume ONCE at the beginning
    print("\n" + "=" * 70)
    print("Resume Selection")
    print("=" * 70)
    resume_to_use = get_resume_path(default_resume_path)
    
    if not resume_to_use or not os.path.exists(resume_to_use):
        print(f"\n❌ Resume not found: {resume_to_use}")
        print("Cannot proceed without a valid resume.")
        session.close()
        return
    
    print(f"\n✓ Using resume: {resume_to_use}")
    print("\n" + "=" * 70)
    print("Preparing Application Materials (Automatic)")
    print("=" * 70)
    print("This will generate cover letters and tailor resumes for all jobs...")
    print("You'll review everything before applying.\n")
    
    # Initialize cover letter generator and resume tailor
    cover_letter_gen = CoverLetterGenerator()
    resume_tailor = ResumeTailor()
    
    # Parse user profile for cover letter/resume generation
    user_profile = {
        'skills': json.loads(user_profile_db.skills) if user_profile_db.skills else [],
        'experience': json.loads(user_profile_db.experience) if user_profile_db.experience else [],
        'education': json.loads(user_profile_db.education) if user_profile_db.education else [],
        'contact_info': {}
    }
    
    # Process all jobs automatically (generate materials)
    processed_jobs = []
    
    for i, job in enumerate(jobs_to_apply, 1):
        print(f"\n[{i}/{len(jobs_to_apply)}] Processing: {job.title} at {job.company}")
        print(f"  Match Score: {job.match_score}/100")
        
        try:
            # Store which resume will be used
            job.original_resume_path = resume_to_use
            
            # Prepare job data
            job_data = {
                'title': job.title,
                'company': job.company,
                'location': job.location or '',
                'description': job.description or '',
                'requirements': job.requirements or ''
            }
            
            # Generate cover letter if not already generated
            if not job.cover_letter or not job.cover_letter_path:
                print("  📝 Generating cover letter...")
                try:
                    cover_letter_text, cover_letter_path = cover_letter_gen.generate_cover_letter(
                        job_data, user_profile
                    )
                    job.cover_letter = cover_letter_text
                    job.cover_letter_path = cover_letter_path
                    print(f"  ✓ Cover letter: {cover_letter_path}")
                except Exception as e:
                    print(f"  ⚠️  Cover letter generation failed: {e}")
                    job.cover_letter_path = None
            else:
                print(f"  ✓ Cover letter already exists")
            
            # Tailor resume if not already tailored
            if not job.tailored_resume_path:
                print("  📄 Tailoring resume...")
                try:
                    tailored_resume_path = resume_tailor.tailor_resume(
                        resume_to_use,
                        job_data,
                        user_profile
                    )
                    job.tailored_resume_path = tailored_resume_path
                    print(f"  ✓ Tailored resume: {tailored_resume_path}")
                except Exception as e:
                    print(f"  ⚠️  Resume tailoring failed: {e}")
                    job.tailored_resume_path = None
            else:
                print(f"  ✓ Tailored resume already exists")
            
            # Save progress
            session.commit()
            
            # Store for review
            processed_jobs.append({
                'job': job,
                'job_data': job_data,
                'resume': resume_to_use
            })
            
        except Exception as e:
            print(f"  ❌ Error processing job: {e}")
            continue
    
    # Show summary and ask for confirmation
    print("\n" + "=" * 70)
    print("📋 APPLICATION REVIEW - Review Before Applying")
    print("=" * 70)
    
    for i, item in enumerate(processed_jobs, 1):
        job = item['job']
        print(f"\n[{i}] {job.title} at {job.company}")
        print(f"    Match Score: {job.match_score}/100")
        print(f"    Platform: {job.platform}")
        print(f"    URL: {job.job_url}")
        if job.cover_letter_path:
            print(f"    Cover Letter: ✓ {job.cover_letter_path}")
        if job.tailored_resume_path:
            print(f"    Tailored Resume: ✓ {job.tailored_resume_path}")
    
    print("\n" + "=" * 70)
    print(f"📊 Summary: {len(processed_jobs)} jobs ready to apply")
    print("=" * 70)
    print("\nThis will:")
    print("  • Generate cover letters (if not already done)")
    print("  • Generate tailored resumes (if not already done)")
    print("  • Apply automatically to Workday/Intern Insider/Greenhouse/etc.")
    print("  • Track everything in the database")
    print("\n" + "=" * 70)
    
    # Ask for confirmation
    confirm = input("\n🤖 Proceed with automatic application? (yes/no, default=yes): ").strip().lower()
    if confirm and confirm not in ['yes', 'y', '']:
        print("\n❌ Application cancelled.")
        print("All materials have been generated and saved.")
        print("You can review them and run again later.")
        session.close()
        return
    
    print("\n" + "=" * 70)
    print(f"🚀 Starting automatic application to {len(processed_jobs)} jobs...")
    print("=" * 70)
    print()
    
    print("\n" + "=" * 70)
    print("Starting Application Process...")
    print("=" * 70)
    
    applied_count = 0
    failed_count = 0
    
    # Initialize LinkedIn scraper if credentials are available
    linkedin_scraper = None
    if Config.LINKEDIN_EMAIL and Config.LINKEDIN_PASSWORD:
        try:
            linkedin_scraper = LinkedInScraper()
            print("✓ LinkedIn scraper initialized")
        except Exception as e:
            print(f"⚠️  LinkedIn scraper failed: {e}")
            print("  Will only provide application links for manual application")
    
    # Now apply to all processed jobs
    for i, item in enumerate(processed_jobs, 1):
        job = item['job']
        resume_to_use = item['resume']
        
        print(f"\n[{i}/{len(processed_jobs)}] Applying: {job.title} at {job.company}")
        print(f"  Platform: {job.platform}")
        print(f"  URL: {job.job_url}")
        
        try:
            # Try to apply based on platform
            application_method = 'manual'
            success = False
            
            # Detect platform from URL
            job_url_lower = job.job_url.lower()
            is_workday = 'myworkdayjobs.com' in job_url_lower or 'workday.com' in job_url_lower
            is_interninsider = 'interninsider.com' in job_url_lower or 'interninsider' in job_url_lower
            is_greenhouse = 'greenhouse.io' in job_url_lower or 'boards.greenhouse.io' in job_url_lower
            is_lever = 'lever.co' in job_url_lower or 'jobs.lever.co' in job_url_lower
            is_smartrecruiters = 'smartrecruiters.com' in job_url_lower
            
            # Workday automation
            if is_workday:
                # Use Workday scraper for automation
                print(f"  🔄 Detected Workday application - attempting automation...")
                try:
                    workday_scraper = WorkdayScraper()
                    workday_scraper.login()
                    
                    # Get user contact info
                    user_info = {
                        'email': user_profile_db.email or '',
                        'phone': user_profile_db.phone or '',
                        'first_name': user_profile_db.first_name or '',
                        'last_name': user_profile_db.last_name or ''
                    }
                    
                    # Check if contact info is available
                    if not user_info['email']:
                        print(f"  ⚠️  Email not set in profile. Please run setup_profile.py to add contact info.")
                        print(f"  → Visit: {job.job_url}")
                        print(f"  → Materials ready: {job.cover_letter_path}, {job.tailored_resume_path}")
                        success = False
                        application_method = 'workday_manual'
                    else:
                        # Convert cover letter to file if it's text only
                        cover_letter_file = job.cover_letter_path
                        if not cover_letter_file and job.cover_letter:
                            # Save cover letter to temp file
                            import tempfile
                            temp_dir = tempfile.gettempdir()
                            cover_letter_file = os.path.join(temp_dir, f"cover_letter_{job.id}.txt")
                            with open(cover_letter_file, 'w', encoding='utf-8') as f:
                                f.write(job.cover_letter)
                        
                        resume_for_application = job.tailored_resume_path or resume_to_use
                        success = workday_scraper.apply_to_job(
                            job.job_url,
                            user_info,
                            resume_for_application,
                            cover_letter_file
                        )
                        
                        if success:
                            application_method = 'workday_auto'
                        else:
                            application_method = 'workday_manual'
                            print(f"  → Visit: {job.job_url}")
                            if job.cover_letter_path:
                                print(f"  → Cover letter: {job.cover_letter_path}")
                            if job.tailored_resume_path:
                                print(f"  → Tailored resume: {job.tailored_resume_path}")
                        
                        workday_scraper.close_driver()
                except Exception as e:
                    print(f"  ⚠️  Workday automation failed: {e}")
                    print(f"  → Visit: {job.job_url}")
                    success = False
                    application_method = 'workday_manual'
            
            # Intern Insider, Greenhouse, Lever, SmartRecruiters - similar to Workday
            elif is_interninsider or is_greenhouse or is_lever or is_smartrecruiters:
                print(f"  🔄 Detected {job.platform} application - attempting automation...")
                try:
                    # Use Workday scraper as base (similar form structure)
                    workday_scraper = WorkdayScraper()
                    workday_scraper.login()
                    
                    user_info = {
                        'email': user_profile_db.email or '',
                        'phone': user_profile_db.phone or '',
                        'first_name': user_profile_db.first_name or '',
                        'last_name': user_profile_db.last_name or ''
                    }
                    
                    if not user_info['email']:
                        print(f"  ⚠️  Email not set in profile. Please run setup_profile.py to add contact info.")
                        success = False
                        application_method = f'{job.platform}_manual'
                    else:
                        cover_letter_file = job.cover_letter_path
                        if not cover_letter_file and job.cover_letter:
                            import tempfile
                            temp_dir = tempfile.gettempdir()
                            cover_letter_file = os.path.join(temp_dir, f"cover_letter_{job.id}.txt")
                            with open(cover_letter_file, 'w', encoding='utf-8') as f:
                                f.write(job.cover_letter)
                        
                        resume_for_application = job.tailored_resume_path or resume_to_use
                        success = workday_scraper.apply_to_job(
                            job.job_url,
                            user_info,
                            resume_for_application,
                            cover_letter_file
                        )
                        
                        if success:
                            application_method = f'{job.platform}_auto'
                        else:
                            application_method = f'{job.platform}_manual'
                            print(f"  → Visit: {job.job_url}")
                        
                        workday_scraper.close_driver()
                except Exception as e:
                    print(f"  ⚠️  {job.platform} automation failed: {e}")
                    print(f"  → Visit: {job.job_url}")
                    success = False
                    application_method = f'{job.platform}_manual'
            
            elif job.platform == 'linkedin' and linkedin_scraper:
                # Use tailored resume if available, otherwise original
                resume_for_application = job.tailored_resume_path or resume_to_use
                success = apply_linkedin_job(linkedin_scraper, job, resume_for_application)
                if success:
                    application_method = 'linkedin_easy_apply'
            else:
                # For other platforms or if LinkedIn scraper not available
                # Just mark as ready for manual application
                print(f"  ℹ️  Manual application required")
                print(f"  → Visit: {job.job_url}")
                if job.cover_letter_path:
                    print(f"  → Cover letter: {job.cover_letter_path}")
                if job.tailored_resume_path:
                    print(f"  → Tailored resume: {job.tailored_resume_path}")
                success = False  # Mark as not auto-applied
                application_method = 'manual'
            
            # Record application details
            now = datetime.now(timezone.utc)
            
            if success:
                job.applied = True
                job.applied_date = now
                job.application_status = 'applied'
                job.application_method = application_method
                job.application_notes = f"Auto-applied via {application_method} on {now.strftime('%Y-%m-%d %H:%M')}"
                job.notes = (job.notes or '') + f"\n[Auto-applied on {now.strftime('%Y-%m-%d %H:%M')}]"
                
                # Create detailed application record
                # Set follow-up date to 2 hours from now (auto-complete if no response)
                follow_up_time = now + timedelta(hours=2)
                
                app_record = ApplicationRecord(
                    job_id=job.id,
                    application_date=now,
                    resume_used=resume_to_use,
                    cover_letter_used=job.cover_letter_path,
                    tailored_resume_used=job.tailored_resume_path,
                    application_method=application_method,
                    application_status='submitted',
                    follow_up_date=follow_up_time,
                    notes=f"Application submitted successfully via {application_method}. Auto-complete after 2 hours if no response."
                )
                session.add(app_record)
                session.commit()
                applied_count += 1
                print(f"  ✅ Successfully applied!")
                print(f"  📝 Application recorded in database")
            else:
                # Mark as needing manual application
                job.application_method = 'manual'
                job.application_notes = f"Manual application required - {now.strftime('%Y-%m-%d %H:%M')}"
                job.notes = (job.notes or '') + f"\n[Manual application required - {now.strftime('%Y-%m-%d %H:%M')}]"
                
                # Create record for manual application
                # Set follow-up date to 2 hours from now (auto-complete if no response)
                follow_up_time = now + timedelta(hours=2)
                
                app_record = ApplicationRecord(
                    job_id=job.id,
                    application_date=now,
                    resume_used=resume_to_use,
                    cover_letter_used=job.cover_letter_path,
                    tailored_resume_used=job.tailored_resume_path,
                    application_method='manual',
                    application_status='pending',
                    follow_up_date=follow_up_time,
                    notes="Materials prepared, awaiting manual submission. Auto-complete after 2 hours if no response."
                )
                session.add(app_record)
                session.commit()
                
                print(f"  ⚠️  Requires manual application")
                print(f"  📝 Application record created (status: pending)")
                failed_count += 1
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            job.notes = (job.notes or '') + f"\n[Error applying: {str(e)}]"
            session.commit()
            failed_count += 1
        
        print("-" * 70)
    
    # Cleanup
    if linkedin_scraper:
        try:
            linkedin_scraper.close_driver()
        except:
            pass
    
    session.close()
    
    print("\n" + "=" * 70)
    print("Application Summary:")
    print(f"  ✅ Successfully applied: {applied_count}")
    print(f"  ⚠️  Manual application needed: {failed_count}")
    print("=" * 70)
    
    if failed_count > 0:
        print("\n💡 Tip: Check the job URLs above for manual applications")
    print("=" * 70)

def get_resume_path(default_path: str = None) -> str:
    """Get resume path from user, with option to use default."""
    if default_path:
        print(f"\n  📄 Default resume: {default_path}")
        use_default = input("  Use default resume? (y/n, default=y): ").strip().lower()
        if use_default != 'n':
            return default_path
    
    while True:
        resume_path = input("\n  Enter path to resume for this job (PDF or DOCX): ").strip()
        resume_path = resume_path.strip('"').strip("'")
        resume_path = os.path.expanduser(resume_path)
        
        if not resume_path:
            if default_path:
                print(f"  Using default: {default_path}")
                return default_path
            continue
        
        if not os.path.exists(resume_path):
            print(f"  ❌ File not found: {resume_path}")
            retry = input("  Try again? (y/n): ").strip().lower()
            if retry != 'y':
                return None
            continue
        
        if not resume_path.lower().endswith(('.pdf', '.docx')):
            print(f"  ❌ Unsupported format. Please use PDF or DOCX.")
            retry = input("  Try again? (y/n): ").strip().lower()
            if retry != 'y':
                return None
            continue
        
        return resume_path

def apply_linkedin_job(scraper: LinkedInScraper, job: Job, resume_path: str) -> bool:
    """Attempt to apply to a LinkedIn job using Easy Apply."""
    try:
        scraper.login()
        
        # Navigate to job page
        scraper.driver.get(job.job_url)
        scraper.random_delay(2, 4)
        
        # Look for Easy Apply button
        try:
            easy_apply_button = scraper.driver.find_element(By.XPATH, 
                "//button[contains(., 'Easy Apply') or contains(., 'Apply')]")
            easy_apply_button.click()
            scraper.random_delay(2, 3)
            
            # This is a simplified version - full implementation would:
            # 1. Fill out application form fields
            # 2. Upload resume
            # 3. Answer questions if any
            # 4. Submit application
            
            print("  ⚠️  LinkedIn Easy Apply detected but full automation not implemented")
            print("  → Please complete application manually")
            return False
            
        except Exception as e:
            print(f"  ⚠️  Easy Apply button not found: {e}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error applying to LinkedIn job: {e}")
        return False

if __name__ == "__main__":
    apply_to_jobs()

