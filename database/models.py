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
    notes = Column(Text)
    external_site = Column(Boolean, default=False)
    external_url = Column(Text)

class UserProfile(Base):
    __tablename__ = 'user_profile'
    
    id = Column(Integer, primary_key=True)
    resume_path = Column(String(500))
    skills = Column(Text)  # JSON string
    experience = Column(Text)
    education = Column(Text)
    preferred_titles = Column(Text)  # JSON string
    preferred_locations = Column(Text)  # JSON string
    min_salary = Column(Integer)
    updated_date = Column(DateTime, default=datetime.utcnow)

# Database setup
try:
    engine = create_engine(Config.DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
except Exception as e:
    print(f"Database initialization error: {e}")
    Session = None
