'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = (currency, value) => value == null ? '—' : `${currency || ''} ${Number(value).toFixed(2)}`.trim();
const TITLES = {discover:'Browse cards', overview:'Saved overview', deals:'Saved matches', bids:'Auction history', values:'Price references', collection:'My portfolio', watchlist:'Watchlist & budget', scans:'Past scans', listings:'Saved listings'};
const BUCKETS = ['raw', '7', '8', '9', '9.5', '10'];
const BUCKET_LABEL = {raw: 'Raw market reference', '7': 'PSA 7', '8': 'PSA 8', '9': 'PSA 9', '9.5': 'Grade 9.5', '10': 'PSA 10'};
const listingPrice = row => row.total_price == null && row.price != null
  ? `${money(row.currency, row.price)} + shipping unknown` : money(row.currency, row.total_price);
let portfolioValue = null; // in listing currency, set by loadCollection
let watchlistData = null;
let editingTargetName = null;
let budgetDirty = false;

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
  if (location.hash !== `#${view}`) location.hash = view;
}
function openSnipeView(view, options = {}) {
  if (!TITLES[view]) return;
  const already = document.getElementById(`view-${view}`)?.classList.contains('active');
  switchView(view);
  if (options.load && !already) LOADERS[view]?.().catch(err => console.error(view, err));
}
document.querySelectorAll('[data-view], [data-view-link]').forEach(el => el.addEventListener('click', () => openSnipeView(el.dataset.view || el.dataset.viewLink, {load: true})));

function lanePill(row) {
  const bits = [];
  bits.push(row.lane === 'regrade' ? '<span class="lane-pill regrade">♻️ regrade</span>' : `<span class="lane-pill">${row.market_value ? 'deal' : 'budget match'}</span>`);
  if (row.irregular) bits.push(`<span class="lane-pill irregular" title="Verify before buying">⚠️ ${esc(row.irregular_reason || 'irregular')}</span>`);
  if (row.listing_type === 'auction') bits.push('<span class="lane-pill auction">auction</span>');
  if (row.source === 'facebook') bits.push('<span class="lane-pill facebook">facebook</span>');
  return bits.join(' ');
}

function valueText(row) {
  if (!row.market_value) return '<span class="detail-meta">cap only</span>';
  return `${esc(money(row.currency, row.market_value))}<span class="sub">${esc(BUCKET_LABEL[row.value_bucket] || row.value_bucket)} · ${esc(row.value_source)}</span>`;
}

