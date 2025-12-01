#!/usr/bin/env python3
"""
Review and manage discovered jobs.
Allows you to approve/reject jobs before applying.
"""

import sys
import os
from database.models import Session, Job
from datetime import datetime
from sqlalchemy import desc
from cover_letter_generator import CoverLetterGenerator
from resume_tailor import ResumeTailor
import json

def display_job(job: Job, index: int, total: int):
    """Display a single job in a formatted way."""
    print("\n" + "=" * 70)
    print(f"Job {index}/{total}")
    print("=" * 70)
    print(f"Title:      {job.title}")
    print(f"Company:    {job.company}")
    print(f"Location:   {job.location}")
    print(f"Platform:   {job.platform}")
    print(f"Match Score: {job.match_score}/100")
    print(f"Discovered: {job.discovered_date.strftime('%Y-%m-%d %H:%M') if job.discovered_date else 'N/A'}")
    print(f"Applied:    {'Yes' if job.applied else 'No'}")
    
    # Show application materials status
    print(f"\nApplication Materials:")
    if job.cover_letter_path and os.path.exists(job.cover_letter_path):
        print(f"  ✓ Cover letter: {job.cover_letter_path}")
    else:
        print(f"  ⊘ Cover letter: Not generated")
    
    if job.tailored_resume_path and os.path.exists(job.tailored_resume_path):
        print(f"  ✓ Tailored resume: {job.tailored_resume_path}")
    else:
        print(f"  ⊘ Tailored resume: Not generated")
    
    if job.description:
        desc_preview = job.description[:200] + "..." if len(job.description) > 200 else job.description
        print(f"\nDescription Preview:")
        print(f"  {desc_preview}")
    
    print(f"\nURL: {job.job_url}")
    print("=" * 70)

