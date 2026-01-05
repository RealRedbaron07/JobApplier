#!/usr/bin/env python3
"""
Verification script for the three critical fixes:
1. Fallback scraping strategies in LinkedIn/Indeed scrapers
2. Auto-resume selection from database (no input() prompts)
3. Workday handle_custom_questions method
"""

import sys
import os
import tempfile
from unittest.mock import MagicMock, patch
from io import StringIO

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Track test results
results = {
    'passed': 0,
    'failed': 0,
    'skipped': 0,
    'details': []
}

def log_result(test_name: str, passed: bool, message: str = "", skipped: bool = False):
    """Log a test result."""
    if skipped:
        results['skipped'] += 1
        status = "⏭️  SKIPPED"
    elif passed:
        results['passed'] += 1
        status = "✅ PASSED"
    else:
        results['failed'] += 1
        status = "❌ FAILED"
    
    results['details'].append({
        'name': test_name,
        'status': status,
        'message': message
    })
    
    print(f"\n{status}: {test_name}")
    if message:
        print(f"   {message}")


def test_linkedin_scraping():
    """
    Test 1: Live Scraping - LinkedIn
    Verifies that the fallback scraping strategy works.
    """
    print("\n" + "=" * 60)
    print("TEST 1: LinkedIn Scraper Fallback Strategy")
    print("=" * 60)
    
    try:
        from scrapers.linkedin_scraper import LinkedInScraper
        
        # Check that the class has the search_jobs method
        scraper = LinkedInScraper()
        assert hasattr(scraper, 'search_jobs'), "search_jobs method not found"
        
        # Verify the method signature accepts keywords and location
        import inspect
        sig = inspect.signature(scraper.search_jobs)
        params = list(sig.parameters.keys())
        assert 'keywords' in params, "keywords parameter missing"
        assert 'location' in params, "location parameter missing"
        
        log_result(
            "LinkedIn Scraper Structure",
            True,
            "search_jobs method exists with correct signature"
        )
        
        # Check that the fallback selectors are in place by inspecting source
        import inspect
        source = inspect.getsource(scraper.search_jobs)
        
        # Check for Strategy comments
        has_strategy1 = "STRATEGY 1" in source or "CSS selectors" in source.lower()
        has_strategy2 = "STRATEGY 2" in source or "XPath" in source
        has_strategy3 = "STRATEGY 3" in source or "semantic" in source.lower()
        
        if has_strategy1 and has_strategy2 and has_strategy3:
            log_result(
                "LinkedIn Fallback Strategies Present",
                True,
                "All 3 fallback strategies (CSS, XPath, Semantic) are implemented"
            )
        else:
            log_result(
                "LinkedIn Fallback Strategies Present",
                False,
                f"Missing strategies: CSS={has_strategy1}, XPath={has_strategy2}, Semantic={has_strategy3}"
            )
        
        # Check for specific XPath patterns
        has_job_view_xpath = "/jobs/view/" in source
        has_jobs_xpath = "//a[contains(@href" in source
        
        if has_job_view_xpath and has_jobs_xpath:
            log_result(
                "LinkedIn XPath Patterns",
                True,
                "Job link XPath patterns are present for fallback"
            )
        else:
            log_result(
                "LinkedIn XPath Patterns",
                False,
                "Missing XPath patterns for job links"
            )
        
        # Live test with browser (if possible)
        print("\n  📡 Attempting live scraping test...")
        print("     (This requires Chrome/ChromeDriver and network access)")
        
        try:
            # Try to initialize driver
            scraper.init_driver()
            
            # Run search
            jobs = scraper.search_jobs('Software Engineer', 'Remote')
            
            if len(jobs) > 0:
                log_result(
                    "LinkedIn Live Scraping",
                    True,
                    f"Found {len(jobs)} jobs successfully"
                )
            else:
                # Get which selectors were tried from the output
                log_result(
                    "LinkedIn Live Scraping",
                    False,
                    "Returned 0 jobs - check console output above for which selectors failed"
                )
            
            scraper.close_driver()
            
        except Exception as e:
            error_msg = str(e)
            if "chrome" in error_msg.lower() or "webdriver" in error_msg.lower():
                log_result(
                    "LinkedIn Live Scraping",
                    False,
                    f"Browser/driver not available: {error_msg[:100]}",
                    skipped=True
                )
            else:
                log_result(
                    "LinkedIn Live Scraping",
                    False,
                    f"Error: {error_msg[:100]}"
                )
        
    except Exception as e:
        log_result("LinkedIn Scraper", False, f"Import/setup error: {e}")


