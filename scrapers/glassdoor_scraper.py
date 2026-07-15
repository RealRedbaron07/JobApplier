"""Disabled Glassdoor automation adapter retained for import compatibility."""

from .base_scraper import BaseScraper


class GlassdoorScraper(BaseScraper):
    """Inert adapter: import job text or owned exports through the dashboard."""

    def __init__(self) -> None:
        super().__init__()
        self.base_url = "https://www.glassdoor.com"
        self.requires_login = False

    def login(self) -> bool:
        self.logger.warning("Glassdoor login automation is disabled.")
        return False

    def search_jobs(self, *_args, **_kwargs) -> list[dict]:
        self.logger.warning("Glassdoor scraping is disabled; paste a posting or import owned data.")
        return []

    def get_job_details(self, *_args, **_kwargs) -> dict:
        return {"description": "", "external_site": True}
