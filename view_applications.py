#!/usr/bin/env python3
"""
View and manage application records.
Shows all applications with their status, materials used, and tracking information.
"""

import sys
from database.models import Session, Job, ApplicationRecord
from datetime import datetime
from sqlalchemy import desc
import os

def view_all_applications():
    """View all application records."""
    if Session is None:
        print("\n❌ Error: Database not initialized")
        return
    
    session = Session()
    
    # Get all application records
    records = session.query(ApplicationRecord).order_by(desc(ApplicationRecord.application_date)).all()
    
    if not records:
        print("\n📋 No applications found.")
        print("Run 'python3 apply_jobs.py' to start applying to jobs.")
        session.close()
        return
    
    print("=" * 80)
    print("Application Records")
    print("=" * 80)
    print(f"\nTotal Applications: {len(records)}")
    
    # Count by status
    status_counts = {}
    for record in records:
        status = record.application_status or 'unknown'
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("\nStatus Summary:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status.capitalize()}: {count}")
    
    print("\n" + "=" * 80)
    print("Recent Applications:")
    print("=" * 80)
    
    for i, record in enumerate(records[:20], 1):  # Show last 20
        job = session.query(Job).filter_by(id=record.job_id).first()
        if not job:
            continue
        
        print(f"\n[{i}] {job.title} at {job.company}")
        print(f"    Applied: {record.application_date.strftime('%Y-%m-%d %H:%M') if record.application_date else 'N/A'}")
        print(f"    Status: {record.application_status or 'N/A'}")
        print(f"    Method: {record.application_method or 'N/A'}")
        
        if record.resume_used:
            exists = "✓" if os.path.exists(record.resume_used) else "✗"
            print(f"    Resume: {exists} {record.resume_used}")
        
        if record.cover_letter_used:
            exists = "✓" if os.path.exists(record.cover_letter_used) else "✗"
            print(f"    Cover Letter: {exists} {record.cover_letter_used}")
        
        if record.tailored_resume_used:
            exists = "✓" if os.path.exists(record.tailored_resume_used) else "✗"
            print(f"    Tailored Resume: {exists} {record.tailored_resume_used}")
        
        if record.response_received:
            print(f"    ✓ Response received: {record.response_date.strftime('%Y-%m-%d') if record.response_date else 'N/A'}")
        
        if record.interview_date:
            print(f"    📅 Interview: {record.interview_date.strftime('%Y-%m-%d %H:%M')}")
        
        if record.notes:
            print(f"    Notes: {record.notes[:100]}...")
    
    if len(records) > 20:
        print(f"\n... and {len(records) - 20} more applications")
    
    session.close()

