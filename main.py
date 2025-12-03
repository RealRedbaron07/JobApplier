from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.glassdoor_scraper import GlassdoorScraper
from resume_parser.parser import ResumeParser
from matcher.job_matcher import JobMatcher
from database.models import Session, Job, UserProfile
from config import Config
import json
from datetime import datetime, timezone
import time
from urllib.parse import urlparse, parse_qs, urlencode

def main():
    print("Starting Job Applier Bot...")
    print("=" * 50)
    print("STEP 1: Finding and scoring jobs")
    print("STEP 2: You review them in review_ui.py")
    print("STEP 3: Apply to approved jobs with apply_jobs.py")
    print("=" * 50)
    
    # Initialize database session
    if Session is None:
        print("Error: Database not initialized")
        return
    
    session = Session()
    
    # Check if user profile exists
    user_profile_db = session.query(UserProfile).first()
    
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
    print("\n[3/3] Searching for jobs...")
    print("=" * 50)
    
    # Separate Turkish and English job titles/locations for efficiency
    turkish_keywords = ['yazılım', 'stajyer', 'geliştirici', 'mühendis', 'veri', 'fintech', 'teknoloji', 'bilgisayar']
    turkish_locations = ['istanbul', 'ankara', 'turkey', 'türkiye', 'türkçe']
    
    def is_turkish_title(title):
        """Check if job title contains Turkish keywords."""
        title_lower = title.lower()
        return any(keyword in title_lower for keyword in turkish_keywords)
    
    def is_turkish_location(location):
        """Check if location is Turkish."""
        location_lower = location.lower()
        return any(turkish_loc in location_lower for turkish_loc in turkish_locations)
    
    def normalize_url(url):
        """Normalize URL to remove tracking parameters for duplicate detection."""
        try:
            parsed = urlparse(url)
            # Remove common tracking parameters
            query_params = parse_qs(parsed.query)
            # Keep only essential parameters, remove tracking ones
            essential_params = {}
            for key, value in query_params.items():
                if key.lower() not in ['refid', 'trackingid', 'ref', 'utm_source', 'utm_medium', 'utm_campaign', 'position', 'pagenum']:
                    essential_params[key] = value[0] if value else ''
            # Rebuild URL with only essential params
            normalized_query = urlencode(essential_params) if essential_params else ''
            normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if normalized_query:
                normalized_url += f"?{normalized_query}"
            return normalized_url
        except:
            return url
    
    def is_duplicate_job(session, job_data):
        """Check if job is a duplicate using multiple methods."""
        # Method 1: Check by normalized URL
        normalized_url = normalize_url(job_data['url'])
        existing = session.query(Job).filter(Job.job_url.like(f"%{normalized_url.split('?')[0]}%")).first()
        if existing:
            return True
        
        # Method 2: Check by title + company (case-insensitive)
        title = job_data.get('title', '').strip().lower()
        company = job_data.get('company', '').strip().lower()
        if title and company:
            existing = session.query(Job).filter(
                Job.title.ilike(f"%{title}%"),
                Job.company.ilike(f"%{company}%")
            ).first()
            if existing:
                return True
        
        return False
    
    total_jobs_found = 0
    new_jobs_added = 0
    start_time = time.time()
    max_time = Config.MAX_SEARCH_TIME_MINUTES * 60  # Convert to seconds
    max_new_jobs = Config.MAX_NEW_JOBS_TO_FIND
    
    for platform_name, scraper, needs_login in scrapers:
        try:
            print(f"\n--- {platform_name} ---")
            
            scraper.login()
            
            for title in Config.JOB_TITLES:
                title_clean = title.strip()
                if not title_clean:
                    continue
                    
                title_is_turkish = is_turkish_title(title_clean)
                
                for location in Config.LOCATIONS:
                    location_clean = location.strip()
                    if not location_clean:
                        continue
                    
                    location_is_turkish = is_turkish_location(location_clean)
                    
                    # Optimize: Only search Turkish titles for Turkish locations, and vice versa
                    # But also search English titles for Turkish locations (bilingual jobs)
                    # Skip Turkish titles for non-Turkish locations to save time
                    if title_is_turkish and not location_is_turkish:
                        continue  # Skip Turkish titles for non-Turkish locations
                    
                    # Check time limit
                    elapsed_time = time.time() - start_time
                    if elapsed_time > max_time:
                        print(f"\n⏰ Time limit reached ({Config.MAX_SEARCH_TIME_MINUTES} minutes). Stopping search.")
                        break
                    
                    # Check job limit
                    if new_jobs_added >= max_new_jobs:
                        print(f"\n✅ Found {new_jobs_added} new jobs (limit: {max_new_jobs}). Stopping search.")
                        break
                    
                    print(f"\nSearching: {title_clean} in {location_clean}")
                    
                    try:
                        jobs = scraper.search_jobs(title_clean, location_clean)
                        print(f"Found {len(jobs)} jobs")
                        total_jobs_found += len(jobs)
                        
                        for job_data in jobs:
                            # Check if job is duplicate (improved detection)
                            if is_duplicate_job(session, job_data):
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
                            
                            # Detect platform from URL
                            job_url_lower = job_data['url'].lower()
                            
                            # Workday detection
                            if 'myworkdayjobs.com' in job_url_lower or 'workday.com' in job_url_lower or 'wd' in job_url_lower:
                                job_data['platform'] = 'workday'
                                job_data['external_site'] = False
                                print(f"  🔄 Workday job detected: {job_data['title']}")
                            
                            # Intern Insider detection
                            elif 'interninsider.com' in job_url_lower or 'interninsider' in job_url_lower:
                                job_data['platform'] = 'interninsider'
                                job_data['external_site'] = False
                                print(f"  🔄 Intern Insider job detected: {job_data['title']}")
                            
                            # Other common ATS platforms
                            elif 'greenhouse.io' in job_url_lower or 'boards.greenhouse.io' in job_url_lower:
                                job_data['platform'] = 'greenhouse'
                                job_data['external_site'] = False
                                print(f"  🔄 Greenhouse job detected: {job_data['title']}")
                            elif 'lever.co' in job_url_lower or 'jobs.lever.co' in job_url_lower:
                                job_data['platform'] = 'lever'
                                job_data['external_site'] = False
                                print(f"  🔄 Lever job detected: {job_data['title']}")
                            elif 'smartrecruiters.com' in job_url_lower:
                                job_data['platform'] = 'smartrecruiters'
                                job_data['external_site'] = False
                                print(f"  🔄 SmartRecruiters job detected: {job_data['title']}")
                            
                            # Save to database
                            job_db = Job(
                                title=job_data['title'],
                                company=job_data['company'],
                                location=job_data['location'],
                                platform=job_data['platform'],
                                job_url=job_data['url'],
                                description=job_data.get('description', ''),
                                match_score=match_score,
                                external_site=job_data.get('external_site', True),
                                    discovered_date=datetime.now(timezone.utc),
                                applied=False,
                                application_status=None
                            )
                            
                            session.add(job_db)
                            new_jobs_added += 1
                            
                            if match_score >= Config.MIN_MATCH_SCORE:
                                print(f"  ⭐ {job_data['title']} - Score: {match_score}")
                            else:
                                print(f"  • {job_data['title']} - Score: {match_score} (below threshold)")
                        
                        session.commit()
                        
                        # Check limits after each search
                        if new_jobs_added >= max_new_jobs:
                            break
                    except Exception as e:
                        print(f"Error searching {title} in {location}: {e}")
                        continue
                
                # Break from location loop if limit reached
                if new_jobs_added >= max_new_jobs:
                    break
            
            # Break from title loop if limit reached
            if new_jobs_added >= max_new_jobs:
                break
        
        except Exception as e:
            print(f"✗ Error with {platform_name}: {e}")
        finally:
            try:
                scraper.close_driver()
            except:
                pass
    
    session.close()
    
    elapsed_minutes = (time.time() - start_time) / 60
    print("\n" + "=" * 50)
    print("Job search completed!")
    print(f"⏱️  Time elapsed: {elapsed_minutes:.1f} minutes")
    print(f"📊 Total jobs found: {total_jobs_found}")
    print(f"✨ New jobs added: {new_jobs_added}")
    if new_jobs_added >= max_new_jobs:
        print(f"   (Stopped at limit: {max_new_jobs} new jobs)")
    if elapsed_minutes * 60 >= max_time:
        print(f"   (Stopped at time limit: {Config.MAX_SEARCH_TIME_MINUTES} minutes)")
    print("=" * 50)
    print("\n📋 Next steps:")
    print("1. Review jobs:  python3 review_ui.py")
    print("2. Apply to approved jobs:  python3 apply_jobs.py")
    print("=" * 50)

if __name__ == "__main__":
    main()