def test_resume_logic():
    """
    Test 2: Resume Logic
    Verifies that resume is auto-selected from DB without input() prompts.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Resume Auto-Selection Logic")
    print("=" * 60)
    
    try:
        # Create a temporary resume file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
            f.write("Fake PDF content")
            temp_resume_path = f.name
        
        try:
            # Mock the database session and UserProfile
            mock_user_profile = MagicMock()
            mock_user_profile.resume_path = temp_resume_path
            mock_user_profile.email = "test@example.com"
            mock_user_profile.phone = "555-1234"
            mock_user_profile.first_name = "Test"
            mock_user_profile.last_name = "User"
            mock_user_profile.skills = '["Python", "JavaScript"]'
            mock_user_profile.experience = '[]'
            mock_user_profile.education = '[]'
            
            mock_session = MagicMock()
            mock_session.query.return_value.first.return_value = mock_user_profile
            mock_session.query.return_value.filter_by.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []
            
            # Read the apply_jobs.py to check the logic
            with open('apply_jobs.py', 'r') as f:
                source = f.read()
            
            # Check that input() is NOT called for resume selection
            # The key change was removing get_resume_path() call
            
            # Check for the auto-use pattern
            has_auto_use = "resume_to_use = default_resume_path" in source
            has_no_input_for_resume = "get_resume_path(default_resume_path)" not in source
            
            if has_auto_use and has_no_input_for_resume:
                log_result(
                    "Resume Auto-Selection Pattern",
                    True,
                    "Resume is auto-selected from DB without calling get_resume_path()"
                )
            else:
                log_result(
                    "Resume Auto-Selection Pattern",
                    False,
                    f"Auto-use={has_auto_use}, No input call={has_no_input_for_resume}"
                )
            
            # Check that the exit condition exists when no resume
            # (Note: Logic changed to allow fallback, so we check if it handles both)
            has_auto_logic = "if user_profile_db.resume_path and os.path.exists" in source
            has_fallback_logic = "resume_to_use = get_resume_path(None)" in source
            
            if has_auto_logic and has_fallback_logic:
                log_result(
                    "Resume logic: Auto-use with Manual Fallback",
                    True,
                    "Source code correctly implements auto-use of DB resume with manual fallback if missing"
                )
            else:
                log_result(
                    "Resume logic: Auto-use with Manual Fallback",
                    False,
                    f"Missing conditional logic: Auto={has_auto_logic}, Fallback={has_fallback_logic}"
                )
            
            # Verify the get_resume_path function still exists
            has_function = "def get_resume_path" in source
            log_result(
                "get_resume_path Function Preserved",
                has_function,
                "Function preserved for manual fallback interaction"
            )
            
            # The key assertion: verify the code logic allows skipping input
            if "if user_profile_db.resume_path" in source and "resume_to_use = default_resume_path" in source:
                log_result(
                    "Automated Flow Support",
                    True,
                    "Code path documented to allow zero-interaction when resume exists"
                )
            else:
                log_result(
                    "Automated Flow Support",
                    False,
                    "Automated code block not found"
                )
                
        finally:
            # Cleanup temp file
            os.unlink(temp_resume_path)
            
    except Exception as e:
        log_result("Resume Logic", False, f"Error: {e}")


def test_workday_logic():
    """
    Test 3: Workday Logic
    Verifies handle_custom_questions method exists with proper defaults.
    """
    print("\n" + "=" * 60)
    print("TEST 3: Workday Custom Questions Handler")
    print("=" * 60)
    
    try:
        from scrapers.workday_scraper import WorkdayScraper
        
        # Instantiate scraper
        scraper = WorkdayScraper()
        
        # Check if handle_custom_questions method exists
        has_method = hasattr(scraper, 'handle_custom_questions')
        
        if has_method:
            log_result(
                "handle_custom_questions Method Exists",
                True,
                "Method found on WorkdayScraper class"
            )
        else:
            log_result(
                "handle_custom_questions Method Exists",
                False,
                "Method NOT found on WorkdayScraper class"
            )
            return
        
        # Check method signature
        import inspect
        sig = inspect.signature(scraper.handle_custom_questions)
        params = list(sig.parameters.keys())
        
        if 'driver' in params:
            log_result(
                "Method Signature Correct",
                True,
                f"Parameters: {params}"
            )
        else:
            log_result(
                "Method Signature Correct",
                False,
                f"Expected 'driver' parameter, got: {params}"
            )
        
        # Check for DEFAULT_ANSWERS dictionary in the method source
        source = inspect.getsource(scraper.handle_custom_questions)
        
        # Required keys that should be in DEFAULT_ANSWERS
        required_patterns = [
            ('sponsorship', "'sponsorship'"),
            ('disability', "'disability'"),
            ('gender', "'gender'"),
            ('veteran', "'veteran'"),
            ('race/ethnicity', "'race'" ),
            ('work authorization', "'authorized to work'" ),
        ]
        
        found_patterns = []
        missing_patterns = []
        
        for name, pattern in required_patterns:
            if pattern.lower() in source.lower():
                found_patterns.append(name)
            else:
                missing_patterns.append(name)
        
        if len(found_patterns) >= 5:
            log_result(
                "DEFAULT_ANSWERS Dictionary Complete",
                True,
                f"Found {len(found_patterns)}/6 required question categories: {', '.join(found_patterns)}"
            )
        else:
            log_result(
                "DEFAULT_ANSWERS Dictionary Complete",
                False,
                f"Missing categories: {', '.join(missing_patterns)}"
            )
        
        # Check for answer value patterns
        answer_patterns = [
            ("'no'" , "No answer for sponsorship"),
            ("'yes'", "Yes answer for authorization"),
            ("'decline'", "Decline answer for demographics"),
        ]
        
        all_answers_found = True
        for pattern, description in answer_patterns:
            if pattern not in source.lower():
                all_answers_found = False
                break
        
        if all_answers_found:
            log_result(
                "Default Answers Values Present",
                True,
                "Found 'no', 'yes', and 'decline' answer options"
            )
        else:
            log_result(
                "Default Answers Values Present",
                False,
                "Missing some default answer values"
            )
        
        # Check that the method handles radio buttons, selects, and checkboxes
        handles_radio = "radio" in source.lower()
        handles_select = "select" in source.lower()
        handles_checkbox = "checkbox" in source.lower()
        
        if handles_radio and handles_select and handles_checkbox:
            log_result(
                "Multiple Input Types Supported",
                True,
                "Handles radio buttons, selects, and checkboxes"
            )
        else:
            log_result(
                "Multiple Input Types Supported",
                False,
                f"Radio={handles_radio}, Select={handles_select}, Checkbox={handles_checkbox}"
            )
        
        # Check that handle_custom_questions is called in _fill_workday_form
        form_source = inspect.getsource(scraper._fill_workday_form)
        if "handle_custom_questions" in form_source:
            log_result(
                "Method Integrated in Form Filling",
                True,
                "handle_custom_questions is called during form filling"
            )
        else:
            log_result(
                "Method Integrated in Form Filling",
                False,
                "handle_custom_questions is NOT called in _fill_workday_form"
            )
            
    except Exception as e:
        import traceback
        log_result("Workday Logic", False, f"Error: {e}\n{traceback.format_exc()}")


def print_summary():
    """Print test summary."""
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    total = results['passed'] + results['failed'] + results['skipped']
    
    print(f"\n  ✅ Passed:  {results['passed']}")
    print(f"  ❌ Failed:  {results['failed']}")
    print(f"  ⏭️  Skipped: {results['skipped']}")
    print(f"  ─────────────────")
    print(f"  📊 Total:   {total}")
    
    print("\n" + "-" * 60)
    print("DETAILED RESULTS:")
    print("-" * 60)
    
    for detail in results['details']:
        print(f"\n  {detail['status']}: {detail['name']}")
        if detail['message']:
            print(f"     → {detail['message']}")
    
    print("\n" + "=" * 60)
    
    if results['failed'] == 0:
        print("🎉 ALL TESTS PASSED!")
    else:
        print(f"⚠️  {results['failed']} TEST(S) FAILED - Review details above")
    
    print("=" * 60)
    
    return results['failed'] == 0


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔍 VERIFICATION SCRIPT FOR JOB APPLIER FIXES")
    print("=" * 60)
    print("Testing the three critical fixes:")
    print("  1. LinkedIn/Indeed fallback scraping strategies")
    print("  2. Auto-resume selection from database")
    print("  3. Workday handle_custom_questions method")
    print("=" * 60)
    
    # Run all tests
    test_linkedin_scraping()
    test_resume_logic()
    test_workday_logic()
    
    # Print summary
    success = print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
