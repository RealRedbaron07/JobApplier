#!/usr/bin/env python3
"""Small, non-pytest smoke check for the supported local-first system."""

__test__ = False

from config import Config
from job_os.profile import load_profile
from scrapers.glassdoor_scraper import GlassdoorScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.workday_scraper import WorkdayScraper


def main() -> int:
    profile = load_profile()
    adapters = (IndeedScraper(), GlassdoorScraper(), LinkedInScraper(), WorkdayScraper())
    checks = {
        "candidate profile": profile.get("name") == "Mustafa Alp ARI",
        "loopback dashboard": Config.DASHBOARD_HOST in {"127.0.0.1", "localhost", "::1"},
        "submission disabled": not Config.AUTO_APPLY_ENABLED and Config.STOP_BEFORE_SUBMIT,
        "protected-board adapters inert": all(adapter.search_jobs("intern", "Toronto") == [] for adapter in adapters),
    }
    for label, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
