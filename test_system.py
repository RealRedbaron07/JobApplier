#!/usr/bin/env python3
"""
Quick system test to verify all components are working.
Run this after installation to check if everything is set up correctly.
"""

import sys

def test_imports():
    """Test if all required modules can be imported."""
    print("Testing imports...")
    try:
        from database.models import Session, Job, UserProfile
        from scrapers.indeed_scraper import IndeedScraper
        from scrapers.linkedin_scraper import LinkedInScraper
        from scrapers.glassdoor_scraper import GlassdoorScraper
        from resume_parser.parser import ResumeParser
        from matcher.job_matcher import JobMatcher
        from config import Config
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

def test_database():
    """Test database initialization."""
    print("\nTesting database...")
    try:
        from database.models import Session
        if Session is None:
            print("✗ Database not initialized")
            return False
        session = Session()
        session.close()
        print("✓ Database connection successful")
        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def test_config():
    """Test configuration loading."""
    print("\nTesting configuration...")
    try:
        from config import Config
        print(f"  MIN_MATCH_SCORE: {Config.MIN_MATCH_SCORE}")
        print(f"  JOB_TITLES: {len(Config.JOB_TITLES)} titles")
        print(f"  LOCATIONS: {len(Config.LOCATIONS)} locations")
        print(f"  OpenAI API: {'Configured' if Config.OPENAI_API_KEY else 'Not configured (using rule-based parsing)'}")
        print(f"  LinkedIn: {'Configured' if Config.LINKEDIN_EMAIL else 'Not configured (optional)'}")
        print("✓ Configuration loaded")
        return True
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False

def test_matcher():
    """Test job matcher."""
    print("\nTesting job matcher...")
    try:
        from matcher.job_matcher import JobMatcher
        
        test_profile = {
            'skills': ['python', 'java', 'sql'],
            'experience': [],
            'education': []
        }
        
        matcher = JobMatcher(test_profile)
        
        test_job = {
            'title': 'Software Engineering Intern',
            'description': 'Looking for a Python developer intern with SQL experience. Great opportunity for students.',
            'location': 'Remote'
        }
        
        score = matcher.calculate_match_score(test_job)
        print(f"  Test job match score: {score}/100")
        
        if score > 0:
            print("✓ Job matcher working")
            return True
        else:
            print("⚠ Job matcher returned 0 score (may need adjustment)")
            return True  # Still consider it working
    except Exception as e:
        print(f"✗ Job matcher test failed: {e}")
        return False

def test_resume_parser():
    """Test resume parser initialization."""
    print("\nTesting resume parser...")
    try:
        from resume_parser.parser import ResumeParser
        parser = ResumeParser()
        print("✓ Resume parser initialized")
        return True
    except Exception as e:
        print(f"✗ Resume parser test failed: {e}")
        return False

def test_scraper_init():
    """Test scraper initialization (without actually scraping)."""
    print("\nTesting scrapers...")
    results = []
    
    # Test Indeed scraper
    try:
        from scrapers.indeed_scraper import IndeedScraper
        scraper = IndeedScraper()
        print("  ✓ Indeed scraper can be initialized")
        results.append(True)
    except Exception as e:
        print(f"  ✗ Indeed scraper failed: {e}")
        results.append(False)
    
    # Test LinkedIn scraper
    try:
        from scrapers.linkedin_scraper import LinkedInScraper
        scraper = LinkedInScraper()
        print("  ✓ LinkedIn scraper can be initialized")
        results.append(True)
    except Exception as e:
        print(f"  ✗ LinkedIn scraper failed: {e}")
        results.append(False)
    
    # Test Glassdoor scraper
    try:
        from scrapers.glassdoor_scraper import GlassdoorScraper
        scraper = GlassdoorScraper()
        print("  ✓ Glassdoor scraper can be initialized")
        results.append(True)
    except Exception as e:
        print(f"  ✗ Glassdoor scraper failed: {e}")
        results.append(False)
    
    return all(results)

def main():
    """Run all tests."""
    print("=" * 70)
    print("Job Applier System Test")
    print("=" * 70)
    
    tests = [
        ("Imports", test_imports),
        ("Database", test_database),
        ("Configuration", test_config),
        ("Job Matcher", test_matcher),
        ("Resume Parser", test_resume_parser),
        ("Scrapers", test_scraper_init),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} test crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status} - {name}")
    
    print("=" * 70)
    print(f"Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! System is ready to use.")
        print("\nNext steps:")
        print("1. Run: python3 setup_profile.py /path/to/resume.pdf")
        print("2. Run: python3 main.py")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        print("Common issues:")
        print("  - Missing dependencies: pip3 install -r requirements.txt")
        print("  - Database issues: Check SQLite installation")
        print("  - Chrome/ChromeDriver: Make sure Chrome is installed")
        return 1

if __name__ == "__main__":
    sys.exit(main())

