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
        print("Glassdoor scraper initialized (attempting without login)")
        
        # Only attempt login if credentials are provided
        if Config.GLASSDOOR_EMAIL != 'your-email@example.com' and Config.GLASSDOOR_PASSWORD != 'your-password-here':
            try:
                self._attempt_login()
            except Exception as e:
                print(f"Glassdoor login skipped or failed: {e}")
    
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
        """Search for jobs on Glassdoor."""
        jobs = []
        search_url = f"{self.base_url}/Job/jobs.htm?sc.keyword={keywords.replace(' ', '%20')}&locT=C&locId={location.replace(' ', '%20')}"
        
        try:
            self.driver.get(search_url)
            self.random_delay(2, 4)
            
            # Try multiple selectors for job cards
            job_cards = []
            card_selectors = [
                "li[data-test='jobListing']",
                "li.jobListing",
                "div[data-test='job-listing']",
            ]
            
            for selector in card_selectors:
                try:
                    job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if job_cards:
                        break
                except:
                    continue
            
            for card in job_cards[:50]:
                try:
                    # Try multiple selectors for each field
                    title = None
                    title_selectors = [
                        "a[data-test='job-link']",
                        "a.jobLink",
                    ]
                    for sel in title_selectors:
                        try:
                            title_elem = card.find_element(By.CSS_SELECTOR, sel)
                            title = title_elem.text
                            if title:
                                break
                        except:
                            continue
                    
                    if not title:
                        continue
                    
                    company = None
                    company_selectors = [
                        "div[data-test='employer-name']",
                        "span.employerName",
                    ]
                    for sel in company_selectors:
                        try:
                            company_elem = card.find_element(By.CSS_SELECTOR, sel)
                            company = company_elem.text
                            if company:
                                break
                        except:
                            continue
                    
                    job_location = None
                    location_selectors = [
                        "div[data-test='emp-location']",
                        "div.location",
                    ]
                    for sel in location_selectors:
                        try:
                            loc_elem = card.find_element(By.CSS_SELECTOR, sel)
                            job_location = loc_elem.text
                            if job_location:
                                break
                        except:
                            continue
                    
                    job_link = None
                    try:
                        link_elem = card.find_element(By.CSS_SELECTOR, "a[data-test='job-link']")
                        job_link = link_elem.get_attribute("href")
                        if job_link and not job_link.startswith('http'):
                            job_link = f"{self.base_url}{job_link}"
                    except:
                        pass
                    
                    if title and company and job_link:
                        jobs.append({
                            'title': title,
                            'company': company,
                            'location': job_location or location,
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
            
            # Try multiple selectors for job description
            description = None
            desc_selectors = [
                (By.CLASS_NAME, "jobDescriptionContent"),
                (By.CSS_SELECTOR, "div.jobDescriptionContent"),
                (By.CSS_SELECTOR, "div[data-test='jobDescriptionText']"),
                (By.CSS_SELECTOR, "div.jobDescription"),
            ]
            
            for by, selector in desc_selectors:
                try:
                    desc_elem = self.driver.find_element(by, selector)
                    description = desc_elem.text
                    if description and len(description) > 50:
                        break
                except:
                    continue
            
            if description:
                details['description'] = description
            else:
                details['description'] = "Description not available"
        except Exception as e:
            print(f"Error getting Glassdoor job details: {e}")
        
        return details