function underText(row) {
  const pct = Math.round(row.savings_pct || 0);
  return row.market_value ? `${pct}% under value` : `${pct}% under cap`;
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
    metric('Saved deals', summary.deals_total, 'checked within 24h; confirm on seller page'),
    metric('♻️ Regrade candidates', summary.regrade_total, 'lower grade / TAG near-miss'),
    metric('⚠️ Irregular', summary.irregular_total || 0, 'too far under value — verify'),
    metric('Saved auction records', pending + placed, 'automatic bidding is disabled'),
  ].join('');
  $('#snipe-metrics-2').innerHTML = [
    metric('Listings checked', summary.listings_seen_24h, `${summary.listings_seen} all time · ${summary.scans_total} scans`),
    metric('Cards valued', summary.valuations || 0, 'TCGPlayer · PriceCharting · eBay sold'),
    metric('Independent portfolio reference', portfolioValue != null ? money(summary.settings.currency || '', portfolioValue) : '—', 'saved estimate; see portfolio for source and date'),
  ].join('');

  const last = summary.last_scan;
  const badge = $('#last-scan-badge');
  if (last) {
    badge.textContent = `Last saved scan ${ago(last.started)} · ${last.scanned} listings · ${last.deals} new alerts`;
    $('#mode-label').textContent = summary.settings.browser_scans_enabled ? 'Browser-only scans' : 'Local-only';
    $('#mode-sub').textContent = 'Scans start on click. Paid APIs and automatic purchases are off.';
    $('#live-dot').style.background = '#e9a23b';
  } else {
    badge.textContent = 'No scans yet';
  }

  $('#latest-deals').innerHTML = deals.deals.length ? deals.deals.map(row => `
    <div class="deal-row">
      <div><a href="${esc(row.url)}" target="_blank" rel="noopener">${esc(row.title)}</a><small>${lanePill(row)} ${esc(gradeText(row))} · ${esc(row.matched_target)} · checked ${ago(row.last_seen)}</small></div>
      <div class="deal-price">${esc(listingPrice(row))}<small>${esc(underText(row))}${row.market_value ? ` (${esc(money(row.currency, row.market_value))})` : ''}</small></div>
    </div>`).join('') : '<div class="empty compact-empty">No independently priced matches. Browse cards to run a broad scan and review all collected candidates.</div>';

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
    `<i class="${r.errors.length ? 'has-errors' : r.deals ? 'has-deals' : ''}" style="height:${Math.max(5, Math.round((r.scanned || 0) / maxScanned * 100))}%" title="${esc(r.started)} · ${r.scanned} scanned · ${r.deals} new alerts${r.errors.length ? ' · errors' : ''}"></i>`).join('')}</div>` : '<div class="empty compact-empty">No scans recorded.</div>';
  const recentErrors = scans.scans.slice(0, 5).flatMap(r => r.errors.map(e => ({when: r.started, text: e})));
  $('#scan-errors').innerHTML = recentErrors.length ? '<p class="detail-meta">Errors from saved scan runs. Current scan status appears in Browse cards.</p>' + recentErrors.slice(0, 4).map(e => `<div class="err">${esc(ago(e.when))}. ${esc(e.text)}</div>`).join('') : '<div class="ok" style="font-size:11px">No errors in saved recent scans.</div>';
}

// ── deals ───────────────────────────────────────────────────────────────────
async function loadDeals() {
  const lane = $('#deal-lane').value, source = $('#deal-source').value, flag = $('#deal-flag').value, q = $('#deal-search').value.toLowerCase();
  const data = await api(`/api/snipe/deals?limit=300&lane=${lane}&source=${source}`);
  const rows = data.deals
    .filter(r => flag === '' || (flag === 'irregular') === !!r.irregular)
    .filter(r => !q || `${r.title} ${r.matched_target} ${r.grade || ''}`.toLowerCase().includes(q));
  $('#deals-table').innerHTML = rows.length ? rows.map(r => `<tr class="${r.irregular ? 'row-irregular' : ''}">
    <td>${esc(ago(r.last_seen))}</td><td>${lanePill(r)}</td>
    <td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a><span class="sub">${esc(r.source)} · ${esc(r.location || '')}${r.end_time ? ' · ends ' + untilText(r.end_time) : ''}</span></td>
    <td>${esc(gradeText(r))}${r.condition ? `<span class="sub">Seller: ${esc(r.condition)}</span>` : ''}</td><td>${esc(listingPrice(r))}${r.shipping ? `<span class="sub">incl. ship ${Number(r.shipping).toFixed(2)}</span>` : ''}</td>
    <td>${valueText(r)}</td>
    <td>${Math.round(r.savings_pct || 0)}%</td><td>${esc(r.matched_target)}</td>
    <td>${esc(r.action || 'alerted')}${r.action_detail ? `<span class="sub" title="${esc(r.action_detail)}">${esc(r.action_detail.slice(0, 60))}</span>` : ''}</td>
    <td><button class="button secondary small" data-dismiss="${r.id}">Remove</button></td>
  </tr>`).join('') : '<tr><td colspan="10" class="empty">No deals match.</td></tr>';
  bindDismiss('#deals-table', loadDeals);
}

// ── market values ───────────────────────────────────────────────────────────
async function loadValues() {
  const data = await api('/api/snipe/valuations');
  $('#values').innerHTML = data.valuations.length ? data.valuations.map(row => {
    const v = row.valuation;
    if (!row.use_market) return `<div class="target-card"><header><strong>${esc(row.target)}</strong><span class="detail-meta">market lookups off · cap ${esc(row.max_price ?? '—')}</span></header></div>`;
    if (!v) return `<div class="target-card"><header><strong>${esc(row.target)}</strong><span class="err">No saved valuation. Live updates are disabled.</span></header><div class="kw">${esc(row.market_query)}</div></div>`;
    const sources = [...new Set(v.prices.map(p => p.source))];
    const cells = BUCKETS.map(b => {
      const chosen = v.values[b];
      const bySource = sources.filter(s => b !== 'raw' || s === 'tcgplayer').map(s => { const p = v.prices.find(x => x.bucket === b && x.source === s); return p ? `${s} ${money(v.currency, p.price_usd * v.fx)}` : null; }).filter(Boolean);
      const mixed = b === 'raw' ? v.prices.filter(p => p.bucket === 'raw_any') : [];
      const mixedNote = mixed.length ? `<em class="all-sources">mixed condition, unused: ${esc(mixed.map(p => `${p.source} ${money(v.currency, p.price_usd * v.fx)}`).join(' · '))}</em>` : '';
      const ceiling = chosen ? Math.min(chosen.value * (1 - row.bargain_pct / 100), row.effective_budget ?? Infinity) : null;
      const sourcePrice = chosen ? v.prices.find(p => p.source === chosen.source && p.bucket === b) : null;
      return `<div class="value-cell ${chosen ? '' : 'muted'}"><small>${esc(BUCKET_LABEL[b])}</small><strong>${chosen ? esc(money(v.currency, chosen.value)) : '—'}</strong><em>${chosen ? esc(`${chosen.source} · ${row.stale ? 'expired reference' : `deal ≤ ${money(v.currency, ceiling)}`}`) : 'no data'}</em>${sourcePrice?.url ? `<a href="${esc(sourcePrice.url)}" target="_blank" rel="noopener">Source</a>` : ''}${bySource.length > 1 ? `<em class="all-sources">${esc(bySource.join(' · '))}</em>` : ''}${mixedNote}</div>`;
    }).join('');
    return `<div class="target-card">
      <header><strong>${esc(row.target)}</strong><div class="target-actions">${v.card_url ? `<a class="button secondary small" href="${esc(v.card_url)}" target="_blank" rel="noopener">Open saved source link</a>` : ''}</div></header>
      <div class="meta"><span>${esc(row.market_query)}</span><span>Saved FX: 1 USD = ${v.fx.toFixed(3)} ${esc(v.currency)}</span><span>Saved ${esc(new Date(v.fetched_at).toLocaleString())}</span>${v.floor_usd ? `<span>Saved lowest listed US$${Number(v.floor_usd).toFixed(2)} (any condition)</span>` : ''}${row.effective_budget ? `<span>budget ${esc(money(v.currency, row.effective_budget))}</span>` : ''}<span>bargain ≥ ${row.bargain_pct}% · irregular ≥ ${row.irregular_pct}%</span></div>
      <div class="value-grid">${cells}</div>
      ${row.stale ? '<div class="err">Expired saved reference. Check the source manually before using this price.</div>' : ''}
      ${v.notes.length ? `<div class="err">${esc(v.notes.join(' · '))}</div>` : ''}
    </div>`;
  }).join('') : '<div class="empty">No targets.</div>';
}
$('#revalue').addEventListener('click', async () => {
  const btn = $('#revalue'); btn.disabled = true; btn.textContent = 'Re-judging…';
  try { const r = await api('/api/snipe/revalue', {method: 'POST'}); toast(r.message); await Promise.all([loadDeals(), loadOverview()]); }
  catch (err) { toast(err.message, true); }
  btn.disabled = false; btn.textContent = 'Re-judge saved listings';
});

// ── collection ──────────────────────────────────────────────────────────────
async function loadCollection() {
  const [data, deals] = await Promise.all([api('/api/snipe/collection'), api('/api/snipe/deals?limit=300')]);
  const snap = data.snapshot;
  const stale = snap && Date.now() - new Date(snap.synced_at).getTime() > 86400000;
  portfolioValue = snap && !stale && snap.market_value_usd != null ? snap.market_value_usd * data.fx : null;
  $('#collection-metrics').innerHTML = snap ? [
    metric('Collectr snapshot', money('USD', snap.total_value_usd), 'source estimate, not verified resale value'),
    metric('Cards owned', snap.total_cards, `${snap.total_graded || 0} graded`),
    metric('Independent reference', money('USD', snap.market_value_usd), snap.market_value_usd == null ? 'not priced independently' : `${snap.unvalued_items || 0} card entries unpriced${stale ? ' · expired reference' : ' · saved estimate'}`),
    metric('Last imported', ago(snap.synced_at), new Date(snap.synced_at).toLocaleString()),
  ].join('') : metric('Portfolio', '—', 'Import a Collectr snapshot to get started.');
  $('#collection-meta').innerHTML = (snap ? `${snap.source_url ? `<a href="${esc(snap.source_url)}" target="_blank" rel="noopener">Open Collectr showcase ↗</a> · ` : ''}Saved ${esc(new Date(snap.synced_at).toLocaleString())}. ` : 'No saved collection snapshot. ') + 'No automatic sync. Reload reads this local snapshot only.' + (stale ? ' This snapshot is over 24 hours old.' : '');
  const bucketText = b => BUCKET_LABEL[b] || 'grade unknown';
  $('#collection-table').innerHTML = data.items.length ? data.items.map(i => `<tr>
    <td><strong>${esc(i.name)}</strong><span class="sub">${esc(i.set_name || '')} · ${esc(i.number || '')}</span></td>
    <td>${esc(i.condition || (i.graded ? i.grade || 'Grade unknown' : 'Condition unknown'))}<span class="sub">${esc(i.finish || 'Finish not supplied')}</span></td>
    <td>${i.market_value_usd ? `<strong>US$${Number(i.market_value_usd).toFixed(2)}</strong><span class="sub">${esc(money(data.currency, i.market_value_usd * data.fx))} · ${esc(bucketText(i.market_bucket))} via ${esc(i.market_source || '')}${i.market_source === 'collectr' ? ' (low trust)' : ''}</span>`
      : '<span class="status-pill">Unpriced</span><span class="sub">no verified independent price</span>'}</td>
    <td>${esc(money('USD', i.value_usd))}<span class="sub">at import time</span></td>
    <td class="${(i.change_pct || 0) >= 0 ? 'ok' : 'err'}">${i.change_pct != null ? `${i.change_pct >= 0 ? '+' : ''}${Number(i.change_pct).toFixed(1)}%` : '—'}</td>
    <td>${i.quantity}</td>
  </tr>`).join('') : '<tr><td colspan="6" class="empty">Import a snapshot to see your cards.</td></tr>';

  const board = deals.deals.filter(d => d.market_value && d.total_price != null)
    .map(d => ({...d, equity: d.market_value - d.total_price}))
    .sort((a, b) => b.equity - a.equity).slice(0, 25);
  $('#tradeup-table').innerHTML = board.length ? board.map(d => `<tr class="${d.irregular ? 'row-irregular' : ''}">
    <td><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a><span class="sub">${lanePill(d)} ${esc(gradeText(d))} · ${esc(d.matched_target)}</span></td>
    <td>${esc(money(d.currency, d.total_price))}</td><td>${esc(money(d.currency, d.market_value))}</td>
    <td class="ok"><strong>${esc(money(d.currency, d.equity))}</strong><span class="sub">${Math.round(d.savings_pct || 0)}%</span></td>
    <td>${portfolioValue == null ? '—' : d.total_price <= portfolioValue ? '<span class="lane-pill">within estimate</span>' : `<span class="detail-meta">${esc(money(d.currency, d.total_price - portfolioValue))} above estimate</span>`}</td>
  </tr>`).join('') : '<tr><td colspan="5" class="empty">No valued deals yet.</td></tr>';
}

let collectionImportText = null;
const resetCollectionPreview = () => {
  collectionImportText = null;
  $('#collection-import-preview').hidden = true;
  $('#collection-import-save').hidden = true;
};
$('#collection-import-text').addEventListener('input', resetCollectionPreview);
$('#collection-import-form').addEventListener('submit', async event => {
  event.preventDefault();
  resetCollectionPreview();
  const button = $('#collection-preview-button');
  button.disabled = true;
  $('#collection-import-status').textContent = 'Checking the copied portfolio…';
  try {
    const text = $('#collection-import-text').value;
    const data = await api('/api/snipe/collection/import', {method: 'POST', body: JSON.stringify({text})});
    if (text !== $('#collection-import-text').value) return;
    collectionImportText = text;
    $('#collection-import-preview').innerHTML = `<strong>${data.total_cards} cards · ${esc(money('USD', data.total_value_usd))} Collectr estimate</strong><ul>${data.items.map(i => `<li>${esc(i.name)} · ${esc(i.number)} · ${esc(i.condition || 'condition unknown')} · ${i.quantity} × ${esc(money('USD', i.value_usd))}</li>`).join('')}</ul><p>This replaces the local card list. Independent estimates will be unpriced until verified.</p>`;
    $('#collection-import-preview').hidden = false;
    $('#collection-import-save').hidden = false;
    $('#collection-import-status').textContent = 'Preview ready. Check the cards, quantities and conditions before saving.';
  } catch (err) { $('#collection-import-status').textContent = err.message; }
  finally { button.disabled = false; }
});
$('#collection-import-save').addEventListener('click', async () => {
  if (collectionImportText == null || collectionImportText !== $('#collection-import-text').value) return;
  const button = $('#collection-import-save');
  button.disabled = true;
  try {
    const data = await api('/api/snipe/collection/import', {method: 'POST', body: JSON.stringify({text: collectionImportText, confirm: true})});
    resetCollectionPreview();
    $('#collection-import-status').textContent = data.message;
    await loadCollection();
    await loadOverview();
    toast(data.message);
  } catch (err) { $('#collection-import-status').textContent = err.message; }
  finally { button.disabled = false; }
});
$('#collection-reload').addEventListener('click', async () => {
  try { await loadCollection(); toast('Local snapshot reloaded. Collectr changes need a new import.'); }
  catch (err) { toast(err.message, true); }
});

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

function browserSearchButtons(links) {
  const labels = {facebook: 'Search Marketplace', ebay: 'Search eBay'};
  return Object.entries(links || {}).map(([source, url]) => `<a class="button secondary small" href="${esc(url)}" target="_blank" rel="noopener">${labels[source]}</a>`).join('');
}

async function loadDiscovery() {
  const data = await api(`/api/snipe/discovery?query=${encodeURIComponent($('#discovery-query').value.trim())}`);
  document.querySelectorAll('[data-discovery-source]').forEach(link => {
    link.href = (data.search_modes?.[link.dataset.discoveryMode] || data.search_links)[link.dataset.discoverySource];
  });
  document.querySelectorAll('[data-discovery-query]').forEach(link => {
    const url = new URL(data.search_links.ebay);
    url.searchParams.set('_nkw', link.dataset.discoveryQuery);
    link.href = url.href;
  });
  $('#discovery-meta').textContent = `${data.query} · ${data.budget == null ? 'No shared price cap' : `Price cap: ${money(data.currency, data.budget)} before shipping and other charges`} · no watchlist, condition or grading-company filter`;
}

function updateDiscoveryQuery() {
  const query = $('#discovery-query').value.trim() || 'pokemon cards';
  $('#discovery-query').value = query;
  document.querySelectorAll('[data-discovery-source]').forEach(link => {
    const url = new URL(link.href);
    url.searchParams.set(link.dataset.discoverySource === 'ebay' ? '_nkw' : 'query', query);
    link.href = url.href;
  });
}
document.querySelectorAll('[data-discovery-source]').forEach(link => link.addEventListener('click', updateDiscoveryQuery));
$('#discovery-form').addEventListener('submit', event => {
  event.preventDefault();
  // Keep navigation in the user's click so the browser does not block the new tab.
  $('#discovery-ebay').click();
});
document.querySelectorAll('[data-discovery-query]').forEach(link => link.addEventListener('click', () => {
  $('#discovery-query').value = link.dataset.discoveryQuery;
  updateDiscoveryQuery();
  loadDiscovery().catch(err => toast(err.message, true));
}));

let discoveryResultData = {listings: [], scan: null};
let completedBroadScan = null;
let broadStatusInFlight = false;

function renderDiscoveryResults() {
  const source = $('#broad-result-source').value;
  const format = $('#broad-result-format').value;
  const query = $('#broad-result-query').value.trim().toLowerCase();
  const set = $('#broad-result-set').value.trim().toLowerCase();
  const type = $('#broad-result-type').value.trim().toLowerCase();
  const minField = $('#broad-min-price'), maxField = $('#broad-max-price');
  const min = minField.value.trim() === '' ? null : Number(minField.value);
  const max = maxField.value.trim() === '' ? null : Number(maxField.value);
  const invalidMin = minField.validity?.badInput || (min != null && (!Number.isFinite(min) || min < 0));
  const invalidMax = maxField.validity?.badInput || (max != null && (!Number.isFinite(max) || max < 0));
  const reversed = min != null && max != null && min > max;
  const priceError = invalidMin || invalidMax ? 'Enter non-negative prices, or leave either limit blank.'
    : reversed ? 'Minimum price cannot exceed maximum price.' : '';
  minField.setAttribute('aria-invalid', String(!!invalidMin || reversed));
  maxField.setAttribute('aria-invalid', String(!!invalidMax || reversed));
  const priceActive = min != null || max != null;
  const rows = discoveryResultData.listings.filter(row => !priceError && (!source || row.source === source)
    && (!format || row.listing_type === format)
    && (!priceActive || (Number.isFinite(row.total_price) && (min == null || row.total_price >= min) && (max == null || row.total_price <= max)))
    && (!set || row.title.toLowerCase().includes(set))
    && (!type || row.title.toLowerCase().includes(type))
    && (!query || `${row.title} ${row.condition} ${row.promotion} ${row.discovery_routes.join(' ')}`.toLowerCase().includes(query)));
  const scan = discoveryResultData.scan;
  $('#broad-price-help').textContent = priceError || `Price filters${scan?.currency ? ` (${scan.currency})` : ''} include reported shipping, before tax. Unknown totals are hidden while a price range is set. Marketplace listings count as fixed price. Set and type match listing titles only; verify on the seller page. Filters do not start a scan.`;
  $('#broad-result-count').textContent = scan ? `${rows.length} of ${discoveryResultData.listings.length} candidates` : 'No scan yet';
  $('#broad-result-meta').textContent = scan
    ? `Scanned ${new Date(scan.started).toLocaleString()} · ${scan.scanned} rows read · ${scan.errors.length} source errors${scan.budget != null ? ` · older scan capped at ${money(scan.currency, scan.budget)} listed price; scan again to include higher prices` : ''}. Seller promotions and bids are leads, without an independently verified market price.`
    : 'Promotions and asking prices are leads. Below-market value is not independently verified.';
  $('#broad-results-table').innerHTML = rows.length ? rows.map(row => `<tr>
    <td><a href="${esc(row.url)}" target="_blank" rel="noopener">${esc(row.title)}</a><span class="sub">${esc(row.source)} · ${row.listing_type === 'auction' ? 'Auction, current bid can rise' : 'Listed asking price'}${row.location ? ` · ${esc(row.location)}` : ''}</span></td>
    <td>${row.promotion ? `<div class="candidate-promotion">${esc(row.promotion)}</div>` : ''}${row.discovery_routes.map(route => `<span class="sub">${esc(route)}</span>`).join('')}</td>
    <td><strong>${row.price == null ? 'Price varies / unavailable' : esc(listingPrice(row))}</strong>${row.shipping != null && row.shipping > 0 ? `<span class="sub">Includes ${esc(money(row.currency, row.shipping))} shipping</span>` : ''}<span class="sub">Before tax and other charges</span></td>
    <td>${esc(row.condition || 'Not verified')}</td><td>${esc(ago(row.last_seen))}</td>
    <td><button class="button secondary small" data-dismiss="${row.id}">Remove</button></td>
  </tr>`).join('') : `<tr><td colspan="6" class="empty">${priceError || (scan ? 'No candidates to show for the latest scan and filters. Check the source errors above.' : 'Click Scan all cards automatically to collect listings here.')}</td></tr>`;
  bindDismiss('#broad-results-table', loadDiscoveryResults);
}

async function loadDiscoveryResults() {
  discoveryResultData = await api('/api/snipe/discovery/results');
  renderDiscoveryResults();
}

async function loadBroadStatus() {
  if (broadStatusInFlight) return;
  broadStatusInFlight = true;
  try {
    const data = await api('/api/snipe/discovery/scan');
    const busy = data.running;
    const scanning = busy && data.operation === 'broad';
    const signingIn = busy && data.operation === 'login';
    $('#broad-scan').disabled = busy || data.cooldown_seconds > 0 || !data.browser_scans_enabled;
    $('#broad-scan').textContent = scanning ? 'Scanning all cards…' : data.cooldown_seconds > 0 ? `Scan again in ${data.cooldown_seconds}s` : 'Scan all cards automatically';
    $('#broad-source').disabled = busy;
    $('#broad-stop').hidden = !scanning;
    $('#broad-stop').disabled = false;
    $('#broad-progress').hidden = !scanning;
    $('#broad-progress').max = data.page_limit || data.max_searches;
    $('#broad-progress').value = data.pages_done || 0;
    $('#broad-status').textContent = (data.message || 'Ready to scan.') + (scanning ? ` ${data.pages_done || 0}/${data.page_limit} searches · ${data.candidates || 0} candidates so far.` : '');
    $('#broad-errors').innerHTML = (data.errors || []).map(error => `<p class="err">${esc(error)}</p>`).join('');
    $('#facebook-login').disabled = busy || !data.browser_scans_enabled;
    $('#facebook-finish').hidden = !signingIn;
    $('#facebook-finish').disabled = !data.login_waiting;
    $('#facebook-cancel').hidden = !signingIn;
    if (!busy && data.operation === 'broad' && data.started !== completedBroadScan) {
      completedBroadScan = data.started;
      await loadDiscoveryResults();
      await loadOverview();
    }
  } finally { broadStatusInFlight = false; }
}

$('#broad-scan').addEventListener('click', async () => {
  $('#broad-scan').disabled = true;
  $('#broad-status').textContent = 'Starting broad browser scan…';
  try {
    await api('/api/snipe/discovery/scan', {method: 'POST', body: JSON.stringify({source: $('#broad-source').value})});
    await loadBroadStatus();
  } catch (err) { $('#broad-status').textContent = err.message; $('#broad-scan').disabled = false; }
});
$('#broad-stop').addEventListener('click', async () => {
  $('#broad-stop').disabled = true;
  try { await api('/api/snipe/discovery/stop', {method: 'POST'}); await loadBroadStatus(); }
  catch (err) { toast(err.message, true); }
});
for (const [id, path] of [['#facebook-login', ''], ['#facebook-finish', '/finish'], ['#facebook-cancel', '/cancel']]) {
  $(id).addEventListener('click', async () => {
    $(id).disabled = true;
    try { await api(`/api/snipe/facebook/login${path}`, {method: 'POST'}); await loadBroadStatus(); }
    catch (err) { toast(err.message, true); $(id).disabled = false; }
  });
}
$('#broad-result-source').addEventListener('change', renderDiscoveryResults);
$('#broad-result-format').addEventListener('change', renderDiscoveryResults);
['#broad-result-query', '#broad-result-set', '#broad-result-type'].forEach(selector => $(selector).addEventListener('input', renderDiscoveryResults));
['#broad-min-price', '#broad-max-price'].forEach(selector => $(selector).addEventListener('input', renderDiscoveryResults));
$('#broad-price-clear').addEventListener('click', () => {
  $('#broad-min-price').value = '';
  $('#broad-max-price').value = '';
  renderDiscoveryResults();
});

async function loadDiscover() {
  await Promise.all([loadDiscovery(), loadDiscoveryResults(), loadBroadStatus()]);
}

// ── watchlist ───────────────────────────────────────────────────────────────
function renderWatchlist(data) {
  watchlistData = data;
  if (!budgetDirty) $('#card-budget').value = data.budget ?? '';
  $('#budget-badge').textContent = data.budget == null ? 'Set card budget' : `Per card: ${money(data.currency, data.budget)}`;
  $('#watchlist-targets').innerHTML = data.targets.length ? data.targets.map(t => `
    <div class="target-card ${t.enabled ? '' : 'disabled'}">
      <header><strong>${esc(t.name)}</strong><div class="target-actions"><button class="button secondary small" data-edit="${esc(t.name)}">Edit</button><button class="button secondary small" data-toggle="${esc(t.name)}" data-enabled="${t.enabled}">${t.enabled ? 'Pause' : 'Resume'}</button><button class="button secondary small" data-remove="${esc(t.name)}">Remove</button></div></header>
      <div class="target-actions">${browserSearchButtons(Object.fromEntries(Object.entries(t.search_links || {}).filter(([source]) => t.sources.includes(source))))}</div>
      <div class="kw">${esc(t.keywords.join('  +  '))}</div>
      <div class="meta">
        ${t.use_market && (t.card_name || t.number) ? `<span>💲 ${esc([t.card_name, t.set_name, t.number].filter(Boolean).join(' · '))} · deal ≥ ${t.bargain_pct}% under</span>` : ''}
        <span>Budget: ${data.budget == null && t.max_price == null ? 'market value' : esc(money(data.currency, Math.min(data.budget ?? Infinity, t.max_price ?? Infinity)))}</span>
        ${t.min_price != null ? `<span>minimum ${esc(money(data.currency, t.min_price))}</span>` : ''}
        ${t.graded_only ? `<span>graded only${t.min_grade ? ` ≥ ${t.min_grade}` : ''}</span>` : ''}
        ${t.regrade ? `<span>♻️ ${t.regrade_min_grade}–${t.regrade_max_grade} · budget also applies</span>` : ''}
        <span>${esc(t.sources.join(' + '))}</span>
        ${t.exclude.length ? `<span>− ${esc(t.exclude.join(', '))}</span>` : ''}
      </div>
      ${t.note ? `<small class="detail-meta">${esc(t.note)}</small>` : ''}
    </div>`).join('') : '<div class="empty">No targets. Add one on the right.</div>';
  $('#watchlist-meta').textContent = `${data.targets.filter(t => t.enabled).length} saved targets · broad automatic scans run from Browse cards without using these targets`;
  document.querySelectorAll('[data-edit]').forEach(btn => btn.addEventListener('click', () => editTarget(btn.dataset.edit)));
  document.querySelectorAll('[data-remove]').forEach(btn => btn.addEventListener('click', async () => {
    if (!confirm(`Remove "${btn.dataset.remove}" from the watchlist?`)) return;
    try { const data = await api(`/api/snipe/watchlist/${encodeURIComponent(btn.dataset.remove)}`, {method: 'DELETE'}); if (editingTargetName === btn.dataset.remove) resetTargetForm(); renderWatchlist(data); toast('Target removed'); }
    catch (err) { toast(err.message, true); }
  }));
  document.querySelectorAll('[data-toggle]').forEach(btn => btn.addEventListener('click', async () => {
    try { renderWatchlist(await api(`/api/snipe/watchlist/${encodeURIComponent(btn.dataset.toggle)}`, {method: 'PATCH', body: JSON.stringify({enabled: btn.dataset.enabled !== 'true'})})); }
    catch (err) { toast(err.message, true); }
  }));
}

async function loadWatchlist() { renderWatchlist(await api('/api/snipe/watchlist')); }

function resetTargetForm() {
  $('#target-form').reset();
  editingTargetName = null;
  $('#target-form-title').textContent = 'Add a card';
  $('#save-target').textContent = 'Add card';
  $('#cancel-edit').hidden = true;
}

function editTarget(name) {
  const target = watchlistData.targets.find(t => t.name === name);
  if (!target) return;
  resetTargetForm();
  editingTargetName = name;
  const form = $('#target-form');
  for (const key of ['name', 'card_name', 'set_name', 'number', 'bargain_pct', 'max_price', 'min_price', 'min_grade', 'regrade_max_price']) {
    form.elements.namedItem(key).value = target[key] ?? '';
  }
  form.elements.keywords.value = target.keywords.join('\n');
  form.elements.exclude.value = target.exclude.join(', ');
  form.elements.sources.value = ['ebay', 'facebook'].filter(s => target.sources.includes(s)).join(',');
  form.elements.regrade.checked = target.regrade;
  form.elements.graded_only.checked = target.graded_only;
  form.elements.regrade_grades.value = `${target.regrade_min_grade} ${target.regrade_max_grade}`;
  $('#target-form-title').textContent = `Edit ${name}`;
  $('#save-target').textContent = 'Save changes';
  $('#cancel-edit').hidden = false;
  form.elements.name.focus();
}

$('#cancel-edit').addEventListener('click', resetTargetForm);
$('#card-budget').addEventListener('input', () => { budgetDirty = true; });
$('#budget-form').addEventListener('submit', async event => {
  event.preventDefault();
  const btn = event.submitter;
  btn.disabled = true;
  try {
    const data = await api('/api/snipe/budget', {method: 'PATCH', body: JSON.stringify({budget: $('#card-budget').value})});
    budgetDirty = false;
    renderWatchlist(data);
    await loadDiscovery();
    toast('Budget saved. Browser search links updated.');
  } catch (err) { toast(err.message, true); }
  finally { btn.disabled = false; }
});

$('#target-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const grades = (form.get('regrade_grades') || '').trim().split(/\s+/).filter(Boolean).map(Number);
  const payload = {
    name: form.get('name'), keywords: String(form.get('keywords')).split('\n').map(s => s.trim()).filter(Boolean),
    max_price: form.get('max_price'), min_price: form.get('min_price'),
    card_name: form.get('card_name'), set_name: form.get('set_name'), number: form.get('number'), bargain_pct: form.get('bargain_pct'),
    exclude: String(form.get('exclude') || '').split(',').map(s => s.trim()).filter(Boolean),
    regrade: form.get('regrade') === 'on', graded_only: form.get('graded_only') === 'on', min_grade: form.get('min_grade'),
    regrade_min_grade: grades[0], regrade_max_grade: grades[1], regrade_max_price: form.get('regrade_max_price'),
    sources: String(form.get('sources')).split(','),
  };
  const editing = editingTargetName;
  const btn = $('#save-target');
  btn.disabled = true;
  try {
    const url = editing ? `/api/snipe/watchlist/${encodeURIComponent(editing)}` : '/api/snipe/watchlist';
    renderWatchlist(await api(url, {method: editing ? 'PATCH' : 'POST', body: JSON.stringify(payload)}));
    resetTargetForm();
    toast(`Card ${editing ? 'updated' : 'added'}. Applies next scan.`);
  }
  catch (err) { toast(err.message, true); }
  finally { btn.disabled = false; }
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
    <td title="${esc(r.last_seen || 'Not rechecked since the accuracy update')}">${r.last_seen ? esc(ago(r.last_seen)) : 'not rechecked'}</td><td>${esc(r.source)}</td>
    <td><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>${r.condition ? `<span class="sub">Seller condition: ${esc(r.condition)}</span>` : ''}${r.location ? `<span class="sub">${esc(r.location)}</span>` : ''}</td>
    <td>${esc(r.listing_type)}</td><td>${esc(listingPrice(r))}</td>
    <td>${r.matched_target ? `${lanePill(r)} <span class="sub">${esc(r.matched_target)}</span>` : '<span class="detail-meta">no</span>'}</td>
    <td><button class="button secondary small" data-dismiss="${r.id}">Remove</button></td>
  </tr>`).join('') : '<tr><td colspan="7" class="empty">Nothing seen yet.</td></tr>';
  bindDismiss('#listings-table', loadListings);
}

