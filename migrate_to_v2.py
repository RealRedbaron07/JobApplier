#!/usr/bin/env python3
"""
Database migration script to add new columns for the automation update.
Run this once to update your existing database.
"""

import sqlite3
import os

def migrate():
    db_path = 'job_applications.db'
    
    if not os.path.exists(db_path):
        print("Database not found. It will be created when you run the app.")
        return
    
    print("Migrating database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # New columns for user_profile table
    user_profile_columns = [
        ('first_name', 'VARCHAR(100)'),
        ('last_name', 'VARCHAR(100)'),
        ('email', 'VARCHAR(255)'),
        ('phone', 'VARCHAR(50)'),
        ('linkedin_url', 'VARCHAR(500)'),
    ]
    
    # New columns for jobs table
    jobs_columns = [
        ('application_method', 'VARCHAR(50)'),
        ('application_notes', 'TEXT'),
        ('cover_letter_path', 'VARCHAR(500)'),
        ('tailored_resume_path', 'VARCHAR(500)'),
        ('original_resume_path', 'VARCHAR(500)'),
    ]
    
    # Add columns to user_profile
    for col_name, col_type in user_profile_columns:
        try:
            cursor.execute(f"ALTER TABLE user_profile ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ Added user_profile.{col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"  - user_profile.{col_name} already exists")
            else:
                print(f"  ✗ Error adding user_profile.{col_name}: {e}")
    
    # Add columns to jobs
    for col_name, col_type in jobs_columns:
        try:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ Added jobs.{col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"  - jobs.{col_name} already exists")
            else:
                print(f"  ✗ Error adding jobs.{col_name}: {e}")
    
    # Create new tables if they don't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS application_records (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            application_date DATETIME,
            resume_used VARCHAR(500),
            cover_letter_used VARCHAR(500),
            tailored_resume_used VARCHAR(500),
            application_method VARCHAR(50),
            application_status VARCHAR(50),
            follow_up_date DATETIME,
            response_date DATETIME,
            notes TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)
    print("  ✓ Created/verified application_records table")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_links (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            saved_date DATETIME,
            notes TEXT,
            category VARCHAR(50),
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        )
    """)
    print("  ✓ Created/verified saved_links table")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Database migration complete!")
    print("You can now run: python3 auto_apply.py --dry-run")

if __name__ == "__main__":
    migrate()
