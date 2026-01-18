// Job Applier Dashboard - Frontend JavaScript

let currentSort = 'match_score';
let currentOrder = 'desc';
let searchTimeout = null;
let savedOnlyMode = false;
let currentTab = 'new-matches'; // 'new-matches' or 'history'

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadJobs();
});

// Switch between tabs
function switchTab(tab) {
    currentTab = tab;
    
    // Update tab button states
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    
    // Update sort and filters based on tab
    if (tab === 'new-matches') {
        currentSort = 'match_score';
        currentOrder = 'desc';
        document.getElementById('filter-score-group').style.display = 'block';
    } else if (tab === 'history') {
        currentSort = 'applied_date';
        currentOrder = 'desc';
        document.getElementById('filter-score-group').style.display = 'none';
    }
    
    loadJobs();
}

// Load dashboard statistics
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const data = await response.json();

        document.querySelector('#stat-total .stat-value').textContent = data.total_jobs || 0;
        document.querySelector('#stat-applied .stat-value').textContent = data.applied || 0;
        document.querySelector('#stat-pending .stat-value').textContent = data.pending || 0;
        document.querySelector('#stat-saved .stat-value').textContent = data.saved || 0;
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// Load jobs list
async function loadJobs() {
    const tbody = document.getElementById('jobs-tbody');
    tbody.innerHTML = '<tr><td colspan="7" class="loading">Loading jobs...</td></tr>';

    try {
        const minScore = document.getElementById('filter-score').value;
        const search = document.getElementById('filter-search').value;
        
        const tab = currentTab === 'new-matches' ? 'new' : 'history';

        let url = `/api/jobs?tab=${tab}&min_score=${minScore}&sort=${currentSort}&order=${currentOrder}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;

        if (savedOnlyMode) {
            url = '/api/saved';
        }

        const response = await fetch(url);
        const data = await response.json();

        let jobs = savedOnlyMode ? data.saved : data.jobs;

        if (!jobs || jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="loading">No jobs found</td></tr>';
            return;
        }

        tbody.innerHTML = jobs.map(job => createJobRow(job)).join('');
    } catch (error) {
        console.error('Failed to load jobs:', error);
        tbody.innerHTML = '<tr><td colspan="7" class="loading">Error loading jobs</td></tr>';
    }
}

// Create a table row for a job
function createJobRow(job) {
    const scoreClass = job.match_score >= 80 ? 'score-high' :
        job.match_score >= 60 ? 'score-medium' : 'score-low';

    // Determine status badge based on application_method
    let statusClass = 'status-pending';
    let statusText = 'Pending';
    
    if (job.application_method === 'manual') {
        statusClass = 'status-manual';
        statusText = 'Ready for Manual Apply';
    } else if (job.application_method && job.application_method.includes('auto')) {
        statusClass = 'status-auto';
        statusText = 'Auto-Applied';
    } else if (job.applied) {
        statusClass = job.application_status === 'rejected' ? 'status-rejected' : 'status-applied';
        statusText = job.application_status || 'Applied';
    }

    const saveClass = job.is_saved ? 'saved' : '';
    const saveText = job.is_saved ? '⭐ Saved' : '☆ Save';
    
    // Show materials button if job has cover letter or resume
    const hasMaterials = job.has_cover_letter || job.has_tailored_resume;

    return `
        <tr data-id="${job.id || job.job_id}">
            <td>
                <span class="score-badge ${scoreClass}">${job.match_score}</span>
            </td>
            <td>
                <strong>${escapeHtml(job.title)}</strong>
                ${job.has_cover_letter ? '<span title="Cover letter ready">📝</span>' : ''}
                ${job.has_tailored_resume ? '<span title="Resume tailored">📄</span>' : ''}
            </td>
            <td>${escapeHtml(job.company)}</td>
            <td>${escapeHtml(job.location || 'N/A')}</td>
            <td>${escapeHtml(job.platform || 'N/A')}</td>
            <td><span class="status-badge ${statusClass}">${statusText}</span></td>
            <td>
                <div class="action-buttons">
                    <button class="action-btn action-view" onclick="viewJob(${job.id || job.job_id})" title="View details">👁️</button>
                    ${hasMaterials ? `<button class="action-btn action-materials" onclick="viewMaterials(${job.id || job.job_id})" title="View materials">📄</button>` : ''}
                    <button class="action-btn action-save ${saveClass}" onclick="toggleSave(${job.id || job.job_id})" title="Save link">${saveText}</button>
                    <button class="action-btn action-copy" onclick="copyLink('${escapeHtml(job.job_url)}')" title="Copy link">📋</button>
                    ${!job.applied ? `<button class="action-btn action-reject" onclick="rejectJob(${job.id || job.job_id})" title="Reject">✗</button>` : ''}
                </div>
            </td>
        </tr>
    `;
}

// View job details in modal
async function viewJob(jobId) {
    const modal = document.getElementById('job-modal');
    const modalBody = document.getElementById('modal-body');
    const modalTitle = document.getElementById('modal-title');

    try {
        const response = await fetch(`/api/jobs/${jobId}`);
        const job = await response.json();

        modalTitle.textContent = job.title;

        modalBody.innerHTML = `
            <div class="detail-row">
                <div class="detail-label">Company</div>
                <div class="detail-value">${escapeHtml(job.company)}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Location</div>
                <div class="detail-value">${escapeHtml(job.location || 'N/A')}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Platform</div>
                <div class="detail-value">${escapeHtml(job.platform || 'N/A')}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Match Score</div>
                <div class="detail-value"><span class="score-badge ${job.match_score >= 80 ? 'score-high' : job.match_score >= 60 ? 'score-medium' : 'score-low'}">${job.match_score}/100</span></div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Status</div>
                <div class="detail-value">${job.application_status || (job.applied ? 'Applied' : 'Pending')}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Discovered</div>
                <div class="detail-value">${job.discovered_date || 'N/A'}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">URL</div>
                <div class="detail-value"><a href="${job.job_url}" target="_blank" style="color: var(--accent-primary)">${job.job_url}</a></div>
            </div>
            ${job.cover_letter_path ? `
            <div class="detail-row">
                <div class="detail-label">Cover Letter</div>
                <div class="detail-value">✓ ${escapeHtml(job.cover_letter_path)}</div>
            </div>
            ` : ''}
            ${job.tailored_resume_path ? `
            <div class="detail-row">
                <div class="detail-label">Resume</div>
                <div class="detail-value">✓ ${escapeHtml(job.tailored_resume_path)}</div>
            </div>
            ` : ''}
            ${job.description ? `
            <h3 style="margin-top: 24px; margin-bottom: 12px;">Description</h3>
            <div class="detail-description">${escapeHtml(job.description)}</div>
            ` : ''}
        `;

        modal.classList.add('active');
    } catch (error) {
        console.error('Failed to load job details:', error);
    }
}

// Close modal
function closeModal() {
    document.getElementById('job-modal').classList.remove('active');
}

// Close modal on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
        closeMaterialsModal();
    }
});

// Close modal on background click
document.getElementById('job-modal').addEventListener('click', (e) => {
    if (e.target.id === 'job-modal') closeModal();
});

// Close materials modal on background click
document.getElementById('materials-modal').addEventListener('click', (e) => {
    if (e.target.id === 'materials-modal') closeMaterialsModal();
});

// Toggle save/unsave a job
async function toggleSave(jobId) {
    try {
        // Check current state from the button
        const btn = document.querySelector(`tr[data-id="${jobId}"] .action-save`);
        const isSaved = btn.classList.contains('saved');

        const endpoint = isSaved ? `/api/jobs/${jobId}/unsave` : `/api/jobs/${jobId}/save`;

        await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        // Update UI
        if (isSaved) {
            btn.classList.remove('saved');
            btn.textContent = '☆ Save';
        } else {
            btn.classList.add('saved');
            btn.textContent = '⭐ Saved';
        }

        loadStats();
    } catch (error) {
        console.error('Failed to toggle save:', error);
    }
}

// Copy link to clipboard
async function copyLink(url) {
    try {
        await navigator.clipboard.writeText(url);
        showNotification('Link copied to clipboard!');
    } catch (error) {
        console.error('Failed to copy:', error);
    }
}

// Reject a job
async function rejectJob(jobId) {
    if (!confirm('Mark this job as rejected?')) return;

    try {
        await fetch(`/api/jobs/${jobId}/reject`, { method: 'POST' });
        loadJobs();
        loadStats();
    } catch (error) {
        console.error('Failed to reject job:', error);
    }
}

// View application materials in modal
async function viewMaterials(jobId) {
    const modal = document.getElementById('materials-modal');
    const modalBody = document.getElementById('materials-modal-body');
    const modalTitle = document.getElementById('materials-modal-title');

    try {
        const response = await fetch(`/api/jobs/${jobId}/materials`);
        const data = await response.json();

        modalTitle.textContent = 'Application Materials';

        let materialsHtml = '';
        
        if (data.cover_letter) {
            materialsHtml += `
                <div class="materials-section">
                    <h3>📝 Cover Letter</h3>
                    <div class="cover-letter-text">${escapeHtml(data.cover_letter).replace(/\n/g, '<br>')}</div>
                </div>
            `;
        }
        
        if (data.cover_letter_path) {
            materialsHtml += `
                <div class="materials-section">
                    <h3>📄 Cover Letter File</h3>
                    <p>${escapeHtml(data.cover_letter_path)}</p>
                </div>
            `;
        }
        
        if (data.tailored_resume_path) {
            materialsHtml += `
                <div class="materials-section">
                    <h3>📄 Tailored Resume</h3>
                    <p>${escapeHtml(data.tailored_resume_path)}</p>
                </div>
            `;
        }
        
        if (!materialsHtml) {
            materialsHtml = '<p>No materials available for this job.</p>';
        }

        modalBody.innerHTML = materialsHtml;
        modal.classList.add('active');
    } catch (error) {
        console.error('Failed to load materials:', error);
        modalBody.innerHTML = '<p>Error loading materials.</p>';
        modal.classList.add('active');
    }
}

// Close materials modal
function closeMaterialsModal() {
    document.getElementById('materials-modal').classList.remove('active');
}

// Show notification
function showNotification(message) {
    const notification = document.createElement('div');
    notification.className = 'copy-notification';
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => notification.remove(), 2000);
}

// Sort by column
function sortBy(column) {
    if (currentSort === column) {
        currentOrder = currentOrder === 'desc' ? 'asc' : 'desc';
    } else {
        currentSort = column;
        currentOrder = 'desc';
    }
    loadJobs();
}

// Debounce search input
function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(loadJobs, 300);
}

// Show saved jobs only
function showSavedOnly() {
    savedOnlyMode = !savedOnlyMode;
    const btn = document.querySelector('.filters-section .btn-secondary:last-child');
    btn.textContent = savedOnlyMode ? '📋 Show All' : '⭐ Saved Only';
    loadJobs();
}

// Export jobs
function exportJobs(format) {
    const status = document.getElementById('filter-status').value;
    window.open(`/api/export?format=${format}&status=${status}&saved_only=${savedOnlyMode}`, '_blank');
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
