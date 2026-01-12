"""
Base scraper class with anti-detection, retry logic, and proxy support.
All platform scrapers inherit from this class.
"""

from abc import ABC, abstractmethod
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    ElementClickInterceptedException,
    StaleElementReferenceException,
    NoSuchElementException
)
from typing import List, Dict, Callable, TypeVar, Optional
from functools import wraps
import time
import random
import ssl
import certifi
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from logger import get_logger

# Type variable for generic return type
T = TypeVar('T')

# User-Agent rotation pool
USER_AGENTS = [
    # Chrome on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Chrome on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Chrome on Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    # Firefox on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Firefox on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Edge on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]

# Retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0  # Base delay in seconds


def retry_on_failure(
    max_retries: int = DEFAULT_MAX_RETRIES, 
    delay_base: float = DEFAULT_RETRY_DELAY,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Decorator for retrying failed operations with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay_base: Base delay in seconds (doubles each retry)
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback function called before each retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            logger = get_logger("scraper.retry")
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries - 1:
                        wait_time = delay_base * (2 ** attempt) + random.uniform(0, 1)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed for {func.__name__}: {e}"
                        )
                        logger.info(f"Retrying in {wait_time:.1f}s...")
                        
                        if on_retry:
                            on_retry(attempt, e)
                        
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"All {max_retries} attempts failed for {func.__name__}: {e}"
                        )
            
            raise last_exception
        return wrapper
    return decorator


