// Job Applier Dashboard - Frontend JavaScript

let currentSort = 'match_score';
let currentOrder = 'desc';
let searchTimeout = null;
let savedOnlyMode = false;
let currentTab = 'new'; // 'new' or 'history'
let searchPolling = null;
let applyPolling = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    loadStats();
    loadJobs();
    checkActiveTasks();
});

// Toggle settings panel
function toggleSettings() {
    const panel = document.getElementById('settings-panel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}

// Load user settings
async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const settings = await response.json();
        
        document.getElementById('current-resume-path').textContent = settings.resume_path || 'No resume set';
        document.getElementById('setting-locations').value = (settings.locations || []).join(', ');
        document.getElementById('setting-fields').value = (settings.fields || []).join(', ');
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

// Save user settings
async function saveSettings() {
    const locations = document.getElementById('setting-locations').value.split(',').map(s => s.trim()).filter(s => s);
    const fields = document.getElementById('setting-fields').value.split(',').map(s => s.trim()).filter(s => s);
    const resume_path = document.getElementById('current-resume-path').textContent;

    const settings = {
        resume_path,
        locations,
        fields,
        last_updated: new Date().toISOString().split('T')[0]
    };

    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        showNotification('Settings saved!');
        toggleSettings();
    } catch (error) {
        console.error('Failed to save settings:', error);
        alert('Failed to save settings');
    }
}

// Handle resume selection (mocked - normally would upload, but we'll just set path for now)
function handleResumeUpload(event) {
    const file = event.target.files[0];
    if (file) {
        // In a real app we'd upload, but here we'll just show the name
        // The backend run.py logic will use the absolute path if set via CLI
        document.getElementById('current-resume-path').textContent = file.name;
        showNotification('Resume selected (Path not finalized - use CLI --set-resume for absolute path)');
    }
}

// Switch between tabs
function switchTab(tab) {
    currentTab = tab;
    
    // Update tab button states
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-tab') === tab) {
            btn.classList.add('active');
        }
    });
    
    // Update sort and filters based on tab
    if (tab === 'new') {
        currentSort = 'match_score';
        currentOrder = 'desc';
        document.getElementById('filter-score-group').style.display = 'block';
    } else {
        currentSort = 'applied_date';
        currentOrder = 'desc';
        document.getElementById('filter-score-group').style.display = 'none';
    }
    
    loadJobs();
}

// Start job search
async function startSearch() {
    try {
        const response = await fetch('/api/search/start', { method: 'POST' });
        if (!response.ok) throw new Error('Search already running');
        
        document.getElementById('btn-start-search').disabled = true;
        document.getElementById('search-progress-container').style.display = 'block';
        
        pollSearchStatus();
    } catch (error) {
        alert(error.message);
    }
}