def review_jobs():
    """Main function to review jobs."""
    print("=" * 70)
    print("Job Review Interface")
    print("=" * 70)
    
    if Session is None:
        print("\n❌ Error: Database not initialized")
        print("Please check your database configuration.")
        return
    
    session = Session()
    
    # Get jobs sorted by match score (highest first)
    jobs = session.query(Job).filter_by(applied=False).order_by(desc(Job.match_score)).all()
    
    if not jobs:
        print("\nNo jobs to review. Run 'python3 main.py' to search for jobs first.")
        session.close()
        return
    
    print(f"\nFound {len(jobs)} jobs to review")
    print("\nCommands:")
    print("  [Enter] or [n] - Next job")
    print("  [a] - Approve (mark for application)")
    print("  [r] - Reject (skip this job)")
    print("  [s] - Show full description")
    print("  [c] - Generate/view cover letter")
    print("  [t] - Generate tailored resume")
    print("  [q] - Quit")
    print("\n" + "=" * 70)
    
    # Get user profile for cover letter/resume generation
    from database.models import UserProfile
    user_profile_db = session.query(UserProfile).first()
    user_profile = {}
    if user_profile_db:
        user_profile = {
            'skills': json.loads(user_profile_db.skills) if user_profile_db.skills else [],
            'experience': json.loads(user_profile_db.experience) if user_profile_db.experience else [],
            'education': json.loads(user_profile_db.education) if user_profile_db.education else [],
            'contact_info': {}
        }
    
    cover_letter_gen = CoverLetterGenerator()
    resume_tailor = ResumeTailor()
    
    index = 0
    approved_count = 0
    rejected_count = 0
    
    while index < len(jobs):
        job = jobs[index]
        display_job(job, index + 1, len(jobs))
        
        # Get user input
        action = input("\nAction: ").strip().lower()
        
        if action == '' or action == 'n':
            index += 1
        elif action == 'a':
            # Approve - mark with notes
            job.notes = (job.notes or '') + f"\n[Approved on {datetime.now().strftime('%Y-%m-%d %H:%M')}]"
            session.commit()
            approved_count += 1
            print(f"✓ Approved: {job.title} at {job.company}")
            index += 1
        elif action == 'r':
            # Reject - mark as not to apply
            job.notes = (job.notes or '') + f"\n[Rejected on {datetime.now().strftime('%Y-%m-%d %H:%M')}]"
            job.applied = True  # Mark as "processed" so it doesn't show up again
            job.application_status = 'rejected'
            session.commit()
            rejected_count += 1
            print(f"✗ Rejected: {job.title} at {job.company}")
            index += 1
        elif action == 's':
            # Show full description
            if job.description:
                print("\n" + "=" * 70)
                print("Full Description:")
                print("=" * 70)
                print(job.description)
                print("=" * 70)
            else:
                print("No description available.")
        elif action == 'c':
            # Generate or view cover letter
            if job.cover_letter_path and os.path.exists(job.cover_letter_path):
                # Show existing cover letter
                print("\n" + "=" * 70)
                print("Cover Letter:")
                print("=" * 70)
                if job.cover_letter:
                    print(job.cover_letter)
                else:
                    # Read from file
                    try:
                        with open(job.cover_letter_path, 'r', encoding='utf-8') as f:
                            print(f.read())
                    except Exception as e:
                        print(f"Error reading cover letter: {e}")
                print("=" * 70)
                print(f"\nFile: {job.cover_letter_path}")
                edit = input("\nEdit this cover letter? (y/n): ").strip().lower()
                if edit == 'y':
                    # Simple text editor
                    print("\nEnter new cover letter (end with 'END' on a new line):")
                    lines = []
                    while True:
                        line = input()
                        if line.strip() == 'END':
                            break
                        lines.append(line)
                    new_cover_letter = '\n'.join(lines)
                    job.cover_letter = new_cover_letter
                    # Update file
                    try:
                        with open(job.cover_letter_path, 'w', encoding='utf-8') as f:
                            f.write(new_cover_letter)
                        session.commit()
                        print("✓ Cover letter updated")
                    except Exception as e:
                        print(f"Error saving cover letter: {e}")
            else:
                # Generate new cover letter
                if not user_profile_db:
                    print("❌ No user profile found. Run 'python3 setup_profile.py' first.")
                else:
                    print("Generating cover letter...")
                    try:
                        job_data = {
                            'title': job.title,
                            'company': job.company,
                            'location': job.location or '',
                            'description': job.description or '',
                            'requirements': job.requirements or ''
                        }
                        cover_letter_text, cover_letter_path = cover_letter_gen.generate_cover_letter(
                            job_data, user_profile
                        )
                        job.cover_letter = cover_letter_text
                        job.cover_letter_path = cover_letter_path
                        session.commit()
                        print(f"✓ Cover letter generated: {cover_letter_path}")
                        print("\nPreview:")
                        print("-" * 70)
                        print(cover_letter_text[:500] + "..." if len(cover_letter_text) > 500 else cover_letter_text)
                        print("-" * 70)
                    except Exception as e:
                        print(f"❌ Error generating cover letter: {e}")
        elif action == 't':
            # Generate tailored resume
            if not user_profile_db or not user_profile_db.resume_path:
                print("❌ No resume found in profile. Run 'python3 setup_profile.py' first.")
            else:
                if job.tailored_resume_path and os.path.exists(job.tailored_resume_path):
                    print(f"✓ Tailored resume already exists: {job.tailored_resume_path}")
                    regenerate = input("Regenerate? (y/n): ").strip().lower()
                    if regenerate != 'y':
                        continue
                
                print("Generating tailored resume...")
                try:
                    job_data = {
                        'title': job.title,
                        'company': job.company,
                        'location': job.location or '',
                        'description': job.description or '',
                        'requirements': job.requirements or ''
                    }
                    tailored_resume_path = resume_tailor.tailor_resume(
                        user_profile_db.resume_path,
                        job_data,
                        user_profile
                    )
                    job.tailored_resume_path = tailored_resume_path
                    session.commit()
                    print(f"✓ Tailored resume generated: {tailored_resume_path}")
                except Exception as e:
                    print(f"❌ Error generating tailored resume: {e}")
        elif action == 'q':
            print("\nExiting review...")
            break
        else:
            print("Invalid command. Try again.")
    
    session.close()
    
    print("\n" + "=" * 70)
    print("Review Summary:")
    print(f"  Approved: {approved_count}")
    print(f"  Rejected: {rejected_count}")
    print(f"  Remaining: {len(jobs) - index}")
    print("=" * 70)
    
    if approved_count > 0:
        print(f"\n📋 Next step: Run 'python3 apply_jobs.py' to apply to approved jobs")
    print("=" * 70)

def list_jobs():
    """List all jobs with their status."""
    if Session is None:
        print("\n❌ Error: Database not initialized")
        print("Please check your database configuration.")
        return
    
    session = Session()
    
    all_jobs = session.query(Job).order_by(desc(Job.match_score)).all()
    applied_jobs = session.query(Job).filter_by(applied=True).count()
    pending_jobs = session.query(Job).filter_by(applied=False).count()
    
    print("=" * 70)
    print("Job Summary")
    print("=" * 70)
    print(f"Total jobs:     {len(all_jobs)}")
    print(f"Pending review: {pending_jobs}")
    print(f"Applied:        {applied_jobs}")
    print("=" * 70)
    
    if all_jobs:
        print("\nTop 10 Jobs by Match Score:")
        print("-" * 70)
        for i, job in enumerate(all_jobs[:10], 1):
            status = "✓ Applied" if job.applied else "⏳ Pending"
            print(f"{i:2}. [{status}] {job.match_score:3}/100 - {job.title} at {job.company}")
    
    session.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--list':
        list_jobs()
    else:
        review_jobs()

