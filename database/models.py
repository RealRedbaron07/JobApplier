from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timezone
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
    discovered_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    match_score = Column(Integer)  # 0-100
    applied = Column(Boolean, default=False)
    applied_date = Column(DateTime)
    application_status = Column(String(50))  # applied, rejected, interview, etc.
    application_method = Column(String(50))
    application_notes = Column(Text)
    cover_letter = Column(Text)
    cover_letter_path = Column(String(500))
    tailored_resume_path = Column(String(500))
    original_resume_path = Column(String(500))
    notes = Column(Text)
    external_site = Column(Boolean, default=False)
    external_url = Column(Text)

class UserProfile(Base):
    __tablename__ = 'user_profile'
    
    id = Column(Integer, primary_key=True)
    resume_path = Column(String(500))
    skills = Column(Text)
    experience = Column(Text)
    education = Column(Text)
    preferred_titles = Column(Text)
    preferred_locations = Column(Text)
    min_salary = Column(Integer)
    email = Column(String(255))
    phone = Column(String(50))
    first_name = Column(String(100))
    last_name = Column(String(100))
    updated_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ApplicationRecord(Base):
    __tablename__ = 'application_records'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'))
    application_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resume_used = Column(String(500))
    cover_letter_used = Column(String(500))
    tailored_resume_used = Column(String(500))
    application_method = Column(String(50))
    application_status = Column(String(50))
    follow_up_date = Column(DateTime)
    notes = Column(Text)

# Database setup
try:
    engine = create_engine(Config.DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
except Exception as e:
    print(f"Database initialization error: {e}")
    Session = None
