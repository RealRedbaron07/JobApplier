'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = (currency, value) => value == null ? '—' : `${currency || ''} ${Number(value).toFixed(2)}`.trim();
const TITLES = {overview:'Overview', deals:'Deals', bids:'Snipes', watchlist:'Watchlist', scans:'Scan history', listings:'Everything seen'};

async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json', ...(options.headers || {})}, ...options});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  return data;
}

function toast(message, isError = false) {
  const el = $('#toast');
  el.textContent = message;
  el.style.background = isError ? '#a73d37' : '';
  el.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('show'), 3200);
}

function ago(iso) {
  if (!iso) return '—';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.max(0, Math.round(diff))}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function untilText(iso) {
  if (!iso) return '—';
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  if (diff <= 0) return 'ended';
  const h = Math.floor(diff / 3600), m = Math.floor((diff % 3600) / 60), s = Math.floor(diff % 60);
  return h ? `${h}h ${m}m` : m ? `${m}m ${s}s` : `${s}s`;
}

function switchView(view) {
  document.querySelectorAll('.view').forEach(el => el.classList.toggle('active', el.id === `view-${view}`));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  $('#page-title').textContent = TITLES[view] || view;
  location.hash = view;
}
document.querySelectorAll('[data-view], [data-view-link]').forEach(el => el.addEventListener('click', () => switchView(el.dataset.view || el.dataset.viewLink)));

function lanePill(row) {
  const bits = [];
  bits.push(row.lane === 'regrade' ? '<span class="lane-pill regrade">♻️ regrade</span>' : '<span class="lane-pill">deal</span>');
  if (row.listing_type === 'auction') bits.push('<span class="lane-pill auction">auction</span>');
  if (row.source === 'facebook') bits.push('<span class="lane-pill facebook">facebook</span>');
  return bits.join(' ');
}

function gradeText(row) {
  const parts = [];
  if (row.grade) parts.push(row.grade);
  if (row.tag_score) parts.push(`TAG ${row.tag_score}`);
  return parts.join(' · ') || 'raw';
}

// ── overview ────────────────────────────────────────────────────────────────
function metric(label, value, note = '') {
  return `<div class="metric"><small>${esc(label)}</small><strong>${esc(value)}</strong>${note ? `<em>${esc(note)}</em>` : ''}</div>`;
}

function bars(container, mapping, emptyText) {
  const entries = Object.entries(mapping || {}).sort((a, b) => b[1] - a[1]);
  if (!entries.length) { container.innerHTML = `<div class="empty compact-empty">${esc(emptyText)}</div>`; return; }
  const max = Math.max(...entries.map(([, v]) => v), 1);
  container.innerHTML = entries.map(([name, value]) =>
    `<div class="bar-row"><span title="${esc(name)}">${esc(name.length > 26 ? name.slice(0, 25) + '…' : name)}</span><div class="bar"><i style="width:${Math.round(value / max * 100)}%"></i></div><strong>${value}</strong></div>`).join('');
}

