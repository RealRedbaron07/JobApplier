#!/usr/bin/env python3
"""
Auto-complete applications that have been pending for more than 2 hours with no response.
Marks them as 'completed' or 'no_response' status.
"""

import sys
from database.models import Session, ApplicationRecord
from datetime import datetime, timedelta, timezone

def auto_complete_pending_applications(hours_threshold: int = 2):
    """Mark applications as completed if no response within threshold hours."""
    if Session is None:
        print("\n❌ Error: Database not initialized")
        return
    
    session = Session()
    
    # Calculate cutoff time (2 hours ago)
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_threshold)
    
    # Find applications that:
    # 1. Are pending/submitted status
    # 2. Have no response
    # 3. Are older than threshold
    pending_apps = session.query(ApplicationRecord).filter(
        ApplicationRecord.application_status.in_(['pending', 'submitted']),
        ApplicationRecord.response_received == False,
        ApplicationRecord.application_date < cutoff_time
    ).all()
    
    if not pending_apps:
        print(f"\n✓ No applications to auto-complete.")
        print(f"   (All pending applications are within {hours_threshold} hours)")
        session.close()
        return
    
    print(f"\nFound {len(pending_apps)} applications pending for more than {hours_threshold} hours")
    print("These will be marked as 'completed' (no response).")
    
    # Show what will be updated
    print("\nApplications to auto-complete:")
    for i, app in enumerate(pending_apps[:10], 1):
        hours_ago = (datetime.now(timezone.utc) - app.application_date.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        print(f"  [{i}] Application #{app.id} - {hours_ago:.1f} hours ago - Status: {app.application_status}")
    
    if len(pending_apps) > 10:
        print(f"  ... and {len(pending_apps) - 10} more")
    
    confirm = input("\nAuto-complete these applications? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("Cancelled.")
        session.close()
        return
    
    # Update applications
    updated_count = 0
    for app in pending_apps:
        # Mark as completed (no response)
        app.application_status = 'completed'
        app.notes = (app.notes or '') + f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}]: Auto-completed - No response within {hours_threshold} hours"
        updated_count += 1
    
    session.commit()
    session.close()
    
    print(f"\n✅ Auto-completed {updated_count} applications")
    print(f"   Status changed to: 'completed' (no response)")

def check_pending_applications():
    """Check and show pending applications."""
    if Session is None:
        print("\n❌ Error: Database not initialized")
        return
    
    session = Session()
    
    # Get pending applications
    pending_apps = session.query(ApplicationRecord).filter(
        ApplicationRecord.application_status.in_(['pending', 'submitted']),
        ApplicationRecord.response_received == False
    ).order_by(ApplicationRecord.application_date).all()
    
    if not pending_apps:
        print("\n✓ No pending applications.")
        session.close()
        return
    
    print(f"\nPending Applications: {len(pending_apps)}")
    print("=" * 80)
    
    now = datetime.now(timezone.utc)
    for app in pending_apps:
        app_time = app.application_date.replace(tzinfo=timezone.utc) if app.application_date else None
        if app_time:
            hours_ago = (now - app_time).total_seconds() / 3600
            status_icon = "⚠️" if hours_ago >= 2 else "⏳"
            print(f"{status_icon} Application #{app.id} - {hours_ago:.1f} hours ago - Status: {app.application_status}")
        else:
            print(f"⏳ Application #{app.id} - Status: {app.application_status}")
    
    # Count applications over 2 hours
    over_2_hours = [app for app in pending_apps 
                   if app.application_date and 
                   (now - app.application_date.replace(tzinfo=timezone.utc)).total_seconds() / 3600 >= 2]
    
    if over_2_hours:
        print(f"\n⚠️  {len(over_2_hours)} applications have been pending for 2+ hours")
        print("   Run with --auto-complete to mark them as completed")
    
    session.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == '--check':
            check_pending_applications()
        elif sys.argv[1] == '--auto-complete':
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 2
            auto_complete_pending_applications(hours)
        else:
            print("Usage: python3 auto_complete_applications.py [--check|--auto-complete [hours]]")
    else:
        # Default: check pending applications
        check_pending_applications()

