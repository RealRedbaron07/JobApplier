from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from config import Config
from typing import List, Dict
import time
import re
import os

class WorkdayScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.base_url = None  # Will be determined from job URL
        self.logged_in = False
    
    def login(self):
        """Initialize driver (Workday doesn't require pre-login for browsing)."""
        self.init_driver()
        print("Workday scraper initialized (login handled per application)")
    
    def _extract_workday_base_url(self, job_url: str) -> str:
        """Extract base Workday URL from job URL."""
        # Workday URLs typically: https://company.wd1.myworkdayjobs.com/...
        match = re.match(r'(https://[^/]+\.myworkdayjobs\.com)', job_url)
        if match:
            return match.group(1)
        return None
    
    def _detect_workday_form_fields(self, driver):
        """Detect common Workday form field patterns."""
        fields = {}
        
        # Common field patterns
        field_selectors = [
            # Text inputs
            ("input[type='text']", "text"),
            ("input[type='email']", "email"),
            ("input[type='tel']", "phone"),
            ("input[type='number']", "number"),
            # Textareas
            ("textarea", "textarea"),
            # Selects
            ("select", "select"),
            # File inputs
            ("input[type='file']", "file"),
        ]
        
        for selector, field_type in field_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    # Try to identify field by label, placeholder, or aria-label
                    label = self._get_field_label(elem)
                    if label:
                        fields[label.lower()] = {
                            'element': elem,
                            'type': field_type
                        }
            except:
                continue
        
        return fields
    
    def _get_field_label(self, element):
        """Get label for a form field."""
        try:
            # Try aria-label
            aria_label = element.get_attribute('aria-label')
            if aria_label:
                return aria_label
            
            # Try associated label
            field_id = element.get_attribute('id')
            if field_id:
                try:
                    label = element.find_element(By.XPATH, f"//label[@for='{field_id}']")
                    return label.text
                except:
                    pass
            
            # Try placeholder
            placeholder = element.get_attribute('placeholder')
            if placeholder:
                return placeholder
            
            # Try parent label
            try:
                parent = element.find_element(By.XPATH, "./ancestor::label")
                return parent.text
            except:
                pass
        except:
            pass
        
        return None
    
    def _fill_workday_form(self, driver, user_info: Dict, resume_path: str, cover_letter_path: str = None, step: int = 1, max_steps: int = 5):
        """Attempt to fill Workday application form with multi-step support."""
        if step > max_steps:
            return True  # Prevent infinite recursion
        
        try:
            # Wait for form to load
            self.random_delay(2, 3)
            
            # Detect form fields
            fields = self._detect_workday_form_fields(driver)
            
            if not fields:
                # Try alternative field detection
                fields = self._detect_workday_form_fields_alternative(driver)
            
            # Fill common fields
            filled_count = 0
            
            # Email - try multiple patterns
            email_filled = False
            for label, field_info in fields.items():
                if not email_filled and ('email' in label or 'e-mail' in label):
                    try:
                        elem = field_info['element']
                        if elem.is_displayed() and elem.is_enabled():
                            elem.clear()
                            elem.send_keys(user_info.get('email', ''))
                            filled_count += 1
                            email_filled = True
                    except:
                        pass
            
            # Phone - try multiple patterns
            phone_filled = False
            for label, field_info in fields.items():
                if not phone_filled and ('phone' in label or 'tel' in label or 'mobile' in label):
                    try:
                        elem = field_info['element']
                        if elem.is_displayed() and elem.is_enabled() and user_info.get('phone'):
                            elem.clear()
                            elem.send_keys(user_info.get('phone', ''))
                            filled_count += 1
                            phone_filled = True
                    except:
                        pass
            
            # First Name
            first_name_filled = False
            for label, field_info in fields.items():
                if not first_name_filled and 'first' in label and 'name' in label:
                    try:
                        elem = field_info['element']
                        if elem.is_displayed() and elem.is_enabled() and user_info.get('first_name'):
                            elem.clear()
                            elem.send_keys(user_info.get('first_name', ''))
                            filled_count += 1
                            first_name_filled = True
                    except:
                        pass
            
            # Last Name
            last_name_filled = False
            for label, field_info in fields.items():
                if not last_name_filled and 'last' in label and 'name' in label:
                    try:
                        elem = field_info['element']
                        if elem.is_displayed() and elem.is_enabled() and user_info.get('last_name'):
                            elem.clear()
                            elem.send_keys(user_info.get('last_name', ''))
                            filled_count += 1
                            last_name_filled = True
                    except:
                        pass
            
            # Upload resume - try all file inputs
            resume_uploaded = False
            file_inputs = [f for f in fields.values() if f['type'] == 'file']
            for field_info in file_inputs:
                if not resume_uploaded:
                    try:
                        elem = field_info['element']
                        label = field_info.get('label', '').lower()
                        # Upload to resume/CV field or first file field if no label
                        if 'resume' in label or 'cv' in label or 'curriculum' in label or 'document' in label or not label:
                            if os.path.exists(resume_path):
                                elem.send_keys(resume_path)
                                filled_count += 1
                                resume_uploaded = True
                                self.random_delay(2, 3)  # Wait for upload
                                print(f"  ✓ Resume uploaded")
                    except Exception as e:
                        continue
            
            # Upload cover letter if field exists and not already uploaded resume to it
            if cover_letter_path and os.path.exists(cover_letter_path):
                cover_letter_uploaded = False
                for label, field_info in fields.items():
                    if not cover_letter_uploaded and field_info['type'] == 'file' and 'cover' in label.lower():
                        try:
                            elem = field_info['element']
                            elem.send_keys(cover_letter_path)
                            filled_count += 1
                            cover_letter_uploaded = True
                            self.random_delay(2, 3)
                            print(f"  ✓ Cover letter uploaded")
                        except:
                            pass
            
            # Handle multi-step forms
            # Look for "Next" or "Continue" buttons
            try:
                next_selectors = [
                    "//button[contains(., 'Next')]",
                    "//button[contains(., 'Continue')]",
                    "//button[contains(., 'next')]",
                    "//button[contains(@aria-label, 'Next')]",
                    "//a[contains(., 'Next')]",
                ]
                
                next_button = None
                for selector in next_selectors:
                    try:
                        buttons = driver.find_elements(By.XPATH, selector)
                        for btn in buttons:
                            if btn.is_displayed() and btn.is_enabled():
                                next_button = btn
                                break
                        if next_button:
                            break
                    except:
                        continue
                
                if next_button:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                    self.random_delay(1, 2)
                    self.driver.execute_script("arguments[0].click();", next_button)
                    self.random_delay(3, 5)
                    # Recursively fill next page
                    return self._fill_workday_form(driver, user_info, resume_path, cover_letter_path, step + 1, max_steps)
            except Exception as e:
                pass  # No next button or error clicking - continue
            
            return filled_count > 0 or step > 1  # Return True if we've progressed through steps
            
        except Exception as e:
            print(f"  ⚠️  Form filling error: {e}")
            return False
    
    def _detect_workday_form_fields_alternative(self, driver):
        """Alternative method to detect form fields using data-automation-id and other Workday-specific attributes."""
        fields = {}
        
        try:
            # Workday often uses data-automation-id
            automation_inputs = driver.find_elements(By.CSS_SELECTOR, "[data-automation-id]")
            for elem in automation_inputs:
                automation_id = elem.get_attribute('data-automation-id')
                if automation_id:
                    fields[automation_id.lower()] = {
                        'element': elem,
                        'type': elem.tag_name.lower(),
                        'label': automation_id
                    }
        except:
            pass
        
        # Also try input fields with labels
        try:
            inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, select")
            for inp in inputs:
                try:
                    # Get label via various methods
                    label = self._get_field_label(inp)
                    if not label:
                        # Try data-automation-id
                        automation_id = inp.get_attribute('data-automation-id')
                        if automation_id:
                            label = automation_id
                    
                    if label:
                        fields[label.lower()] = {
                            'element': inp,
                            'type': inp.tag_name.lower() if inp.tag_name else 'input',
                            'label': label
                        }
                except:
                    continue
        except:
            pass
        
        return fields
    
    def apply_to_job(self, job_url: str, user_info: Dict, resume_path: str, cover_letter_path: str = None) -> bool:
        """Apply to a Workday job."""
        try:
            # Extract base URL
            self.base_url = self._extract_workday_base_url(job_url)
            if not self.base_url:
                print(f"  ⚠️  Could not extract Workday base URL from: {job_url}")
                return False
            
            # Navigate to job page
            self.driver.get(job_url)
            self.random_delay(2, 4)
            
            # Look for "Apply" button with multiple strategies
            apply_selectors = [
                "//button[contains(., 'Apply')]",
                "//a[contains(., 'Apply')]",
                "//button[contains(@aria-label, 'Apply')]",
                "//a[contains(@aria-label, 'Apply')]",
                "//button[@data-automation-id='applyButton']",
                "//a[@data-automation-id='applyButton']",
                "//button[contains(@class, 'apply')]",
                "//a[contains(@class, 'apply')]",
            ]
            
            apply_button = None
            for selector in apply_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for btn in buttons:
                        if btn.is_displayed():
                            apply_button = btn
                            break
                    if apply_button:
                        break
                except:
                    continue
            
            if not apply_button:
                print("  ⚠️  Apply button not found - may already be on application page")
                # Continue anyway - might already be on the form page
            
            # Click Apply if button found
            if apply_button:
                try:
                    # Scroll into view first
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", apply_button)
                    self.random_delay(1, 2)
                    # Try JavaScript click first (more reliable)
                    self.driver.execute_script("arguments[0].click();", apply_button)
                    self.random_delay(3, 5)
                except:
                    try:
                        apply_button.click()
                        self.random_delay(3, 5)
                    except Exception as e:
                        print(f"  ⚠️  Could not click Apply button: {e}")
                        # Continue anyway - might already be on form
            else:
                # No apply button - might already be on application form
                self.random_delay(2, 3)
            
            # Check if login/account creation is required
            # Look for sign-in or create account prompts - but don't block, just warn
            try:
                # Wait a bit for page to load
                self.random_delay(2, 3)
                
                sign_in_indicators = [
                    "//*[contains(., 'Sign In')]",
                    "//*[contains(., 'Log In')]",
                    "//*[contains(., 'Create Account')]",
                    "//input[@type='email' and contains(@placeholder, 'email')]",
                    "//input[@id='username']",
                ]
                
                requires_login = False
                for indicator in sign_in_indicators:
                    try:
                        elements = self.driver.find_elements(By.XPATH, indicator)
                        if elements and any(elem.is_displayed() for elem in elements):
                            requires_login = True
                            break
                    except:
                        continue
                
                if requires_login:
                    print("  ⚠️  Login prompt detected - attempting to continue")
                    print("  → If login required, application will fail gracefully")
                    # Don't return False - try to continue, some forms work without login
            except:
                pass
            
            # Fill application form
            print("  📝 Filling application form...")
            form_filled = self._fill_workday_form(self.driver, user_info, resume_path, cover_letter_path)
            
            if not form_filled:
                print("  ⚠️  Could not fill form automatically")
                print("  → Some fields may need manual completion")
                # Don't return False immediately - try to submit anyway
                # Some forms may have fields pre-filled or not require all fields
            
            # Look for submit button with multiple strategies
            submit_selectors = [
                "//button[contains(., 'Submit')]",
                "//button[contains(., 'Submit Application')]",
                "//button[@type='submit']",
                "//button[contains(@aria-label, 'Submit')]",
                "//button[@data-automation-id='submitButton']",
                "//button[contains(@class, 'submit')]",
                "//button[contains(., 'Apply')]",  # Some forms use "Apply" as submit
            ]
            
            submit_button = None
            for selector in submit_selectors:
                try:
                    buttons = self.driver.find_elements(By.XPATH, selector)
                    for btn in buttons:
                        if btn.is_displayed() and btn.is_enabled():
                            submit_button = btn
                            break
                    if submit_button:
                        break
                except:
                    continue
            
            if submit_button:
                # Scroll to button
                self.driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                self.random_delay(1, 2)
                
                # Check for required fields that might be missing
                # This is a safety check - but be lenient since Workday forms are complex
                try:
                    required_fields = self.driver.find_elements(By.CSS_SELECTOR, 
                        "input[required], select[required], textarea[required]")
                    empty_required = []
                    for field in required_fields:
                        try:
                            value = field.get_attribute('value') or field.text
                            # Check if field is actually empty (not just whitespace)
                            if not value or not value.strip():
                                # Check if it's a file input (already uploaded)
                                if field.get_attribute('type') != 'file':
                                    empty_required.append(field)
                        except:
                            pass
                    
                    # Only warn if many required fields are empty
                    if len(empty_required) > 3:
                        print(f"  ⚠️  {len(empty_required)} required fields appear empty")
                        print("  → Attempting to submit anyway (some fields may be auto-filled)")
                    elif len(empty_required) > 0:
                        print(f"  ℹ️  {len(empty_required)} required field(s) may be empty - submitting anyway")
                except:
                    pass  # Continue with submission
                
                # Submit
                try:
                    self.driver.execute_script("arguments[0].click();", submit_button)
                    self.random_delay(3, 5)
                    
                    # Check for success message or confirmation
                    success_indicators = [
                        "//*[contains(., 'Thank you')]",
                        "//*[contains(., 'Application submitted')]",
                        "//*[contains(., 'Success')]",
                        "//*[contains(., 'submitted successfully')]",
                        "//*[contains(., 'confirmation')]",
                    ]
                    
                    for indicator in success_indicators:
                        try:
                            elems = self.driver.find_elements(By.XPATH, indicator)
                            for elem in elems:
                                if elem.is_displayed():
                                    print("  ✅ Application submitted successfully!")
                                    return True
                        except:
                            continue
                    
                    # Check URL change (often indicates submission)
                    current_url = self.driver.current_url.lower()
                    original_url = job_url.lower()
                    
                    # If URL changed significantly, likely submitted
                    if current_url != original_url and 'apply' not in current_url:
                        print("  ✅ Application appears submitted (URL changed)")
                        return True
                    
                    # Check for error messages
                    error_indicators = [
                        "//*[contains(., 'error')]",
                        "//*[contains(., 'required')]",
                        "//*[contains(., 'invalid')]",
                    ]
                    
                    has_errors = False
                    for indicator in error_indicators:
                        try:
                            if self.driver.find_elements(By.XPATH, indicator):
                                has_errors = True
                                break
                        except:
                            continue
                    
                    if not has_errors:
                        # No errors and form was filled - likely successful
                        print("  ✅ Application submitted (no errors detected)")
                        return True
                    else:
                        print("  ⚠️  Possible errors detected - check manually")
                        return False
                    
                except Exception as e:
                    print(f"  ⚠️  Submit error: {e}")
                    return False
            else:
                print("  ⚠️  Submit button not found")
                return False
            
            return False
            
        except Exception as e:
            print(f"  ❌ Error applying to Workday job: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Workday doesn't have a public search - jobs are found via other platforms."""
        # This scraper is for applying, not searching
        # Jobs are discovered via LinkedIn/Indeed/Glassdoor and then applied via this scraper
        return []
    
    def get_job_details(self, job_url: str) -> Dict:
        """Get job details from Workday page."""
        try:
            if not self.driver:
                self.init_driver()
            
            self.driver.get(job_url)
            self.random_delay(2, 3)
            
            details = {
                'description': '',
                'external_site': False  # Workday is the application site
            }
            
            # Try to extract job description using multiple selectors
            desc_selectors = [
                "//div[contains(@class, 'description')]",
                "//div[contains(@class, 'job-description')]",
                "//div[@data-automation-id='jobPostingDescription']",
                "//div[contains(@data-automation-id, 'description')]",
                "//section[contains(@class, 'description')]",
                "//div[contains(@class, 'jobPosting')]",
            ]
            
            for selector in desc_selectors:
                try:
                    desc_elems = self.driver.find_elements(By.XPATH, selector)
                    for desc_elem in desc_elems:
                        text = desc_elem.text
                        if text and len(text) > 50:  # Make sure it's substantial
                            details['description'] = text
                            break
                    if details['description']:
                        break
                except:
                    continue
            
            # If still no description, try to get any text content
            if not details['description']:
                try:
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                    # Take a reasonable chunk
                    if len(body_text) > 100:
                        details['description'] = body_text[:2000]  # Limit length
                except:
                    pass
            
            return details
            
        except Exception as e:
            print(f"Error getting Workday job details: {e}")
            return {'description': '', 'external_site': False}