async function loadOverview() {
  const [summary, deals, bids, scans] = await Promise.all([
    api('/api/snipe/summary'), api('/api/snipe/deals?limit=6'), api('/api/snipe/bids?limit=50'), api('/api/snipe/scans?limit=40'),
  ]);
  const pending = (summary.bids_by_status || {}).pending || 0;
  const placed = (summary.bids_by_status || {}).placed || 0;
  $('#snipe-metrics').innerHTML = [
    metric('Deals (24h)', summary.deals_24h, `${summary.deals_total} all time`),
    metric('♻️ Regrade candidates', summary.regrade_total, 'lower grade / TAG near-miss'),
    metric('Pending snipes', pending, `${placed} placed`),
    metric('Listings checked', summary.listings_seen_24h, `${summary.listings_seen} all time · ${summary.scans_total} scans`),
  ].join('');

  const last = summary.last_scan;
  const badge = $('#last-scan-badge');
  if (last) {
    badge.textContent = `Last scan ${ago(last.started)} · ${last.scanned} listings · ${last.deals} deals`;
    $('#mode-label').textContent = last.live ? 'LIVE mode last scan' : 'Dry-run last scan';
    $('#mode-sub').innerHTML = `Polling every ${summary.settings.poll_seconds}s when running`;
    $('#live-dot').style.background = (Date.now() - new Date(last.started).getTime()) < summary.settings.poll_seconds * 3000 ? '#6ee7a8' : '#e9a23b';
  } else {
    badge.textContent = 'No scans yet';
  }

  $('#latest-deals').innerHTML = deals.deals.length ? deals.deals.map(row => `
    <div class="deal-row">
      <div><a href="${esc(row.url)}" target="_blank" rel="noopener">${esc(row.title)}</a><small>${lanePill(row)} ${esc(gradeText(row))} · ${esc(row.matched_target)} · ${ago(row.first_seen)}</small></div>
      <div class="deal-price">${esc(money(row.currency, row.total_price))}<small>${Math.round(row.savings_pct || 0)}% under cap</small></div>
    </div>`).join('') : '<div class="empty compact-empty">No deals yet. Run <code>make snipe</code>.</div>';

  bars($('#by-target'), summary.deals_by_target, 'No matches recorded yet');
  bars($('#by-source'), summary.deals_by_source, 'No matches recorded yet');

  const upcoming = bids.bids.filter(b => b.status === 'pending' || b.status === 'firing');
  $('#upcoming-bids').innerHTML = upcoming.length ? upcoming.slice(0, 6).map(b => `
    <div class="deal-row">
      <div><a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.title)}</a><small><span class="status-pill ${esc(b.status)}">${esc(b.status)}</span> ${esc(b.target_name || '')} · ends in ${untilText(b.end_time)}</small></div>
      <div class="deal-price">${esc(money(b.currency, b.max_bid))}<small>max bid</small></div>
    </div>`).join('') : '<div class="empty compact-empty">No auctions queued.</div>';

  const runs = [...scans.scans].reverse();
  const maxScanned = Math.max(...runs.map(r => r.scanned || 0), 1);
  $('#scan-spark').innerHTML = runs.length ? `<div class="spark">${runs.map(r =>
    `<i class="${r.errors.length ? 'has-errors' : r.deals ? 'has-deals' : ''}" style="height:${Math.max(5, Math.round((r.scanned || 0) / maxScanned * 100))}%" title="${esc(r.started)} · ${r.scanned} scanned · ${r.deals} deals${r.errors.length ? ' · errors' : ''}"></i>`).join('')}</div>` : '<div class="empty compact-empty">No scans recorded.</div>';
  const recentErrors = scans.scans.slice(0, 5).flatMap(r => r.errors.map(e => ({when: r.started, text: e})));
  $('#scan-errors').innerHTML = recentErrors.length ? recentErrors.slice(0, 4).map(e => `<div class="err">${esc(ago(e.when))} — ${esc(e.text)}</div>`).join('') : '<div class="ok" style="font-size:11px">No errors in recent scans.</div>';
}

// ── deals ───────────────────────────────────────────────────────────────────
async function loadDeals() {
  const lane = $('#deal-lane').value, source = $('#deal-source').value, q = $('#deal-search').value.toLowerCase();
  const data = await api(`/api/snipe/deals?limit=300&lane=${lane}&source=${source}`);
  const rows = data.deals.filter(r => !q || `${r.title} ${r.matched_target} ${r.grade || ''}`.toLowerCase().includes(q));
  $('#deals-table').innerHTML = rows.length ? rows.map(r => `<tr>
    <td>${esc(ago(r.first_seen))}</td><td>${lanePill(r)}</td>
    <td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a><span class="sub">${esc(r.source)} · ${esc(r.location || '')}${r.end_time ? ' · ends ' + untilText(r.end_time) : ''}</span></td>
    <td>${esc(gradeText(r))}</td><td>${esc(money(r.currency, r.total_price))}${r.shipping ? `<span class="sub">incl. ship ${Number(r.shipping).toFixed(2)}</span>` : ''}</td>
    <td>${Math.round(r.savings_pct || 0)}%</td><td>${esc(r.matched_target)}</td>
    <td>${esc(r.action || 'alerted')}${r.action_detail ? `<span class="sub" title="${esc(r.action_detail)}">${esc(r.action_detail.slice(0, 60))}</span>` : ''}</td>
  </tr>`).join('') : '<tr><td colspan="8" class="empty">No deals match.</td></tr>';
}

