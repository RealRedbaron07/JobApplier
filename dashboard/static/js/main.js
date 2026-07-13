const state = { jobs: [], profile: null, activeView: 'dashboard' };
const statuses = ['discovered','interested','resume_tailored','applied','follow_up_needed','interview','rejected','offer','archived'];

const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const fmtDate = value => value ? new Intl.DateTimeFormat('en-CA', {dateStyle:'medium'}).format(new Date(value)) : '—';
const label = value => String(value || '').replaceAll('_', ' ');

async function api(url, options = {}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json', ...(options.headers || {})}, ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function toast(message, error = false) {
  const element = document.getElementById('toast');
  element.textContent = message;
  element.style.background = error ? '#8d3935' : '';
  element.classList.add('show');
  setTimeout(() => element.classList.remove('show'), 3400);
}

function switchView(view) {
  state.activeView = view;
  document.querySelectorAll('.view').forEach(el => el.classList.toggle('active', el.id === `view-${view}`));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  document.getElementById('page-title').textContent = ({'add-job':'Add job','tracker':'Application tracker','tailor':'Resume tailor','followups':'Follow-ups','contacts':'Contacts','analytics':'Analytics','settings':'Settings & profile'})[view] || 'Dashboard';
  if (view === 'analytics') loadAnalytics();
  if (view === 'followups') loadFollowups();
  if (view === 'contacts') loadContacts();
  if (view === 'settings') loadProfile();
}

