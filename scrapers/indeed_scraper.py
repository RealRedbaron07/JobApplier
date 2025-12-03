from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from typing import List, Dict
import time

class IndeedScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.indeed.com"
        self.requires_login = False  # Indeed can be scraped without login
    
    def login(self):
        """Indeed doesn't require login for browsing."""
        self.init_driver()
        print("Indeed scraper initialized (no login required)")
    
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Search for jobs on Indeed."""
        jobs = []
        search_url = f"{self.base_url}/jobs?q={keywords.replace(' ', '+')}&l={location.replace(' ', '+')}"
        
        try:
            self.driver.get(search_url)
            self.random_delay(2, 4)
            
            job_cards = self.driver.find_elements(By.CLASS_NAME, "job_seen_beacon")
            
            for card in job_cards[:50]:
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, "h2.jobTitle span")
                    title = title_elem.text
                    company = card.find_element(By.CSS_SELECTOR, "span[data-testid='company-name']").text
                    location_elem = card.find_element(By.CSS_SELECTOR, "div[data-testid='text-location']")
                    job_location = location_elem.text
                    job_link = card.find_element(By.CSS_SELECTOR, "h2.jobTitle a").get_attribute("href")
                    
                    jobs.append({
                        'title': title,
                        'company': company,
                        'location': job_location,
                        'url': job_link,
                        'platform': 'indeed'
                    })
                except Exception as e:
                    continue
        except Exception as e:
            print(f"Error searching Indeed jobs: {e}")
        
        return jobs
    
    def get_job_details(self, job_url: str) -> Dict:
        """Get detailed job information."""
        details = {
            'description': '',
            'external_site': False
        }
        
        try:
            self.driver.get(job_url)
            self.random_delay(2, 3)
            
            description = self.driver.find_element(By.ID, "jobDescriptionText").text
            details['description'] = description
            details['external_site'] = self._check_if_external_application()
        except Exception as e:
            print(f"Error getting Indeed job details: {e}")
        
        return details
    
    def _check_if_external_application(self) -> bool:
        """Check if application is on external site."""
        try:
            apply_button = self.driver.find_element(By.ID, "applyButtonLinkContainer")
            return "company" in apply_button.text.lower() or "employer" in apply_button.text.lower()
        except:
            return False
