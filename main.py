from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.glassdoor_scraper import GlassdoorScraper
from resume_parser.parser import ResumeParser
from matcher.job_matcher import JobMatcher
from database.models import Session, Job, UserProfile
from config import Config
import json
from datetime import datetime, timezone
import signal
import sys

# Global variables for cleanup
current_session = None
current_scrapers = []

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Stopping job search...")
    print("Saving progress and cleaning up...")
    
    # Close all browser instances
    for scraper in current_scrapers:
        try:
            scraper.close_driver()
            print(f"✓ Closed {scraper.__class__.__name__} browser")
        except:
            pass
    
    # Commit any pending database changes
    if current_session:
        try:
            current_session.commit()
            current_session.close()
            print("✓ Saved database changes")
        except:
            pass
    
    print("\n✅ Program stopped safely. Your progress is saved!")
    print("Run 'python3 main.py' to continue searching.")
    sys.exit(0)

# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)

def main():
    global current_session, current_scrapers
    
    print("Starting Job Applier Bot...")
    print("=" * 50)
    print("STEP 1: Finding and scoring jobs (most recent first)")
    print("STEP 2: You have 15 min to review (python3 review_ui.py)")
    print("STEP 3: After 15 min, auto-applies to good matches")
    print("\n💡 TIP: Press Ctrl+C anytime to stop safely")
    print("=" * 50)
    
    # Initialize database session
    if Session is None:
        print("Error: Database not initialized")
        return
    
    current_session = Session()
    
    # Check if user profile exists
    user_profile_db = current_session.query(UserProfile).first()
    
    if not user_profile_db:
        print("No user profile found. Please run: python3 setup_profile.py")
        return
    
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
    
    print("\n[1/3] Initializing scrapers...")
    
    # LinkedIn
    if Config.LINKEDIN_EMAIL and Config.LINKEDIN_EMAIL != '':
        try:
            linkedin = LinkedInScraper()
            scrapers.append(('LinkedIn', linkedin, True))
            print("✓ LinkedIn scraper ready")
        except Exception as e:
            print(f"✗ LinkedIn scraper failed: {e}")
    else:
        print("⊘ LinkedIn credentials not configured (optional)")
    
    # Indeed
    try:
        indeed = IndeedScraper()
        scrapers.append(('Indeed', indeed, False))
        print("✓ Indeed scraper ready")
    except Exception as e:
        print(f"✗ Indeed scraper failed: {e}")
    
    # Glassdoor
    try:
        glassdoor = GlassdoorScraper()
        scrapers.append(('Glassdoor', glassdoor, False))
        print("✓ Glassdoor scraper ready")
    except Exception as e:
        print(f"✗ Glassdoor scraper failed: {e}")
    
    # Initialize matcher
    print("\n[2/3] Initializing job matcher...")
    matcher = JobMatcher(user_profile)
    print("✓ Job matcher ready (no API key needed)")
    
    # Search for jobs
    print("\n[3/3] Searching for jobs (recent first)...")
    print("💡 Press Ctrl+C to stop at any time")
    print("=" * 50)
    
    total_jobs_found = 0
    new_jobs_added = 0
    search_start_time = datetime.now(timezone.utc)
    
    for platform_name, scraper, needs_login in scrapers:
        current_scrapers.append(scraper)  # Track for cleanup
        
        try:
            print(f"\n--- {platform_name} ---")
            
            scraper.login()
            
            for title in Config.JOB_TITLES:
                for location in Config.LOCATIONS:
                    print(f"\nSearching: {title} in {location}")
                    print("(Press Ctrl+C to stop)")
                    
                    try:
                        jobs = scraper.search_jobs(title, location)
                        print(f"Found {len(jobs)} jobs")
                        total_jobs_found += len(jobs)
                        
                        # Process jobs in order (most recent first - already sorted by platforms)
                        for job_data in jobs:
                            # Check if job already exists
                            existing = current_session.query(Job).filter_by(job_url=job_data['url']).first()
                            if existing:
                                continue
                            
                            # Get job details
                            try:
                                details = scraper.get_job_details(job_data['url'])
                                job_data.update(details)
                            except Exception as e:
                                print(f"  Warning: Could not get details for {job_data['title']}")
                                job_data['description'] = ''
                            
                            # Calculate match score
                            match_score = matcher.calculate_match_score(job_data)
                            
                            # Save with search timestamp for 15-min auto-apply logic
                            job_db = Job(
                                title=job_data['title'],
                                company=job_data['company'],
                                location=job_data['location'],
                                platform=job_data['platform'],
                                job_url=job_data['url'],
                                description=job_data.get('description', ''),
                                match_score=match_score,
                                external_site=job_data.get('external_site', True),
                                discovered_date=search_start_time,  # Use search start time
                                applied=False,
                                application_status=None
                            )
                            
                            current_session.add(job_db)
                            new_jobs_added += 1
                            
                            if match_score >= Config.MIN_MATCH_SCORE:
                                print(f"  ⭐ {job_data['title']} - Score: {match_score}")
                            else:
                                print(f"  • {job_data['title']} - Score: {match_score} (below threshold)")
                        
                        # Commit after each search to save progress
                        current_session.commit()
                        print(f"  ✓ Saved {len(jobs)} jobs to database")
                        
                    except Exception as e:
                        print(f"Error searching {title} in {location}: {e}")
                        continue
        
        except Exception as e:
            print(f"✗ Error with {platform_name}: {e}")
        finally:
            try:
                scraper.close_driver()
                current_scrapers.remove(scraper)
            except:
                pass
    
    current_session.close()
    current_session = None
    
    print("\n" + "=" * 50)
    print("✅ Job search completed!")
    print(f"Total jobs found: {total_jobs_found}")
    print(f"New jobs added: {new_jobs_added}")
    print("=" * 50)
    print(f"\n⏰ Search started at: {search_start_time.strftime('%H:%M:%S')}")
    print(f"⏰ Auto-apply deadline: {(search_start_time).strftime('%H:%M:%S')} + 15 min")
    print("\n📋 Next steps:")
    print("1. Quick! Review jobs: python3 review_ui.py")
    print("2. Or wait 15 min, then run: python3 auto_apply_pending.py")
    print("=" * 50)

if __name__ == "__main__":
    main()