document.querySelectorAll('[data-view], [data-view-link]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.view || button.dataset.viewLink)));

async function loadJobs() {
  const data = await api('/api/jobs?limit=500');
  state.jobs = data.jobs;
  renderTracker();
  fillJobSelectors();
  return data.jobs;
}

async function loadDashboard() {
  const [analytics] = await Promise.all([api('/api/analytics'), loadJobs()]);
  const totals = analytics.totals;
  document.getElementById('metrics').innerHTML = [
    ['Tracked roles', totals.jobs, `${analytics.companies} companies`],
    ['Applications', totals.applied, `${analytics.rates.response_rate}% response rate`],
    ['Interviews', totals.interviews, `${analytics.rates.interview_rate}% interview rate`],
    ['Upcoming deadlines', analytics.upcoming_deadlines, `${analytics.stale_applications} stale applications`],
  ].map(([name,value,note]) => `<div class="metric"><small>${esc(name)}</small><strong>${esc(value)}</strong><em>${esc(note)}</em></div>`).join('');

  const priority = [...state.jobs].filter(job => ['strong_apply','apply'].includes(job.fit_category) && !['applied','rejected','archived'].includes(job.application_status)).slice(0,5);
  document.getElementById('priority-jobs').innerHTML = priority.length ? priority.map(job => `<button class="job-row" data-job="${job.id}"><span class="score">${job.match_score}</span><span class="job-copy"><strong>${esc(job.title)}</strong><small>${esc(job.company)} · ${esc(job.location)}</small></span><span class="pill">${esc(label(job.fit_category))}</span></button>`).join('') : '<div class="empty">Add a job post to build your priority queue.</div>';
  document.querySelectorAll('[data-job]').forEach(el => el.addEventListener('click', () => openJob(el.dataset.job)));
  const attention = state.jobs.filter(job => job.safety_flags?.length || job.follow_up_date || job.deadline).slice(0,5);
  document.getElementById('attention-list').innerHTML = attention.length ? attention.map(job => `<div class="attention"><i>${job.safety_flags?.length ? '!' : '→'}</i><div class="job-copy"><strong>${esc(job.company)} — ${esc(job.title)}</strong><small>${esc(job.safety_flags?.[0]?.message || (job.follow_up_date ? `Follow up ${fmtDate(job.follow_up_date)}` : `Deadline ${fmtDate(job.deadline)}`))}</small></div></div>`).join('') : '<div class="empty">No deadlines or risk flags need attention.</div>';
}

function renderTracker() {
  const search = (document.getElementById('job-search')?.value || '').toLowerCase();
  const status = document.getElementById('status-filter')?.value || 'all';
  const category = document.getElementById('category-filter')?.value || 'all';
  const rows = state.jobs.filter(job => (!search || `${job.title} ${job.company} ${job.location}`.toLowerCase().includes(search)) && (status === 'all' || job.application_status === status) && (category === 'all' || job.fit_category === category));
  document.getElementById('jobs-table').innerHTML = rows.length ? rows.map(job => `<tr>
    <td><button class="score ${job.match_score < 52 ? 'low' : ''}" data-open-job="${job.id}">${job.match_score}</button></td>
    <td class="opportunity">${esc(job.title)}<small>${esc(job.company)} · <span class="pill ${job.safety_flags?.length ? 'warn':''}">${esc(label(job.fit_category))}</span></small></td>
    <td>${esc(job.location || 'Unspecified')}<br><small>${esc(label(job.work_mode))}</small></td>
    <td><select class="status-select" data-status-job="${job.id}">${statuses.map(item => `<option value="${item}" ${item === job.application_status ? 'selected':''}>${label(item)}</option>`).join('')}</select></td>
    <td>${fmtDate(job.deadline)}</td><td class="next-action">${esc(job.next_action)}</td>
  </tr>`).join('') : '<tr><td colspan="6" class="empty">No jobs match these filters.</td></tr>';
  document.querySelectorAll('[data-open-job]').forEach(el => el.addEventListener('click', () => openJob(el.dataset.openJob)));
  document.querySelectorAll('[data-status-job]').forEach(el => el.addEventListener('change', async () => {
    try { await api(`/api/jobs/${el.dataset.statusJob}`, {method:'PATCH', body:JSON.stringify({application_status:el.value})}); toast('Status updated'); await loadDashboard(); }
    catch (error) { toast(error.message, true); await loadJobs(); }
  }));
}

function fillJobSelectors() {
  const options = '<option value="">Select a tracked job</option>' + state.jobs.map(job => `<option value="${job.id}">${esc(job.company)} — ${esc(job.title)} (${job.match_score})</option>`).join('');
  ['tailor-job','followup-job'].forEach(id => { const el = document.getElementById(id); if (el) { const current = el.value; el.innerHTML = options; el.value = current; } });
}

async function openJob(id) {
  try {
    const job = await api(`/api/jobs/${id}`);
    const explanation = job.match_explanation || {};
    document.getElementById('job-detail').innerHTML = `<div class="detail-head"><p class="eyebrow">${esc(label(job.fit_category))} · ${job.match_score}/100</p><h2>${esc(job.title)}</h2><p>${esc(job.company)} · ${esc(job.location)} · ${esc(label(job.work_mode))}</p></div>
      ${job.safety_flags.map(flag => `<div class="warning-flag"><strong>${esc(flag.code)}</strong> — ${esc(flag.message)}</div>`).join('')}
      <div class="detail-actions"><button class="button" data-prepare="${job.id}">Prepare package</button><button class="button secondary" data-tailor="${job.id}">Resume suggestions</button><button class="button secondary" data-answers="${job.id}">Draft answers</button>${job.job_url ? `<a class="button dark" href="${esc(job.job_url)}" target="_blank" rel="noopener">Open official application ↗</a>`:''}</div>
      <div class="detail-columns"><div class="detail-card"><h4>Why it fits</h4><ul class="compact-list">${(explanation.why_it_fits || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><h4>Matched skills</h4><p>${(explanation.matched_skills || []).map(x => `<span class="pill">${esc(x)}</span>`).join(' ') || 'None detected'}</p></div><div class="detail-card"><h4>Risks & missing skills</h4><ul class="compact-list">${(explanation.risks || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><p><strong>Resume:</strong> ${esc(job.resume_profile)}</p><p><strong>Project:</strong> ${esc(job.suggested_project)}</p></div></div>
      <div class="detail-columns"><div class="detail-card"><h4>Application checklist</h4><ul class="compact-list"><li>Verify eligibility, dates, and location</li><li>Review every generated claim</li><li>Prepare: ${esc((job.required_documents || []).join(', ') || 'resume')}</li><li>Submit manually</li><li>Mark applied here afterwards</li></ul><p><strong>Start:</strong> ${esc(job.start_date || 'Unspecified')} · <strong>Term:</strong> ${esc(job.term_length || 'Unspecified')}</p></div><div class="detail-card"><label>Private notes<textarea id="detail-notes" rows="6">${esc(job.notes)}</textarea></label><button class="button secondary small" data-save-notes="${job.id}">Save notes</button></div></div>
      <h4>Posting</h4><div class="description">${esc(job.description)}</div>`;
    const dialog = document.getElementById('job-dialog'); dialog.showModal();
    document.querySelector('[data-prepare]')?.addEventListener('click', () => runDraftAction(id, 'prepare'));
    document.querySelector('[data-tailor]')?.addEventListener('click', () => runDraftAction(id, 'tailor'));
    document.querySelector('[data-answers]')?.addEventListener('click', () => runDraftAction(id, 'answers'));
    document.querySelector('[data-save-notes]')?.addEventListener('click', async () => { await api(`/api/jobs/${id}`, {method:'PATCH', body:JSON.stringify({notes:document.getElementById('detail-notes').value})}); toast('Notes saved locally'); });
  } catch (error) { toast(error.message, true); }
}

document.querySelector('.dialog-close').addEventListener('click', () => document.getElementById('job-dialog').close());

async function jobFormPayload(form) {
  return Object.fromEntries(new FormData(form).entries());
}

document.getElementById('preview-job').addEventListener('click', async () => {
  try {
    const payload = await jobFormPayload(document.getElementById('job-form'));
    const data = await api('/api/jobs/parse', {method:'POST', body:JSON.stringify(payload)});
    const score = data.score;
    document.getElementById('parse-preview').innerHTML = `<div class="preview-score"><strong>${score.overall_score}</strong><span>/ 100</span><p><span class="pill">${esc(label(score.category))}</span></p></div><h4>Matched</h4><p>${score.matched_skills.map(x => `<span class="pill">${esc(x)}</span>`).join(' ') || 'No explicit matches detected yet.'}</p><h4>Missing / unverified</h4><ul class="compact-list">${score.missing_skills.map(x => `<li>${esc(x)}</li>`).join('') || '<li>None detected</li>'}</ul><h4>Strategy</h4><p>${esc(score.strategy)}</p>${score.safety_flags.map(flag => `<div class="warning-flag">${esc(flag.message)}</div>`).join('')}`;
  } catch (error) { toast(error.message, true); }
});

document.getElementById('job-form').addEventListener('submit', async event => {
  event.preventDefault();
  try { const payload = await jobFormPayload(event.target); const data = await api('/api/jobs', {method:'POST', body:JSON.stringify(payload)}); toast(`${data.job.match_score}/100 — ${label(data.job.fit_category)}`); event.target.reset(); await loadDashboard(); switchView('tracker'); }
  catch (error) { toast(error.message, true); }
});

document.getElementById('csv-file').addEventListener('change', async event => {
  if (!event.target.files[0]) return;
  const form = new FormData(); form.append('file', event.target.files[0]);
  try { const response = await fetch('/api/import/csv', {method:'POST', body:form}); const data = await response.json(); if (!response.ok) throw new Error(data.error); toast(`${data.created} jobs imported; ${data.skipped_duplicates} duplicates skipped`); await loadDashboard(); }
  catch (error) { toast(error.message, true); }
});

['job-search','status-filter','category-filter'].forEach(id => document.getElementById(id).addEventListener(id === 'job-search' ? 'input' : 'change', renderTracker));
document.getElementById('status-filter').innerHTML = '<option value="all">All statuses</option>' + statuses.map(item => `<option value="${item}">${label(item)}</option>`).join('');

function renderTailoring(data, kind) {
  const target = document.getElementById('tailor-result');
  if (kind === 'answers') {
    target.innerHTML = Object.entries(data.answers).map(([key,value]) => `<div class="result-section"><h4>${esc(label(key))}</h4><textarea rows="5">${esc(value)}</textarea></div>`).join('') + '<div class="warning-note">These are drafts. Copy only after editing and verifying the job/company-specific details.</div>';
    return;
  }
  const plan = data.plan || data.tailoring;
  target.innerHTML = `<div class="result-section"><p class="eyebrow">${esc(plan.resume_profile)}</p><h3>Tailoring plan</h3><p><strong>Project:</strong> ${esc(plan.project_to_emphasize.name)}</p><p><strong>Skills to move higher:</strong> ${plan.skills_to_move_higher.map(x => `<span class="pill">${esc(x)}</span>`).join(' ')}</p></div>
    <div class="result-section"><h4>Keyword gaps</h4><p>${plan.keyword_gaps.map(x => `<span class="pill warn">${esc(x)}</span>`).join(' ') || 'No explicit gaps detected.'}</p><small>${esc(plan.keyword_gap_rule)}</small></div>
    ${plan.experience_suggestions.map(item => `<div class="result-section"><h4>${esc(item.experience)}</h4><ul class="compact-list">${item.suggested_bullets.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`).join('')}
    <div class="result-section"><h4>One-page estimate</h4><p class="${plan.one_page_check.passes_estimate ? 'success-flag':'warning-flag'}">${plan.one_page_check.estimated_lines} estimated lines / ${plan.one_page_check.limit} line target</p></div>
    ${data.latex_path || plan.latex_path ? `<div class="result-section"><h4>LaTeX draft</h4><div class="code-path">${esc(data.latex_path || plan.latex_path)}</div></div>`:''}
    <div class="warning-note">${esc(plan.base_resume_warning)} Human review is required.</div>`;
}

async function runDraftAction(jobId, action) {
  if (!jobId) return toast('Choose a tracked job first', true);
  try {
    const payload = action === 'tailor' ? {resume_profile:document.getElementById('resume-profile').value} : {};
    const data = await api(`/api/jobs/${jobId}/${action}`, {method:'POST', body:JSON.stringify(payload)});
    renderTailoring(data, action);
    document.getElementById('job-dialog').open && document.getElementById('job-dialog').close();
    switchView('tailor'); toast(data.message); await loadJobs();
  } catch (error) { toast(error.message, true); }
}

document.getElementById('generate-tailor').addEventListener('click', () => runDraftAction(document.getElementById('tailor-job').value, 'tailor'));
document.getElementById('generate-answers').addEventListener('click', () => runDraftAction(document.getElementById('tailor-job').value, 'answers'));
document.getElementById('prepare-package').addEventListener('click', () => runDraftAction(document.getElementById('tailor-job').value, 'prepare'));
document.getElementById('tailor-job').addEventListener('change', event => { const job = state.jobs.find(item => String(item.id) === event.target.value); if (job) document.getElementById('resume-profile').value = job.resume_profile; });

async function loadFollowups() {
  const data = await api('/api/follow-ups');
  document.getElementById('followup-list').innerHTML = data.follow_ups.length ? data.follow_ups.map(item => `<div class="follow-row"><div class="job-copy"><strong>${esc(label(item.type))}</strong><small>${fmtDate(item.due_date)} · ${esc(item.status)}</small>${item.message_draft ? `<p>${esc(item.message_draft)}</p>`:''}</div><span class="pill">${esc(item.status)}</span></div>`).join('') : '<div class="empty">No follow-up reminders yet.</div>';
}
document.getElementById('followup-form').addEventListener('submit', async event => { event.preventDefault(); const payload = Object.fromEntries(new FormData(event.target)); if (payload.job_id) payload.job_id = Number(payload.job_id); try { await api('/api/follow-ups', {method:'POST', body:JSON.stringify(payload)}); toast('Reminder created; nothing will be sent automatically'); event.target.reset(); await loadFollowups(); } catch(error){toast(error.message,true);} });

async function loadContacts() {
  const data = await api('/api/contacts');
  document.getElementById('contact-list').innerHTML = data.contacts.length ? data.contacts.map(contact => `<div><div class="contact-row"><div class="job-copy"><strong>${esc(contact.name)}</strong><small>${esc(contact.company || '')} · ${esc(contact.role || '')}<br>${esc(contact.email || contact.linkedin || '')}</small></div><button class="button secondary small" data-contact-message="${contact.id}">Draft note</button></div><div id="contact-message-${contact.id}"></div></div>`).join('') : '<div class="empty">Add a recruiter, teammate, or referral contact.</div>';
  document.querySelectorAll('[data-contact-message]').forEach(button => button.addEventListener('click', async () => {
    try { const data = await api(`/api/contacts/${button.dataset.contactMessage}/message`, {method:'POST', body:JSON.stringify({kind:'coffee_chat'})}); document.getElementById(`contact-message-${button.dataset.contactMessage}`).innerHTML = `<textarea rows="5">${esc(data.message)}</textarea><small>Draft only — edit and send manually.</small>`; }
    catch(error){ toast(error.message,true); }
  }));
}
document.getElementById('contact-form').addEventListener('submit', async event => { event.preventDefault(); try { await api('/api/contacts',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(event.target))) }); toast('Contact saved locally'); event.target.reset(); await loadContacts(); } catch(error){toast(error.message,true);} });

