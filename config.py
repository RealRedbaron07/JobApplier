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
    
    # AUTO-APPLY SETTINGS
    # If True, automatically applies to jobs above MIN_MATCH_SCORE without review
    # If False, requires manual review before applying
    AUTO_APPLY_ENABLED = os.getenv('AUTO_APPLY_ENABLED', 'false').lower() == 'true'
    
    # Add missing config
    MAX_JOB_AGE_DAYS = int(os.getenv('MAX_JOB_AGE_DAYS', 30))
    MAX_SEARCH_TIME_MINUTES = int(os.getenv('MAX_SEARCH_TIME_MINUTES', 60))
    
    # Dashboard settings
    DASHBOARD_HOST = os.getenv('DASHBOARD_HOST', '127.0.0.1')
    DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', 5000))
    
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
        'Economics Intern,'
        'Quantitative Developer Intern,'
        'Summer Intern Software'
    ).split(',')
    
    # Locations: Canada first, then Turkey
    LOCATIONS = os.getenv('LOCATIONS', 
        'Toronto, ON,'
        'Canada,'
        'Remote,'
        'Mississauga, ON,'
        'Markham, ON,'
        'Ontario, Canada,'
        'Istanbul, Turkey,'
        'Ankara, Turkey,'
        'Antalya, Turkey,'
        'Turkey'
    ).split(',')
    
    # Matching priorities
    TARGET_LOCATIONS = ["Toronto", "Canada", "Istanbul", "Ankara", "Antalya", "Turkey"]
    LOCATION_PRIORITY = {"Toronto": 1, "Canada": 2, "Istanbul": 3, "Ankara": 4, "Antalya": 5, "Turkey": 6}
    TARGET_FIELDS = ["software", "tech", "data", "analytics", "finance", "fintech", "quantitative", "economics"]
    JOB_TYPES = ["internship", "intern", "entry-level", "junior", "new grad", "student", "undergraduate"]

    # Platforms
    ENABLED_PLATFORMS = ["linkedin", "workday"]

    # Resume settings file path
    USER_SETTINGS_FILE = "user_settings.json"
    
    EXPERIENCE_LEVELS = ['Internship', 'Entry Level', 'Student']
