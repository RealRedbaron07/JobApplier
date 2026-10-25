import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # JobApplier prepares application packages but never submits them. These
    # constants intentionally cannot be enabled through environment variables.
    AUTO_MODE = False

    # Protected-board credentials and automation are deliberately unsupported.
    PROTECTED_BOARD_AUTOMATION_ENABLED = False
    LINKEDIN_EMAIL = ''
    LINKEDIN_PASSWORD = ''
    INDEED_EMAIL = ''
    GLASSDOOR_EMAIL = ''
    GLASSDOOR_PASSWORD = ''
    
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///job_applications.db')
    # Retained for legacy config compatibility; no built-in scraper consumes it.
    SCRAPE_INTERVAL_MINUTES = int(os.getenv('SCRAPE_INTERVAL_MINUTES', 30))
    MIN_MATCH_SCORE = int(os.getenv('MIN_MATCH_SCORE', 60))  # Lower for internships
    
    # Hard-disabled legacy switch. Environment variables cannot enable it.
    AUTO_APPLY_ENABLED = False

    # Only apply to internship roles
    REQUIRE_INTERNSHIP = os.getenv('REQUIRE_INTERNSHIP', 'true').lower() == 'true'

    # Hard safety boundary: browser assistance must stop before final submit.
    STOP_BEFORE_SUBMIT = True

    WAIT_FOR_LOGIN = False

    # Prefer jobs posted/discovered within this many hours ("new" postings)
    NEW_JOB_HOURS = int(os.getenv('NEW_JOB_HOURS', '12'))

    # Default resume path (used when profile DB path is missing or stale)
    DEFAULT_RESUME_PATH = os.getenv(
        'DEFAULT_RESUME_PATH',
        ''
    )
    LOCAL_RESUME_PATH = os.getenv(
        'LOCAL_RESUME_PATH',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resumes', 'Mustafa_Alp_ARI_Resume_10.pdf')
    )

    MIN_REQUEST_DELAY = float(os.getenv('MIN_REQUEST_DELAY', '1.0'))
    MAX_REQUEST_DELAY = float(os.getenv('MAX_REQUEST_DELAY', '3.0'))
    
    # Add missing config
    MAX_JOB_AGE_DAYS = int(os.getenv('MAX_JOB_AGE_DAYS', 1))
    MAX_SEARCH_TIME_MINUTES = int(os.getenv('MAX_SEARCH_TIME_MINUTES', 60))
    
    # Dashboard settings
    DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '127.0.0.1')
    DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', 5000))
    
    # Job search parameters - focused on tech/fintech internships
    JOB_TITLES = [value.strip() for value in os.getenv('JOB_TITLES',
        'Software Developer Intern|Web Developer Intern|QA Software Testing Intern|'
        'Data Reporting BI Co-op|Fintech Technology Co-op|Applied AI Automation Intern|'
        'Technical Analyst Intern'
    ).split('|') if value.strip()]
    
    # Locations are intentionally Canada-first and tailored to Mustafa's search.
    LOCATIONS = [value.strip() for value in os.getenv('LOCATIONS',
        'Toronto, ON|North York, ON|Vaughan, ON|Mississauga, ON|Markham, ON|'
        'Brampton, ON|Ontario, Canada|Remote, Canada'
    ).split('|') if value.strip()]
    
    # Matching priorities
    TARGET_LOCATIONS = ["Toronto", "North York", "Vaughan", "Markham", "Brampton", "Mississauga", "Ontario", "Canada", "Remote"]
    LOCATION_PRIORITY = {"Toronto": 1, "North York": 2, "Vaughan": 2, "Markham": 2, "Mississauga": 2, "Brampton": 2, "Ontario": 3, "Canada": 4, "Remote": 1}
    TARGET_FIELDS = ["software", "tech", "data", "analytics", "finance", "fintech", "quantitative", "economics"]
    JOB_TYPES = ["internship", "intern", "entry-level", "junior", "new grad", "student", "undergraduate"]

    # Platforms
    ENABLED_PLATFORMS = []

    # Resume settings file path
    USER_SETTINGS_FILE = "user_settings.json"
    
    EXPERIENCE_LEVELS = ['Internship', 'Entry Level', 'Student']

    # Safe automation levels: 0=tracking, 1=parse/score, 2=drafts,
    # 3=package preparation, 4=user-confirmed reviewed link/checklist handoff.
    AUTOMATION_LEVEL = min(4, max(0, int(os.getenv('AUTOMATION_LEVEL', '3'))))
    PROFILE_PATH = os.getenv('PROFILE_PATH', os.path.join('data', 'candidate_profile.json'))
    DRAFTS_DIR = os.getenv('DRAFTS_DIR', os.path.join('data', 'drafts'))
