#!/usr/bin/env python3
"""
Database migration script to add contact info columns to user_profile table.
Run this once to update your existing database.
"""

import sqlite3
import os
from config import Config

def migrate_database():
    """Add missing columns to user_profile table."""
    
    # Get database path
    db_url = Config.DATABASE_URL
    if db_url.startswith('sqlite:///'):
        db_path = db_url.replace('sqlite:///', '')
    else:
        print("❌ Only SQLite databases are supported for migration")
        return False
    
    if not os.path.exists(db_path):
        print(f"✅ Database doesn't exist yet - it will be created with correct schema")
        return True
    
    print(f"📊 Migrating database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check which columns exist
        cursor.execute("PRAGMA table_info(user_profile)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"Current columns: {columns}")
        
        # Add missing columns to user_profile
        columns_to_add = {
            'email': 'VARCHAR(255)',
            'phone': 'VARCHAR(50)',
            'first_name': 'VARCHAR(100)',
            'last_name': 'VARCHAR(100)',
        }
        
        added = []
        for col_name, col_type in columns_to_add.items():
            if col_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE user_profile ADD COLUMN {col_name} {col_type}")
                    added.append(col_name)
                    print(f"  ✓ Added column to user_profile: {col_name}")
                except Exception as e:
                    print(f"  ⚠️  Error adding {col_name}: {e}")
            else:
                print(f"  ⊘ Column user_profile.{col_name} already exists")
        
        # Migrate jobs table
        print("\n📊 Checking jobs table...")
        cursor.execute("PRAGMA table_info(jobs)")
        job_columns = [row[1] for row in cursor.fetchall()]
        print(f"Current columns: {job_columns}")
        
        # Add missing columns to jobs table
        jobs_columns_to_add = {
            'cover_letter_path': 'VARCHAR(500)',
            'original_resume_path': 'VARCHAR(500)',
            'tailored_resume_path': 'VARCHAR(500)',
            'application_method': 'VARCHAR(50)',
            'application_notes': 'TEXT',
            'external_url': 'TEXT',
            'requirements': 'TEXT',
        }
        
        jobs_added = []
        for col_name, col_type in jobs_columns_to_add.items():
            if col_name not in job_columns:
                try:
                    cursor.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
                    jobs_added.append(col_name)
                    print(f"  ✓ Added column to jobs: {col_name}")
                except Exception as e:
                    print(f"  ⚠️  Error adding {col_name}: {e}")
            else:
                print(f"  ⊘ Column jobs.{col_name} already exists")
        
        conn.commit()
        conn.close()
        
        total_added = len(added) + len(jobs_added)
        if total_added > 0:
            print(f"\n✅ Migration complete! Added {total_added} column(s)")
            if added:
                print(f"   user_profile: {', '.join(added)}")
            if jobs_added:
                print(f"   jobs: {', '.join(jobs_added)}")
        else:
            print(f"\n✅ Database already up to date!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Database Migration")
    print("=" * 50)
    print()
    
    success = migrate_database()
    
    if success:
        print("\n" + "=" * 50)
        print("✅ Migration successful!")
        print("You can now run: python3 setup_profile.py")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print("❌ Migration failed")
        print("=" * 50)
    
    exit(0 if success else 1)

