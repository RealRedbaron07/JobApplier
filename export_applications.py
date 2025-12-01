#!/usr/bin/env python3
"""
Export all applied jobs to a table (CSV format).
Extracts all application data for easy viewing and analysis.
"""

import sys
import csv
from database.models import Session, Job, ApplicationRecord
from datetime import datetime
from sqlalchemy import desc
import os

def export_to_csv(output_file: str = None):
    """Export all applications to CSV file."""
    if Session is None:
        print("\n❌ Error: Database not initialized")
        return False
    
    session = Session()
    
    # Get all application records
    records = session.query(ApplicationRecord).order_by(desc(ApplicationRecord.application_date)).all()
    
    if not records:
        print("\n📋 No applications found to export.")
        session.close()
        return False
    
    # Generate filename if not provided
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"applications_export_{timestamp}.csv"
    
    # Get job details for each record
    applications_data = []
    
    for record in records:
        job = session.query(Job).filter_by(id=record.job_id).first()
        if not job:
            continue
        
        applications_data.append({
            'Application Date': record.application_date.strftime('%Y-%m-%d %H:%M') if record.application_date else '',
            'Job Title': job.title,
            'Company': job.company,
            'Location': job.location or '',
            'Platform': job.platform or '',
            'Job URL': job.job_url or '',
            'Match Score': job.match_score or '',
            'Application Status': record.application_status or '',
            'Application Method': record.application_method or '',
            'Resume Used': record.resume_used or '',
            'Cover Letter': record.cover_letter_used or '',
            'Tailored Resume': record.tailored_resume_used or '',
            'Response Received': 'Yes' if record.response_received else 'No',
            'Response Date': record.response_date.strftime('%Y-%m-%d') if record.response_date else '',
            'Interview Date': record.interview_date.strftime('%Y-%m-%d %H:%M') if record.interview_date else '',
            'Follow-up Date': record.follow_up_date.strftime('%Y-%m-%d') if record.follow_up_date else '',
            'Offer Details': record.offer_details or '',
            'Notes': record.notes or ''
        })
    
    # Write to CSV
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            if not applications_data:
                print("\n📋 No applications to export.")
                session.close()
                return False
            
            fieldnames = applications_data[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for app in applications_data:
                writer.writerow(app)
        
        print(f"\n✅ Exported {len(applications_data)} applications to: {output_file}")
        print(f"   File location: {os.path.abspath(output_file)}")
        session.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Error exporting to CSV: {e}")
        session.close()
        return False

def export_summary_table():
    """Export a summary table with key information."""
    if Session is None:
        print("\n❌ Error: Database not initialized")
        return False
    
    session = Session()
    
    # Get all application records
    records = session.query(ApplicationRecord).order_by(desc(ApplicationRecord.application_date)).all()
    
    if not records:
        print("\n📋 No applications found to export.")
        session.close()
        return False
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"applications_summary_{timestamp}.csv"
    
    # Create summary data
    summary_data = []
    
    for record in records:
        job = session.query(Job).filter_by(id=record.job_id).first()
        if not job:
            continue
        
        # Calculate days since application
        days_since = ''
        if record.application_date:
            delta = datetime.now() - record.application_date.replace(tzinfo=None)
            days_since = str(delta.days)
        
        summary_data.append({
            'Date Applied': record.application_date.strftime('%Y-%m-%d') if record.application_date else '',
            'Days Since': days_since,
            'Job Title': job.title,
            'Company': job.company,
            'Location': job.location or '',
            'Status': record.application_status or 'pending',
            'Response': 'Yes' if record.response_received else 'No',
            'Interview': 'Yes' if record.interview_date else 'No',
            'Match Score': job.match_score or '',
            'URL': job.job_url or ''
        })
    
    # Write to CSV
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            if not summary_data:
                print("\n📋 No applications to export.")
                session.close()
                return False
            
            fieldnames = summary_data[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for app in summary_data:
                writer.writerow(app)
        
        print(f"\n✅ Exported summary of {len(summary_data)} applications to: {output_file}")
        print(f"   File location: {os.path.abspath(output_file)}")
        session.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Error exporting summary: {e}")
        session.close()
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == '--summary':
            export_summary_table()
        elif sys.argv[1] == '--full':
            export_to_csv()
        else:
            # Use argument as output filename
            export_to_csv(sys.argv[1])
    else:
        # Default: export full details
        export_to_csv()