def view_application_details(application_id: int = None):
    """View detailed information about a specific application."""
    if Session is None:
        print("\n❌ Error: Database not initialized")
        return
    
    session = Session()
    
    if application_id:
        record = session.query(ApplicationRecord).filter_by(id=application_id).first()
    else:
        # Get most recent
        record = session.query(ApplicationRecord).order_by(desc(ApplicationRecord.application_date)).first()
    
    if not record:
        print("\n❌ Application not found")
        session.close()
        return
    
    job = session.query(Job).filter_by(id=record.job_id).first()
    if not job:
        print("\n❌ Job not found")
        session.close()
        return
    
    print("=" * 80)
    print("Application Details")
    print("=" * 80)
    print(f"\nJob: {job.title} at {job.company}")
    print(f"Location: {job.location}")
    print(f"URL: {job.job_url}")
    print(f"Match Score: {job.match_score}/100")
    
    print(f"\nApplication Information:")
    print(f"  Date: {record.application_date.strftime('%Y-%m-%d %H:%M') if record.application_date else 'N/A'}")
    print(f"  Status: {record.application_status or 'N/A'}")
    print(f"  Method: {record.application_method or 'N/A'}")
    
    print(f"\nMaterials Used:")
    if record.resume_used:
        exists = "✓" if os.path.exists(record.resume_used) else "✗ MISSING"
        print(f"  Resume: {exists}")
        print(f"    {record.resume_used}")
    
    if record.cover_letter_used:
        exists = "✓" if os.path.exists(record.cover_letter_used) else "✗ MISSING"
        print(f"  Cover Letter: {exists}")
        print(f"    {record.cover_letter_used}")
    
    if record.tailored_resume_used:
        exists = "✓" if os.path.exists(record.tailored_resume_used) else "✗ MISSING"
        print(f"  Tailored Resume: {exists}")
        print(f"    {record.tailored_resume_used}")
    
    print(f"\nResponse Tracking:")
    print(f"  Response Received: {'Yes' if record.response_received else 'No'}")
    if record.response_date:
        print(f"  Response Date: {record.response_date.strftime('%Y-%m-%d')}")
    if record.response_notes:
        print(f"  Response Notes: {record.response_notes}")
    
    if record.interview_date:
        print(f"  Interview Scheduled: {record.interview_date.strftime('%Y-%m-%d %H:%M')}")
    
    if record.follow_up_date:
        print(f"  Follow-up Date: {record.follow_up_date.strftime('%Y-%m-%d')}")
    
    if record.offer_details:
        print(f"  Offer Details: {record.offer_details}")
    
    if record.notes:
        print(f"\nNotes:")
        print(f"  {record.notes}")
    
    session.close()

def update_application_status():
    """Update application status interactively."""
    if Session is None:
        print("\n❌ Error: Database not initialized")
        return
    
    session = Session()
    
    # Show recent applications
    records = session.query(ApplicationRecord).order_by(desc(ApplicationRecord.application_date)).limit(10).all()
    
    if not records:
        print("\n📋 No applications found.")
        session.close()
        return
    
    print("\nRecent Applications:")
    for i, record in enumerate(records, 1):
        job = session.query(Job).filter_by(id=record.job_id).first()
        if job:
            print(f"  [{i}] {job.title} at {job.company} - {record.application_status or 'N/A'}")
    
    try:
        choice = int(input("\nSelect application number to update (or 0 to cancel): "))
        if choice < 1 or choice > len(records):
            print("Cancelled.")
            session.close()
            return
        
        record = records[choice - 1]
        
        print(f"\nCurrent status: {record.application_status or 'N/A'}")
        print("\nStatus options:")
        print("  1. submitted")
        print("  2. pending")
        print("  3. rejected")
        print("  4. interview")
        print("  5. offer")
        print("  6. accepted")
        print("  7. declined")
        
        status_choice = input("\nSelect status (1-7): ").strip()
        status_map = {
            '1': 'submitted',
            '2': 'pending',
            '3': 'rejected',
            '4': 'interview',
            '5': 'offer',
            '6': 'accepted',
            '7': 'declined'
        }
        
        if status_choice in status_map:
            record.application_status = status_map[status_choice]
            
            if status_choice == '4':  # Interview
                interview_date = input("Interview date (YYYY-MM-DD, optional): ").strip()
                if interview_date:
                    try:
                        record.interview_date = datetime.strptime(interview_date, '%Y-%m-%d')
                    except:
                        print("Invalid date format, skipping")
            
            notes = input("Add notes (optional): ").strip()
            if notes:
                record.notes = (record.notes or '') + f"\n[{datetime.now().strftime('%Y-%m-%d')}]: {notes}"
            
            session.commit()
            print(f"✓ Status updated to: {status_map[status_choice]}")
        else:
            print("Invalid choice")
        
    except (ValueError, KeyboardInterrupt):
        print("\nCancelled.")
    finally:
        session.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == '--details':
            view_application_details()
        elif sys.argv[1] == '--update':
            update_application_status()
        elif sys.argv[1] == '--export':
            from export_applications import export_to_csv
            export_to_csv()
        else:
            print("Usage: python3 view_applications.py [--details|--update|--export]")
    else:
        view_all_applications()

