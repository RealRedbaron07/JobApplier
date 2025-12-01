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
        
        try:
            self.driver.get(search_url)
            self.random_delay(2, 4)
            
            # Try multiple selectors for job cards (LinkedIn changes HTML)
            job_cards = []
            card_selectors = [
                "div.base-card",
                "div.job-search-card",
                "li.jobs-search-results__list-item",
                "div[data-job-id]",
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
                    # Try multiple selectors for title
                    title = None
                    title_selectors = [
                        "h3.base-search-card__title",
                        "h3.job-search-card__title",
                        "a.job-search-card__link",
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
                    
                    # Try multiple selectors for company
                    company = None
                    company_selectors = [
                        "h4.base-search-card__subtitle",
                        "h4.job-search-card__subtitle",
                        "a.job-search-card__subtitle-link",
                    ]
                    for sel in company_selectors:
                        try:
                            company_elem = card.find_element(By.CSS_SELECTOR, sel)
                            company = company_elem.text
                            if company:
                                break
                        except:
                            continue
                    
                    # Try multiple selectors for location
                    job_location = None
                    location_selectors = [
                        "span.job-search-card__location",
                        "span.base-search-card__metadata",
                    ]
                    for sel in location_selectors:
                        try:
                            loc_elem = card.find_element(By.CSS_SELECTOR, sel)
                            job_location = loc_elem.text
                            if job_location:
                                break
                        except:
                            continue
                    
                    # Get job link
                    job_link = None
                    link_selectors = [
                        "a.base-card__full-link",
                        "a.job-search-card__link",
                    ]
                    for sel in link_selectors:
                        try:
                            link_elem = card.find_element(By.CSS_SELECTOR, sel)
                            job_link = link_elem.get_attribute("href")
                            if job_link:
                                break
                        except:
                            continue
                    
                    if title and company and job_link:
                        jobs.append({
                            'title': title,
                            'company': company,
                            'location': job_location or location,
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
        details = {
            'description': '',
            'external_site': True # Assume external unless Easy Apply is found
        }
        
        try:
            self.driver.get(job_url)
            self.random_delay(2, 3)
            
            # Try multiple selectors for job description
            description = None
            desc_selectors = [
                "div.show-more-less-html__markup",
                "div.jobs-description-content__text",
                "div[data-test-id='job-description']",
                "section.jobs-description",
            ]
            
            for selector in desc_selectors:
                try:
                    desc_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    description = desc_elem.text
                    if description and len(description) > 50:
                        break
                except:
                    continue
            
            if description:
                details['description'] = description
            else:
                details['description'] = "Description not available"
            
            # Check for Easy Apply button
            if self.logged_in:
                easy_apply_selectors = [
                    "button.jobs-apply-button--easy-apply",
                    "button[data-control-name='jobdetails_topcard_inapply']",
                    "button[aria-label*='Easy Apply']",
                ]
                for selector in easy_apply_selectors:
                    try:
                        if self.driver.find_elements(By.CSS_SELECTOR, selector):
                            details['external_site'] = False
                            break
                    except:
                        continue
        except Exception as e:
            print(f"Error getting LinkedIn job details: {e}")
            details['description'] = "Could not load description."
        
        return details