function bindDismiss(root, reload) {
  document.querySelectorAll(`${root} [data-dismiss]`).forEach(btn => btn.addEventListener('click', async () => {
    btn.disabled = true;
    try { await api(`/api/snipe/listings/${btn.dataset.dismiss}`, {method: 'DELETE'}); toast('Removed'); await reload(); }
    catch (err) { toast(err.message, true); btn.disabled = false; }
  }));
}

// ── wiring ──────────────────────────────────────────────────────────────────
const LOADERS = {discover: loadDiscover, collection: loadCollection, overview: loadOverview, deals: loadDeals, bids: loadBids, values: loadValues, watchlist: loadWatchlist, scans: loadScans, listings: loadListings};

async function refreshAll() {
  const failed = [];
  for (const [name, loader] of Object.entries(LOADERS)) {
    try { await loader(); } catch (err) { console.error(name, err); failed.push(name); }
  }
  return failed;
}

['#deal-lane', '#deal-source', '#deal-flag'].forEach(sel => $(sel).addEventListener('change', loadDeals));
$('#deal-search').addEventListener('input', loadDeals);
$('#listing-source').addEventListener('change', loadListings);
$('#listing-search').addEventListener('input', loadListings);
$('#refresh').addEventListener('click', async () => {
  const btn = $('#refresh'); btn.disabled = true;
  try {
    const failed = await refreshAll();
    toast(failed.length ? `Could not reload: ${failed.join(', ')}` : 'Saved results reloaded. Use Discover for broad browser searches.', !!failed.length);
  } finally { btn.disabled = false; }
});

