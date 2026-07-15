"""Inert legacy scraper interface.

Remote browser scraping was removed from the supported JobApplier workflow.
Ingestion is manual, pasted text, owned CSV/JSON, or a separately reviewed
official API integration.
"""

from __future__ import annotations

import logging
from typing import Any


class BaseScraper:
    def __init__(self) -> None:
        self.driver = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def init_driver(self):
        raise RuntimeError(
            "Browser scraping is disabled. Use the local dashboard's manual, pasted-text, CSV, or JSON ingestion."
        )

    def close_driver(self) -> None:
        self.driver = None

    def random_delay(self, *_args, **_kwargs) -> None:
        return None

    def login(self) -> bool:
        return False

    def search_jobs(self, *_args, **_kwargs) -> list[dict[str, Any]]:
        return []

    def get_job_details(self, *_args, **_kwargs) -> dict[str, Any]:
        return {"description": "", "external_site": True}

    def apply_to_job(self, *_args, **_kwargs) -> bool:
        return False
