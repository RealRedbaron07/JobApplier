const state = { jobs: [], contacts: [], profile: null, activeView: 'dashboard' };
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
  element.setAttribute('role', error ? 'alert' : 'status');
  element.style.background = error ? '#8d3935' : '';
  element.classList.add('show');
  setTimeout(() => element.classList.remove('show'), 3400);
}

function setAutomationLevel(level) {
  const badge = document.getElementById('automation-level-badge');
  if (badge) badge.textContent = `Automation level ${level} / 4`;
  const requirements = {'preview-job':1, 'generate-tailor':2, 'generate-answers':2, 'prepare-package':3, 'guided-handoff':4};
  Object.entries(requirements).forEach(([id, required]) => {
    const control = document.getElementById(id);
    if (!control) return;
    control.disabled = level < required;
    control.title = level < required ? `Requires automation level ${required}` : '';
  });
  const submit = document.getElementById('add-job-submit');
  if (submit) submit.textContent = level >= 1 ? 'Add & score job' : 'Add job for tracking';
}

function switchView(view) {
  state.activeView = view;
  document.querySelectorAll('.view').forEach(el => el.classList.toggle('active', el.id === `view-${view}`));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  document.getElementById('page-title').textContent = ({'add-job':'Add job','tracker':'Application tracker','tailor':'Resume tailor','followups':'Follow-ups','contacts':'Contacts','analytics':'Analytics','settings':'Settings & profile'})[view] || 'Dashboard';
  if (view === 'analytics') loadAnalytics();
  if (view === 'followups') Promise.all([loadFollowups(), loadContacts()]);
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
    <td><select class="status-select" data-status-job="${job.id}">${(job.allowed_statuses || statuses).map(item => `<option value="${item}" ${item === job.application_status ? 'selected':''}>${label(item)}</option>`).join('')}</select></td>
    <td>${fmtDate(job.deadline)}</td><td class="next-action">${esc(job.next_action)}</td>
  </tr>`).join('') : '<tr><td colspan="6" class="empty">No jobs match these filters.</td></tr>';
  document.querySelectorAll('[data-open-job]').forEach(el => el.addEventListener('click', () => openJob(el.dataset.openJob)));
  document.querySelectorAll('[data-status-job]').forEach(el => el.addEventListener('change', async () => {
    const previous = state.jobs.find(job => String(job.id) === el.dataset.statusJob)?.application_status;
    const payload = {application_status:el.value};
    if (el.value === 'applied' && previous !== 'applied') {
      const confirmed = window.confirm('Confirm only if you personally submitted this application on the official portal. Mark as applied?');
      if (!confirmed) { el.value = previous; return; }
      payload.confirm_submission = true;
    }
    try { await api(`/api/jobs/${el.dataset.statusJob}`, {method:'PATCH', body:JSON.stringify(payload)}); toast('Status updated'); await loadDashboard(); }
    catch (error) { toast(error.message, true); await loadJobs(); }
  }));
}

function fillJobSelectors() {
  const options = '<option value="">Select a tracked job</option>' + state.jobs.map(job => `<option value="${job.id}">${esc(job.company)} — ${esc(job.title)} (${job.match_score})</option>`).join('');
  ['tailor-job','followup-job'].forEach(id => { const el = document.getElementById(id); if (el) { const current = el.value; el.innerHTML = options; el.value = current; } });
}

async function openJob(id) {
  try {
    const [job, draftData] = await Promise.all([api(`/api/jobs/${id}`), api(`/api/jobs/${id}/drafts`)]);
    const explanation = job.match_explanation || {};
    const salary = job.salary_min != null ? `${job.salary_currency || ''} $${job.salary_min}${job.salary_max != null && job.salary_max !== job.salary_min ? `–$${job.salary_max}` : ''}${job.salary_unit ? ` / ${job.salary_unit}` : ''}` : (job.salary || 'Not listed');
    const draftHistory = draftData.drafts.length ? draftData.drafts.map(draft => {
      const preview = (typeof draft.content === 'string' ? draft.content : JSON.stringify(draft.content, null, 2)).slice(0, 6000);
      return `<div class="draft-row"><span><strong>${esc(label(draft.type))}</strong><small>${fmtDate(draft.created_date)} · ${esc(draft.review_status)} · safety ${draft.safety_report?.passed ? 'passed' : 'review'}</small></span><code>${esc(draft.file_path || 'Stored in database')}</code></div><details class="draft-preview"><summary>View stored draft</summary><pre>${esc(preview)}</pre></details>`;
    }).join('') : '<p class="empty compact-empty">No drafts yet.</p>';
    document.getElementById('job-detail').innerHTML = `<div class="detail-head"><p class="eyebrow">${esc(label(job.fit_category))} · ${job.match_score}/100</p><h2 id="job-dialog-title">${esc(job.title)}</h2><p>${esc(job.company)} · ${esc(job.location)} · ${esc(label(job.work_mode))}</p><p class="detail-meta">${esc(job.source)} · ${esc(label(job.job_type))} · Posted ${fmtDate(job.posted_date)} · Deadline ${fmtDate(job.deadline)} · ${esc(salary)}</p></div>
      ${job.safety_flags.map(flag => `<div class="warning-flag"><strong>${esc(flag.code)}</strong> — ${esc(flag.message)}</div>`).join('')}
      <div class="detail-actions"><button class="button" data-prepare="${job.id}">Prepare package</button><button class="button secondary" data-tailor="${job.id}">Resume suggestions</button><button class="button secondary" data-answers="${job.id}">Draft answers</button><button class="button secondary" data-handoff="${job.id}" ${Number(state.profile?.automation_level ?? 3) < 4 ? 'disabled title="Requires automation level 4"' : ''}>Reviewed handoff</button>${job.job_url ? `<a class="button dark" href="${esc(job.job_url)}" target="_blank" rel="noopener noreferrer">Open official application ↗</a>`:''}</div>
      <div class="detail-columns"><div class="detail-card"><h4>Why it fits</h4><ul class="compact-list">${(explanation.why_it_fits || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><h4>Matched skills</h4><p>${(explanation.matched_skills || []).map(x => `<span class="pill">${esc(x)}</span>`).join(' ') || 'None detected'}</p></div><div class="detail-card"><h4>Risks & missing skills</h4><ul class="compact-list">${(explanation.risks || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul><p><strong>Resume:</strong> ${esc(job.resume_profile)}</p><p><strong>Project:</strong> ${esc(job.suggested_project)}</p></div></div>
      <div class="detail-card next-card"><h4>Suggested next action</h4><p>${esc(job.next_action)}</p></div>
      <div class="detail-columns"><div class="detail-card"><h4>Application checklist</h4><ul class="compact-list"><li>Verify eligibility, dates, and location</li><li>Review every generated claim</li><li>Prepare: ${esc((job.required_documents || []).join(', ') || 'resume')}</li><li>Submit manually on the official portal</li><li>Return and explicitly mark applied</li></ul><p><strong>Start:</strong> ${esc(job.start_date || 'Unspecified')} · <strong>Term:</strong> ${esc(job.term_length || 'Unspecified')}</p><h4>Score breakdown</h4>${Object.entries(job.score_breakdown || {}).map(([name,item]) => `<div class="score-line"><span>${esc(label(name))}</span><b>${item.points}/${item.max}</b></div>`).join('')}</div><div class="detail-card"><form id="detail-tracker-form"><label>Private notes<textarea name="notes" rows="4">${esc(job.notes)}</textarea></label><label>Follow-up date<input name="follow_up_date" type="datetime-local" value="${job.follow_up_date ? esc(job.follow_up_date.slice(0,16)) : ''}"></label><label>Recruiter/contact<input name="contact_name" value="${esc(job.contact_name || '')}"></label><label>Resume version used<input name="resume_version_used" value="${esc(job.resume_version_used || job.tailored_resume_path || '')}"></label><label>Cover-letter version used<input name="cover_letter_version_used" value="${esc(job.cover_letter_version_used || '')}"></label><label>Portal/login note<input name="login_portal" value="${esc(job.login_portal || '')}"></label><button class="button secondary small" type="submit">Save tracker details</button></form></div></div>
      <div class="detail-card"><h4>Draft history</h4>${draftHistory}</div>
      <h4>Posting</h4><div class="description">${esc(job.description)}</div>`;
    const dialog = document.getElementById('job-dialog'); dialog.showModal();
    document.querySelector('[data-prepare]')?.addEventListener('click', () => runDraftAction(id, 'prepare'));
    document.querySelector('[data-tailor]')?.addEventListener('click', () => runDraftAction(id, 'tailor'));
    document.querySelector('[data-answers]')?.addEventListener('click', () => runDraftAction(id, 'answers'));
    document.querySelector('[data-handoff]')?.addEventListener('click', () => createHandoff(id));
    document.getElementById('detail-tracker-form')?.addEventListener('submit', async event => {
      event.preventDefault();
      const payload = Object.fromEntries(new FormData(event.target));
      await api(`/api/jobs/${id}`, {method:'PATCH', body:JSON.stringify(payload)});
      toast('Tracker details saved locally');
      await loadJobs();
    });
  } catch (error) { toast(error.message, true); }
}

document.querySelector('.dialog-close').addEventListener('click', () => document.getElementById('job-dialog').close());

async function jobFormPayload(form) {
  const payload = Object.fromEntries(new FormData(form).entries());
  const splitSkills = value => String(value || '').split(/[,|\n]/).map(item => item.trim()).filter(Boolean);
  if (payload.required_skills_input) payload.required_skills = splitSkills(payload.required_skills_input);
  if (payload.preferred_skills_input) payload.preferred_skills = splitSkills(payload.preferred_skills_input);
  delete payload.required_skills_input;
  delete payload.preferred_skills_input;
  return payload;
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
  try { const payload = await jobFormPayload(event.target); const data = await api('/api/jobs', {method:'POST', body:JSON.stringify(payload)}); toast(data.message); event.target.reset(); await loadDashboard(); switchView('tracker'); }
  catch (error) { toast(error.message, true); }
});

document.getElementById('csv-file').addEventListener('change', async event => {
  if (!event.target.files[0]) return;
  const form = new FormData(); form.append('file', event.target.files[0]);
  try { const response = await fetch('/api/import/csv', {method:'POST', body:form}); const data = await response.json(); if (!response.ok) throw new Error(data.error); toast(`${data.created} jobs imported; ${data.skipped_duplicates} duplicates skipped`); await loadDashboard(); }
  catch (error) { toast(error.message, true); }
});

document.getElementById('json-file').addEventListener('change', async event => {
  if (!event.target.files[0]) return;
  const confirmed = window.confirm('Restore this local JobApplier backup? Existing jobs with the same URL will be kept.');
  if (!confirmed) { event.target.value = ''; return; }
  const form = new FormData(); form.append('file', event.target.files[0]);
  try {
    const response = await fetch('/api/import/json', {method:'POST', body:form});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    toast(`${data.created_jobs} jobs restored; ${data.skipped_duplicate_jobs} duplicates kept`);
    await loadDashboard();
  } catch (error) { toast(error.message, true); }
});

['job-search','status-filter','category-filter'].forEach(id => document.getElementById(id).addEventListener(id === 'job-search' ? 'input' : 'change', renderTracker));
document.getElementById('status-filter').innerHTML = '<option value="all">All statuses</option>' + statuses.map(item => `<option value="${item}">${label(item)}</option>`).join('');

function safetyMarkup(report) {
  if (!report) return '';
  const issues = (report.violations || []).map(item => `<li>${esc(item.message)}</li>`).join('');
  return `<div class="result-section"><h4>Claim safety check</h4><p class="${report.passed ? 'success-flag':'warning-flag'}">${report.passed ? 'No deterministic violations detected' : 'Resolve these warnings before use'}</p>${issues ? `<ul class="compact-list">${issues}</ul>` : ''}<small>Human fact-checking is still required.</small></div>`;
}

function answerEditor(answers, draftId) {
  return `<form data-draft-form data-draft-id="${draftId}">${Object.entries(answers || {}).map(([key,value]) => `<div class="result-section"><label>${esc(label(key))}<textarea rows="5" data-answer-key="${esc(key)}">${esc(value)}</textarea></label></div>`).join('')}<div class="form-actions"><button class="button secondary" type="submit" value="draft">Save edited draft</button><button class="button" type="submit" value="reviewed">Save as reviewed</button></div></form>`;
}

function bindDraftEditor(data, kind, plan) {
  const form = document.querySelector('[data-draft-form]');
  if (!form) return;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const answers = {};
    form.querySelectorAll('[data-answer-key]').forEach(field => { answers[field.dataset.answerKey] = field.value; });
    const content = kind === 'prepare' ? {tailoring:plan, answers} : answers;
    try {
      const result = await api(`/api/drafts/${form.dataset.draftId}`, {method:'PATCH', body:JSON.stringify({content, review_status:event.submitter?.value || 'draft'})});
      toast(result.message);
    } catch (error) { toast(error.message, true); }
  });
}

function renderTailoring(data, kind) {
  const target = document.getElementById('tailor-result');
  if (kind === 'answers') {
    target.innerHTML = `${safetyMarkup(data.safety_report)}${answerEditor(data.answers, data.draft_id)}<div class="warning-note">These are local drafts. Edit, save, and verify every job/company-specific detail before use.</div>`;
    bindDraftEditor(data, kind, null);
    return;
  }
  const plan = data.plan || data.tailoring;
  const checklist = (data.checklist || []).map(item => `<li>${esc(item)}</li>`).join('');
  target.innerHTML = `<div class="result-section"><p class="eyebrow">${esc(plan.resume_profile)}</p><h3>Tailoring plan</h3><p><strong>Project:</strong> ${esc(plan.project_to_emphasize.name)}</p><p><strong>Skills to move higher:</strong> ${plan.skills_to_move_higher.map(x => `<span class="pill">${esc(x)}</span>`).join(' ')}</p></div>
    <div class="result-section"><h4>Keyword gaps</h4><p>${plan.keyword_gaps.map(x => `<span class="pill warn">${esc(x)}</span>`).join(' ') || 'No explicit gaps detected.'}</p><small>${esc(plan.keyword_gap_rule)}</small></div>
    ${plan.experience_suggestions.map(item => `<div class="result-section"><h4>${esc(item.experience)}</h4><ul class="compact-list">${item.suggested_bullets.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`).join('')}
    <div class="result-section"><h4>One-page estimate</h4><p class="${plan.one_page_check.passes_estimate ? 'success-flag':'warning-flag'}">${plan.one_page_check.estimated_lines} estimated lines / ${plan.one_page_check.limit} line target</p></div>
    ${data.latex_path || plan.latex_path ? `<div class="result-section"><h4>LaTeX draft</h4><div class="code-path">${esc(data.latex_path || plan.latex_path)}</div></div>`:''}
    ${safetyMarkup(data.safety_report || plan.safety_report)}
    ${checklist ? `<div class="result-section"><h4>Manual application checklist</h4><ul class="compact-list">${checklist}</ul></div>` : ''}
    ${data.answers ? `<div class="result-section"><h3>Editable application answers</h3></div>${answerEditor(data.answers, data.draft_id)}` : ''}
    <div class="warning-note">${esc(plan.base_resume_warning)} Human review is required.</div>`;
  if (data.answers) bindDraftEditor(data, kind, plan);
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

async function createHandoff(jobId) {
  if (!jobId) return toast('Choose a tracked job first', true);
  if (!window.confirm('Create a Level 4 handoff only after reviewing the full package. Continue?')) return;
  try {
    const data = await api(`/api/jobs/${jobId}/handoff`, {method:'POST', body:JSON.stringify({confirm_reviewed:true})});
    document.getElementById('tailor-job').value = String(jobId);
    document.getElementById('tailor-result').innerHTML = `<div class="result-section"><p class="eyebrow">LEVEL 4 · HUMAN-ACTION HANDOFF</p><h3>Reviewed application handoff</h3><p>${esc(data.message)}</p><a class="button dark" href="${esc(data.application_url)}" target="_blank" rel="noopener noreferrer">Open official application ↗</a></div><div class="result-section"><h4>You remain responsible for every step</h4><ul class="compact-list">${data.human_actions.map(item => `<li>${esc(item)}</li>`).join('')}</ul></div>`;
    document.getElementById('job-dialog').open && document.getElementById('job-dialog').close();
    switchView('tailor');
  } catch (error) { toast(error.message, true); }
}

document.getElementById('generate-tailor').addEventListener('click', () => runDraftAction(document.getElementById('tailor-job').value, 'tailor'));
document.getElementById('generate-answers').addEventListener('click', () => runDraftAction(document.getElementById('tailor-job').value, 'answers'));
document.getElementById('prepare-package').addEventListener('click', () => runDraftAction(document.getElementById('tailor-job').value, 'prepare'));
document.getElementById('guided-handoff').addEventListener('click', () => createHandoff(document.getElementById('tailor-job').value));
document.getElementById('tailor-job').addEventListener('change', event => { const job = state.jobs.find(item => String(item.id) === event.target.value); if (job) document.getElementById('resume-profile').value = job.resume_profile; });

async function loadFollowups() {
  const data = await api('/api/follow-ups');
  document.getElementById('followup-list').innerHTML = data.follow_ups.length ? data.follow_ups.map(item => `<div class="follow-row"><div class="job-copy"><strong>${esc(label(item.type))}</strong><small>${fmtDate(item.due_date)} · ${esc(item.status)}</small>${item.message_draft ? `<p>${esc(item.message_draft)}</p>`:''}</div><div class="row-actions"><span class="pill">${esc(item.status)}</span>${item.status === 'pending' ? `<button class="button secondary small" data-complete-followup="${item.id}">Complete</button>` : ''}</div></div>`).join('') : '<div class="empty">No follow-up reminders yet.</div>';
  document.querySelectorAll('[data-complete-followup]').forEach(button => button.addEventListener('click', async () => {
    try { await api(`/api/follow-ups/${button.dataset.completeFollowup}`, {method:'PATCH', body:JSON.stringify({status:'completed'})}); toast('Follow-up completed'); await loadFollowups(); }
    catch(error) { toast(error.message, true); }
  }));
}
document.getElementById('followup-form').addEventListener('submit', async event => { event.preventDefault(); const payload = Object.fromEntries(new FormData(event.target)); if (payload.job_id) payload.job_id = Number(payload.job_id); else delete payload.job_id; if (payload.contact_id) payload.contact_id = Number(payload.contact_id); else delete payload.contact_id; try { await api('/api/follow-ups', {method:'POST', body:JSON.stringify(payload)}); toast('Reminder created; nothing will be sent automatically'); event.target.reset(); await loadFollowups(); } catch(error){toast(error.message,true);} });

async function loadContacts() {
  const data = await api('/api/contacts');
  state.contacts = data.contacts;
  const selector = document.getElementById('followup-contact');
  if (selector) selector.innerHTML = '<option value="">Optional contact</option>' + data.contacts.map(contact => `<option value="${contact.id}">${esc(contact.name)} — ${esc(contact.company || '')}</option>`).join('');
  document.getElementById('contact-list').innerHTML = data.contacts.length ? data.contacts.map(contact => `<div><div class="contact-row"><div class="job-copy"><strong>${esc(contact.name)}</strong><small>${esc(contact.company || '')} · ${esc(contact.role || '')}<br>${esc(contact.email || contact.linkedin || '')} · ${esc(label(contact.relationship_strength))}${contact.follow_up_needed ? ' · follow-up needed' : ''}</small></div><div class="message-action"><select aria-label="Message type" data-message-kind="${contact.id}"><option value="coffee_chat">Coffee chat</option><option value="referral_request">Referral request</option><option value="application_follow_up">Application follow-up</option><option value="thank_you">Thank-you</option><option value="send_resume">Can I send my resume?</option><option value="rejection_networking">Rejection networking</option></select><button class="button secondary small" data-contact-message="${contact.id}">Draft note</button></div></div><div id="contact-message-${contact.id}"></div></div>`).join('') : '<div class="empty">Add a recruiter, teammate, or referral contact.</div>';
  document.querySelectorAll('[data-contact-message]').forEach(button => button.addEventListener('click', async () => {
    const kind = document.querySelector(`[data-message-kind="${button.dataset.contactMessage}"]`).value;
    try { const data = await api(`/api/contacts/${button.dataset.contactMessage}/message`, {method:'POST', body:JSON.stringify({kind})}); document.getElementById(`contact-message-${button.dataset.contactMessage}`).innerHTML = `<label>Editable message draft<textarea rows="5">${esc(data.message)}</textarea></label><small>Draft only — edit and send manually.</small>`; }
    catch(error){ toast(error.message,true); }
  }));
}
document.getElementById('contact-form').addEventListener('submit', async event => { event.preventDefault(); const formData = new FormData(event.target); const payload = Object.fromEntries(formData); payload.follow_up_needed = formData.has('follow_up_needed'); try { await api('/api/contacts',{method:'POST',body:JSON.stringify(payload) }); toast('Contact saved locally'); event.target.reset(); await loadContacts(); } catch(error){toast(error.message,true);} });

async function loadAnalytics() {
  const data = await api('/api/analytics');
  const maxFunnel = Math.max(1, ...data.funnel.map(item => item.count));
  document.getElementById('analytics-content').innerHTML = `<div class="analytics-grid"><div class="analytics-card"><small>Response rate</small><br><strong>${data.rates.response_rate}%</strong></div><div class="analytics-card"><small>Interview rate</small><br><strong>${data.rates.interview_rate}%</strong></div><div class="analytics-card"><small>Rejection rate</small><br><strong>${data.rates.rejection_rate}%</strong></div><div class="analytics-card"><small>Companies applied to</small><br><strong>${data.companies_applied}</strong></div><div class="analytics-card"><small>Stale applications</small><br><strong>${data.stale_applications}</strong></div><div class="analytics-card"><small>Upcoming deadlines</small><br><strong>${data.upcoming_deadlines}</strong></div><div class="analytics-card"><h3>Conversion funnel</h3>${data.funnel.map(item => `<div class="bar-row"><span>${esc(label(item.status))}</span><span class="bar"><i style="width:${item.count/maxFunnel*100}%"></i></span><b>${item.count}</b></div>`).join('')}</div><div class="analytics-card"><h3>Top missing skills</h3>${data.top_missing_skills.map(([name,count]) => `<div class="bar-row"><span>${esc(name)}</span><span class="bar"><i style="width:${Math.min(100,count*15)}%"></i></span><b>${count}</b></div>`).join('') || '<p class="empty">No scored gaps yet.</p>'}</div><div class="analytics-card"><h3>Applied sources</h3>${data.best_sources.map(([name,count]) => `<div class="bar-row"><span>${esc(name)}</span><span class="bar"><i style="width:${Math.min(100,count*15)}%"></i></span><b>${count}</b></div>`).join('') || '<p class="empty">No applied-source data yet.</p>'}</div><div class="analytics-card"><h3>Applications per week</h3>${data.applications_per_week.map(([week,count]) => `<div class="bar-row"><span>${esc(week)}</span><span class="bar"><i style="width:${Math.min(100,count*15)}%"></i></span><b>${count}</b></div>`).join('') || '<p class="empty">No weekly application data yet.</p>'}</div><div class="analytics-card"><h3>Applied role categories</h3>${data.best_role_categories.map(([name,count]) => `<div class="bar-row"><span>${esc(label(name))}</span><span class="bar"><i style="width:${Math.min(100,count*15)}%"></i></span><b>${count}</b></div>`).join('') || '<p class="empty">No applied categories yet.</p>'}</div></div>`;
}

async function loadProfile() {
  const profile = await api('/api/profile'); state.profile = profile;
  document.getElementById('profile-heading').textContent = profile.name || 'Candidate profile';
  const form = document.getElementById('profile-form');
  ['name','graduation','email','phone','location','linkedin','github','portfolio','work_authorization','availability','relocation','automation_level'].forEach(key => { if (form.elements[key]) form.elements[key].value = profile[key] ?? ''; });
  form.elements.target_roles.value = (profile.target_roles || []).join('\n');
  form.elements.target_locations.value = (profile.target_locations || []).join(', ');
  form.elements.skills.value = (profile.skills || []).join(', ');
  setAutomationLevel(Number(profile.automation_level ?? 3));
  return profile;
}
document.getElementById('profile-form').addEventListener('submit', async event => { event.preventDefault(); const payload = Object.fromEntries(new FormData(event.target)); const splitList = value => value.split(/[,|\n]/).map(x => x.trim()).filter(Boolean); payload.automation_level = Number(payload.automation_level); payload.target_roles = splitList(payload.target_roles); payload.target_locations = splitList(payload.target_locations); payload.skills = splitList(payload.skills); try { const data = await api('/api/profile',{method:'PUT',body:JSON.stringify(payload)}); state.profile=data.profile; setAutomationLevel(data.profile.automation_level); toast('Profile saved to local private data'); } catch(error){toast(error.message,true);} });

document.getElementById('seed-demo').addEventListener('click', async () => { try { const data=await api('/api/seed-demo',{method:'POST'}); toast(data.message); await loadDashboard(); } catch(error){toast(error.message,true);} });

Promise.all([loadDashboard(), loadProfile()]).catch(error => toast(error.message, true));
