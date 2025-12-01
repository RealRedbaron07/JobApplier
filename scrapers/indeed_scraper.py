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
            
            # Try multiple selectors for job cards (Indeed changes HTML structure)
            job_cards = []
            selectors = [
                "div.job_seen_beacon",
                "div[data-jk]",
                "div.jobsearch-SerpJobCard",
                "td.resultContent",
            ]
            
            for selector in selectors:
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
                        "h2.jobTitle span",
                        "h2.jobTitle a",
                        "a[data-jk]",
                        "h2 a",
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
                        "span[data-testid='company-name']",
                        "span.companyName",
                        "a[data-testid='company-name']",
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
                        "div[data-testid='text-location']",
                        "div.companyLocation",
                        "span[data-testid='text-location']",
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
                    try:
                        link_elem = card.find_element(By.CSS_SELECTOR, "h2.jobTitle a")
                        job_link = link_elem.get_attribute("href")
                    except:
                        try:
                            link_elem = card.find_element(By.CSS_SELECTOR, "a[data-jk]")
                            job_link = link_elem.get_attribute("href")
                        except:
                            pass
                    
                    if title and company and job_link:
                        # Make sure link is absolute
                        if not job_link.startswith('http'):
                            job_link = f"{self.base_url}{job_link}"
                        
                        jobs.append({
                            'title': title,
                            'company': company,
                            'location': job_location or location,
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
            
            # Try multiple selectors for job description
            description = None
            desc_selectors = [
                (By.ID, "jobDescriptionText"),
                (By.CSS_SELECTOR, "div#jobDescriptionText"),
                (By.CSS_SELECTOR, "div.jobsearch-jobDescriptionText"),
                (By.CSS_SELECTOR, "div[data-testid='job-description']"),
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
