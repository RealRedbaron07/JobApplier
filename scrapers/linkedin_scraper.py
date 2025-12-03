from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from config import Config
from typing import List, Dict
import time

class LinkedInScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.linkedin.com"
        self.logged_in = False
    
    def login(self):
        """Login to LinkedIn (optional)."""
        self.init_driver()
        
        # Only login if credentials are provided in .env
        if Config.LINKEDIN_EMAIL and Config.LINKEDIN_PASSWORD:
            print("Attempting to log into LinkedIn...")
            self.driver.get(f"{self.base_url}/login")
            self.random_delay()
            
            try:
                email_field = self.wait_for_element(By.ID, "username")
                email_field.send_keys(Config.LINKEDIN_EMAIL)
                
                password_field = self.driver.find_element(By.ID, "password")
                password_field.send_keys(Config.LINKEDIN_PASSWORD)
                password_field.send_keys(Keys.RETURN)
                
                time.sleep(5)
                self.logged_in = True
                print("✓ LinkedIn login successful.")
            except Exception as e:
                print(f"✗ LinkedIn login failed: {e}")
                print("  Continuing without login.")
                self.logged_in = False
        else:
            print("LinkedIn credentials not provided. Scraping public jobs only.")
    
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Search for jobs on LinkedIn."""
        jobs = []
        # Use public job search URL
        search_url = f"{self.base_url}/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
        
        self.driver.get(search_url)
        self.random_delay(2, 4)
        
        try:
            # Updated selector for job cards
            job_cards = self.driver.find_elements(By.CSS_SELECTOR, "div.base-card")
            
            for card in job_cards[:50]:
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, "h3.base-search-card__title")
                    title = title_elem.text
                    company = card.find_element(By.CSS_SELECTOR, "h4.base-search-card__subtitle").text
                    location_elem = card.find_element(By.CSS_SELECTOR, "span.job-search-card__location")
                    job_location = location_elem.text
                    job_link = card.find_element(By.CSS_SELECTOR, "a.base-card__full-link").get_attribute("href")
                    
                    jobs.append({
                        'title': title,
                        'company': company,
                        'location': job_location,
                        'url': job_link,
                        'platform': 'linkedin'
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"Error searching LinkedIn jobs: {e}")
        
        return jobs
    
    def get_job_details(self, job_url: str) -> Dict:
        """Get detailed job information."""
        self.driver.get(job_url)
        self.random_delay(2, 3)
        
        details = {
            'description': '',
            'external_site': True # Assume external unless Easy Apply is found
        }
        try:
            description = self.driver.find_element(By.CSS_SELECTOR, "div.show-more-less-html__markup").text
            details['description'] = description
            
            # Check for Easy Apply button
            if self.logged_in:
                if self.driver.find_elements(By.CSS_SELECTOR, "button.jobs-apply-button--easy-apply"):
                    details['external_site'] = False
        except Exception:
            details['description'] = "Could not load description."
        
        return details
