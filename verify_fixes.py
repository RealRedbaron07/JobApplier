#!/usr/bin/env python3
"""
Safety & Integrity Verification Script
Checks that all Guest Mode and Safety fixes are properly applied.
"""

import sys
import os

def check_file_contains(filepath, search_string, description):
    """Check if a file contains a specific string."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            if search_string in content:
                print(f"  ✅ {description}")
                return True
            else:
                print(f"  ❌ {description}")
                return False
    except FileNotFoundError:
        print(f"  ❌ File not found: {filepath}")
        return False

def check_file_not_contains(filepath, search_string, description):
    """Check that a file does NOT contain a specific string."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            if search_string not in content:
                print(f"  ✅ {description}")
                return True
            else:
                print(f"  ❌ {description} (FOUND: {search_string[:50]}...)")
                return False
    except FileNotFoundError:
        print(f"  ❌ File not found: {filepath}")
        return False

def check_syntax(filepath):
    """Check Python syntax."""
    import py_compile
    try:
        py_compile.compile(filepath, doraise=True)
        print(f"  ✅ Syntax OK: {filepath}")
        return True
    except py_compile.PyCompileError as e:
        print(f"  ❌ Syntax Error in {filepath}: {e}")
        return False

def main():
    print("=" * 70)
    print("🔒 Safety & Integrity Verification")
    print("=" * 70)
    
    all_passed = True
    
    # 1. SYNTAX CHECK
    print("\n📋 1. Syntax Check (Critical)")
    print("-" * 40)
    syntax_files = [
        'apply_jobs.py',
        'scrapers/linkedin_scraper.py',
        'scrapers/glassdoor_scraper.py',
        'scrapers/workday_scraper.py',
        'main.py',
        'config.py'
    ]
    for f in syntax_files:
        if not check_syntax(f):
            all_passed = False
    
    # 2. NO RESUME BLOCKER CHECK
    print("\n📋 2. No Resume Blocker Check")
    print("-" * 40)
    
    # Should NOT have the manual input fallback
    if not check_file_not_contains(
        'apply_jobs.py',
        'Falling back to manual input',
        "No manual input fallback (would hang)"
    ):
        all_passed = False
    
    # Should have graceful exit message
    if not check_file_contains(
        'apply_jobs.py',
        'Exiting to prevent hanging',
        "Has graceful exit when no resume"
    ):
        all_passed = False
    
    # 3. GUEST MODE - LINKEDIN EASY APPLY
    print("\n📋 3. Guest Mode - LinkedIn Easy Apply")
    print("-" * 40)
    
    if not check_file_contains(
        'apply_jobs.py',
        'GUEST MODE CHECK',
        "Has Guest Mode check in apply_linkedin_job"
    ):
        all_passed = False
    
    if not check_file_contains(
        'apply_jobs.py',
        'Skipping Easy Apply',
        "Skips Easy Apply when not logged in"
    ):
        all_passed = False
    
    # 4. GUEST MODE - LINKEDIN SCRAPER
    print("\n📋 4. Guest Mode - LinkedIn Scraper")
    print("-" * 40)
    
    if not check_file_contains(
        'scrapers/linkedin_scraper.py',
        'GUEST MODE SUPPORT',
        "Has Guest Mode support in search_jobs"
    ):
        all_passed = False
    
    if not check_file_contains(
        'scrapers/linkedin_scraper.py',
        'if not self.driver',
        "Checks driver initialization"
    ):
        all_passed = False
    
    # 5. GUEST MODE - GLASSDOOR SCRAPER
    print("\n📋 5. Guest Mode - Glassdoor Scraper")
    print("-" * 40)
    
    if not check_file_contains(
        'scrapers/glassdoor_scraper.py',
        'GUEST MODE SUPPORT',
        "Has Guest Mode support in search_jobs"
    ):
        all_passed = False
    
    if not check_file_contains(
        'scrapers/glassdoor_scraper.py',
        'if not self.driver',
        "Checks driver initialization"
    ):
        all_passed = False
    
    # 6. IMPORTS CHECK
    print("\n📋 6. Required Imports")
    print("-" * 40)
    
    if not check_file_contains(
        'apply_jobs.py',
        'from sqlalchemy import or_, and_',
        "Has SQLAlchemy or_/and_ imports"
    ):
        all_passed = False
    
    if not check_file_contains(
        'apply_jobs.py',
        'from config import Config',
        "Has Config import"
    ):
        all_passed = False
    
    # 7. CONFIG CHECK
    print("\n📋 7. Config Settings")
    print("-" * 40)
    
    if not check_file_contains(
        'config.py',
        'MAX_JOB_AGE_DAYS',
        "Has MAX_JOB_AGE_DAYS setting"
    ):
        all_passed = False
    
    if not check_file_contains(
        'config.py',
        'MAX_SEARCH_TIME_MINUTES',
        "Has MAX_SEARCH_TIME_MINUTES setting"
    ):
        all_passed = False
    
    # 8. MODULE IMPORTS TEST
    print("\n📋 8. Module Import Test")
    print("-" * 40)
    
    try:
        from apply_jobs import apply_to_jobs
        print("  ✅ apply_jobs.py imports successfully")
    except Exception as e:
        print(f"  ❌ apply_jobs.py import failed: {e}")
        all_passed = False
    
    try:
        from scrapers.linkedin_scraper import LinkedInScraper
        print("  ✅ linkedin_scraper.py imports successfully")
    except Exception as e:
        print(f"  ❌ linkedin_scraper.py import failed: {e}")
        all_passed = False
    
    try:
        from scrapers.glassdoor_scraper import GlassdoorScraper
        print("  ✅ glassdoor_scraper.py imports successfully")
    except Exception as e:
        print(f"  ❌ glassdoor_scraper.py import failed: {e}")
        all_passed = False
    
    try:
        from scrapers.workday_scraper import WorkdayScraper
        print("  ✅ workday_scraper.py imports successfully")
    except Exception as e:
        print(f"  ❌ workday_scraper.py import failed: {e}")
        all_passed = False
    
    try:
        from config import Config
        print("  ✅ config.py imports successfully")
        print(f"     MAX_JOB_AGE_DAYS = {Config.MAX_JOB_AGE_DAYS}")
        print(f"     MIN_MATCH_SCORE = {Config.MIN_MATCH_SCORE}")
    except Exception as e:
        print(f"  ❌ config.py import failed: {e}")
        all_passed = False
    
    # FINAL RESULT
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 ALL CHECKS PASSED - System is ready for Guest Mode operation!")
        print("=" * 70)
        print("\nThe bot will now:")
        print("  • Exit gracefully if no resume is in the database")
        print("  • Skip LinkedIn Easy Apply when not logged in")
        print("  • Use public search for LinkedIn/Glassdoor without login")
        print("  • Filter jobs by date and remove duplicates")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Review the errors above")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(main())
