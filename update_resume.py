#!/usr/bin/env python3
"""
Update resume path in user profile.
Usage: python3 update_resume.py /path/to/new/resume.pdf
"""

import sys
import os
from database.models import Session, UserProfile
from datetime import datetime, timezone

def update_resume_path(resume_path: str = None):
    """Update the resume path in the user profile."""
    
    print("=" * 50)
    print("Update Resume Path")
    print("=" * 50)
    
    # Get resume path
    if not resume_path:
        if len(sys.argv) > 1:
            resume_path = sys.argv[1]
        else:
            resume_path = input("\nEnter the path to your new resume (PDF or DOCX): ").strip()
    
    # Remove quotes if present
    resume_path = resume_path.strip('"').strip("'")
    
    # Expand user home directory if needed
    resume_path = os.path.expanduser(resume_path)
    
    # Check if file exists
    if not os.path.exists(resume_path):
        print(f"\n❌ Error: File not found: {resume_path}")
        print("\nPlease provide a valid path to your resume file.")
        return False
    
    # Check file extension
    if not resume_path.lower().endswith(('.pdf', '.docx')):
        print(f"\n❌ Error: Unsupported file format. Please use PDF or DOCX.")
        return False
    
    print(f"\n📄 New resume file: {resume_path}")
    
    # Initialize database session
    if Session is None:
        print("\n❌ Error: Database not initialized")
        return False
    
    session = Session()
    
    # Get user profile
    user_profile = session.query(UserProfile).first()
    
    if not user_profile:
        print("\n❌ No user profile found.")
        print("   Please run: python3 setup_profile.py")
        session.close()
        return False
    
    # Show current resume
    if user_profile.resume_path:
        print(f"\n📄 Current resume: {user_profile.resume_path}")
    else:
        print("\n📄 No resume currently set in profile")
    
    # Update resume path
    user_profile.resume_path = resume_path
    user_profile.updated_at = datetime.now(timezone.utc)
    
    try:
        session.commit()
        print("\n✅ Resume path updated successfully!")
        print(f"   New path: {resume_path}")
        print("\n💡 This resume will be used for all future job applications.")
        return True
    except Exception as e:
        session.rollback()
        print(f"\n❌ Error updating resume path: {e}")
        return False
    finally:
        session.close()

if __name__ == "__main__":
    update_resume_path()
