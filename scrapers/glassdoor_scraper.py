from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from config import Config
from typing import List, Dict
import time

class GlassdoorScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.glassdoor.com"
        self.requires_login = False  # Try without login first
    
    def login(self):
        """Try to browse Glassdoor without login."""
        self.init_driver()
        self.logger.info("Glassdoor scraper initialized (attempting without login)")
        
        # Only attempt login if credentials are provided
        if Config.GLASSDOOR_EMAIL != 'your-email@example.com' and Config.GLASSDOOR_PASSWORD != 'your-password-here':
            try:
                self._attempt_login()
            except Exception as e:
                self.logger.debug(f"Glassdoor login skipped or failed: {e}")
    
    def _attempt_login(self):
        """Attempt login if credentials are available."""
        self.driver.get(f"{self.base_url}/profile/login_input.htm")
        self.random_delay()
        
        try:
            email_field = self.wait_for_element(By.ID, "inlineUserEmail")
            email_field.send_keys(Config.GLASSDOOR_EMAIL)
            
            continue_btn = self.driver.find_element(By.NAME, "submit")
            self.safe_click(continue_btn)
            self.random_delay()
            
            password_field = self.wait_for_element(By.ID, "inlineUserPassword")
            password_field.send_keys(Config.GLASSDOOR_PASSWORD)
            password_field.send_keys(Keys.RETURN)
            
            time.sleep(5)
            self.logger.info("Glassdoor login successful")
        except Exception as e:
            self.logger.warning(f"Glassdoor login error: {e}")
    
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Search for jobs on Glassdoor.
        
        GUEST MODE SUPPORT: Works without login using public job search.
        Glassdoor allows public job browsing with limited functionality.
        """
        jobs = []
        
        # Ensure driver is initialized (for guest mode)
        if not self.driver:
            try:
                self.init_driver()
                self.logger.info("Guest Mode: Using public Glassdoor search")
            except Exception as e:
                self.logger.warning(f"Failed to initialize driver: {e}")
                return []
        
        search_url = f"{self.base_url}/Job/jobs.htm?sc.keyword={keywords.replace(' ', '%20')}&locT=C&locId={location.replace(' ', '%20')}"
        
        try:
            self.driver.get(search_url)
            self.random_delay(2, 4)
            
            job_cards = self.driver.find_elements(By.CSS_SELECTOR, "li[data-test='jobListing']")
            
            for card in job_cards[:50]:
                try:
                    title = card.find_element(By.CSS_SELECTOR, "a[data-test='job-link']").text
                    company = card.find_element(By.CSS_SELECTOR, "div[data-test='employer-name']").text
                    location_elem = card.find_element(By.CSS_SELECTOR, "div[data-test='emp-location']")
                    job_location = location_elem.text
                    job_link = card.find_element(By.CSS_SELECTOR, "a[data-test='job-link']").get_attribute("href")
                    
                    jobs.append({
                        'title': title,
                        'company': company,
                        'location': job_location,
                        'url': job_link,
                        'platform': 'glassdoor'
                    })
                except Exception as e:
                    continue
        except Exception as e:
            self.logger.error(f"Error searching Glassdoor jobs: {e}")
        
        return jobs
    
    def get_job_details(self, job_url: str) -> Dict:
        """Get detailed job information."""
        details = {
            'description': '',
            'external_site': True
        }
        
        try:
            self.driver.get(job_url)
            self.random_delay(2, 3)
            
            description = self.driver.find_element(By.CLASS_NAME, "jobDescriptionContent").text
            details['description'] = description
        except Exception as e:
            self.logger.debug(f"Error getting Glassdoor job details: {e}")
        
        return details
