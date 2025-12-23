#!/usr/bin/env python3
"""
Web Dashboard for Job Applier.
Provides a visual interface to view, manage, and apply to jobs.
"""

import os
import sys
import json
import csv
from io import StringIO
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import Session, Job, UserProfile, ApplicationRecord, SavedLink
from config import Config
from sqlalchemy import desc, or_

app = Flask(__name__)


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@app.route('/api/stats')
def get_stats():
    """Get dashboard statistics."""
    if Session is None:
        return jsonify({'error': 'Database not initialized'}), 500
    
    session = Session()
    try:
        total_jobs = session.query(Job).count()
        applied = session.query(Job).filter_by(applied=True).filter(Job.application_status != 'rejected').count()
        pending = session.query(Job).filter_by(applied=False).filter(Job.match_score >= Config.MIN_MATCH_SCORE).count()
        rejected = session.query(Job).filter_by(application_status='rejected').count()
        saved = session.query(SavedLink).count()
        
        # Average match score
        avg_score = session.query(Job).with_entities(
            db_func.avg(Job.match_score)
        ).scalar() or 0
        
        return jsonify({
            'total_jobs': total_jobs,
            'applied': applied,
            'pending': pending,
            'rejected': rejected,
            'saved': saved,
            'avg_score': round(avg_score, 1)
        })
    except Exception as e:
        return jsonify({
            'total_jobs': 0,
            'applied': 0,
            'pending': 0,
            'rejected': 0,
            'saved': 0,
            'avg_score': 0
        })
    finally:
        session.close()


@app.route('/api/jobs')
def get_jobs():
    """Get jobs list with optional filtering."""
    if Session is None:
        return jsonify({'error': 'Database not initialized'}), 500
    
    session = Session()
    try:
        # Get filter parameters
        status = request.args.get('status', 'all')
        min_score = int(request.args.get('min_score', 0))
        search = request.args.get('search', '').lower()
        sort_by = request.args.get('sort', 'match_score')
        order = request.args.get('order', 'desc')
        limit = int(request.args.get('limit', 100))
        
        # Base query
        query = session.query(Job)
        
        # Apply filters
        if status == 'applied':
            query = query.filter_by(applied=True)
        elif status == 'pending':
            query = query.filter_by(applied=False)
        elif status == 'rejected':
            query = query.filter_by(application_status='rejected')
        
        if min_score > 0:
            query = query.filter(Job.match_score >= min_score)
        
        if search:
            query = query.filter(
                or_(
                    Job.title.ilike(f'%{search}%'),
                    Job.company.ilike(f'%{search}%'),
                    Job.location.ilike(f'%{search}%')
                )
            )
        
        # Apply sorting
        sort_column = getattr(Job, sort_by, Job.match_score)
        if order == 'desc':
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(sort_column)
        
        # Limit results
        jobs = query.limit(limit).all()
        
        # Convert to JSON-serializable format
        result = []
        for job in jobs:
            # Check if job is saved
            is_saved = session.query(SavedLink).filter_by(job_id=job.id).first() is not None
            
            result.append({
                'id': job.id,
                'title': job.title,
                'company': job.company,
                'location': job.location or 'N/A',
                'platform': job.platform or 'N/A',
                'job_url': job.job_url,
                'match_score': job.match_score or 0,
                'applied': job.applied,
                'application_status': job.application_status or ('Applied' if job.applied else 'Pending'),
                'discovered_date': job.discovered_date.strftime('%Y-%m-%d') if job.discovered_date else 'N/A',
                'has_cover_letter': bool(job.cover_letter_path),
                'has_tailored_resume': bool(job.tailored_resume_path),
                'is_saved': is_saved
            })
        
        return jsonify({'jobs': result, 'count': len(result)})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/jobs/<int:job_id>')
