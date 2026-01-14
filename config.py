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