async function loadAnalytics() {
  const data = await api('/api/analytics');
  const maxFunnel = Math.max(1, ...data.funnel.map(item => item.count));
  document.getElementById('analytics-content').innerHTML = `<div class="analytics-grid"><div class="analytics-card"><small>Response rate</small><br><strong>${data.rates.response_rate}%</strong></div><div class="analytics-card"><small>Interview rate</small><br><strong>${data.rates.interview_rate}%</strong></div><div class="analytics-card"><small>Rejection rate</small><br><strong>${data.rates.rejection_rate}%</strong></div><div class="analytics-card"><h3>Conversion funnel</h3>${data.funnel.map(item => `<div class="bar-row"><span>${esc(label(item.status))}</span><span class="bar"><i style="width:${item.count/maxFunnel*100}%"></i></span><b>${item.count}</b></div>`).join('')}</div><div class="analytics-card"><h3>Top missing skills</h3>${data.top_missing_skills.map(([name,count]) => `<div class="bar-row"><span>${esc(name)}</span><span class="bar"><i style="width:${Math.min(100,count*15)}%"></i></span><b>${count}</b></div>`).join('') || '<p class="empty">No scored gaps yet.</p>'}</div><div class="analytics-card"><h3>Best sources</h3>${data.best_sources.map(([name,count]) => `<div class="bar-row"><span>${esc(name)}</span><span class="bar"><i style="width:${Math.min(100,count*15)}%"></i></span><b>${count}</b></div>`).join('') || '<p class="empty">No source data yet.</p>'}</div><div class="analytics-card"><h3>Applications per week</h3>${data.applications_per_week.map(([week,count]) => `<div class="bar-row"><span>${esc(week)}</span><span class="bar"><i style="width:${Math.min(100,count*15)}%"></i></span><b>${count}</b></div>`).join('') || '<p class="empty">No weekly data yet.</p>'}</div><div class="analytics-card"><h3>Role categories</h3>${data.best_role_categories.map(([name,count]) => `<div class="bar-row"><span>${esc(label(name))}</span><span class="bar"><i style="width:${Math.min(100,count*15)}%"></i></span><b>${count}</b></div>`).join('') || '<p class="empty">No categories yet.</p>'}</div></div>`;
}

async function loadProfile() {
  const profile = await api('/api/profile'); state.profile = profile;
  const form = document.getElementById('profile-form');
  ['name','graduation','email','phone','location','availability','automation_level'].forEach(key => { if (form.elements[key]) form.elements[key].value = profile[key] ?? ''; });
  form.elements.target_locations.value = (profile.target_locations || []).join(', ');
}
document.getElementById('profile-form').addEventListener('submit', async event => { event.preventDefault(); const payload = Object.fromEntries(new FormData(event.target)); payload.automation_level = Number(payload.automation_level); payload.target_locations = payload.target_locations.split(',').map(x => x.trim()).filter(Boolean); try { const data = await api('/api/profile',{method:'PUT',body:JSON.stringify(payload)}); state.profile=data.profile; toast('Profile saved to local private data'); } catch(error){toast(error.message,true);} });

document.getElementById('seed-demo').addEventListener('click', async () => { try { const data=await api('/api/seed-demo',{method:'POST'}); toast(data.message); await loadDashboard(); } catch(error){toast(error.message,true);} });

loadDashboard().catch(error => toast(error.message, true));
