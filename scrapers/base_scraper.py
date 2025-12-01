from abc import ABC, abstractmethod
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import List, Dict
import time
import random
import ssl
import os

# Fix SSL certificate issues on macOS
# This is a common issue where Python can't verify SSL certificates
try:
    # Try to use certifi if available
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
except ImportError:
    # If certifi not available, use unverified context (less secure but works)
    # Note: For production, install certificates: /Applications/Python\ 3.x/Install\ Certificates.command
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    # Fallback: unverified context
    ssl._create_default_https_context = ssl._create_unverified_context

class BaseScraper(ABC):
    def __init__(self):
        self.driver = None
    
    def init_driver(self):
        """Initialize undetected Chrome driver."""
        try:
            options = uc.ChromeOptions()
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            self.driver = uc.Chrome(options=options)
        except Exception as e:
            print(f"Error initializing driver: {e}")
            raise
    
    def close_driver(self):
        """Close the browser."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"Error closing driver: {e}")
    
    def wait_for_element(self, by, value, timeout=10):
        """Wait for element to be present."""
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except Exception as e:
            print(f"Element not found: {by}={value}")
            raise
    
    def safe_click(self, element):
        """Safely click an element with retry."""
        try:
            element.click()
        except Exception as e:
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except Exception as e2:
                print(f"Failed to click element: {e2}")
                raise
    
    @abstractmethod
    def login(self):
        """Login to the platform."""
        pass
    
    @abstractmethod
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """Search for jobs and return list of job dictionaries."""
        pass
    
    @abstractmethod
    def get_job_details(self, job_url: str) -> Dict:
        """Get detailed information about a specific job."""
        pass
    
    def random_delay(self, min_sec=1, max_sec=3):
        """Add random delay to appear more human-like."""
        time.sleep(random.uniform(min_sec, max_sec))