def get_job_details(job_id):
    """Get detailed information about a specific job."""
    if Session is None:
        return jsonify({'error': 'Database not initialized'}), 500
    
    session = Session()
    try:
        job = session.query(Job).get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Get application records
        app_records = session.query(ApplicationRecord).filter_by(job_id=job_id).all()
        
        return jsonify({
            'id': job.id,
            'title': job.title,
            'company': job.company,
            'location': job.location,
            'platform': job.platform,
            'job_url': job.job_url,
            'description': job.description or '',
            'requirements': job.requirements or '',
            'match_score': job.match_score,
            'applied': job.applied,
            'applied_date': job.applied_date.strftime('%Y-%m-%d %H:%M') if job.applied_date else None,
            'application_status': job.application_status,
            'cover_letter': job.cover_letter,
            'cover_letter_path': job.cover_letter_path,
            'tailored_resume_path': job.tailored_resume_path,
            'notes': job.notes,
            'discovered_date': job.discovered_date.strftime('%Y-%m-%d %H:%M') if job.discovered_date else None,
            'applications': [{
                'date': r.application_date.strftime('%Y-%m-%d %H:%M') if r.application_date else None,
                'method': r.application_method,
                'status': r.application_status,
                'notes': r.notes
            } for r in app_records]
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/jobs/<int:job_id>/save', methods=['POST'])
def save_job(job_id):
    """Save/bookmark a job link."""
    if Session is None:
        return jsonify({'error': 'Database not initialized'}), 500
    
    session = Session()
    try:
        job = session.query(Job).get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Check if already saved
        existing = session.query(SavedLink).filter_by(job_id=job_id).first()
        if existing:
            return jsonify({'message': 'Job already saved', 'id': existing.id})
        
        # Get optional data from request
        data = request.get_json() or {}
        
        saved_link = SavedLink(
            job_id=job_id,
            notes=data.get('notes', ''),
            category=data.get('category', 'interesting')
        )
        session.add(saved_link)
        session.commit()
        
        return jsonify({'message': 'Job saved successfully', 'id': saved_link.id})
    
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/jobs/<int:job_id>/unsave', methods=['POST'])
def unsave_job(job_id):
    """Remove a saved job link."""
    if Session is None:
        return jsonify({'error': 'Database not initialized'}), 500
    
    session = Session()
    try:
        saved = session.query(SavedLink).filter_by(job_id=job_id).first()
        if saved:
            session.delete(saved)
            session.commit()
            return jsonify({'message': 'Job unsaved'})
        return jsonify({'message': 'Job was not saved'})
    
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/saved')
def get_saved_jobs():
    """Get all saved job links."""
    if Session is None:
        return jsonify({'error': 'Database not initialized'}), 500
    
    session = Session()
    try:
        saved_links = session.query(SavedLink).order_by(desc(SavedLink.saved_date)).all()
        
        result = []
        for link in saved_links:
            job = session.query(Job).get(link.job_id)
            if job:
                result.append({
                    'id': link.id,
                    'job_id': job.id,
                    'title': job.title,
                    'company': job.company,
                    'location': job.location,
                    'job_url': job.job_url,
                    'match_score': job.match_score,
                    'saved_date': link.saved_date.strftime('%Y-%m-%d'),
                    'notes': link.notes,
                    'category': link.category
                })
        
        return jsonify({'saved': result, 'count': len(result)})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/export')
def export_jobs():
    """Export jobs as CSV or JSON."""
    if Session is None:
        return jsonify({'error': 'Database not initialized'}), 500
    
    format_type = request.args.get('format', 'csv')
    status = request.args.get('status', 'all')
    saved_only = request.args.get('saved_only', 'false').lower() == 'true'
    
    session = Session()
    try:
        if saved_only:
            # Get saved jobs
            saved_links = session.query(SavedLink).all()
            job_ids = [link.job_id for link in saved_links]
            jobs = session.query(Job).filter(Job.id.in_(job_ids)).all()
        else:
            query = session.query(Job)
            if status == 'applied':
                query = query.filter_by(applied=True)
            elif status == 'pending':
                query = query.filter_by(applied=False)
            jobs = query.order_by(desc(Job.match_score)).all()
        
        if format_type == 'json':
            data = [{
                'title': job.title,
                'company': job.company,
                'location': job.location,
                'url': job.job_url,
                'match_score': job.match_score,
                'status': job.application_status or ('Applied' if job.applied else 'Pending'),
                'discovered_date': job.discovered_date.strftime('%Y-%m-%d') if job.discovered_date else None
            } for job in jobs]
            
            return Response(
                json.dumps(data, indent=2),
                mimetype='application/json',
                headers={'Content-Disposition': 'attachment; filename=jobs_export.json'}
            )
        else:
            # CSV format
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['Title', 'Company', 'Location', 'URL', 'Match Score', 'Status', 'Discovered Date'])
            
            for job in jobs:
                writer.writerow([
                    job.title,
                    job.company,
                    job.location,
                    job.job_url,
                    job.match_score,
                    job.application_status or ('Applied' if job.applied else 'Pending'),
                    job.discovered_date.strftime('%Y-%m-%d') if job.discovered_date else ''
                ])
            
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=jobs_export.csv'}
            )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@app.route('/api/jobs/<int:job_id>/reject', methods=['POST'])
def reject_job(job_id):
    """Mark a job as rejected (not interested)."""
    if Session is None:
        return jsonify({'error': 'Database not initialized'}), 500
    
    session = Session()
    try:
        job = session.query(Job).get(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        job.applied = True  # Mark as processed
        job.application_status = 'rejected'
        job.notes = (job.notes or '') + f"\n[Rejected via dashboard on {datetime.now().strftime('%Y-%m-%d %H:%M')}]"
        session.commit()
        
        return jsonify({'message': 'Job rejected'})
    
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🖥️  Job Applier Dashboard")
    print("=" * 60)
    print(f"Open in browser: http://{Config.DASHBOARD_HOST}:{Config.DASHBOARD_PORT}")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    app.run(
        host=Config.DASHBOARD_HOST,
        port=Config.DASHBOARD_PORT,
        debug=True
    )
