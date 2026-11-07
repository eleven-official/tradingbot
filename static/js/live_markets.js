/* LIVE MARKETS — a self-refreshing board of public quotes.
 *
 * Polls /api/markets/live every refresh_seconds while the view is open and
 * the tab is visible (no background traffic). Prices that move flash
 * green/red. A watchlist of extra symbols is saved in this browser
 * (account-scoped by scoped_storage.js). Clicking a tile opens its chart
 * and the AI engine's current, review-only read for that instrument.
 */
'use strict';
(() => {
  const root = document.getElementById('live-markets');
  if (!root) return;

  const WATCH_KEY = 'loki_live_watchlist_v1';
  const PREFS_KEY = 'loki_live_prefs_v1';
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const load = (key, fallback) => { try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch { return fallback; } };
  const store = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage full or blocked */ } };

  const prefs = { tab: 'all', tf: '1d', selected: null, ...load(PREFS_KEY, {}) };
  const ALERTS_KEY = 'loki_price_alerts_v1';
  let alerts = (load(ALERTS_KEY, []) || []).filter((a) => a && a.symbol && Number.isFinite(Number(a.price)) && (a.op === 'above' || a.op === 'below')).slice(0, 30);
  let watchlist = (load(WATCH_KEY, []) || []).filter((s) => typeof s === 'string').slice(0, 20);
  let board = null;
  let watchItems = [];
  let paused = false;
  let timer = null;
  let inflight = false;
  let refreshMs = 15000;
  let lastOkAt = 0;
  const lastPrice = new Map();
  const flashes = new Map();

  const savePrefs = () => store(PREFS_KEY, { tab: prefs.tab, tf: prefs.tf, selected: prefs.selected });

  function isActive() {
    return !root.hidden && !document.hidden;
  }

  // Board symbols → the engine's (Yahoo) spelling for charts and AI reads.
  function engineSymbol(symbol) {
    const s = String(symbol || '').toUpperCase();
    const pair = s.match(/^([A-Z0-9]{2,10})\/(USDT|USDC|USD|BUSD|FDUSD)$/);
    if (pair) return `${pair[1]}-USD`;
    return s;
  }

  function fmtPrice(value, symbol) {
    if (!Number.isFinite(value)) return '—';
    const fx = /=X$/.test(symbol || '');
    const digits = fx ? 4 : value >= 1000 ? 2 : value >= 1 ? 2 : value >= 0.01 ? 4 : 6;
    return value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }
  const fmtPct = (v) => (Number.isFinite(v) ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '—');

  function spark(values, up) {
    const pts = (values || []).filter(Number.isFinite);
    if (pts.length < 2) return '<svg class="lm-spark" viewBox="0 0 80 24" aria-hidden="true"></svg>';
    const lo = Math.min(...pts), hi = Math.max(...pts), span = hi - lo || 1;
    const d = pts.map((v, i) => `${i ? 'L' : 'M'}${(i / (pts.length - 1) * 80).toFixed(1)},${(22 - (v - lo) / span * 20).toFixed(1)}`).join(' ');
    return `<svg class="lm-spark ${up ? 'up' : 'down'}" viewBox="0 0 80 24" aria-hidden="true"><path pathLength="1" d="${d}"/></svg>`;
  }

  function allItems() {
    const items = [];
    for (const cat of (board && board.categories) || []) for (const item of cat.items) items.push({ ...item, cat: cat.key });
    for (const item of watchItems) items.push({ ...item, cat: 'watch' });
    return items;
  }

  function renderTabs() {
    const tabs = [['all', 'All'], ...(((board && board.categories) || []).map((c) => [c.key, c.label])), ['watch', `★ Watchlist (${watchlist.length})`]];
    $('lm-tabs').innerHTML = tabs.map(([key, label]) =>
      `<button type="button" role="tab" class="lm-tab${prefs.tab === key ? ' active' : ''}" aria-selected="${prefs.tab === key}" data-tab="${esc(key)}">${esc(label)}</button>`).join('');
  }

  function renderSessions() {
    const sessions = (board && board.sessions) || [];
    $('lm-sessions').innerHTML = sessions.map((s) =>
      `<span class="lm-session ${esc(s.state)}" title="${esc(s.detail)}"><span class="dot"></span>${esc(s.market)} · ${esc({ open: 'Open', closed: 'Closed', pre: 'Pre-market', post: 'After hours' }[s.state] || s.state)}</span>`).join('');
  }

  function renderMovers() {
    const m = (board && board.movers) || { gainers: [], losers: [] };
    const chip = (r) => `<button type="button" class="lm-mover ${r.change_pct >= 0 ? 'up' : 'down'}" data-symbol="${esc(r.symbol)}" data-label="${esc(r.label || r.symbol)}"><strong>${esc(r.label || r.symbol)}</strong> ${esc(fmtPct(r.change_pct))}</button>`;
    const parts = [];
    if (m.gainers.length) parts.push(`<span class="lm-movers-label">Leading</span>${m.gainers.map(chip).join('')}`);
    if (m.losers.length) parts.push(`<span class="lm-movers-label">Lagging</span>${m.losers.map(chip).join('')}`);
    $('lm-movers').innerHTML = parts.length
      ? parts.join('<span class="lm-sep" aria-hidden="true"></span>')
      : '<span class="lm-movers-label">Movers appear once the feeds answer.</span>';
  }

  function renderGrid() {
    const grid = $('lm-grid');
    let items = allItems();
    if (prefs.tab !== 'all') items = items.filter((i) => i.cat === prefs.tab);
    else items = items.filter((i, idx, arr) => arr.findIndex((j) => j.symbol === i.symbol) === idx);
    if (!items.length) {
      grid.innerHTML = prefs.tab === 'watch'
        ? '<p class="muted">Your watchlist is empty. Add a symbol above, or tap ☆ on any tile.</p>'
        : '<p class="muted">Waiting for the first quotes…</p>';
      return;
    }
    const now = Date.now();
    grid.classList.toggle('lm-animate', !grid.dataset.painted);
    grid.dataset.painted = '1';
    grid.innerHTML = items.map((item) => {
      const starred = watchlist.includes(item.symbol);
      const label = item.label || item.symbol;
      const star = `<span role="button" tabindex="0" class="lm-star${starred ? ' on' : ''}" data-star="${esc(item.symbol)}" aria-label="${starred ? 'Remove from' : 'Add to'} watchlist" title="${starred ? 'Remove from' : 'Add to'} watchlist">${starred ? '★' : '☆'}</span>`;
      if (!item.ok) {
        return `<div class="lm-tile degraded"><div class="lm-tile-top"><span class="lm-name">${esc(label)}</span>${star}</div><span class="lm-sym">${esc(item.symbol)}</span><span class="lm-err">${esc(item.error || 'unavailable')}</span></div>`;
      }
      const up = (item.change_pct ?? 0) >= 0;
      const flash = flashes.get(item.symbol);
      const flashCls = flash && now - flash.at < 1600 ? ` flash-${flash.dir}` : '';
      const sel = prefs.selected && prefs.selected.symbol === item.symbol ? ' selected' : '';
      const heat = Math.min(0.2, Math.abs(Number(item.change_pct) || 0) / 30).toFixed(3);
      return `<button type="button" class="lm-tile loki-glow${flashCls}${sel}" style="--heat:${heat};--heat-rgb:${up ? '168,240,198' : '255,179,167'}" data-symbol="${esc(item.symbol)}" data-label="${esc(label)}">` +
        `<div class="lm-tile-top"><span class="lm-name">${esc(label)}</span>${star}</div>` +
        `<span class="lm-sym">${esc(item.symbol)}</span>` +
        `<div class="lm-tile-mid"><span class="lm-price">${esc(fmtPrice(item.price, item.symbol))}</span>${spark(item.spark, up)}</div>` +
        `<span class="lm-chg ${up ? 'up' : 'down'}">${up ? '▲' : '▼'} ${esc(fmtPct(item.change_pct))}</span>` +
        `</button>`;
    }).join('');
  }

  function renderLive() {
    const el = $('lm-live'), text = $('lm-live-text');
    if (paused) { el.className = 'lm-live paused'; text.textContent = 'Paused'; return; }
    if (!lastOkAt) { el.className = 'lm-live'; text.textContent = 'Connecting…'; return; }
    const items = allItems();
    if (items.length && items.every((i) => !i.ok)) { el.className = 'lm-live stale'; text.textContent = 'Feeds unavailable · retrying'; return; }
    const age = Math.round((Date.now() - lastOkAt) / 1000);
    const stale = age > refreshMs / 1000 * 3;
    el.className = `lm-live${stale ? ' stale' : ' on'}`;
    text.textContent = stale ? `Stale · last update ${age}s ago` : `Live · updated ${age}s ago`;
  }

  function trackFlashes(items) {
    const now = Date.now();
    for (const item of items) {
      if (!item.ok || !Number.isFinite(item.price)) continue;
      const prev = lastPrice.get(item.symbol);
      if (prev !== undefined && prev !== item.price) flashes.set(item.symbol, { dir: item.price > prev ? 'up' : 'down', at: now });
      lastPrice.set(item.symbol, item.price);
    }
  }

  async function refresh(force) {
    if (inflight || (!force && (paused || !isActive()))) return;
    inflight = true;
    try {
      const requests = [fetch('/api/markets/live', { cache: 'no-store', signal: AbortSignal.timeout(20000) })];
      if (watchlist.length) requests.push(fetch(`/api/markets/quotes?symbols=${encodeURIComponent(watchlist.join(','))}`, { cache: 'no-store', signal: AbortSignal.timeout(20000) }));
      const [boardRes, watchRes] = await Promise.all(requests);
      if (!boardRes.ok) throw new Error(`board answered ${boardRes.status}`);
      board = await boardRes.json();
      refreshMs = Math.max(5, Number(board.refresh_seconds) || 15) * 1000;
      if (watchRes && watchRes.ok) watchItems = (await watchRes.json()).items || [];
      else if (!watchlist.length) watchItems = [];
      trackFlashes(allItems());
      checkAlerts(allItems());
      lastOkAt = Date.now();
      const degraded = Number(board.degraded) || 0;
      $('lm-message').textContent = degraded ? `${degraded} instrument(s) unavailable from their public feed right now — shown as such, never guessed.` : '';
      renderTabs(); renderSessions(); renderMovers(); renderGrid();
    } catch (error) {
      $('lm-message').textContent = `Could not reach the market feeds (${error.message || 'network'}). Retrying automatically.`;
    } finally {
      inflight = false;
      renderLive();
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(async () => { await refresh(false); schedule(); }, refreshMs);
  }

  // ---- price alerts (this browser only) ----------------------------------
  function toast(text) {
    const el = document.createElement('div');
    el.className = 'lm-toast'; el.setAttribute('role', 'alert'); el.textContent = text;
    document.body.appendChild(el);
    setTimeout(() => el.classList.add('out'), 6000);
    setTimeout(() => el.remove(), 6800);
  }
  function renderAlerts() {
    const chip = (a, i) => `<span class="lm-alert-chip">🔔 ${esc(a.label || a.symbol)} ${a.op === 'above' ? '≥' : '≤'} ${esc(fmtPrice(Number(a.price), a.symbol))}<button type="button" data-alert-del="${i}" aria-label="Remove alert">×</button></span>`;
    $('lm-alerts-all').innerHTML = alerts.length ? `<span class="lm-movers-label">Your alerts</span>${alerts.map(chip).join('')}` : '';
    const mine = prefs.selected ? alerts.map((a, i) => [a, i]).filter(([a]) => a.symbol === prefs.selected.symbol) : [];
    $('lm-alerts').innerHTML = mine.map(([a, i]) => chip(a, i)).join('');
  }
  function checkAlerts(items) {
    if (!alerts.length) return;
    const bySymbol = new Map(items.filter((i) => i.ok).map((i) => [i.symbol, i]));
    const fired = [];
    alerts = alerts.filter((a) => {
      const item = bySymbol.get(a.symbol);
      if (!item || !Number.isFinite(item.price)) return true;
      const hit = a.op === 'above' ? item.price >= a.price : item.price <= a.price;
      if (hit) fired.push({ ...a, now: item.price });
      return !hit;
    });
    if (!fired.length) return;
    store(ALERTS_KEY, alerts);
    for (const a of fired) {
      const text = `${a.label || a.symbol} is ${a.op} ${fmtPrice(Number(a.price), a.symbol)} — now ${fmtPrice(a.now, a.symbol)}`;
      toast('🔔 ' + text);
      try { if (window.Notification && Notification.permission === 'granted') new Notification('Loki price alert', { body: text }); } catch { /* unsupported */ }
    }
    renderAlerts();
  }

  // ---- watchlist ---------------------------------------------------------
  function toggleWatch(symbol) {
    const i = watchlist.indexOf(symbol);
    if (i >= 0) watchlist.splice(i, 1);
    else if (watchlist.length >= 20) { $('lm-message').textContent = 'Watchlist holds up to 20 symbols.'; return; }
    else watchlist.push(symbol);
    store(WATCH_KEY, watchlist);
    watchItems = watchItems.filter((w) => watchlist.includes(w.symbol));
    renderTabs(); renderGrid();
    if (i < 0) refresh(true);
  }

  // ---- detail: chart + AI read ------------------------------------------
  let chartCandles = [];
  function drawChart() {
    const canvas = $('lm-chart');
    const empty = $('lm-chart-empty');
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 600, height = 300;
    canvas.width = width * dpr; canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    if (!chartCandles.length) return;
    empty.hidden = true;
    const pad = { l: 8, r: 64, t: 12, b: 22 };
    const lows = chartCandles.map((c) => c.l), highs = chartCandles.map((c) => c.h);
    const lo = Math.min(...lows), hi = Math.max(...highs), span = hi - lo || 1;
    const y = (v) => pad.t + (1 - (v - lo) / span) * (height - pad.t - pad.b);
    const step = (width - pad.l - pad.r) / chartCandles.length;
    ctx.strokeStyle = 'rgba(162,181,196,.12)'; ctx.fillStyle = '#a2b5c4'; ctx.font = '11px ui-monospace, monospace'; ctx.lineWidth = 1;
    for (let g = 0; g <= 4; g += 1) {
      const v = lo + span * g / 4, yy = y(v);
      ctx.beginPath(); ctx.moveTo(pad.l, yy); ctx.lineTo(width - pad.r, yy); ctx.stroke();
      ctx.fillText(fmtPrice(v, prefs.selected && prefs.selected.symbol), width - pad.r + 6, yy + 4);
    }
    chartCandles.forEach((c, i) => {
      const x = pad.l + i * step + step / 2;
      const up = c.c >= c.o;
      ctx.strokeStyle = ctx.fillStyle = up ? '#a8f0c6' : '#ffb3a7';
      ctx.beginPath(); ctx.moveTo(x, y(c.h)); ctx.lineTo(x, y(c.l)); ctx.stroke();
      const top = y(Math.max(c.o, c.c)), bottom = y(Math.min(c.o, c.c));
      ctx.fillRect(x - Math.max(1, step * 0.32), top, Math.max(2, step * 0.64), Math.max(1, bottom - top));
    });
    const last = chartCandles[chartCandles.length - 1];
    const ly = y(last.c);
    ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(201,255,226,.5)';
    ctx.beginPath(); ctx.moveTo(pad.l, ly); ctx.lineTo(width - pad.r, ly); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = '#c9ffe2'; ctx.fillRect(width - pad.r + 2, ly - 9, pad.r - 4, 18);
    ctx.fillStyle = '#0a131c'; ctx.fillText(fmtPrice(last.c, prefs.selected && prefs.selected.symbol), width - pad.r + 6, ly + 4);
    ctx.fillStyle = '#a2b5c4';
    const first = chartCandles[0].t, end = last.t;
    ctx.fillText(String(first).slice(0, 10), pad.l, height - 6);
    ctx.fillText(String(end).slice(0, prefs.tf === '1d' ? 10 : 16).replace('T', ' '), width - pad.r - 110, height - 6);
  }

  async function loadChart() {
    if (!prefs.selected) return;
    const sym = engineSymbol(prefs.selected.symbol);
    const empty = $('lm-chart-empty');
    document.querySelectorAll('#lm-tf [data-tf]').forEach((b) => b.classList.toggle('active', b.dataset.tf === prefs.tf));
    try {
      const res = await fetch(`/api/fusion/ai/bars?symbol=${encodeURIComponent(sym)}&timeframe=${prefs.tf}&limit=120`, { cache: 'no-store', signal: AbortSignal.timeout(20000) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Chart data unavailable');
      if (!prefs.selected || engineSymbol(prefs.selected.symbol) !== sym) return;
      chartCandles = data.candles || [];
      drawChart();
    } catch (error) {
      chartCandles = [];
      drawChart();
      empty.hidden = false;
      empty.textContent = `${error.message || 'Chart data unavailable'} — the chart stays empty rather than inventing candles.`;
    }
  }

  function select(symbol, label) {
    prefs.selected = { symbol, label: label || symbol };
    savePrefs();
    $('lm-detail').hidden = false;
    $('lm-detail-title').textContent = `${label || symbol}`;
    $('lm-detail-eyebrow').textContent = `SELECTED · ${symbol}`;
    $('lm-ai-out').innerHTML = '<p class="caption">Runs the trained strategy\'s entry checklist on the last completed daily bar. Review only — nothing is bought.</p>';
    renderGrid();
    renderAlerts();
    loadChart();
  }

  const GATE_NAMES = { signal: 'Signal strength', volatility_cap: 'Volatility cap', trend_filter: '200-day trend filter', regime_filter: 'Regime filter', learned_filter: 'Learned from past mistakes' };

  async function askAi() {
    if (!prefs.selected) return;
    const sym = engineSymbol(prefs.selected.symbol);
    const out = $('lm-ai-out');
    const button = $('lm-ask-ai');
    if (!/^[A-Za-z0-9.^=\-]{1,12}$/.test(sym)) { out.innerHTML = '<p class="form-message">The AI engine cannot read this symbol format.</p>'; return; }
    button.disabled = true;
    out.innerHTML = '<p class="caption">Reading the last completed bar…</p>';
    try {
      const res = await fetch('/api/fusion/ai/step', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(25000),
        body: JSON.stringify({ symbol: sym, equity: 10000, cash: 10000 })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'AI engine unavailable');
      const trail = data.trail || [];
      const quant = trail.find((t) => t.agent === 'quant') || {};
      const risk = trail.find((t) => t.agent === 'risk') || {};
      const director = trail.find((t) => t.agent === 'director') || {};
      const plan = data.plan || {};
      const verdict = risk.approved && (quant.action || '').toUpperCase() === 'BUY' ? ['BUY setup', 'up'] : (quant.action || '').toUpperCase() === 'SELL' ? ['Exit / avoid', 'down'] : ['Wait', 'flat'];
      const gates = (plan.gates || []).map((g) => `<li><span class="${g.passed ? 'ok' : 'no'}">${g.passed ? '✓' : '✗'}</span> <strong>${esc(GATE_NAMES[g.name] || g.name)}</strong> <span class="muted">— ${esc(g.detail)}</span></li>`).join('');
      const sizing = risk.approved && risk.stop
        ? `<p class="caption">If taken with $10,000 paper: ${esc(Number(risk.qty).toFixed(4))} units · stop ${esc(fmtPrice(risk.stop, sym))} · target ${esc(fmtPrice(risk.target, sym))} · risks ${esc(risk.risk_pct_of_equity)}% at the stop.</p>`
        : '';
      out.innerHTML =
        `<div class="lm-verdict ${verdict[1]}"><strong>${esc(verdict[0])}</strong><span>${esc(director.thesis || '')}</span></div>` +
        (gates ? `<ul class="lm-gates">${gates}</ul>` : (plan.ready === false ? `<p class="caption">Warming up — ${esc(plan.bars)} of ${esc(plan.bars_needed)} bars of history.</p>` : '')) +
        sizing +
        `<p class="caption">${data.trained_profile_applied ? 'Using this symbol\'s trained, out-of-sample-checked profile.' : 'No trained profile for this symbol — default rules.'} Price ${esc(fmtPrice(data.price, sym))} · regime ${esc(data.regime || '—')}. Information, never advice.</p>`;
    } catch (error) {
      out.innerHTML = `<p class="form-message">${esc(error.message || 'AI engine unavailable')} — try again shortly.</p>`;
    } finally {
      button.disabled = false;
    }
  }

  // ---- wiring -------------------------------------------------------------
  root.addEventListener('click', (event) => {
    const star = event.target.closest('[data-star]');
    if (star) { event.preventDefault(); event.stopPropagation(); toggleWatch(star.dataset.star); return; }
    const tab = event.target.closest('[data-tab]');
    if (tab) { prefs.tab = tab.dataset.tab; savePrefs(); renderTabs(); renderGrid(); return; }
    const tf = event.target.closest('#lm-tf [data-tf]');
    if (tf) { prefs.tf = tf.dataset.tf; savePrefs(); loadChart(); return; }
    const tile = event.target.closest('[data-symbol]');
    if (tile) { select(tile.dataset.symbol, tile.dataset.label); $('lm-detail').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
  });
  root.addEventListener('keydown', (event) => {
    const star = event.target.closest('[data-star]');
    if (star && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); event.stopPropagation(); toggleWatch(star.dataset.star); }
  });
  $('lm-alert-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!prefs.selected) return;
    const price = Number($('lm-alert-price').value);
    if (!(price > 0)) { $('lm-message').textContent = 'Enter a positive alert price.'; return; }
    if (alerts.length >= 30) { $('lm-message').textContent = 'Up to 30 alerts at a time.'; return; }
    alerts.push({ symbol: prefs.selected.symbol, label: prefs.selected.label, op: $('lm-alert-op').value, price, created: Date.now() });
    store(ALERTS_KEY, alerts);
    $('lm-alert-price').value = '';
    renderAlerts();
    $('lm-message').textContent = 'Alert set. It checks on every board refresh while Loki is open in this browser.';
    try { if (window.Notification && Notification.permission === 'default') Notification.requestPermission(); } catch { /* unsupported */ }
    if (!watchlist.includes(prefs.selected.symbol) && !(board && board.categories.some((c) => c.items.some((i) => i.symbol === prefs.selected.symbol)))) toggleWatch(prefs.selected.symbol);
  });
  root.addEventListener('click', (event) => {
    const del = event.target.closest('[data-alert-del]');
    if (!del) return;
    alerts.splice(Number(del.dataset.alertDel), 1);
    store(ALERTS_KEY, alerts);
    renderAlerts();
  });
  $('lm-pause').addEventListener('click', () => {
    paused = !paused;
    $('lm-pause').textContent = paused ? 'Resume' : 'Pause';
    $('lm-pause').setAttribute('aria-pressed', String(paused));
    renderLive();
    if (!paused) refresh(true);
  });
  $('lm-refresh').addEventListener('click', () => refresh(true));
  $('lm-ask-ai').addEventListener('click', askAi);
  $('lm-trade-link').addEventListener('click', () => {
    if (!prefs.selected) return;
    const symbol = engineSymbol(prefs.selected.symbol);
    setTimeout(() => document.dispatchEvent(new CustomEvent('loki:ai-symbol', { detail: { symbol } })), 50);
  });
  $('lm-add-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = $('lm-add-input');
    const sym = input.value.trim().toUpperCase();
    if (!/^[A-Z0-9^.=\-/]{1,15}$/.test(sym)) { $('lm-message').textContent = 'Use a ticker like NFLX, ^FTSE, GC=F or a crypto pair like LINK/USDT.'; return; }
    input.value = '';
    if (!watchlist.includes(sym)) toggleWatch(sym);
    prefs.tab = 'watch'; savePrefs(); renderTabs(); renderGrid();
  });

  function onViewChange() {
    if (isActive()) {
      refresh(true);
      schedule();
      if (prefs.selected && $('lm-detail').hidden) select(prefs.selected.symbol, prefs.selected.label);
    }
  }
  document.addEventListener('loki:view', onViewChange);
  document.addEventListener('visibilitychange', onViewChange);
  window.addEventListener('resize', () => { if (isActive() && chartCandles.length) drawChart(); });
  setInterval(() => { if (isActive()) { renderLive(); if (flashes.size) renderGrid(); flashes.forEach((f, k) => { if (Date.now() - f.at > 1600) flashes.delete(k); }); } }, 1000);
  renderTabs();
  renderAlerts();
  onViewChange();
})();
