#!/usr/bin/env python3
"""
Setup user profile by parsing resume and saving to database.
Usage: python3 setup_profile.py [resume_path]
"""

import sys
import os
import json
from pathlib import Path
from resume_parser.parser import ResumeParser
from database.models import Session, UserProfile
from datetime import datetime, timezone

def setup_profile(resume_path: str = None):
    """Parse resume and save user profile to database."""
    
    print("=" * 50)
    print("Job Applier - Profile Setup")
    print("=" * 50)
    
    # Get resume path
    if not resume_path:
        if len(sys.argv) > 1:
            resume_path = sys.argv[1]
        else:
            resume_path = input("\nEnter the path to your resume (PDF or DOCX): ").strip()
    
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
    
    print(f"\n📄 Resume file: {resume_path}")
    print("Parsing resume...")
    
    # Initialize parser
    try:
        parser = ResumeParser()
        parsed_data = parser.parse_resume(resume_path)
    except Exception as e:
        print(f"\n❌ Error parsing resume: {e}")
        return False
    
    # Display parsed information
    print("\n" + "=" * 50)
    print("Parsed Information:")
    print("=" * 50)
    
    print(f"\n📚 Skills ({len(parsed_data.get('skills', []))}):")
    skills = parsed_data.get('skills', [])
    if skills:
        print(f"   {', '.join(skills[:10])}")
        if len(skills) > 10:
            print(f"   ... and {len(skills) - 10} more")
    else:
        print("   (No skills detected)")
    
    print(f"\n💼 Experience ({len(parsed_data.get('experience', []))}):")
    experience = parsed_data.get('experience', [])
    for i, exp in enumerate(experience[:3], 1):
        title = exp.get('title', 'N/A')
        company = exp.get('company', 'N/A')
        print(f"   {i}. {title} at {company}")
    if len(experience) > 3:
        print(f"   ... and {len(experience) - 3} more")
    
    print(f"\n🎓 Education ({len(parsed_data.get('education', []))}):")
    education = parsed_data.get('education', [])
    for i, edu in enumerate(education, 1):
        degree = edu.get('degree', 'N/A')
        field = edu.get('field', 'N/A')
        institution = edu.get('institution', 'N/A')
        print(f"   {i}. {degree} in {field} - {institution}")
    if not education:
        print("   (No education detected)")
    
    contact = parsed_data.get('contact_info', {})
    if contact:
        print(f"\n📧 Contact Info:")
        if contact.get('email'):
            print(f"   Email: {contact['email']}")
        if contact.get('phone'):
            print(f"   Phone: {contact['phone']}")
        if contact.get('linkedin'):
            print(f"   LinkedIn: {contact['linkedin']}")
    
    # Ask for contact info if not found in resume
    if not contact.get('email'):
        print("\n" + "=" * 50)
        print("Contact Information Required for Auto-Application")
        print("=" * 50)
        print("To enable automatic application on Workday and other platforms,")
        print("please provide your contact information:")
        
        email = input("\nEmail (required): ").strip()
        while not email or '@' not in email:
            if email:
                print("⚠️  Please enter a valid email address")
            email = input("Email (required): ").strip()
        
        phone = input("Phone (optional, press Enter to skip): ").strip()
        first_name = input("First Name (optional, press Enter to skip): ").strip()
        last_name = input("Last Name (optional, press Enter to skip): ").strip()
        
        # Update contact dict with user input
        contact['email'] = email
        if phone:
            contact['phone'] = phone
        if first_name:
            contact['first_name'] = first_name
        if last_name:
            contact['last_name'] = last_name
    
    # Save to database
    print("\n" + "=" * 50)
    print("Saving to database...")
    
    if Session is None:
        print("\n❌ Error: Database not initialized")
        print("Please check your database configuration.")
        return False
    
    try:
        session = Session()
        
        # Check if profile already exists
        existing_profile = session.query(UserProfile).first()
        
        if existing_profile:
            # Update existing profile (resume_path is optional - can be None)
            if resume_path:
                existing_profile.resume_path = resume_path
            existing_profile.skills = json.dumps(parsed_data.get('skills', []))
            existing_profile.experience = json.dumps(parsed_data.get('experience', []))
            existing_profile.education = json.dumps(parsed_data.get('education', []))
            
            # Update contact info (use the contact dict that may have been updated with user input)
            if contact.get('email'):
                existing_profile.email = contact['email']
            if contact.get('phone'):
                existing_profile.phone = contact['phone']
            if contact.get('first_name'):
                existing_profile.first_name = contact['first_name']
            if contact.get('last_name'):
                existing_profile.last_name = contact['last_name']
            
            existing_profile.updated_date = datetime.now(timezone.utc)
            print("✓ Updated existing profile")
        else:
            # Create new profile (use the contact dict that may have been updated with user input)
            new_profile = UserProfile(
                resume_path=resume_path,
                skills=json.dumps(parsed_data.get('skills', [])),
                experience=json.dumps(parsed_data.get('experience', [])),
                education=json.dumps(parsed_data.get('education', [])),
                email=contact.get('email'),
                phone=contact.get('phone'),
                first_name=contact.get('first_name'),
                last_name=contact.get('last_name'),
                updated_date=datetime.now(timezone.utc)
            )
            session.add(new_profile)
            print("✓ Created new profile")
        
        session.commit()
        session.close()
        
        print("\n" + "=" * 50)
        print("✅ Profile setup complete!")
        print("=" * 50)
        print("\n📋 Next steps:")
        print("1. Run job search:  python3 main.py")
        print("2. Review jobs:     python3 review_ui.py")
        print("3. Apply to jobs:   python3 apply_jobs.py")
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error saving to database: {e}")
        return False

if __name__ == "__main__":
    # Check if resume path was provided as argument
    resume_path = None
    if len(sys.argv) > 1:
        resume_path = sys.argv[1]
    
    success = setup_profile(resume_path)
    sys.exit(0 if success else 1)

