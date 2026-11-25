(async () => {
  const head = document.getElementById('head'), text = document.getElementById('text');
  const raw = location.hash.slice(1);
  history.replaceState(null, '', location.pathname);
  try {
    if (!raw) throw new Error('Nothing was sent. Use the bookmark on an eBay results page.');
    const response = await fetch('/api/snipe/capture', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: decodeURIComponent(raw)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The listings could not be saved.');
    head.textContent = 'Sent to Card desk';
    text.textContent = data.message;
  } catch (error) {
    head.textContent = 'Could not send';
    text.textContent = error.message;
  }
})();