// ── bids ────────────────────────────────────────────────────────────────────
async function loadBids() {
  const data = await api('/api/snipe/bids?limit=200');
  $('#bids-table').innerHTML = data.bids.length ? data.bids.map(b => `<tr>
    <td>#${b.id}</td><td><span class="status-pill ${esc(b.status)}">${esc(b.status)}</span></td>
    <td><a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.title)}</a><span class="sub">${esc(b.target_name || '')}</span></td>
    <td>${esc(money(b.currency, b.max_bid))}</td><td>${esc(untilText(b.end_time))}<span class="sub">${esc(b.end_time ? new Date(b.end_time).toLocaleString() : '')}</span></td>
    <td>${esc(b.fire_at ? new Date(b.fire_at).toLocaleTimeString() : '')}</td>
    <td>${esc(b.result || '')}</td>
    <td>${b.status === 'pending' ? `<button class="button secondary small" data-cancel="${b.id}">Cancel</button>` : ''}</td>
  </tr>`).join('') : '<tr><td colspan="8" class="empty">No snipes scheduled.</td></tr>';
  document.querySelectorAll('[data-cancel]').forEach(btn => btn.addEventListener('click', async () => {
    try { await api(`/api/snipe/bids/${btn.dataset.cancel}/cancel`, {method: 'POST'}); toast(`Bid #${btn.dataset.cancel} cancelled`); await loadBids(); }
    catch (err) { toast(err.message, true); }
  }));
}

// ── watchlist ───────────────────────────────────────────────────────────────
function renderWatchlist(data) {
  $('#watchlist').innerHTML = data.targets.length ? data.targets.map(t => `
    <div class="target-card ${t.enabled ? '' : 'disabled'}">
      <header><strong>${esc(t.name)}</strong><div class="target-actions"><button class="button secondary small" data-toggle="${esc(t.name)}" data-enabled="${t.enabled}">${t.enabled ? 'Pause' : 'Resume'}</button><button class="button secondary small" data-remove="${esc(t.name)}">Remove</button></div></header>
      <div class="kw">${esc(t.keywords.join('  +  '))}</div>
      <div class="meta">
        <span>${t.min_price ? `${t.min_price}–` : '≤'}${t.max_price}</span>
        ${t.max_bid ? `<span>bid ≤ ${t.max_bid}</span>` : '<span>alert only</span>'}
        ${t.graded_only ? `<span>graded only${t.min_grade ? ` ≥ ${t.min_grade}` : ''}</span>` : ''}
        ${t.regrade ? `<span>♻️ ${t.regrade_min_grade}–${t.regrade_max_grade} ≤ ${t.regrade_max_price || t.max_price}</span>` : ''}
        <span>${esc(t.sources.join(' + '))}</span>
        ${t.exclude.length ? `<span>− ${esc(t.exclude.join(', '))}</span>` : ''}
      </div>
      ${t.note ? `<small class="detail-meta">${esc(t.note)}</small>` : ''}
    </div>`).join('') : '<div class="empty">No targets. Add one on the right.</div>';
  $('#watchlist-meta').textContent = `${data.path} · TAG 10 ≥ ${data.tag_ten_score}, near-miss within ${data.tag_near_margin} · ${data.global_exclude.length} global exclude words`;
  document.querySelectorAll('[data-remove]').forEach(btn => btn.addEventListener('click', async () => {
    if (!confirm(`Remove "${btn.dataset.remove}" from the watchlist?`)) return;
    try { renderWatchlist(await api(`/api/snipe/watchlist/${encodeURIComponent(btn.dataset.remove)}`, {method: 'DELETE'})); toast('Target removed'); }
    catch (err) { toast(err.message, true); }
  }));
  document.querySelectorAll('[data-toggle]').forEach(btn => btn.addEventListener('click', async () => {
    try { renderWatchlist(await api(`/api/snipe/watchlist/${encodeURIComponent(btn.dataset.toggle)}`, {method: 'PATCH', body: JSON.stringify({enabled: btn.dataset.enabled !== 'true'})})); }
    catch (err) { toast(err.message, true); }
  }));
}

async function loadWatchlist() { renderWatchlist(await api('/api/snipe/watchlist')); }