class BaseScraper(ABC):
    """Base class for all job scrapers with anti-detection and retry support."""
    
    def __init__(self):
        self.driver = None
        self.logger = get_logger(f"scraper.{self.__class__.__name__}")
        self.user_agent = random.choice(USER_AGENTS)
        
        # Log configuration status at init
        self._log_configuration_status()
    
    def _log_configuration_status(self):
        """Log the current scraper configuration for verification."""
        self.logger.debug(f"Selected User-Agent: {self.user_agent[:50]}...")
        
        # Proxy status
        proxy_url = getattr(Config, 'PROXY_URL', '') or os.getenv('PROXY_URL', '')
        if proxy_url:
            # Hide credentials in log
            proxy_display = proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url
            self.logger.info(f"🌐 Proxy Status: ENABLED ({proxy_display})")
        else:
            self.logger.info("🌐 Proxy Status: DISABLED (no PROXY_URL set)")
        
        # Persistent session status
        chrome_data_dir = getattr(Config, 'CHROME_DATA_DIR', '')
        if chrome_data_dir:
            self.logger.info(f"💾 Persistent Session: ENABLED ({os.path.basename(chrome_data_dir)})")
        else:
            self.logger.info("💾 Persistent Session: DISABLED (fresh session each run)")
        
        # Headless mode status
        headless = getattr(Config, 'HEADLESS_MODE', False)
        if headless:
            self.logger.info("🖥️  Headless Mode: ENABLED (no browser window)")
        else:
            self.logger.info("🖥️  Headless Mode: DISABLED (browser will be visible)")
    
    def init_driver(self, use_profile: bool = False):
        """
        Initialize undetected Chrome driver with anti-detection measures.
        
        Args:
            use_profile: If True, uses system Chrome profile (~/Library/.../Chrome).
                        Otherwise uses CHROME_DATA_DIR for persistent sessions.
        
        Behavior:
            1. First run: Browser opens, you log in manually, cookies saved
            2. Future runs: Loads saved session, no login needed
        """
        try:
            # Fix SSL certificate issues
            os.environ['SSL_CERT_FILE'] = certifi.where()
            
            options = uc.ChromeOptions()
            
            # Basic options
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            # ============================================
            # HEADLESS MODE (configurable)
            # ============================================
            headless_mode = getattr(Config, 'HEADLESS_MODE', False)
            if headless_mode:
                options.add_argument('--headless=new')
                self.logger.info("Running in headless mode")
            
            # ============================================
            # ANTI-DETECTION MEASURES
            # ============================================
            
            # 1. Disable automation indicators
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)
            
            # 2. Random User-Agent
            options.add_argument(f'user-agent={self.user_agent}')
            
            # 3. Disable extensions and infobars
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-infobars')
            options.add_argument('--disable-popup-blocking')
            
            # 4. SSL handling
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')
            
            # 5. Disable GPU (reduces fingerprinting)
            options.add_argument('--disable-gpu')
            
            # 6. Window size (common resolution to blend in)
            options.add_argument('--window-size=1920,1080')
            
            # ============================================
            # PROXY SUPPORT (with verification logging)
            # ============================================
            proxy_url = getattr(Config, 'PROXY_URL', '') or os.getenv('PROXY_URL', '')
            if proxy_url:
                options.add_argument(f'--proxy-server={proxy_url}')
                # Log proxy without credentials for security
                proxy_display = proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url
                self.logger.info(f"✓ Proxy configured: {proxy_display}")
            
            # ============================================
            # PERSISTENT BROWSER SESSION
            # ============================================
            # Priority: 
            #   1. use_profile=True → Use system Chrome profile
            #   2. CHROME_DATA_DIR set → Use persistent session folder
            #   3. Neither → Fresh session (no persistence)
            
            use_system_profile = use_profile or getattr(Config, 'USE_SYSTEM_CHROME_PROFILE', False)
            chrome_data_dir = getattr(Config, 'CHROME_DATA_DIR', '')
            
            if use_system_profile:
                # Use system Chrome profile (macOS path)
                chrome_profile_path = os.path.expanduser(
                    "~/Library/Application Support/Google/Chrome"
                )
                if os.path.exists(chrome_profile_path):
                    options.add_argument(f"--user-data-dir={chrome_profile_path}")
                    options.add_argument("--profile-directory=Default")
                    self.logger.info("✓ Using SYSTEM Chrome profile (with saved logins)")
                    self.logger.warning("  ⚠️  Chrome must be closed for this to work!")
                else:
                    self.logger.warning(f"System Chrome profile not found at: {chrome_profile_path}")
            
            elif chrome_data_dir:
                # Use dedicated persistent session folder
                # Create directory if it doesn't exist
                os.makedirs(chrome_data_dir, exist_ok=True)
                options.add_argument(f"--user-data-dir={chrome_data_dir}")
                
                # Check if this is first run (no existing profile)
                is_first_run = not os.path.exists(os.path.join(chrome_data_dir, 'Default'))
                
                if is_first_run:
                    self.logger.info("✓ Persistent session: FIRST RUN")
                    self.logger.info("  → Log in manually, cookies will be saved for next run")
                else:
                    self.logger.info("✓ Persistent session: Loading saved cookies/session")
            
            else:
                self.logger.info("Using fresh browser session (no persistence)")
            
            # ============================================
            # INITIALIZE DRIVER
            # ============================================
            self.driver = uc.Chrome(options=options, use_subprocess=False)
            
            # Additional anti-detection: Override navigator properties
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                '''
            })
            
            self.logger.info("✓ Browser initialized successfully")
            
        except Exception as e:
            if "user data directory is already in use" in str(e).lower():
                self.logger.error(
                    "Chrome is already running with this profile. "
                    "Close Chrome and try again, OR set CHROME_DATA_DIR to a different path."
                )
            self.logger.error(f"Error initializing driver: {e}")
            raise
    
    def close_driver(self):
        """Close the browser safely."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.debug("Browser closed")
            except Exception as e:
                self.logger.warning(f"Error closing driver: {e}")
    
    def wait_for_element(self, by, value, timeout=10):
        """
        Wait for element to be present with logging.
        
        Args:
            by: Selenium By locator type
            value: Locator value
            timeout: Maximum wait time in seconds
        
        Returns:
            WebElement if found
        
        Raises:
            TimeoutException if element not found
        """
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            self.logger.debug(f"Found element: {by}={value}")
            return element
        except TimeoutException:
            self.logger.warning(f"Element not found after {timeout}s: {by}={value}")
            raise
    
    def wait_for_clickable(self, by, value, timeout=10):
        """
        Wait for element to be clickable.
        
        Args:
            by: Selenium By locator type
            value: Locator value
            timeout: Maximum wait time in seconds
        
        Returns:
            WebElement if found and clickable
        """
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            return element
        except TimeoutException:
            self.logger.warning(f"Element not clickable after {timeout}s: {by}={value}")
            raise
    
    @retry_on_failure(
        max_retries=3,
        delay_base=1.0,
        exceptions=(
            ElementClickInterceptedException,
            StaleElementReferenceException,
            Exception
        )
    )
    def safe_click(self, element):
        """
        Safely click an element with retry logic.
        
        Tries regular click first, then JavaScript click as fallback.
        Automatically retries on transient failures.
        
        Args:
            element: WebElement to click
        """
        try:
            # Scroll element into view first
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", 
                element
            )
            self.random_delay(0.3, 0.5)
            
            # Try regular click
            element.click()
            self.logger.debug("Clicked element successfully")
            
        except (ElementClickInterceptedException, Exception) as e:
            self.logger.debug(f"Regular click failed ({e}), trying JS click")
            # Fallback to JavaScript click
            self.driver.execute_script("arguments[0].click();", element)
            self.logger.debug("JS click successful")
    
    def safe_send_keys(self, element, text: str, clear_first: bool = True):
        """
        Safely send keys to an element with optional clearing.
        
        Args:
            element: WebElement to type into
            text: Text to send
            clear_first: Whether to clear the field first
        """
        try:
            if clear_first:
                element.clear()
                self.random_delay(0.1, 0.3)
            
            # Type with human-like delays
            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.02, 0.08))
            
            self.logger.debug(f"Sent keys: {text[:20]}...")
            
        except Exception as e:
            self.logger.warning(f"Error sending keys: {e}")
            raise
    
    def scroll_page(self, direction: str = "down", amount: int = 500):
        """
        Scroll the page in a human-like manner.
        
        Args:
            direction: "up" or "down"
            amount: Pixels to scroll
        """
        try:
            scroll_amount = amount if direction == "down" else -amount
            # Add some randomness
            scroll_amount += random.randint(-50, 50)
            
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            self.random_delay(0.5, 1.0)
            
        except Exception as e:
            self.logger.debug(f"Scroll error (non-critical): {e}")
    
    def take_screenshot(self, name: str = "screenshot"):
        """
        Take a screenshot for debugging.
        
        Args:
            name: Base name for screenshot file
        
        Returns:
            Path to saved screenshot
        """
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"debug_{name}_{timestamp}.png"
            
            screenshots_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                "debug_screenshots"
            )
            os.makedirs(screenshots_dir, exist_ok=True)
            
            filepath = os.path.join(screenshots_dir, filename)
            self.driver.save_screenshot(filepath)
            self.logger.info(f"Screenshot saved: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.warning(f"Failed to take screenshot: {e}")
            return None
    
    def save_page_source(self, name: str = "page"):
        """
        Save page HTML for debugging.
        
        Args:
            name: Base name for HTML file
        
        Returns:
            Path to saved HTML file
        """
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"debug_{name}_{timestamp}.html"
            
            debug_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                "debug_html"
            )
            os.makedirs(debug_dir, exist_ok=True)
            
            filepath = os.path.join(debug_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            
            self.logger.info(f"Page source saved: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.warning(f"Failed to save page source: {e}")
            return None
    
    @abstractmethod
    def login(self):
        """Login to the platform. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def search_jobs(self, keywords: str, location: str) -> List[Dict]:
        """
        Search for jobs and return list of job dictionaries.
        Must be implemented by subclasses.
        """
        pass
    
    @abstractmethod
    def get_job_details(self, job_url: str) -> Dict:
        """
        Get detailed information about a specific job.
        Must be implemented by subclasses.
        """
        pass
    
    def random_delay(self, min_sec: float = 1, max_sec: float = 3):
        """
        Add random delay to appear more human-like.
        
        Args:
            min_sec: Minimum delay in seconds
            max_sec: Maximum delay in seconds
        """
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
    
    def is_rate_limited(self) -> bool:
        """
        Check if we've been rate limited by the platform.
        
        Returns:
            True if rate limited, False otherwise
        """
        try:
            page_text = self.driver.page_source.lower()
            
            rate_limit_indicators = [
                "rate limit",
                "too many requests",
                "please slow down",
                "unusual activity",
                "temporarily blocked",
                "security check",
                "prove you're not a robot",
            ]
            
            for indicator in rate_limit_indicators:
                if indicator in page_text:
                    self.logger.warning(f"Rate limit detected: {indicator}")
                    return True
            
            return False
            
        except Exception:
            return False
    
    def handle_rate_limit(self, wait_minutes: int = 5):
        """
        Handle rate limiting by waiting.
        
        Args:
            wait_minutes: Minutes to wait before continuing
        """
        self.logger.warning(f"Rate limited! Waiting {wait_minutes} minutes...")
        time.sleep(wait_minutes * 60)
        self.logger.info("Resuming after rate limit wait")
