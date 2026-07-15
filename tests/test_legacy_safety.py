from pathlib import Path

from config import Config
from scrapers.glassdoor_scraper import GlassdoorScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.workday_scraper import WorkdayScraper


def test_protected_board_adapters_are_inert():
    assert Config.PROTECTED_BOARD_AUTOMATION_ENABLED is False
    assert LinkedInScraper().search_jobs("intern", "Toronto") == []
    assert IndeedScraper().search_jobs("intern", "Toronto") == []
    assert GlassdoorScraper().search_jobs("intern", "Toronto") == []
    assert LinkedInScraper().apply_to_job("https://example.com") is False
    assert WorkdayScraper().apply_to_job("https://example.com") is False


def test_no_anti_detection_or_submit_click_code_remains():
    files = [
        "apply_jobs.py", "auto_apply.py", "run_linkedin.py",
        "export_applications.py",
        "cover_letter_generator.py", "resume_tailor.py", "resume_parser/parser.py",
        "scrapers/base_scraper.py", "scrapers/indeed_scraper.py", "scrapers/glassdoor_scraper.py",
        "scrapers/linkedin_scraper.py", "scrapers/workday_scraper.py",
    ]
    content = "\n".join(Path(name).read_text(encoding="utf-8") for name in files)
    assert "undetected_chromedriver" not in content
    assert "AutomationControlled" not in content
    assert ".click()" not in content
    assert "selenium" not in content.lower()
    assert "openai" not in content.lower()
    assert "GPA" not in content


def test_retired_export_cli_cannot_query_stale_columns():
    from export_applications import export_summary_table, export_to_csv

    assert export_to_csv() is False
    assert export_summary_table() is False