$('#target-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const grades = (form.get('regrade_grades') || '').trim().split(/\s+/).filter(Boolean).map(Number);
  const payload = {
    name: form.get('name'), keywords: String(form.get('keywords')).split('\n').map(s => s.trim()).filter(Boolean),
    max_price: form.get('max_price'), min_price: form.get('min_price'), max_bid: form.get('max_bid'),
    exclude: String(form.get('exclude') || '').split(',').map(s => s.trim()).filter(Boolean),
    regrade: form.get('regrade') === 'on', graded_only: form.get('graded_only') === 'on', min_grade: form.get('min_grade'),
    regrade_min_grade: grades[0], regrade_max_grade: grades[1], regrade_max_price: form.get('regrade_max_price'),
    sources: String(form.get('sources')).split(','),
  };
  try { renderWatchlist(await api('/api/snipe/watchlist', {method: 'POST', body: JSON.stringify(payload)})); event.target.reset(); toast('Target added — picked up on the next scan'); }
  catch (err) { toast(err.message, true); }
});

// ── scans ───────────────────────────────────────────────────────────────────
async function loadScans() {
  const data = await api('/api/snipe/scans?limit=200');
  $('#scans-table').innerHTML = data.scans.length ? data.scans.map(r => `<tr>
    <td>${esc(new Date(r.started).toLocaleString())}<span class="sub">${esc(ago(r.started))}</span></td>
    <td>${r.live ? '<span class="status-pill firing">LIVE</span>' : '<span class="status-pill">dry-run</span>'}</td>
    <td>${esc(r.sources)}</td><td>${r.duration_seconds != null ? r.duration_seconds.toFixed(1) + 's' : '—'}</td>
    <td>${r.scanned}</td><td>${r.new_listings}</td><td>${r.deals}</td><td>${r.regrade_deals}</td><td>${r.bids_scheduled}</td>
    <td>${r.errors.length ? r.errors.map(e => `<div class="err">${esc(e)}</div>`).join('') : '<span class="ok">—</span>'}</td>
  </tr>`).join('') : '<tr><td colspan="10" class="empty">No scans recorded yet.</td></tr>';
}

// ── listings ────────────────────────────────────────────────────────────────
async function loadListings() {
  const source = $('#listing-source').value, q = $('#listing-search').value.toLowerCase();
  const data = await api(`/api/snipe/listings?limit=500&source=${source}`);
  const rows = data.listings.filter(r => !q || (r.title || '').toLowerCase().includes(q));
  $('#listings-table').innerHTML = rows.length ? rows.map(r => `<tr>
    <td>${esc(ago(r.first_seen))}</td><td>${esc(r.source)}</td>
    <td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>${r.location ? `<span class="sub">${esc(r.location)}</span>` : ''}</td>
    <td>${esc(r.listing_type)}</td><td>${esc(money(r.currency, r.total_price))}</td>
    <td>${r.matched_target ? `${lanePill(r)} <span class="sub">${esc(r.matched_target)}</span>` : '<span class="detail-meta">no</span>'}</td>
  </tr>`).join('') : '<tr><td colspan="6" class="empty">Nothing seen yet.</td></tr>';
}

// ── wiring ──────────────────────────────────────────────────────────────────
const LOADERS = {overview: loadOverview, deals: loadDeals, bids: loadBids, watchlist: loadWatchlist, scans: loadScans, listings: loadListings};

async function refreshAll() {
  for (const [name, loader] of Object.entries(LOADERS)) {
    try { await loader(); } catch (err) { console.error(name, err); }
  }
}

['#deal-lane', '#deal-source'].forEach(sel => $(sel).addEventListener('change', loadDeals));
$('#deal-search').addEventListener('input', loadDeals);
$('#listing-source').addEventListener('change', loadListings);
$('#listing-search').addEventListener('input', loadListings);
$('#refresh').addEventListener('click', () => refreshAll().then(() => toast('Refreshed')));

const initial = location.hash.replace('#', '');
if (TITLES[initial]) switchView(initial);
refreshAll();
setInterval(() => { loadOverview().catch(() => {}); const active = document.querySelector('.view.active')?.id.replace('view-', ''); if (active && active !== 'overview') LOADERS[active]?.().catch(() => {}); }, 30000);
