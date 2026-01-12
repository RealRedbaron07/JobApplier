import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # OPTIONAL: OpenAI API Key (system works without it)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    
    # OPTIONAL: LinkedIn credentials (only needed for Easy Apply feature)
    # If not provided, will still scrape jobs and apply via company websites
    LINKEDIN_EMAIL = os.getenv('LINKEDIN_EMAIL', '')
    LINKEDIN_PASSWORD = os.getenv('LINKEDIN_PASSWORD', '')
    
    # Not needed - other platforms work without login
    INDEED_EMAIL = os.getenv('INDEED_EMAIL', '')
    GLASSDOOR_EMAIL = os.getenv('GLASSDOOR_EMAIL', '')
    GLASSDOOR_PASSWORD = os.getenv('GLASSDOOR_PASSWORD', '')
    
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///job_applications.db')
    SCRAPE_INTERVAL_MINUTES = int(os.getenv('SCRAPE_INTERVAL_MINUTES', 30))
    MIN_MATCH_SCORE = int(os.getenv('MIN_MATCH_SCORE', 60))  # Lower for internships
    MAX_JOB_AGE_DAYS = int(os.getenv('MAX_JOB_AGE_DAYS', 30))  # Filter out old jobs
    
    # FULL AUTOMATION MODE
    # If True, runs completely hands-free: scrape → match → generate materials → apply
    # No user prompts or confirmations required
    AUTO_MODE = os.getenv('AUTO_MODE', 'false').lower() == 'true'
    
    # Legacy setting (kept for compatibility)
    AUTO_APPLY_ENABLED = os.getenv('AUTO_APPLY_ENABLED', 'false').lower() == 'true'
    
    # Dashboard settings
    DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', 5000))
    DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '127.0.0.1')
    
    # Job search parameters - focused on tech/fintech internships
    JOB_TITLES = os.getenv('JOB_TITLES', 
        'Software Engineering Intern,'
        'Software Developer Intern,'
        'Data Science Intern,'
        'Data Analyst Intern,'
        'Fintech Intern,'
        'Technology Intern,'
        'Computer Science Intern,'
        'Backend Intern,'
        'Frontend Intern,'
        'Full Stack Intern,'
        'Finance Technology Intern,'
        'Quantitative Analyst Intern,'
        'Summer Intern Software,'
        'Summer Intern Technology'
    ).split(',')
    
    # Locations: Canada (GTA) and Turkey (Istanbul, Ankara)
    LOCATIONS = os.getenv('LOCATIONS', 
        'Remote,'
        'Toronto, ON,'
        'Mississauga, ON,'
        'Brampton, ON,'
        'Markham, ON,'
        'Vaughan, ON,'
        'Richmond Hill, ON,'
        'Oakville, ON,'
        'Burlington, ON,'
        'Ontario, Canada,'
        'Istanbul, Turkey,'
        'Ankara, Turkey,'
        'Turkey'
    ).split(',')
    
    EXPERIENCE_LEVELS = ['Internship', 'Entry Level', 'Student']
    
    # Search limits to prevent infinite scraping
    MAX_SEARCH_TIME_MINUTES = int(os.getenv('MAX_SEARCH_TIME_MINUTES', 10))  # Stop after 10 minutes
    MAX_NEW_JOBS_TO_FIND = int(os.getenv('MAX_NEW_JOBS_TO_FIND', 50))  # Stop after finding 50 new jobs
    
    # Job freshness filter - only apply to jobs posted within this many days
    MAX_JOB_AGE_DAYS = int(os.getenv('MAX_JOB_AGE_DAYS', 30))  # Only apply to jobs posted in last 30 days
    
    # ============================================
    # ANTI-DETECTION & PROXY SETTINGS
    # ============================================
    
    # Proxy URL (optional, for anti-ban protection)
    # Format: http://user:pass@proxy.example.com:8080 or http://proxy.example.com:8080
    PROXY_URL = os.getenv('PROXY_URL', '')
    
    # Whether to rotate through multiple proxies (requires proxy list file)
    ROTATE_PROXIES = os.getenv('ROTATE_PROXIES', 'false').lower() == 'true'
    
    # ============================================
    # RETRY & RATE LIMITING SETTINGS
    # ============================================
    
    # Maximum retry attempts for failed operations
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
    
    # Base delay between retries (doubles with each attempt)
    RETRY_DELAY_SECONDS = float(os.getenv('RETRY_DELAY_SECONDS', 2.0))
    
    # Minimum delay between requests (to avoid rate limiting)
    MIN_REQUEST_DELAY = float(os.getenv('MIN_REQUEST_DELAY', 1.0))
    MAX_REQUEST_DELAY = float(os.getenv('MAX_REQUEST_DELAY', 3.0))
    
    # Wait time when rate limited (in minutes)
    RATE_LIMIT_WAIT_MINUTES = int(os.getenv('RATE_LIMIT_WAIT_MINUTES', 5))
    
    # ============================================
    # LOGGING SETTINGS
    # ============================================
    
    # Log directory
    LOG_DIR = os.getenv('LOG_DIR', 'logs')
    
    # Log level for file output (DEBUG, INFO, WARNING, ERROR)
    LOG_LEVEL_FILE = os.getenv('LOG_LEVEL_FILE', 'DEBUG')
    
    # Log level for console output
    LOG_LEVEL_CONSOLE = os.getenv('LOG_LEVEL_CONSOLE', 'INFO')
    
    # Enable debug mode (saves screenshots and HTML on failures)
    DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    
    # ============================================
    # BROWSER SETTINGS (Persistent Sessions)
    # ============================================
    
    # Chrome profile directory for persistent sessions
    # First run: Log in manually → cookies saved here
    # Subsequent runs: Auto-loads saved session (no login needed)
    # Set to empty string '' to use fresh session each time
    CHROME_DATA_DIR = os.getenv('CHROME_DATA_DIR', 
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome_profile')
    )
    
    # Headless mode - set to True for background operation
    # Default: False (visible browser for first run / manual login)
    # After first successful login, can set to True for automation
    HEADLESS_MODE = os.getenv('HEADLESS_MODE', 'false').lower() == 'true'
    
    # Use existing Chrome profile (alternative to CHROME_DATA_DIR)
    # If True, uses your default Chrome profile at ~/Library/Application Support/Google/Chrome
    # WARNING: Chrome must be closed when using this option
    USE_SYSTEM_CHROME_PROFILE = os.getenv('USE_SYSTEM_CHROME_PROFILE', 'false').lower() == 'true'