// Poll search status
function pollSearchStatus() {
    if (searchPolling) clearInterval(searchPolling);
    
    searchPolling = setInterval(async () => {
        try {
            const response = await fetch('/api/search/status');
            const data = await response.json();
            
            const bar = document.getElementById('search-progress-bar');
            const msg = document.getElementById('search-status-msg');
            
            bar.style.width = `${data.progress}%`;
            msg.textContent = data.message;
            
            if (data.status === 'completed' || data.status === 'error') {
                clearInterval(searchPolling);
                document.getElementById('btn-start-search').disabled = false;
                if (data.status === 'completed') {
                    showNotification(data.message);
                    loadJobs();
                    loadStats();
                } else {
                    alert(data.message);
                }
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
}

// Check for active tasks on load
async function checkActiveTasks() {
    try {
        const searchRes = await fetch('/api/search/status');
        const searchData = await searchRes.json();
        if (searchData.status === 'running') {
            document.getElementById('btn-start-search').disabled = true;
            document.getElementById('search-progress-container').style.display = 'block';
            pollSearchStatus();
        }
        
        const applyRes = await fetch('/api/apply/status');
        const applyData = await applyRes.json();
        if (applyData.status === 'running') {
            openApplyModal();
            pollApplyStatus();
        }
    } catch (e) {}
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
        
        // Update badges
        document.getElementById('badge-new').textContent = data.pending || 0;
        document.getElementById('badge-history').textContent = data.applied || 0;
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// Load jobs list
async function loadJobs() {
    const tbody = document.getElementById('jobs-tbody');
    tbody.innerHTML = '<tr><td colspan="8" class="loading">Loading jobs...</td></tr>';

    try {
        const minScore = document.getElementById('filter-score').value;
        const search = document.getElementById('filter-search').value;
        
        let url = `/api/jobs?tab=${currentTab}&min_score=${minScore}&sort=${currentSort}&order=${currentOrder}`;
        if (search) url += `&search=${encodeURIComponent(search)}`;

        const response = await fetch(url);
        const data = await response.json();

        const jobs = data.jobs;

        if (!jobs || jobs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="loading">No jobs found</td></tr>';
            document.getElementById('table-info').textContent = 'Showing 0 jobs';
            return;
        }

        tbody.innerHTML = jobs.map(job => createJobRow(job)).join('');
        document.getElementById('table-info').textContent = `Showing ${jobs.length} jobs`;
        
        // Reset "Select All" checkbox
        document.getElementById('select-all-jobs').checked = false;
        updateBatchControls();
    } catch (error) {
        console.error('Failed to load jobs:', error);
        tbody.innerHTML = '<tr><td colspan="8" class="loading">Error loading jobs</td></tr>';
    }
}

// Create a table row for a job
function createJobRow(job) {
    const scoreClass = job.match_score >= 80 ? 'score-high' :
        job.match_score >= 60 ? 'score-medium' : 'score-low';

    let statusClass = 'status-pending';
    let statusText = 'Pending';
    
    if (job.application_method === 'manual') {
        statusClass = 'status-manual';
        statusText = 'Manual Required';
    } else if (job.application_method && job.application_method.includes('auto')) {
        statusClass = 'status-auto';
        statusText = 'Auto-Applied';
    } else if (job.applied) {
        statusClass = job.application_status === 'rejected' ? 'status-rejected' : 'status-applied';
        statusText = job.application_status || 'Applied';
    }

    const saveClass = job.is_saved ? 'saved' : '';
    const saveText = job.is_saved ? '⭐' : '☆';
    const hasMaterials = job.has_cover_letter || job.has_tailored_resume;

    return `
        <tr data-id="${job.id}">
            <td class="checkbox-col">
                ${!job.applied ? `<input type="checkbox" class="job-checkbox" value="${job.id}" onclick="updateBatchControls()">` : ''}
            </td>
            <td>
                <span class="score-badge ${scoreClass}">${job.match_score}</span>
            </td>
            <td>
                <strong>${escapeHtml(job.title)}</strong>
                <div style="font-size: 0.8em; color: var(--text-muted)">
                    ${job.has_cover_letter ? '<span title="Cover letter ready">📝</span> ' : ''}
                    ${job.has_tailored_resume ? '<span title="Resume tailored">📄</span> ' : ''}
                    ${job.platform || ''}
                </div>
            </td>
            <td>${escapeHtml(job.company)}</td>
            <td>${escapeHtml(job.location || 'N/A')}</td>
            <td>${job.platform || 'N/A'}</td>
            <td><span class="status-badge ${statusClass}">${statusText}</span></td>
            <td>
                <div class="action-buttons">
                    <button class="action-btn action-view" onclick="viewJob(${job.id})" title="View details">👁️</button>
                    ${hasMaterials ? `<button class="action-btn action-materials" onclick="viewMaterials(${job.id})" title="View materials">📄</button>` : ''}
                    <button class="action-btn action-save ${saveClass}" onclick="toggleSave(${job.id})" title="Save link">${saveText}</button>
                    <button class="action-btn action-copy" onclick="copyLink('${escapeHtml(job.job_url)}')" title="Copy link">📋</button>
                    ${!job.applied ? `<button class="action-btn action-reject" onclick="rejectJob(${job.id})" title="Reject">✗</button>` : ''}
                </div>
            </td>
        </tr>
    `;
}

// Batch Selection Logic
function toggleSelectAll() {
    const isChecked = document.getElementById('select-all-jobs').checked;
    document.querySelectorAll('.job-checkbox').forEach(cb => {
        cb.checked = isChecked;
    });
    updateBatchControls();
}

function updateBatchControls() {
    const selected = document.querySelectorAll('.job-checkbox:checked');
    const controls = document.getElementById('batch-controls');
    const msg = document.getElementById('selected-count-msg');
    
    if (selected.length > 0) {
        controls.style.display = 'flex';
        msg.textContent = `${selected.length} jobs selected`;
    } else {
        controls.style.display = 'none';
    }
}

// Batch Apply
async function confirmBatchApply() {
    const selected = Array.from(document.querySelectorAll('.job-checkbox:checked')).map(cb => cb.value);
    if (!confirm(`Are you sure you want to apply to ${selected.length} jobs? This will automatically generate materials and submit applications where possible.`)) return;
    
    try {
        const response = await fetch('/api/apply/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_ids: selected })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to start batch application');
        }
        
        openApplyModal();
        pollApplyStatus();
    } catch (error) {
        alert(error.message);
    }
}

function openApplyModal() {
    document.getElementById('apply-modal').classList.add('active');
    document.getElementById('btn-close-apply').style.display = 'none';
}

function closeApplyModal() {
    document.getElementById('apply-modal').classList.remove('active');
}

function pollApplyStatus() {
    if (applyPolling) clearInterval(applyPolling);
    
    applyPolling = setInterval(async () => {
        try {
            const response = await fetch('/api/apply/status');
            const data = await response.json();
            
            const bar = document.getElementById('apply-progress-bar');
            const msg = document.getElementById('apply-status-msg');
            const jobDisplay = document.getElementById('current-applying-job');
            
            bar.style.width = `${data.progress}%`;
            msg.textContent = data.message;
            jobDisplay.textContent = data.current_job ? `Current: ${data.current_job}` : '';
            
            if (data.status === 'completed' || data.status === 'error') {
                clearInterval(applyPolling);
                document.getElementById('btn-close-apply').style.display = 'block';
                loadJobs();
                loadStats();
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
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
                <div class="detail-label">URL</div>
                <div class="detail-value"><a href="${job.job_url}" target="_blank" style="color: var(--accent-primary)">${job.job_url}</a></div>
            </div>
            ${job.description ? `
            <h3 style="margin-top: 24px; margin-bottom: 12px; color: var(--text-primary);">Description</h3>
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

// Close modals on background click or escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
        closeMaterialsModal();
        closeApplyModal();
    }
});

window.onclick = function(event) {
    if (event.target.className === 'modal active') {
        event.target.classList.remove('active');
    }
}

// Toggle save/unsave a job
async function toggleSave(jobId) {
    try {
        const btn = document.querySelector(`tr[data-id="${jobId}"] .action-save`);
        const isSaved = btn.classList.contains('saved');
        const endpoint = isSaved ? `/api/jobs/${jobId}/unsave` : `/api/jobs/${jobId}/save`;

        await fetch(endpoint, { method: 'POST' });

        if (isSaved) {
            btn.classList.remove('saved');
            btn.textContent = '☆';
        } else {
            btn.classList.add('saved');
            btn.textContent = '⭐';
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
        showNotification('Link copied!');
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

// View materials
async function viewMaterials(jobId) {
    const modal = document.getElementById('materials-modal');
    const modalBody = document.getElementById('materials-modal-body');
    
    try {
        const response = await fetch(`/api/jobs/${jobId}/materials`);
        const data = await response.json();
        
        let html = '';
        if (data.cover_letter) {
            html += `<div class="materials-section"><h3>📝 Cover Letter</h3><div class="cover-letter-text">${escapeHtml(data.cover_letter).replace(/\n/g, '<br>')}</div></div>`;
        }
        if (data.tailored_resume_path) {
            html += `<div class="materials-section"><h3>📄 Tailored Resume</h3><p>${escapeHtml(data.tailored_resume_path)}</p></div>`;
        }
        
        modalBody.innerHTML = html || '<p>No materials generated yet.</p>';
        modal.classList.add('active');
    } catch (e) {
        console.error(e);
    }
}

function closeMaterialsModal() {
    document.getElementById('materials-modal').classList.remove('active');
}

function refreshDashboard() {
    loadStats();
    loadJobs();
}

function sortBy(column) {
    if (currentSort === column) {
        currentOrder = currentOrder === 'desc' ? 'asc' : 'desc';
    } else {
        currentSort = column;
        currentOrder = 'desc';
    }
    loadJobs();
}

function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(loadJobs, 300);
}

function showNotification(message) {
    const notification = document.createElement('div');
    notification.className = 'copy-notification';
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => notification.remove(), 2500);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
