"""Disabled LinkedIn automation adapter retained for import compatibility."""

from __future__ import annotations

from .base_scraper import BaseScraper


class LinkedInScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__()
        self.base_url = "https://www.linkedin.com"
        self.logged_in = False
        self.ready_to_submit = False

    def login(self) -> bool:
        self.logger.warning("LinkedIn login automation is disabled.")
        return False

    def search_jobs(self, *_args, **_kwargs) -> list[dict]:
        self.logger.warning("LinkedIn scraping is disabled; paste a public posting manually.")
        return []

    def get_job_details(self, *_args, **_kwargs) -> dict:
        return {"description": "", "external_site": True}

    def apply_to_job(self, *_args, **_kwargs) -> bool:
        self.ready_to_submit = False
        self.logger.warning("LinkedIn form filling and submission are disabled.")
        return False
