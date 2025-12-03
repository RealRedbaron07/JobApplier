#!/usr/bin/env python3
"""
Upgrade database schema to add missing columns.
Run this after updating the models.
"""

from sqlalchemy import create_engine, text, inspect
from config import Config
import sys

def upgrade_database():
    """Add missing columns to existing database."""
    print("Upgrading database schema...")
    
    try:
        engine = create_engine(Config.DATABASE_URL, echo=False)
        inspector = inspect(engine)
        
        # Get existing columns
        existing_columns = {col['name'] for col in inspector.get_columns('jobs')}
        profile_columns = {col['name'] for col in inspector.get_columns('user_profile')}
        
        # Define columns to add
        job_columns_to_add = {
            'cover_letter': 'TEXT',
            'cover_letter_path': 'VARCHAR(500)',
            'tailored_resume_path': 'VARCHAR(500)',
            'original_resume_path': 'VARCHAR(500)',
            'application_method': 'VARCHAR(50)',
            'application_notes': 'TEXT'
        }
        
        profile_columns_to_add = {
            'email': 'VARCHAR(255)',
            'phone': 'VARCHAR(50)',
            'first_name': 'VARCHAR(100)',
            'last_name': 'VARCHAR(100)'
        }
        
        # Add missing columns to jobs table
        with engine.connect() as conn:
            for col_name, col_type in job_columns_to_add.items():
                if col_name not in existing_columns:
                    try:
                        conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        print(f"✓ Added jobs.{col_name}")
                    except Exception as e:
                        print(f"⚠️  Could not add jobs.{col_name}: {e}")
            
            # Add missing columns to user_profile table
            for col_name, col_type in profile_columns_to_add.items():
                if col_name not in profile_columns:
                    try:
                        conn.execute(text(f"ALTER TABLE user_profile ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        print(f"✓ Added user_profile.{col_name}")
                    except Exception as e:
                        print(f"⚠️  Could not add user_profile.{col_name}: {e}")
            
            # Create application_records table if it doesn't exist
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS application_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id INTEGER,
                        application_date DATETIME,
                        resume_used VARCHAR(500),
                        cover_letter_used VARCHAR(500),
                        tailored_resume_used VARCHAR(500),
                        application_method VARCHAR(50),
                        application_status VARCHAR(50),
                        follow_up_date DATETIME,
                        notes TEXT,
                        FOREIGN KEY(job_id) REFERENCES jobs(id)
                    )
                """))
                conn.commit()
                print("✓ Created application_records table")
            except Exception as e:
                print(f"⚠️  application_records table: {e}")
        
        print("\n✅ Database upgrade complete!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error upgrading database: {e}")
        return False

if __name__ == "__main__":
    success = upgrade_database()
    sys.exit(0 if success else 1)
