const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function boot({respond} = {}) {
  const opened = [];
  const requests = [];
  const elements = new Map();
  let budget = 100;
  function urlFor(source, query, mode = 'all') {
    const url = new URL(source === 'ebay' ? 'https://www.ebay.ca/sch/i.html' : 'https://www.facebook.com/marketplace/toronto/search');
    url.searchParams.set(source === 'ebay' ? '_nkw' : 'query', query);
    if (budget != null) url.searchParams.set(source === 'ebay' ? '_udhi' : 'maxPrice', budget.toFixed(2));
    if (source === 'ebay') {
      url.searchParams.set('_sop', mode === 'auction' ? '1' : '10');
      if (mode === 'sale') url.searchParams.set('LH_SaleItems', '1');
      if (mode === 'auction') url.searchParams.set('LH_Auction', '1');
      if (mode === 'offers') url.searchParams.set('LH_BO', '1');
    }
    return url.href;
  }
  class Element {
    constructor() {
      this.listeners = {};
      this.dataset = {};
      this.value = '';
      this.style = {};
      this.attributes = {};
      this.classList = {add() {}, remove() {}};
    }
    addEventListener(name, handler) { this.listeners[name] = handler; }
    setAttribute(name, value) { this.attributes[name] = value; }
    click() {
      const event = {prevented: false, preventDefault() { this.prevented = true; }};
      this.listeners.click?.(event);
      if (!event.prevented && this.href) opened.push(this.href);
    }
  }
  const element = id => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const query = element('#discovery-query');
  element('#broad-source').value = 'all';
  query.value = 'pokemon cards';
  const ebay = element('#discovery-ebay');
  ebay.dataset.discoverySource = 'ebay';
  ebay.href = urlFor('ebay', query.value);
  const facebook = element('#discovery-facebook');
  facebook.dataset.discoverySource = 'facebook';
  facebook.href = urlFor('facebook', query.value);
  const modes = ['all', 'sale', 'auction', 'offers'].map(mode => {
    const link = element(`#mode-${mode}`);
    link.dataset.discoverySource = 'ebay';
    link.dataset.discoveryMode = mode;
    link.href = urlFor('ebay', query.value, mode);
    return link;
  });
  const presets = [element('#scan-now'), element('#psa-preset')];
  presets.forEach((link, i) => {
    link.dataset.discoveryQuery = i ? 'pokemon PSA' : 'pokemon cards';
    link.href = urlFor('ebay', link.dataset.discoveryQuery);
  });
  const context = vm.createContext({
    URL, console, setTimeout() { return 1; }, clearTimeout() {},
    document: {
      querySelector: element,
      querySelectorAll(selector) {
        if (selector === '[data-discovery-source]') return [ebay, facebook, ...modes];
        if (selector === '[data-discovery-query]') return presets;
        return [];
      },
    },
    fetch(url, options = {}) {
      assert.ok(url.startsWith('/api/'), 'The app must not fetch an external site');
      requests.push({url, options});
      if (respond) return Promise.resolve({ok: true, json: async () => respond(url, options)});
      const query = new URL(url, 'http://127.0.0.1').searchParams.get('query');
      return Promise.resolve({ok: true, json: async () => ({
        query, budget, currency: 'CAD',
        search_links: {ebay: urlFor('ebay', query), facebook: urlFor('facebook', query)},
        search_modes: Object.fromEntries(['all', 'sale', 'auction', 'offers'].map(mode =>
          [mode, {ebay: urlFor('ebay', query, mode), facebook: urlFor('facebook', query)}])),
      })});
    },
  });
  const source = fs.readFileSync(path.join(__dirname, '../dashboard/static/js/snipe.js'), 'utf8');
  const startup = source.indexOf('const initial =');
  assert.ok(startup > 0);
  vm.runInContext(source.slice(0, startup), context);
  return {context, element, query, ebay, facebook, presets, modes, opened, requests, setBudget(value) { budget = value; }};
}

