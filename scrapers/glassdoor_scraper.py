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
        self.requires_login = False
        self.logged_in = False
    
    def login(self):
        """Try to browse Glassdoor without login (Guest Mode)."""
        # Initialize driver first - Guest Mode support
        if self.driver is None:
            self.init_driver()
        
        print("Glassdoor scraper initialized (Guest Mode - no login required)")
        
        # Only attempt login if credentials are provided
        if Config.GLASSDOOR_EMAIL and Config.GLASSDOOR_PASSWORD:
            try:
                self._attempt_login()
                self.logged_in = True
            except Exception as e:
                print(f"Glassdoor login skipped: {e}")
                self.logged_in = False
    
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
            print("Glassdoor login successful")
        except Exception as e:
            print(f"Glassdoor login error: {e}")
    
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Search for jobs on Glassdoor (Guest Mode supported)."""
        jobs = []
        
        # Guest Mode: ensure driver is initialized
        if self.driver is None:
            self.init_driver()
        
        search_url = f"{self.base_url}/Job/jobs.htm?sc.keyword={keywords.replace(' ', '%20')}&locT=C&locId={location.replace(' ', '%20')}"
        
        try:
            self.driver.get(search_url)
            self.random_delay(2, 4)
            
            # Close any popups that might appear
            try:
                close_buttons = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label='Close']")
                for btn in close_buttons:
                    try:
                        self.safe_click(btn)
                    except:
                        pass
            except:
                pass
            
            job_cards = self.driver.find_elements(By.CSS_SELECTOR, "li[data-test='jobListing']")
            
            for card in job_cards[:50]:
                try:
                    title = card.find_element(By.CSS_SELECTOR, "a[data-test='job-link']").text
                    
                    # Validation: skip if no title
                    if not title:
                        continue
                    
                    company = card.find_element(By.CSS_SELECTOR, "div[data-test='employer-name']").text
                    
                    # Validation: skip if no company
                    if not company:
                        continue
                    
                    location_elem = card.find_element(By.CSS_SELECTOR, "div[data-test='emp-location']")
                    job_location = location_elem.text
                    job_link = card.find_element(By.CSS_SELECTOR, "a[data-test='job-link']").get_attribute("href")
                    
                    # Validation: skip if no URL
                    if not job_link:
                        continue
                    
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
            print(f"Error searching Glassdoor jobs: {e}")
        
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
            print(f"Error getting Glassdoor job details: {e}")
        
        return details
