from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from config import Config
from typing import List, Dict
import time
import os

class LinkedInScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.base_url = "https://www.linkedin.com"
        self.logged_in = False
    
    def login(self):
        """Login to LinkedIn - supports auto, manual wait, or skip modes."""
        # Check config for login mode
        wait_for_login = os.getenv('WAIT_FOR_LOGIN', 'true').lower() == 'true'  # Default to true
        use_profile = os.getenv('USE_CHROME_PROFILE', 'false').lower() == 'true'
        
        self.init_driver(use_profile=use_profile)
        
        # Navigate to LinkedIn
        self.driver.get(f"{self.base_url}/login")
        self.random_delay(2, 3)
        
        # Check if already logged in (from Chrome profile)
        if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
            print("✓ Already logged into LinkedIn (from saved session)")
            self.logged_in = True
            return
        
        # Option 1: Wait for manual login (default)
        if wait_for_login:
            print("\n" + "=" * 60)
            print("🔐 MANUAL LOGIN MODE")
            print("=" * 60)
            print("1. Log into LinkedIn in the browser window")
            print("2. Complete any 2FA/security checks if needed")
            print("3. DO NOT close the browser window!")
            print("4. Come back here and press ENTER when logged in")
            print("=" * 60)
            input("\n>>> Press ENTER when you're logged in... ")
            print("\n⏳ Waiting 30 seconds for page to stabilize...")
            print("   (DO NOT close the browser!)")
            time.sleep(30)
            self.logged_in = True
            print("✓ Ready to scrape!")
            return
        
        # Option 2: Auto login with credentials
        if Config.LINKEDIN_EMAIL and Config.LINKEDIN_PASSWORD:
            print("Attempting automatic LinkedIn login...")
            try:
                email_field = self.wait_for_element(By.ID, "username")
                email_field.send_keys(Config.LINKEDIN_EMAIL)
                
                password_field = self.driver.find_element(By.ID, "password")
                password_field.send_keys(Config.LINKEDIN_PASSWORD)
                password_field.send_keys(Keys.RETURN)
                
                print("⏳ Waiting 30 seconds for login to complete...")
                time.sleep(30)
                
                # Check if login succeeded
                if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
                    self.logged_in = True
                    print("✓ LinkedIn login successful")
                elif "challenge" in self.driver.current_url or "checkpoint" in self.driver.current_url:
                    # 2FA required - wait for manual completion
                    print("⚠️  2FA/Security check required")
                    print("   Complete verification in the browser")
                    input(">>> Press ENTER when done... ")
                    print("⏳ Waiting 30 seconds...")
                    time.sleep(30)
                    self.logged_in = True
                else:
                    print("⚠️  Login status unclear, continuing...")
                    self.logged_in = True
                    
            except Exception as e:
                print(f"✗ LinkedIn auto-login failed: {e}")
                print("  Falling back to manual login...")
                input(">>> Please log in manually, then press ENTER... ")
                print("⏳ Waiting 30 seconds...")
                time.sleep(30)
                self.logged_in = True
        else:
            print("⚠️  LinkedIn credentials not provided.")
            print("  Set WAIT_FOR_LOGIN=true in .env for manual login mode,")
            print("  or add LINKEDIN_EMAIL and LINKEDIN_PASSWORD.")
            print("  Continuing with public job search only.")
    
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Search for jobs on LinkedIn."""
        jobs = []
        
        # Use logged-in job search URL (works better when authenticated)
        if self.logged_in:
            search_url = f"{self.base_url}/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}&f_TPR=r604800"  # Last week
        else:
            search_url = f"{self.base_url}/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
        
        self.driver.get(search_url)
        time.sleep(5)  # Wait for jobs to load
        
        # Scroll down to load more jobs
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(2)
        except:
            pass
        
        try:
            # Try multiple selectors for job cards (LinkedIn changes these frequently)
            selectors = [
                "div.job-card-container",  # Logged-in view
                "li.jobs-search-results__list-item",  # Alternative logged-in
                "div.base-card",  # Public view
                "div.base-search-card",  # Alternative public
                "ul.jobs-search__results-list li",  # Another variation
            ]
            
            job_cards = []
            for selector in selectors:
                job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if job_cards:
                    print(f"  Found {len(job_cards)} jobs using selector: {selector}")
                    break
            
            if not job_cards:
                # Try getting page source and print for debugging
                print(f"  Warning: No job cards found. Page title: {self.driver.title}")
                return jobs
            
            for card in job_cards[:30]:
                try:
                    # Try multiple title selectors
                    title = None
                    for title_sel in ["a.job-card-list__title", "h3.base-search-card__title", "a.job-card-container__link", "strong"]:
                        try:
                            title_elem = card.find_element(By.CSS_SELECTOR, title_sel)
                            title = title_elem.text.strip()
                            if title:
                                break
                        except:
                            continue
                    
                    if not title:
                        continue
                    
                    # Try multiple company selectors
                    company = "Unknown Company"
                    for comp_sel in ["span.job-card-container__primary-description", "h4.base-search-card__subtitle", "a.job-card-container__company-name", ".artdeco-entity-lockup__subtitle"]:
                        try:
                            comp_elem = card.find_element(By.CSS_SELECTOR, comp_sel)
                            company = comp_elem.text.strip()
                            if company:
                                break
                        except:
                            continue
                    
                    # Try multiple location selectors
                    job_location = location  # Default to search location
                    for loc_sel in ["span.job-card-container__metadata-item", "span.job-search-card__location", ".artdeco-entity-lockup__caption"]:
                        try:
                            loc_elem = card.find_element(By.CSS_SELECTOR, loc_sel)
                            job_location = loc_elem.text.strip()
                            if job_location:
                                break
                        except:
                            continue
                    
                    # Get job link
                    job_link = None
                    for link_sel in ["a.job-card-list__title", "a.job-card-container__link", "a.base-card__full-link", "a"]:
                        try:
                            link_elem = card.find_element(By.CSS_SELECTOR, link_sel)
                            job_link = link_elem.get_attribute("href")
                            if job_link and "linkedin.com" in job_link:
                                break
                        except:
                            continue
                    
                    if not job_link:
                        continue
                    
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