test('custom search opens synchronously with the typed query and saved cap', () => {
  const page = boot();
  page.query.value = '  eevee 123/456 & PSA  ';
  let prevented = false;
  page.element('#discovery-form').listeners.submit({preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(page.opened.length, 1, 'Opening must happen before any promise or fetch completes');
  const opened = new URL(page.opened[0]);
  assert.equal(opened.hostname, 'www.ebay.ca');
  assert.equal(opened.searchParams.get('_nkw'), 'eevee 123/456 & PSA');
  assert.equal(opened.searchParams.get('_udhi'), '100.00');
});

test('category click opens results and updates the shared query', () => {
  const page = boot();
  page.presets[1].click();
  assert.equal(page.opened.length, 1);
  assert.equal(new URL(page.opened[0]).searchParams.get('_nkw'), 'pokemon PSA');
  assert.equal(page.query.value, 'pokemon PSA');
});

test('Marketplace uses the current query rather than the last loaded metadata', () => {
  const page = boot();
  page.query.value = 'pokemon illustration rare';
  page.facebook.click();
  assert.equal(new URL(page.opened[0]).searchParams.get('query'), page.query.value);
  assert.equal(new URL(page.opened[0]).searchParams.get('maxPrice'), '100.00');
});

test('blank keywords open broad Pokemon results while preserving the saved budget', () => {
  const page = boot();
  page.query.value = '   ';
  page.element('#discovery-form').listeners.submit({preventDefault() {}});
  assert.equal(page.opened.length, 1);
  const url = new URL(page.opened[0]);
  assert.equal(url.searchParams.get('_nkw'), 'pokemon cards');
  assert.equal(url.searchParams.get('_udhi'), '100.00');
  assert.equal(url.searchParams.has('LH_BIN'), false);
});

test('reloading saved budget updates source links and every category', async () => {
  const page = boot();
  page.setBudget(60);
  await page.context.loadDiscovery();
  for (const link of [page.ebay, ...page.presets, ...page.modes]) {
    assert.equal(new URL(link.href).searchParams.get('_udhi'), '60.00');
  }
  assert.equal(new URL(page.facebook.href).searchParams.get('maxPrice'), '60.00');
  page.setBudget(null);
  await page.context.loadDiscovery();
  assert.equal(new URL(page.ebay.href).searchParams.has('_udhi'), false);
});

test('discount routes keep their mode while keywords and budgets change', async () => {
  const page = boot();
  page.query.value = 'pokemon card lot';
  page.setBudget(50);
  await page.context.loadDiscovery();
  for (const link of page.modes) {
    link.click();
    const url = new URL(page.opened.at(-1));
    assert.equal(url.searchParams.get('_nkw'), 'pokemon card lot');
    assert.equal(url.searchParams.get('_udhi'), '50.00');
    assert.equal(url.searchParams.has('LH_BIN'), false);
    assert.equal(url.searchParams.has('LH_SaleItems'), link.dataset.discoveryMode === 'sale');
    assert.equal(url.searchParams.has('LH_Auction'), link.dataset.discoveryMode === 'auction');
    assert.equal(url.searchParams.has('LH_BO'), link.dataset.discoveryMode === 'offers');
  }
});

test('returning to the app reloads the local portfolio before rendering its overview', async () => {
  const page = boot();
  const calls = [];
  page.element('.view.active').id = 'view-overview';
  page.context.recordLoad = name => calls.push(name);
  vm.runInContext(`
    loadCollection = async () => recordLoad('collection');
    LOADERS.overview = async () => recordLoad('overview');
    LOADERS.deals = async () => recordLoad('deals');
    LOADERS.listings = async () => recordLoad('listings');
  `, page.context);
  await page.context.pollSnipe();
  assert.deepEqual(calls, ['collection', 'overview', 'deals', 'listings']);
});

test('one click starts a broad scan and completion imports visible results without opening links', async () => {
  let running = true;
  const page = boot({respond(url) {
    if (url === '/api/snipe/discovery/scan') return {
      running, operation: 'broad', browser_scans_enabled: true, cooldown_seconds: 0,
      started: '2026-10-29T16:00:00Z', page_limit: 8, pages_done: running ? 1 : 8,
      candidates: 1, message: running ? 'Scanning broad pages' : 'Finished: 1 candidate', errors: [],
    };
    if (url === '/api/snipe/discovery/results') return {
      scan: {started: '2026-10-29T16:00:00Z', scanned: 1, errors: [], budget: 45, currency: 'CAD'},
      listings: [{id: 1, source: 'ebay', title: 'Any card <script>', url: 'https://www.ebay.ca/itm/12345678901',
        price: 20, total_price: null, currency: 'CAD', shipping: null, listing_type: 'bin',
        condition: 'Lightly Played', promotion: '10% off 3+ with coupon', discovery_routes: ['sale: pokemon cards'],
        last_seen: '2026-10-29T16:00:00Z'}],
    };
    assert.fail(`Unexpected request: ${url}`);
  }});
  page.context.loadOverview = async () => {};
  await page.element('#broad-scan').listeners.click();
  const posts = page.requests.filter(request => request.options.method === 'POST');
  assert.equal(posts.length, 1);
  assert.equal(posts[0].url, '/api/snipe/discovery/scan');
  assert.deepEqual(JSON.parse(posts[0].options.body), {source: 'all'});
  assert.equal(page.element('#broad-scan').disabled, true);
  assert.deepEqual(page.opened, []);
  running = false;
  await page.context.loadBroadStatus();
  assert.equal(page.element('#broad-result-count').textContent, '1 of 1 candidates');
  assert.match(page.element('#broad-results-table').innerHTML, /Any card &lt;script&gt;/);
  assert.match(page.element('#broad-results-table').innerHTML, /Lightly Played/);
  assert.match(page.element('#broad-results-table').innerHTML, /shipping unknown/);
  assert.equal(page.requests.filter(request => request.options.method === 'POST').length, 1,
    'Status polling must not start another external scan');
});

function priceFilterPage() {
  const listings = [
    ['shipping-included Evolving Skies PSA', 8, 15, 'ebay', 'bin'], ['upper-boundary Evolving Skies raw', 20, 20, 'ebay', 'auction'],
    ['above-with-shipping Base Set PSA', 16, 25, 'ebay'], ['unknown-shipping', 12, null, 'ebay'],
    ['unknown-price', null, null, 'ebay'], ['free-pickup', 0, 0, 'facebook'],
  ].map(([title, price, total_price, source, listing_type = 'bin'], id) => ({
    id, title, price, total_price, source, currency: 'CAD',
    shipping: total_price == null ? null : total_price - price,
    url: 'https://www.ebay.ca/itm/12345678901', listing_type, condition: '',
    promotion: '', discovery_routes: [], last_seen: '2026-10-29T16:00:00Z',
  }));
  return boot({respond(url) {
    assert.equal(url, '/api/snipe/discovery/results');
    return {listings, scan: {started: '2026-10-29T16:00:00Z', scanned: listings.length,
      errors: [], budget: 45, currency: 'CAD'}};
  }});
}

test('price bounds include shipping and endpoints, exclude unknown totals, and never start a scan', async () => {
  const page = priceFilterPage();
  await page.context.loadDiscoveryResults();
  assert.equal(page.element('#broad-result-count').textContent, '6 of 6 candidates');
  page.element('#broad-min-price').value = '15.00';
  page.element('#broad-max-price').value = '20.00';
  page.element('#broad-max-price').listeners.input();
  assert.equal(page.element('#broad-result-count').textContent, '2 of 6 candidates');
  const html = page.element('#broad-results-table').innerHTML;
  assert.match(html, /shipping-included/);
  assert.match(html, /upper-boundary/);
  assert.doesNotMatch(html, /above-with-shipping|unknown-shipping|unknown-price|free-pickup/);
  assert.match(page.element('#broad-price-help').textContent, /CAD/);
  assert.match(page.element('#broad-result-meta').textContent, /older scan capped at CAD 45\.00/);
  assert.equal(page.requests.length, 1, 'Filtering must not make any network requests');
  await page.context.loadDiscoveryResults();
  assert.equal(page.element('#broad-min-price').value, '15.00');
  assert.equal(page.element('#broad-max-price').value, '20.00');
  assert.equal(page.element('#broad-result-count').textContent, '2 of 6 candidates');
});

test('one-sided bounds, zero and clearing work with existing source and keyword filters', async () => {
  const page = priceFilterPage();
  await page.context.loadDiscoveryResults();
  page.element('#broad-max-price').value = '20';
  page.context.renderDiscoveryResults();
  assert.equal(page.element('#broad-result-count').textContent, '3 of 6 candidates');
  page.element('#broad-min-price').value = '0';
  page.element('#broad-max-price').value = '0';
  page.context.renderDiscoveryResults();
  assert.equal(page.element('#broad-result-count').textContent, '1 of 6 candidates');
  assert.match(page.element('#broad-results-table').innerHTML, /free-pickup/);
  page.element('#broad-min-price').value = '15';
  page.element('#broad-max-price').value = '';
  page.context.renderDiscoveryResults();
  assert.equal(page.element('#broad-result-count').textContent, '3 of 6 candidates');
  page.element('#broad-result-source').value = 'ebay';
  page.element('#broad-result-query').value = 'unknown';
  page.context.renderDiscoveryResults();
  assert.equal(page.element('#broad-result-count').textContent, '0 of 6 candidates');
  page.element('#broad-price-clear').click();
  assert.equal(page.element('#broad-result-count').textContent, '2 of 6 candidates');
  assert.equal(page.element('#broad-result-source').value, 'ebay');
  assert.equal(page.element('#broad-result-query').value, 'unknown');
  assert.equal(page.requests.length, 1);
});

test('set and type title filters combine with the high and low price limits without deciding value', async () => {
  const page = priceFilterPage();
  await page.context.loadDiscoveryResults();
  page.element('#broad-min-price').value = '15';
  page.element('#broad-max-price').value = '25';
  page.element('#broad-result-set').value = 'Evolving Skies';
  page.element('#broad-result-type').value = 'PSA';
  page.element('#broad-result-type').listeners.input();
  assert.equal(page.element('#broad-result-count').textContent, '1 of 6 candidates');
  assert.match(page.element('#broad-results-table').innerHTML, /shipping-included/);
  assert.doesNotMatch(page.element('#broad-results-table').innerHTML, /upper-boundary|above-with-shipping/);
  assert.doesNotMatch(page.element('#broad-results-table').innerHTML, /under value|worth buying|value play/);
  page.element('#broad-price-clear').click();
  assert.equal(page.element('#broad-result-set').value, 'Evolving Skies');
  assert.equal(page.element('#broad-result-type').value, 'PSA');
  assert.equal(page.requests.length, 1);
});

test('auction and fixed-price filters combine with price and site without starting a scan', async () => {
  const page = priceFilterPage();
  await page.context.loadDiscoveryResults();
  page.element('#broad-min-price').value = '15';
  page.element('#broad-max-price').value = '20';
  page.element('#broad-result-format').value = 'auction';
  page.element('#broad-result-format').listeners.change();
  assert.equal(page.element('#broad-result-count').textContent, '1 of 6 candidates');
  assert.match(page.element('#broad-results-table').innerHTML, /upper-boundary/);
  assert.doesNotMatch(page.element('#broad-results-table').innerHTML, /shipping-included/);
  page.element('#broad-result-format').value = 'bin';
  page.element('#broad-result-format').listeners.change();
  assert.equal(page.element('#broad-result-count').textContent, '1 of 6 candidates');
  assert.match(page.element('#broad-results-table').innerHTML, /shipping-included/);
  page.element('#broad-result-source').value = 'facebook';
  page.element('#broad-result-source').listeners.change();
  assert.equal(page.element('#broad-result-count').textContent, '0 of 6 candidates');
  page.element('#broad-price-clear').click();
  assert.equal(page.element('#broad-result-count').textContent, '1 of 6 candidates');
  assert.match(page.element('#broad-results-table').innerHTML, /free-pickup/);
  assert.equal(page.requests.length, 1);
});

test('invalid and reversed price ranges show an error instead of misleading results', async () => {
  const page = priceFilterPage();
  await page.context.loadDiscoveryResults();
  for (const [min, max] of [['21', '20'], ['-1', '20'], ['', 'Infinity'], ['NaN', '']]) {
    page.element('#broad-min-price').value = min;
    page.element('#broad-max-price').value = max;
    page.context.renderDiscoveryResults();
    assert.equal(page.element('#broad-result-count').textContent, '0 of 6 candidates');
    assert.match(page.element('#broad-price-help').textContent, /cannot exceed|non-negative/);
  }
  page.element('#broad-min-price').value = '';
  page.element('#broad-max-price').value = '';
  page.element('#broad-min-price').validity = {badInput: true};
  page.context.renderDiscoveryResults();
  assert.equal(page.element('#broad-min-price').attributes['aria-invalid'], 'true');
  assert.equal(page.element('#broad-result-count').textContent, '0 of 6 candidates');
});
