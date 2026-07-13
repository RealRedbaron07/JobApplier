from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Float, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
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
    work_mode = Column(String(30))
    term_length = Column(String(80))
    start_date = Column(String(80))
    required_skills = Column(Text, default='[]')
    preferred_skills = Column(Text, default='[]')
    work_authorization = Column(Text)
    sponsorship = Column(String(40))
    coop_eligible = Column(Boolean)
    tech_stack = Column(Text, default='[]')
    industry = Column(String(100))
    seniority_level = Column(String(80))
    deadline = Column(DateTime)
    salary_min = Column(Float)
    salary_max = Column(Float)
    source = Column(String(100))
    required_documents = Column(Text, default='[]')
    login_portal = Column(Text)
    fit_category = Column(String(40))
    score_breakdown = Column(Text, default='{}')
    match_explanation = Column(Text, default='{}')
    safety_flags = Column(Text, default='[]')
    resume_profile = Column(String(80))
    suggested_project = Column(String(100))
    next_action = Column(Text)
    application_effort = Column(String(30))
    contact_name = Column(String(255))
    contact_details = Column(Text)
    follow_up_date = Column(DateTime)
    resume_version_used = Column(String(500))
    cover_letter_version_used = Column(String(500))

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
    profile_json = Column(Text)
    automation_level = Column(Integer, default=3)
    graduation_date = Column(String(40), default='May 2029')
    work_authorization = Column(String(255), default='Canadian Permanent Resident')

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

class SavedLink(Base):
    __tablename__ = 'saved_links'
    
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'))
    saved_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    notes = Column(Text)
    category = Column(String(50), default='interesting')


class TailoredDraft(Base):
    __tablename__ = 'tailored_drafts'

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'), nullable=False)
    draft_type = Column(String(50), nullable=False)
    resume_profile = Column(String(80))
    content = Column(Text, nullable=False)
    file_path = Column(String(500))
    review_status = Column(String(30), default='draft')
    safety_report = Column(Text, default='{}')
    created_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Contact(Base):
    __tablename__ = 'contacts'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    company = Column(String(255))
    role = Column(String(255))
    email = Column(String(255))
    linkedin = Column(Text)
    last_contact_date = Column(DateTime)
    notes = Column(Text)
    follow_up_needed = Column(Boolean, default=False)
    relationship_strength = Column(String(30), default='new')


class FollowUp(Base):
    __tablename__ = 'follow_ups'

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('jobs.id'))
    contact_id = Column(Integer, ForeignKey('contacts.id'))
    follow_up_type = Column(String(60), nullable=False)
    due_date = Column(DateTime, nullable=False)
    status = Column(String(30), default='pending')
    message_draft = Column(Text)
    created_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def _ensure_sqlite_columns(engine):
    """Add new nullable columns to older local SQLite databases in place."""
    if engine.dialect.name != 'sqlite':
        return
    model_tables = (Job.__table__, UserProfile.__table__, ApplicationRecord.__table__)
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in model_tables:
            existing = {column['name'] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or column.primary_key or column.foreign_keys:
                    continue
                type_sql = column.type.compile(dialect=engine.dialect)
                connection.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {type_sql}'
                ))

# Database setup
try:
    engine = create_engine(Config.DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    _ensure_sqlite_columns(engine)
    Session = sessionmaker(bind=engine)
except Exception as e:
    print(f"Database initialization error: {e}")
    Session = None
