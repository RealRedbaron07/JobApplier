from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
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
    application_method = Column(String(50))  # auto, manual, workday_auto, etc.
    application_notes = Column(Text)
    cover_letter = Column(Text)
    cover_letter_path = Column(String(500))
    tailored_resume_path = Column(String(500))
    original_resume_path = Column(String(500))
    notes = Column(Text)
    external_site = Column(Boolean, default=False)
    external_url = Column(Text)
    
    # Relationships
    applications = relationship("ApplicationRecord", back_populates="job")
    saved_links = relationship("SavedLink", back_populates="job")

class UserProfile(Base):
    __tablename__ = 'user_profile'
    
    id = Column(Integer, primary_key=True)
    resume_path = Column(String(500))
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255))
    phone = Column(String(50))
    linkedin_url = Column(String(500))
    skills = Column(Text)  # JSON string
    experience = Column(Text)
    education = Column(Text)
    preferred_titles = Column(Text)  # JSON string
    preferred_locations = Column(Text)  # JSON string
    min_salary = Column(Integer)
    updated_date = Column(DateTime, default=datetime.utcnow)

class ApplicationRecord(Base):
    """Detailed record of each job application."""
    __tablename__ = 'application_records'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'))
    application_date = Column(DateTime, default=datetime.utcnow)
    resume_used = Column(String(500))
    cover_letter_used = Column(String(500))
    tailored_resume_used = Column(String(500))
    application_method = Column(String(50))  # auto, manual, linkedin_easy_apply, workday_auto
    application_status = Column(String(50))  # submitted, pending, rejected, interview, offer
    follow_up_date = Column(DateTime)
    response_date = Column(DateTime)
    notes = Column(Text)
    
    # Relationship
    job = relationship("Job", back_populates="applications")

class SavedLink(Base):
    """Bookmarked/saved job links for later review."""
    __tablename__ = 'saved_links'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'))
    saved_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)
    category = Column(String(50))  # priority, later, interesting
    
    # Relationship
    job = relationship("Job", back_populates="saved_links")

# Database setup
try:
    engine = create_engine(Config.DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
except Exception as e:
    print(f"Database initialization error: {e}")
    Session = None

