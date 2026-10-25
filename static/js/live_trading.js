/* Explicit-start live Alpaca controller. Broker facts only; no local fills. */
'use strict';
(() => {
  const el = id => document.getElementById(id);
  let connection = null, runner = null, busy = false, timer = null, generation = 0;
  let lastError = '';
  const connected = () => connection?.provider === 'alpaca' && connection?.mode === 'live' && connection?.connected;
  const note = text => { el('ai-live-message').textContent = text; };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function api(path, body) {
    if (!capabilities) await loadCapabilities();
    if (!capabilities?.local_actions_enabled) throw new Error('Live trading requires the local Loki launcher.');
    return request('/api/fusion/broker/live-ai' + path, body, true);
  }
  function render() {
    const account = connection?.account;
    el('ai-live-account').textContent = connected() && account
      ? `Alpaca LIVE · account ending ${account.id_hint} · cash ${account.cash} USD · equity ${account.equity} USD (last account refresh)`
      : 'No verified live account details loaded. Connect or refresh the broker account.';
    el('ai-live-status').textContent = !connected() ? 'Disconnected' : runner?.running ? 'LIVE · running' : 'LIVE · stopped';
    el('ai-live-start').disabled = busy || !connected() || !!runner?.running;
    el('ai-live-fields').disabled = busy || !!runner?.running;
    el('ai-live-stop').disabled = !connected() || !runner?.running;
    el('ai-live-refresh').disabled = busy || !connected();
    if (lastError || runner?.message) note(lastError || runner.message);
    el('ai-live-journal').innerHTML = (runner?.journal || []).length
      ? '<table><thead><tr><th>UTC day</th><th>Order</th><th>Broker status</th><th>Confirmed fill</th></tr></thead><tbody>' + runner.journal.map(r => `<tr><td>${esc(r.day)}</td><td>${esc(r.request.side)} ${esc(r.request.qty)} ${esc(r.request.symbol)}</td><td>${esc(r.order?.status || 'Unconfirmed — reconcile')}</td><td>${esc(r.order?.filled_qty ?? 'Unknown')} @ ${esc(r.order?.filled_avg_price ?? '—')}</td></tr>`).join('') + '</tbody></table>'
      : '<p class="caption">No live order claims for this connected account.</p>';
  }
  function schedule() {
    clearTimeout(timer);
    if (runner?.running && runner.controlled_by_this_session) timer = setTimeout(cycle, 20000);
  }
  async function cycle() {
    if (busy) { schedule(); return; }
    if (!connected() || !runner?.running || !runner.controlled_by_this_session) return;
    const revision = generation;
    lastError = '';
    busy = true;
    try {
      const data = await api('/tick', {});
      if (revision === generation) runner = data;
    } catch (error) {
      if (revision === generation) { if (runner) runner.running = false; lastError = error.message; }
    } finally { busy = false; render(); schedule(); }
  }
  async function stop() {
    lastError = '';
    generation++;
    clearTimeout(timer);
    // Stop remains usable while a cycle is in flight. Server preserves it.
    if (runner) runner.running = false;
    render();
    try { runner = await api('/stop', {}); render(); }
    catch (error) { lastError = 'Stop could not be confirmed. The 90-second heartbeat expires automatically; existing broker orders remain. ' + error.message; render(); }
  }
  async function refresh() {
    if (!connected()) return;
    try { runner = await api(''); render(); }
    catch (error) { note(error.message); }
  }
  function init() {
    if (!el('ai-live-form')) return;
    document.querySelectorAll('[data-trading-scroll]').forEach(button => button.addEventListener('click', () => el(button.dataset.tradingScroll).scrollIntoView({block:'start', behavior:'smooth'})));
    el('ai-live-connect').addEventListener('click', () => el('connect-live-broker').click());
    el('ai-live-stop').addEventListener('click', stop);
    el('ai-live-refresh').addEventListener('click', async () => {
      if (busy) return;
      lastError = ''; busy = true; render();
      try { runner = await api('/reconcile', {}); }
      catch (error) { lastError = error.message; }
      finally { busy = false; render(); }
    });
    el('ai-live-form').addEventListener('submit', async event => {
      event.preventDefault();
      if (busy || !connected()) return;
      const form = new FormData(event.target);
      const body = {symbol: form.get('symbol'), max_notional: Number(form.get('max_notional')), daily_loss: Number(form.get('daily_loss')), max_orders: Number(form.get('max_orders'))};
      lastError = ''; busy = true; render();
      try {
        runner = await api('/start', body);
        const chart = el('ai-chart-symbol'); chart.value = body.symbol; chart.dispatchEvent(new Event('change'));
        generation++;
      } catch (error) { lastError = error.message; }
      finally { busy = false; render(); schedule(); }
    });
    window.addEventListener('loki-broker-connection', event => {
      generation++; clearTimeout(timer); runner = null; lastError = ''; connection = event.detail; render(); refresh();
    });
    // Reading a pre-existing session never silently resumes its heartbeat.
    if (window.lokiBrokerWorkspace?.summary) {
      const summary = window.lokiBrokerWorkspace.summary();
      if (summary) { connection = {...summary, connected: true}; refresh(); }
    }
    render();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