const LIVE_VIEWS = ['collection', 'overview', 'deals', 'listings'];
const SNIPE_POLL_MS = 30000;
const REPLACED_ROOTS = {
  overview: ['#snipe-metrics', '#snipe-metrics-2', '#latest-deals', '#by-target', '#by-source', '#upcoming-bids', '#scan-spark', '#scan-errors'],
  deals: ['#deals-table'],
  bids: ['#bids-table'],
  values: ['#values'],
  collection: ['#collection-metrics', '#collection-table', '#tradeup-table', '#collection-meta'],
  watchlist: ['#watchlist-targets'],
  scans: ['#scans-table'],
  listings: ['#listings-table'],
  discover: ['#broad-results-table'],
};

function isTextField(el) {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  if (tag === 'TEXTAREA') return true;
  if (tag !== 'INPUT') return false;
  const type = (el.type || 'text').toLowerCase();
  return !['button', 'submit', 'reset', 'checkbox', 'radio', 'file', 'hidden', 'range', 'color', 'image'].includes(type);
}

function refreshWouldWipe(name) {
  const el = document.activeElement;
  if (!isTextField(el)) return false;
  return (REPLACED_ROOTS[name] || []).some(sel => document.querySelector(sel)?.contains(el));
}

let snipePollInFlight = false;
async function pollSnipe() {
  if (document.hidden || snipePollInFlight) return;
  snipePollInFlight = true;
  try {
    const names = new Set(LIVE_VIEWS);
    const active = document.querySelector('.view.active')?.id.replace('view-', '');
    if (active) names.add(active);
    const selected = [...names].filter(name => LOADERS[name] && !refreshWouldWipe(name));
    if (selected.includes('collection')) {
      try { await loadCollection(); } catch (err) { console.error('collection', err); }
    }
    await Promise.all(selected.filter(name => name !== 'collection').map(name => LOADERS[name]().catch(err => console.error(name, err))));
  } finally { snipePollInFlight = false; }
}

const initial = location.hash.replace('#', '') || 'discover';
if (TITLES[initial]) switchView(initial);
window.addEventListener('hashchange', () => openSnipeView(location.hash.replace('#', ''), {load: true}));
refreshAll();
setInterval(pollSnipe, SNIPE_POLL_MS);
setInterval(() => { if (!document.hidden) loadBroadStatus().catch(err => console.error('scan status', err)); }, 3000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) pollSnipe(); });
window.addEventListener('focus', pollSnipe);
