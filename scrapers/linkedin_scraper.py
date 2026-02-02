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
        """Login to LinkedIn - supports auto, manual wait, or skip modes.
        
        Uses Chrome profile by default to leverage saved passwords.
        Set USE_CHROME_PROFILE=false to disable.
        """
        # Check config for login mode
        wait_for_login = os.getenv('WAIT_FOR_LOGIN', 'true').lower() == 'true'  # Default to true
        use_profile = os.getenv('USE_CHROME_PROFILE', 'true').lower() == 'true'  # Default to TRUE now
        
        self.init_driver(use_profile=use_profile)
        
        if use_profile:
            print("🔑 Using Chrome profile with saved passwords...")
        
        # Navigate to LinkedIn
        self.driver.get(f"{self.base_url}/login")
        self.random_delay(2, 3)
        
        # Check if already logged in (from Chrome profile)
        if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
            self.logger.info("Already logged into LinkedIn (from saved session)")
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
            self.logger.info("MANUAL LOGIN MODE - Log in via the browser window")
            input("\n>>> Press ENTER when you're logged in... ")
            self.logger.info("Waiting 30 seconds for page to stabilize...")
            time.sleep(30)
            self.logged_in = True
            self.logger.info("Ready to scrape!")
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
                    self.logger.info("LinkedIn login successful")
                elif "challenge" in self.driver.current_url or "checkpoint" in self.driver.current_url:
                    # 2FA required - wait for manual completion
                    self.logger.warning("2FA/Security check required")
                    print("   Complete verification in the browser")
                    input(">>> Press ENTER when done... ")
                    self.logger.info("Waiting 30 seconds...")
                    time.sleep(30)
                    self.logged_in = True
                else:
                    self.logger.warning("Login status unclear, continuing...")
                    self.logged_in = True
                    
            except Exception as e:
                self.logger.error(f"LinkedIn auto-login failed: {e}")
                self.logger.info("Falling back to manual login...")
                input(">>> Please log in manually, then press ENTER... ")
                print("⏳ Waiting 30 seconds...")
                time.sleep(30)
                self.logged_in = True
        else:
            self.logger.warning("LinkedIn credentials not provided.")
            self.logger.info("Set WAIT_FOR_LOGIN=true in .env for manual login mode.")
            self.logger.info("Continuing with public job search only.")
    
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Search for jobs on LinkedIn with fallback scraping strategies.
        
        GUEST MODE SUPPORT: Works without login using public job search.
        When logged_in=False, uses public LinkedIn job search which has 
        limited results but doesn't require authentication.
        """
        jobs = []
        
        # Ensure driver is initialized (for guest mode)
        if not self.driver:
            try:
                self.init_driver()
            except Exception as e:
                print(f"  ⚠️  Failed to initialize driver: {e}")
                return []
        
        # Use logged-in job search URL (works better when authenticated)
        # GUEST MODE: Public search URL works without login
        if self.logged_in:
            search_url = f"{self.base_url}/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}&f_TPR=r604800"  # Last week
        else:
            # Guest mode: Use public search (may have limited results)
            search_url = f"{self.base_url}/jobs/search/?keywords={keywords.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
            print(f"  📢 Guest Mode: Using public LinkedIn search (limited results)")
        
        try:
            self.driver.get(search_url)
        except Exception as e:
            print(f"  ⚠️  Failed to load search page: {e}")
            return []
        time.sleep(5)  # Wait for jobs to load
        
        # Scroll down to load more jobs
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(2)
        except:
            pass
        
        try:
            job_cards = []
            used_strategy = None
            
            # STRATEGY 1 (PRIORITY): Semantic Scraping - find job links by href pattern
            # This is most resilient to DOM changes since href patterns are stable
            print("  🔍 Trying semantic scraping (href patterns)...")
            try:
                job_links = self.driver.find_elements(By.XPATH, 
                    "//a[contains(@href, '/jobs/view/') or contains(@href, '/jobs/collections/')]")
                
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
                            
                            # Get title from link text or parent
                            title = link.text.strip()
                            if not title:
                                try:
                                    title = link.find_element(By.XPATH, ".//span | .//strong | .//h3").text.strip()
                                except:
                                    pass
                            if not title:
                                continue
                            
                            # Try to find company and location from nearby elements
                            parent = link
                            company = "Unknown Company"
                            job_location = location
                            
                            for _ in range(5):  # Walk up to 5 parent levels
                                try:
                                    parent = parent.find_element(By.XPATH, "./..")
                                    parent_text = parent.text
                                    
                                    # Parse company from parent text (usually second line after title)
                                    lines = [l.strip() for l in parent_text.split('\n') if l.strip()]
                                    if len(lines) >= 2 and lines[0] == title:
                                        company = lines[1] if len(lines) > 1 else company
                                        job_location = lines[2] if len(lines) > 2 else job_location
                                        break
                                except:
                                    break
                            
                            jobs.append({
                                'title': title,
                                'company': company,
                                'location': job_location,
                                'url': job_url,
                                'platform': 'linkedin'
                            })
                        except:
                            continue
                    
                    if jobs:
                        print(f"  ✓ Extracted {len(jobs)} jobs via semantic scraping")
                        return jobs
            except Exception as e:
                print(f"  Semantic extraction error: {e}")
            
            # STRATEGY 2: CSS Selectors (fallback - more prone to breakage)
            print("  🔍 Trying CSS selectors...")
            selectors = [
                "div.job-card-container",  # Logged-in view
                "li.jobs-search-results__list-item",  # Alternative logged-in
                "div.base-card",  # Public view
                "div.base-search-card",  # Alternative public
                "ul.jobs-search__results-list li",  # Another variation
                "div[data-job-id]",  # Data attribute pattern
                "li[data-occludable-job-id]",  # Occlusion pattern
            ]
            
            for selector in selectors:
                job_cards = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if job_cards:
                    print(f"  Found {len(job_cards)} jobs using CSS selector: {selector}")
                    used_strategy = 'css'
                    break
            
            # STRATEGY 2: Fallback to generic XPath patterns
            if not job_cards:
                print("  CSS selectors failed, trying XPath fallback...")
                xpath_patterns = [
                    # Find anchor tags with job-related href patterns
                    "//a[contains(@href, '/jobs/view/')]/..",
                    "//a[contains(@href, '/jobs/collections/')]/..",
                    # Find list items containing job links
                    "//li[.//a[contains(@href, '/jobs/')]]",
                    # Find divs with job-related classes (partial match)
                    "//div[contains(@class, 'job')]",
                    # Find cards by semantic structure
                    "//article[.//a[contains(@href, 'jobs')]]",
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
            
            # STRATEGY 3: Semantic HTML fallback - find all job links and extract context
            if not job_cards:
                print("  XPath fallback failed, trying semantic extraction...")
                try:
                    job_links = self.driver.find_elements(By.XPATH, 
                        "//a[contains(@href, '/jobs/view/') or contains(@href, '/jobs/collections/')]")
                    
                    if job_links:
                        print(f"  Found {len(job_links)} job links via semantic extraction")
                        used_strategy = 'semantic'
                        
                        seen_urls = set()
                        for link in job_links[:50]:
                            try:
                                job_url = link.get_attribute("href")
                                if not job_url or job_url in seen_urls:
                                    continue
                                seen_urls.add(job_url)
                                
                                # Get title from link text or parent
                                title = link.text.strip()
                                if not title:
                                    try:
                                        title = link.find_element(By.XPATH, ".//span | .//strong | .//h3").text.strip()
                                    except:
                                        pass
                                if not title:
                                    continue
                                
                                # Try to find company and location from nearby elements
                                parent = link
                                company = "Unknown Company"
                                job_location = location
                                
                                for _ in range(5):  # Walk up to 5 parent levels
                                    try:
                                        parent = parent.find_element(By.XPATH, "./..")
                                        parent_text = parent.text
                                        
                                        # Parse company from parent text (usually second line after title)
                                        lines = [l.strip() for l in parent_text.split('\n') if l.strip()]
                                        if len(lines) >= 2 and lines[0] == title:
                                            company = lines[1] if len(lines) > 1 else company
                                            job_location = lines[2] if len(lines) > 2 else job_location
                                            break
                                    except:
                                        break
                                
                                jobs.append({
                                    'title': title,
                                    'company': company,
                                    'location': job_location,
                                    'url': job_url,
                                    'platform': 'linkedin'
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
                    debug_filename = f"debug_scrape_linkedin_{timestamp}.html"
                    with open(debug_filename, 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    print(f"  📁 DEBUG: Page HTML saved to {debug_filename}")
                    print(f"     Inspect this file to see the actual DOM structure")
                except Exception as e:
                    print(f"  Could not save debug file: {e}")
                
                return jobs
            
            # Parse job cards (for CSS/XPath strategies)
            for card in job_cards[:30]:
                try:
                    # Try multiple title selectors
                    title = None
                    title_selectors = [
                        "a.job-card-list__title", 
                        "h3.base-search-card__title", 
                        "a.job-card-container__link", 
                        "strong",
                        ".//h3",
                        ".//a[contains(@href, '/jobs/')]",
                    ]
                    
                    for title_sel in title_selectors:
                        try:
                            if title_sel.startswith(".//"):
                                title_elem = card.find_element(By.XPATH, title_sel)
                            else:
                                title_elem = card.find_element(By.CSS_SELECTOR, title_sel)
                            title = title_elem.text.strip()
                            if title:
                                break
                        except:
                            continue
                    
                    if not title:
                        # Last resort: get first meaningful text from card
                        try:
                            card_text = card.text.strip()
                            if card_text:
                                title = card_text.split('\n')[0].strip()
                        except:
                            pass
                    
                    if not title:
                        continue
                    
                    # Try multiple company selectors
                    company = "Unknown Company"
                    company_selectors = [
                        "span.job-card-container__primary-description", 
                        "h4.base-search-card__subtitle", 
                        "a.job-card-container__company-name", 
                        ".artdeco-entity-lockup__subtitle",
                        "[data-tracking-control-name*='company']",
                    ]
                    
                    for comp_sel in company_selectors:
                        try:
                            comp_elem = card.find_element(By.CSS_SELECTOR, comp_sel)
                            company = comp_elem.text.strip()
                            if company:
                                break
                        except:
                            continue
                    
                    # Fallback: parse company from card text
                    if company == "Unknown Company":
                        try:
                            lines = [l.strip() for l in card.text.split('\n') if l.strip()]
                            if len(lines) >= 2:
                                company = lines[1]
                        except:
                            pass
                    
                    # Try multiple location selectors
                    job_location = location  # Default to search location
                    location_selectors = [
                        "span.job-card-container__metadata-item", 
                        "span.job-search-card__location", 
                        ".artdeco-entity-lockup__caption",
                        "[class*='location']",
                    ]
                    
                    for loc_sel in location_selectors:
                        try:
                            loc_elem = card.find_element(By.CSS_SELECTOR, loc_sel)
                            job_location = loc_elem.text.strip()
                            if job_location:
                                break
                        except:
                            continue
                    
                    # Get job link
                    job_link = None
                    link_selectors = [
                        "a.job-card-list__title", 
                        "a.job-card-container__link", 
                        "a.base-card__full-link", 
                        "a[href*='/jobs/view/']",
                        "a[href*='/jobs/']",
                        "a"
                    ]
                    
                    for link_sel in link_selectors:
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
    
    def apply_to_job(self, job_url: str, resume_path: str, max_steps: int = 10) -> bool:
        """Attempt to apply to a LinkedIn job using Easy Apply with recursive form navigation.
        
        GUEST MODE: If not logged in, this will skip Easy Apply and mark for manual application.
        """
        # GUEST MODE CHECK: Skip Easy Apply if not logged in
        if not self.logged_in:
            self.logger.warning("Skipping Easy Apply (Guest Mode)")
            print(f"     → Apply manually at: {job_url}")
            return False
        
        try:
            # Navigate to job page
            self.driver.get(job_url)
            self.random_delay(2, 4)
            
            # Look for Easy Apply button
            try:
                easy_apply_button = None
                easy_apply_selectors = [
                    "//button[contains(@class, 'jobs-apply-button')]",
                    "//button[contains(., 'Easy Apply')]",
                    "//button[contains(@aria-label, 'Easy Apply')]",
                    "//button[contains(., 'Apply')]//span[contains(., 'Easy')]/..",
                ]
                
                for selector in easy_apply_selectors:
                    try:
                        buttons = self.driver.find_elements(By.XPATH, selector)
                        for btn in buttons:
                            if btn.is_displayed() and 'easy' in btn.text.lower():
                                easy_apply_button = btn
                                break
                        if easy_apply_button:
                            break
                    except:
                        continue
                
                if not easy_apply_button:
                    self.logger.info("Easy Apply button not found - may require external application")
                    return False
                
                self.driver.execute_script("arguments[0].click();", easy_apply_button)
                self.random_delay(2, 3)
                
                # Now navigate through the multi-step application form
                step = 0
                while step < max_steps:
                    step += 1
                    print(f"  📝 Processing Easy Apply step {step}...")
                    
                    # Wait for modal to load
                    self.random_delay(1, 2)
                    
                    # Try to upload resume if file input is present
                    try:
                        file_inputs = self.driver.find_elements(By.XPATH, "//input[@type='file']")
                        for file_input in file_inputs:
                            try:
                                if os.path.exists(resume_path):
                                    file_input.send_keys(resume_path)
                                    print(f"    ✓ Resume uploaded")
                                    self.random_delay(2, 3)
                                    break
                            except:
                                continue
                    except:
                        pass
                    
                    # Handle common questions with radio buttons
                    try:
                        # Find Yes/No questions and select appropriate answers
                        question_containers = self.driver.find_elements(By.XPATH, 
                            "//fieldset | //div[.//input[@type='radio']]")
                        
                        for container in question_containers:
                            try:
                                question_text = container.text.lower()
                                
                                # Default answers based on common patterns
                                answer_to_select = None
                                if 'sponsor' in question_text or 'visa' in question_text:
                                    answer_to_select = 'no'
                                elif 'authorized' in question_text or 'eligible' in question_text:
                                    answer_to_select = 'yes'
                                elif 'relocate' in question_text:
                                    answer_to_select = 'yes'
                                elif 'experience' in question_text:
                                    # For experience questions, try to enter a number if text input
                                    try:
                                        exp_input = container.find_element(By.XPATH, ".//input[@type='text' or @type='number']")
                                        if exp_input.is_displayed() and not exp_input.get_attribute('value'):
                                            exp_input.send_keys("3")  # Default years of experience
                                    except:
                                        pass
                                    continue
                                
                                if answer_to_select:
                                    radios = container.find_elements(By.XPATH, ".//input[@type='radio']")
                                    for radio in radios:
                                        try:
                                            radio_id = radio.get_attribute('id')
                                            if radio_id:
                                                label_elem = self.driver.find_element(By.XPATH, f"//label[@for='{radio_id}']")
                                                if answer_to_select in label_elem.text.lower():
                                                    if not radio.is_selected():
                                                        self.driver.execute_script("arguments[0].click();", radio)
                                                        self.random_delay(0.3, 0.5)
                                                    break
                                        except:
                                            continue
                            except:
                                continue
                    except:
                        pass
                    
                    # Look for Next/Review/Submit button
                    action_button = None
                    button_selectors = [
                        # Submit buttons (highest priority)
                        "//button[contains(@aria-label, 'Submit')]",
                        "//button[contains(., 'Submit application')]",
                        "//button[contains(., 'Submit')]",
                        # Review button
                        "//button[contains(., 'Review')]",
                        # Next button
                        "//button[contains(@aria-label, 'Continue')]",
                        "//button[contains(., 'Next')]",
                        "//button[contains(., 'Continue')]",
                    ]
                    
                    is_submit = False
                    for selector in button_selectors:
                        try:
                            buttons = self.driver.find_elements(By.XPATH, selector)
                            for btn in buttons:
                                if btn.is_displayed() and btn.is_enabled():
                                    action_button = btn
                                    is_submit = 'submit' in btn.text.lower()
                                    break
                            if action_button:
                                break
                        except:
                            continue
                    
                    if not action_button:
                        # Check if we're done (modal closed or success message)
                        try:
                            success_indicators = self.driver.find_elements(By.XPATH, 
                                "//*[contains(., 'Application submitted') or contains(., 'Your application was sent')]")
                            if success_indicators:
                                print("  ✅ Application submitted successfully!")
                                return True
                        except:
                            pass
                        
                        # No button found - may be done
                        self.logger.warning("No more action buttons found")
                        break
                    
                    # Click the button
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", action_button)
                        self.random_delay(0.5, 1)
                        self.driver.execute_script("arguments[0].click();", action_button)
                        self.random_delay(2, 3)
                        
                        if is_submit:
                            # Check for success
                            self.random_delay(2, 3)
                            try:
                                success = self.driver.find_elements(By.XPATH, 
                                    "//*[contains(., 'Application submitted') or contains(., 'Your application was sent') or contains(., 'successfully')]")
                                if success:
                                    print("  ✅ Application submitted successfully!")
                                    return True
                            except:
                                pass
                            
                            # Check if modal is closed (another success indicator)
                            try:
                                modal = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'jobs-easy-apply-modal')]")
                                if not modal or not any(m.is_displayed() for m in modal):
                                    print("  ✅ Application appears submitted (modal closed)")
                                    return True
                            except:
                                pass
                    except Exception as e:
                        self.logger.error(f"Error clicking button: {e}")
                        break
                
                # If we got here, we went through steps but couldn't confirm submission
                self.logger.warning("Completed form navigation but submission status unclear")
                return False
                
            except Exception as e:
                self.logger.error(f"Easy Apply error: {e}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error applying to LinkedIn job: {e}")
            return False

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
