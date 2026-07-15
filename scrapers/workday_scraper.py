"""Disabled Workday automation adapter retained for import compatibility."""

from __future__ import annotations

from .base_scraper import BaseScraper


class WorkdayScraper(BaseScraper):
    def __init__(self) -> None:
        super().__init__()
        self.base_url = None
        self.logged_in = False
        self.ready_to_submit = False

    def login(self) -> bool:
        self.logger.warning("Workday login/form automation is disabled.")
        return False

    def search_jobs(self, *_args, **_kwargs) -> list[dict]:
        return []

    def get_job_details(self, *_args, **_kwargs) -> dict:
        return {"description": "", "external_site": True}

    def apply_to_job(self, *_args, **_kwargs) -> bool:
        self.ready_to_submit = False
        self.logger.warning("Workday form filling and submission are disabled.")
        return False
