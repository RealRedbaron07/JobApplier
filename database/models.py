from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import Config

Base = declarative_base()

class Job(Base):
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255))
    platform = Column(String(50))  # linkedin, indeed, glassdoor
    job_url = Column(Text, unique=True)
    description = Column(Text)
    requirements = Column(Text)
    salary = Column(String(100))
    job_type = Column(String(50))  # full-time, internship, etc.
    posted_date = Column(DateTime)
    discovered_date = Column(DateTime, default=datetime.utcnow)
    match_score = Column(Integer)  # 0-100
    applied = Column(Boolean, default=False)
    applied_date = Column(DateTime)
    application_status = Column(String(50))  # applied, rejected, interview, etc.
    cover_letter = Column(Text)
    cover_letter_path = Column(String(500))  # Path to generated cover letter file
    original_resume_path = Column(String(500))  # Path to original resume used for this application
    tailored_resume_path = Column(String(500))  # Path to tailored resume file
    application_method = Column(String(50))  # linkedin_easy_apply, manual, external_site
    application_notes = Column(Text)  # Detailed notes about the application
    notes = Column(Text)
    external_site = Column(Boolean, default=False)
    external_url = Column(Text)

class UserProfile(Base):
    __tablename__ = 'user_profile'
    
    id = Column(Integer, primary_key=True)
    resume_path = Column(String(500))  # Optional: default resume path (can be overridden per application)
    skills = Column(Text)  # JSON string
    experience = Column(Text)
    education = Column(Text)
    preferred_titles = Column(Text)  # JSON string
    preferred_locations = Column(Text)  # JSON string
    min_salary = Column(Integer)
    # Contact information for auto-filling forms
    email = Column(String(255))
    phone = Column(String(50))
    first_name = Column(String(100))
    last_name = Column(String(100))
    updated_date = Column(DateTime, default=datetime.utcnow)

class ApplicationRecord(Base):
    """Detailed record of each application for tracking and safety."""
    __tablename__ = 'application_records'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer)  # Reference to Job
    application_date = Column(DateTime, default=datetime.utcnow)
    resume_used = Column(String(500))  # Path to resume used
    cover_letter_used = Column(String(500))  # Path to cover letter used
    tailored_resume_used = Column(String(500))  # Path to tailored resume used
    application_method = Column(String(50))  # How application was submitted
    application_status = Column(String(50))  # submitted, pending, rejected, interview, offer
    follow_up_date = Column(DateTime)  # When to follow up
    response_received = Column(Boolean, default=False)
    response_date = Column(DateTime)
    response_notes = Column(Text)
    interview_date = Column(DateTime)
    offer_details = Column(Text)
    notes = Column(Text)

# Database setup
try:
    engine = create_engine(Config.DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
except Exception as e:
    print(f"Database initialization error: {e}")
    Session = None
