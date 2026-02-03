from abc import ABC, abstractmethod
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import List, Dict
import time
import random
import ssl
import certifi
import logging

class BaseScraper(ABC):
    def __init__(self):
        self.driver = None
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    def init_driver(self, use_profile=False):
        """Initialize undetected Chrome driver with SSL fix."""
        try:
            import os
            os.environ['SSL_CERT_FILE'] = certifi.where()
            
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            
            if use_profile:
                profile_dir = os.path.join(os.getcwd(), "chrome_profile")
                if not os.path.exists(profile_dir):
                    os.makedirs(profile_dir)
                options.add_argument(f"--user-data-dir={profile_dir}")
            
            self.driver = uc.Chrome(options=options, use_subprocess=False, version_main=144)
        except Exception as e:
            self.logger.error(f"Error initializing driver: {e}")
            raise
    
    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                print(f"Error closing driver: {e}")
    
    def wait_for_element(self, by, value, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
        except Exception as e:
            print(f"Element not found: {by}={value}")
            raise
    
    def safe_click(self, element):
        try:
            element.click()
        except:
            try:
                self.driver.execute_script("arguments[0].click();", element)
            except Exception as e2:
                print(f"Failed to click element: {e2}")
                raise
    
    @abstractmethod
    def login(self):
        pass
    
    @abstractmethod
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        pass
    
    @abstractmethod
    def get_job_details(self, job_url: str) -> Dict:
        pass
    
    def random_delay(self, min_sec=1, max_sec=3):
        time.sleep(random.uniform(min_sec, max_sec))
