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
        self.logger.info("Indeed scraper initialized (no login required)")
    
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Search for jobs on Indeed with fallback scraping strategies."""
        jobs = []
        search_url = f"{self.base_url}/jobs?q={keywords.replace(' ', '+')}&l={location.replace(' ', '+')}"
        
        try:
            self.driver.get(search_url)
            self.random_delay(2, 4)
            
            job_cards = []
            used_strategy = None
            
            # STRATEGY 1 (PRIORITY): Semantic Scraping - find job links by href pattern
            # This is most resilient to DOM changes
            print("  🔍 Trying semantic scraping (href patterns)...")
            try:
                job_links = self.driver.find_elements(By.XPATH, 
                    "//a[contains(@href, '/rc/clk') or contains(@href, '/viewjob') or contains(@href, '/pagead/')]")
                
                if job_links and len(job_links) >= 3:
                    print(f"  Found {len(job_links)} job links via semantic extraction")
                    used_strategy = 'semantic'
                    
                    seen_urls = set()
                    for link in job_links[:50]:
                        try:
                            job_url = link.get_attribute("href")
                            if not job_url or job_url in seen_urls:
                                continue
                            seen_urls.add(job_url)
                            
                            # Get title from link text or nested element
                            title = link.text.strip()
                            if not title:
                                try:
                                    title = link.find_element(By.XPATH, ".//span | .//h2 | .//strong").text.strip()
                                except:
                                    pass
                            if not title or len(title) < 3:
                                continue
                            
                            # Try to find company and location from nearby elements
                            parent = link
                            company = "Unknown Company"
                            job_location = location
                            
                            for _ in range(5):
                                try:
                                    parent = parent.find_element(By.XPATH, "./..")
                                    try:
                                        comp_elem = parent.find_element(By.CSS_SELECTOR, 
                                            "[data-testid='company-name'], .companyName, .company")
                                        company = comp_elem.text.strip()
                                    except:
                                        pass
                                    try:
                                        loc_elem = parent.find_element(By.CSS_SELECTOR, 
                                            "[data-testid='text-location'], .companyLocation, .location")
                                        job_location = loc_elem.text.strip()
                                    except:
                                        pass
                                    if company != "Unknown Company":
                                        break
                                except:
                                    break
                            
                            jobs.append({
                                'title': title,
                                'company': company,
                                'location': job_location,
                                'url': job_url,
                                'platform': 'indeed'
                            })
                        except:
                            continue
                    
                    if jobs:
                        print(f"  ✓ Extracted {len(jobs)} jobs via semantic scraping")
                        return jobs
            except Exception as e:
                print(f"  Semantic extraction error: {e}")
            
            # STRATEGY 2: CSS Selectors (fallback)
            print("  🔍 Trying CSS selectors...")
            selectors = [
                "job_seen_beacon",  # Current primary class
                "jobsearch-ResultsList",  # Results container items
                "result",  # Legacy class
                "jobCard_mainContent",  # Alternative structure
            ]
            
            for selector in selectors:
                job_cards = self.driver.find_elements(By.CLASS_NAME, selector)
                if job_cards:
                    print(f"  Found {len(job_cards)} jobs using class: {selector}")
                    used_strategy = 'class'
                    break
            
            # Also try CSS selectors
            if not job_cards:
                css_selectors = [
                    "div.job_seen_beacon",
                    "div[data-jk]",  # Data attribute pattern
                    "td.resultContent",  # Table-based layout
                    "div.slider_container .slider_item",  # Slider layout
                    "li.css-5lfssm",  # Dynamic class pattern (partial)
                ]
                
                for selector in css_selectors:
                    try:
                        job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if job_cards:
                            print(f"  Found {len(job_cards)} jobs using CSS: {selector}")
                            used_strategy = 'css'
                            break
                    except:
                        continue
            
            # STRATEGY 3: XPath patterns (additional fallback)
            if not job_cards:
                print("  🔍 Trying XPath patterns...")
                xpath_patterns = [
                    # Find elements with job ID data attribute
                    "//div[@data-jk]",
                    # Find anchor tags with job-related href patterns
                    "//a[contains(@href, '/rc/clk') or contains(@href, '/viewjob')]/..",
                    # Find divs containing job titles
                    "//div[.//h2[contains(@class, 'jobTitle')]]",
                    # Find list items in job results
                    "//ul[contains(@class, 'jobsearch')]//li",
                    # Find by job card structure
                    "//div[contains(@class, 'cardOutline')]",
                ]
                
                for xpath in xpath_patterns:
                    try:
                        job_cards = self.driver.find_elements(By.XPATH, xpath)
                        if len(job_cards) >= 3:  # Need at least 3 to be valid
                            print(f"  Found {len(job_cards)} jobs using XPath: {xpath}")
                            used_strategy = 'xpath'
                            break
                    except:
                        continue
            
            # STRATEGY 4: Additional semantic fallback (if primary semantic failed)
            if not job_cards:
                print("  🔍 Trying additional semantic patterns...")
                try:
                    # Find all links that look like job postings
                    job_links = self.driver.find_elements(By.XPATH, 
                        "//a[contains(@href, '/rc/clk') or contains(@href, '/viewjob') or contains(@href, '/pagead/')]")
                    
                    if job_links:
                        print(f"  Found {len(job_links)} job links via semantic extraction")
                        used_strategy = 'semantic'
                        
                        seen_urls = set()
                        for link in job_links[:50]:
                            try:
                                job_url = link.get_attribute("href")
                                if not job_url or job_url in seen_urls:
                                    continue
                                
                                # Deduplicate by job key in URL
                                seen_urls.add(job_url)
                                
                                # Get title from link text or nested element
                                title = link.text.strip()
                                if not title:
                                    try:
                                        title = link.find_element(By.XPATH, ".//span | .//h2 | .//strong").text.strip()
                                    except:
                                        pass
                                if not title or len(title) < 3:
                                    continue
                                
                                # Try to find company and location from nearby elements
                                parent = link
                                company = "Unknown Company"
                                job_location = location
                                
                                for _ in range(5):  # Walk up to 5 parent levels
                                    try:
                                        parent = parent.find_element(By.XPATH, "./..")
                                        
                                        # Try to find company name
                                        try:
                                            comp_elem = parent.find_element(By.CSS_SELECTOR, 
                                                "[data-testid='company-name'], .companyName, .company")
                                            company = comp_elem.text.strip()
                                        except:
                                            pass
                                        
                                        # Try to find location
                                        try:
                                            loc_elem = parent.find_element(By.CSS_SELECTOR, 
                                                "[data-testid='text-location'], .companyLocation, .location")
                                            job_location = loc_elem.text.strip()
                                        except:
                                            pass
                                        
                                        if company != "Unknown Company":
                                            break
                                    except:
                                        break
                                
                                jobs.append({
                                    'title': title,
                                    'company': company,
                                    'location': job_location,
                                    'url': job_url,
                                    'platform': 'indeed'
                                })
                            except:
                                continue
                        
                        if jobs:
                            print(f"  Extracted {len(jobs)} jobs via semantic fallback")
                            return jobs
                except Exception as e:
                    print(f"  Semantic extraction failed: {e}")
            
            if not job_cards:
                print(f"  Warning: All scraping strategies failed. Page title: {self.driver.title}")
                
                # DEBUG MODE: Save page source for inspection
                try:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    debug_filename = f"debug_scrape_indeed_{timestamp}.html"
                    with open(debug_filename, 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    print(f"  📁 DEBUG: Page HTML saved to {debug_filename}")
                    print(f"     Inspect this file to see the actual DOM structure")
                except Exception as e:
                    print(f"  Could not save debug file: {e}")
                
                return jobs
            
            # Parse job cards (for class/CSS/XPath strategies)
            for card in job_cards[:50]:
                try:
                    # Try multiple title selectors
                    title = None
                    title_selectors = [
                        ("css", "h2.jobTitle span"),
                        ("css", "h2.jobTitle a"),
                        ("css", "h2 a"),
                        ("css", ".jobTitle"),
                        ("css", "a[data-jk]"),
                        ("xpath", ".//h2"),
                        ("xpath", ".//a[contains(@class, 'jcs-JobTitle')]"),
                    ]
                    
                    for sel_type, selector in title_selectors:
                        try:
                            if sel_type == "css":
                                title_elem = card.find_element(By.CSS_SELECTOR, selector)
                            else:
                                title_elem = card.find_element(By.XPATH, selector)
                            title = title_elem.text.strip()
                            if title:
                                break
                        except:
                            continue
                    
                    if not title:
                        continue
                    
                    # Try multiple company selectors
                    company = "Unknown Company"
                    company_selectors = [
                        ("css", "span[data-testid='company-name']"),
                        ("css", ".companyName"),
                        ("css", ".company"),
                        ("css", "[data-testid='company-name']"),
                        ("xpath", ".//span[contains(@class, 'company')]"),
                    ]
                    
                    for sel_type, selector in company_selectors:
                        try:
                            if sel_type == "css":
                                comp_elem = card.find_element(By.CSS_SELECTOR, selector)
                            else:
                                comp_elem = card.find_element(By.XPATH, selector)
                            company = comp_elem.text.strip()
                            if company:
                                break
                        except:
                            continue
                    
                    # Try multiple location selectors
                    job_location = location  # Default to search location
                    location_selectors = [
                        ("css", "div[data-testid='text-location']"),
                        ("css", ".companyLocation"),
                        ("css", ".location"),
                        ("xpath", ".//div[contains(@class, 'location')]"),
                    ]
                    
                    for sel_type, selector in location_selectors:
                        try:
                            if sel_type == "css":
                                loc_elem = card.find_element(By.CSS_SELECTOR, selector)
                            else:
                                loc_elem = card.find_element(By.XPATH, selector)
                            job_location = loc_elem.text.strip()
                            if job_location:
                                break
                        except:
                            continue
                    
                    # Get job link
                    job_link = None
                    link_selectors = [
                        ("css", "h2.jobTitle a"),
                        ("css", "a[data-jk]"),
                        ("css", "a[href*='/rc/clk']"),
                        ("css", "a[href*='/viewjob']"),
                        ("xpath", ".//a[contains(@href, 'indeed')]"),
                        ("css", "a"),
                    ]
                    
                    for sel_type, selector in link_selectors:
                        try:
                            if sel_type == "css":
                                link_elem = card.find_element(By.CSS_SELECTOR, selector)
                            else:
                                link_elem = card.find_element(By.XPATH, selector)
                            job_link = link_elem.get_attribute("href")
                            if job_link and ("indeed" in job_link or "/rc/" in job_link or "/viewjob" in job_link):
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
