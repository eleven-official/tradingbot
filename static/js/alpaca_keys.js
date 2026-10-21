/* Alpaca paper-key connection (browser-held keys; explicit paper orders).
 *
 * The keys live ONLY in this browser (localStorage: loki_alpaca_keys_v1) and
 * are sent per-request to Loki's relay, which talks only to Alpaca's PAPER
 * endpoint — account facts, plus paper orders the user clicks (armed, then
 * confirmed, day-only, 100 shares a ticket, mirrored with the relay's caps).
 * No storage server-side, and the keys are deliberately kept OUT of the
 * workspace backup export.
 */
'use strict';
(() => {
  const KEY = 'loki_alpaca_keys_v1';
  const viewActive = () => location.hash === '#real-market';
  let busy = false, connected = false, verifiedFor = null;

  const load = () => {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return null;
      const value = JSON.parse(raw);
      return (value && typeof value.key_id === 'string' && typeof value.secret_key === 'string' && value.key_id && value.secret_key) ? value : null;
    } catch { return null; }
  };
  const save = (value) => { try { localStorage.setItem(KEY, JSON.stringify(value)); } catch { /* storage blocked */ } };
  const wipe = () => { try { localStorage.removeItem(KEY); } catch { /* ignore */ } };
  const mask = (keyId) => keyId && keyId.length > 6 ? `${keyId.slice(0, 3)}••••••${keyId.slice(-3)}` : '••••';

  function controls() {
    $('#alpaca-clear').disabled = busy || !load();
    if ($('#alpaca-order-send')) $('#alpaca-order-send').disabled = busy;
  }

  function statusTag() {
    const saved = load();
    $('#alpaca-status').textContent = saved ? `Keys held in this browser (${mask(saved.key_id)})` : 'No keys in this browser';
  }

  function renderAccount(data) {
    const target = $('#alpaca-account');
    target.replaceChildren();
    if (!connected || !data) {
      target.append(element('p', 'Account facts appear once the keys verify against Alpaca.', 'muted'));
      return;
    }
    const usd = (value) => value == null ? 'unavailable' : `US$${number(value)}`;
    const labels = element('p', `Alpaca PAPER · status ${human(data.status).toUpperCase()} · account ••••${(data.account_number || '—').slice(-4)}`, 'integration-note');
    target.append(labels);
    target.append(inlineMetrics([
      ['Cash', usd(data.cash), 'Alpaca reports in USD'],
      ['Equity', usd(data.equity)],
      ['Buying power', usd(data.buying_power)]
    ]));
    if (data.trading_blocked || data.account_blocked) {
      target.append(element('p', 'Alpaca flags this account as trading/blocked — check your Alpaca dashboard before expecting anything.', 'integration-note'));
    }
    target.append(element('p', 'Account facts and the order log come from Alpaca\'s paper endpoint; orders are placed only when you click, armed then confirmed.', 'caption'));
  }

  /* ---------- autopilot (paper, tab-open only, published rule) ---------- */
  const AUTOPILOT_TICK_MS = 60000;
  const AUTOPILOT_SMA = 10;
  const AUTOPILOT_MAX_ORDERS = 10;
  const AUTOPILOT_COOLDOWN_MS = 90000;
  const autopilot = { on: false, timer: 0, held: false, lastSide: null, orders: 0, lastSendAt: 0 };

  function autopilotLog(text, error) {
    const node = $('#alpaca-autopilot-log');
    if (!node) return;
    const row = document.createElement('li');
    row.textContent = text;
    if (error) row.className = 'autopilot-row-error';
    node.prepend(row);
    while (node.children.length > 30) node.removeChild(node.lastChild);
  }

  function autopilotStatus(text) {
    const node = $('#alpaca-autopilot-status');
    if (node) node.textContent = text;
  }

  function stopAutopilot(reason) {
    if (autopilot.on && reason) autopilotLog('Stopped: ' + reason);
    autopilot.on = false;
    if (autopilot.timer) { window.clearInterval(autopilot.timer); autopilot.timer = 0; }
    const sw = $('#alpaca-autopilot-switch');
    if (sw && sw.checked) sw.checked = false;
    autopilotStatus('Autopilot off');
  }

  function startAutopilot() {
    const saved = load();
    if (!connected || !saved) {
      autopilotLog('Switch stayed off — the keys are not verified with Alpaca.', true);
      const sw = $('#alpaca-autopilot-switch');
      if (sw) sw.checked = false;
      return;
    }
    const symbolEl = $('#alpaca-order-symbol');
    if (!symbolEl || !String(symbolEl.value || '').trim()) {
      autopilotLog('Switch stayed off — type a ticker in the order form first; the autopilot uses it.', true);
      const sw = $('#alpaca-autopilot-switch');
      if (sw) sw.checked = false;
      return;
    }
    autopilot.on = true;
    autopilotStatus('Autopilot on · runs while this tab is open, off the moment it is not.');
    autopilotLog('Autopilot ON: ' + AUTOPILOT_SMA + '-bar rule on 1-minute bars, 1 share per crossing, only sells what it bought, ' + AUTOPILOT_MAX_ORDERS + ' orders max this session.');
    autopilotTick();
    autopilot.timer = window.setInterval(autopilotTick, AUTOPILOT_TICK_MS);
  }

  async function autopilotTick() {
    if (!autopilot.on) return;
    if (document.hidden || viewActive() === false) return; // paused while out of sight; resumes by the clock
    if (busy) return; // a manual action owns the lane; the next tick reprices
    if (autopilot.orders >= AUTOPILOT_MAX_ORDERS) {
      stopAutopilot('the session ceiling of ' + AUTOPILOT_MAX_ORDERS + ' orders was reached.');
      return;
    }
    if (autopilot.lastSendAt && Date.now() - autopilot.lastSendAt < AUTOPILOT_COOLDOWN_MS) return;
    const saved = load();
    if (!saved || !connected) {
      stopAutopilot('the keys stopped verifying — the rule does not run unverified.');
      return;
    }
    const symbol = String(($('#alpaca-order-symbol') || {}).value || '').trim().toUpperCase();
    if (!symbol) {
      stopAutopilot('the ticker box went empty — nothing to price.');
      return;
    }
    busy = true;
    try {
      const answer = await request('/api/broker/alpaca/bars', { key_id: saved.key_id, secret_key: saved.secret_key, symbol });
      const bars = Array.isArray(answer.bars) ? answer.bars : [];
      const closes = bars.map((bar) => Number(bar.c)).filter((c) => Number.isFinite(c) && c > 0);
      if (closes.length < AUTOPILOT_SMA + 1) {
        autopilotStatus('Autopilot on · waiting for enough bars (' + closes.length + '/' + (AUTOPILOT_SMA + 1) + ') — nothing traded, nothing invented.');
        return;
      }
      const avg = closes.slice(-AUTOPILOT_SMA).reduce((s, c) => s + c, 0) / AUTOPILOT_SMA;
      const latest = closes[closes.length - 1];
      const side = latest > avg ? 'above' : (latest < avg ? 'below' : autopilot.lastSide);
      autopilotStatus('Autopilot on · ' + symbol + ' ' + latest.toFixed(2) + ' vs ' + AUTOPILOT_SMA + '-bar avg ' + avg.toFixed(2) + ' — ' + (side === 'above' ? 'above' : side === 'below' ? 'below' : 'level') + ' · ' + autopilot.orders + '/' + AUTOPILOT_MAX_ORDERS + ' orders this session');
      if (autopilot.lastSide && side && side !== autopilot.lastSide) {
        const crossingUp = side === 'above' && autopilot.lastSide === 'below' && !autopilot.held;
        const crossingDown = side === 'below' && autopilot.lastSide === 'above' && autopilot.held;
        if (crossingUp || crossingDown) {
          const action = crossingUp ? 'buy' : 'sell';
          const body = { key_id: saved.key_id, secret_key: saved.secret_key, symbol, side: action, quantity: 1, order_type: 'market' };
          const sent = await request('/api/broker/alpaca/order', body);
          autopilot.held = crossingUp;
          autopilot.orders += 1;
          autopilot.lastSendAt = Date.now();
          const status = String((sent.order || {}).status || 'unknown').toLowerCase();
          autopilotLog('Crossing ' + (crossingUp ? 'up' : 'down') + ' (' + latest.toFixed(2) + ' vs avg ' + avg.toFixed(2) + ') → sent ' + action.toUpperCase() + ' 1 ' + symbol + ' @ market — Alpaca status: ' + status + '.');
        } else {
          autopilotLog('Crossing ' + (side === 'above' ? 'up' : 'down') + ' noted — no action this side of the rule (' + (autopilot.held ? 'holding its own share' : 'no position of its own') + ').');
        }
      }
      autopilot.lastSide = side;
    } catch (error) {
      autopilotLog('Check failed, no trade: ' + (error.message || 'the bars could not be read right now.'), true);
    } finally {
      busy = false;
      controls();
    }
  }
  const ORDER_QTY_MAX = 100; // mirrors the relay cap — a guard, not advice
  const LIMIT_PRICE_MAX = 10000; // mirrors the relay cap
  let orderArmed = null, orderArmTimer = 0;

  function disarmOrder() {
    orderArmed = null;
    if (orderArmTimer) { window.clearTimeout(orderArmTimer); orderArmTimer = 0; }
    const send = $('#alpaca-order-send');
    if (send) send.textContent = 'Place paper order →';
  }

  function recap(symbol, side, qty, type, limit) {
    const kind = type === 'limit' ? `limit @ US$${limit}` : 'market (day)';
    return `${String(side).toUpperCase()} ${qty} ${symbol} — ${kind}`;
  }

  function idleOrders(text) {
    const log = $('#alpaca-order-log');
    if (!log) return;
    log.replaceChildren();
    log.append(element('p', text || 'The order log fills once the keys verify and an order moves.', 'muted'));
  }

  function renderOrders(rows) {
    const log = $('#alpaca-order-log');
    if (!log) return;
    log.replaceChildren();
    if (!Array.isArray(rows) || !rows.length) {
      log.append(element('p', 'No orders on Alpaca\'s paper book yet — this log shows only what actually exists.', 'muted'));
      return;
    }
    rows.forEach((order) => {
      if (!order || typeof order !== 'object') return;
      const status = String(order.status || 'unknown').toLowerCase();
      const quiet = status === 'rejected' || status === 'canceled';
      const row = document.createElement('div');
      row.className = 'order-row' + (quiet ? ' order-row-quiet' : '');
      row.title = 'Alpaca paper order · day-only, regular hours';
      row.append(element('span', `${String(order.symbol || '?').toUpperCase()} · ${String(order.side || '?').toUpperCase()} · ${order.qty} × ${order.type || '?'}`, 'order-what'));
      row.append(element('span', status, 'order-status'));
      if (order.filled_avg_price != null) row.append(element('span', `filled @ US$${number(order.filled_avg_price)}`, 'order-price'));
      row.append(element('span', String(order.created_at || '').replace('T', ' ').slice(0, 16), 'order-when'));
      log.append(row);
    });
  }

  function clearOrders() {
    disarmOrder();
    idleOrders('Verify the keys to see the paper order log — nothing is invented in its place.');
  }

  async function fetchOrders() {
    const saved = load();
    if (!saved || !connected) { clearOrders(); return; }
    try {
      const answer = await request('/api/broker/alpaca/orders', { key_id: saved.key_id, secret_key: saved.secret_key });
      renderOrders(answer.orders);
    } catch (error) {
      idleOrders(error.message || 'The order log could not be read right now.');
    }
  }

  async function placeOrder(event) {
    event.preventDefault();
    if (busy) return;
    const saved = load();
    if (!connected || !saved) {
      disarmOrder();
      message('#alpaca-order-message', 'Verify the keys first — the order rail only moves after Alpaca confirms them.', true);
      return;
    }
    const symbolEl = $('#alpaca-order-symbol'), qtyEl = $('#alpaca-order-qty'),
      sideEl = $('#alpaca-order-side'), typeEl = $('#alpaca-order-type'), limitEl = $('#alpaca-order-limit');
    if (!symbolEl || !qtyEl || !sideEl || !typeEl) return;
    const symbol = String(symbolEl.value || '').trim().toUpperCase();
    const qty = Math.floor(Number(qtyEl.value || 0));
    const side = sideEl.value === 'sell' ? 'sell' : 'buy';
    const type = typeEl.value === 'limit' ? 'limit' : 'market';
    const limitRaw = limitEl ? String(limitEl.value || '').trim() : '';
    const limit = limitRaw ? Number(limitRaw) : null;
    if (!symbol) {
      message('#alpaca-order-message', 'Type the symbol — the order rides on it.', true);
      return;
    }
    if (!qty || qty < 1) {
      message('#alpaca-order-message', 'A share count of at least one is needed.', true);
      return;
    }
    if (qty > ORDER_QTY_MAX) {
      message('#alpaca-order-message', `The rail caps orders at ${ORDER_QTY_MAX} shares a ticket (a relay guard, not advice).`, true);
      return;
    }
    if (type === 'limit' && (!limit || limit <= 0)) {
      message('#alpaca-order-message', 'A limit order needs a limit price.', true);
      return;
    }
    if (type === 'limit' && limit > LIMIT_PRICE_MAX) {
      message('#alpaca-order-message', `The relay refuses limit prices above US$${LIMIT_PRICE_MAX} — a guard, not advice.`, true);
      return;
    }
    const summary = recap(symbol, side, qty, type, limitRaw);
    if (orderArmed !== summary) {
      orderArmed = summary;
      const send = $('#alpaca-order-send');
      if (send) send.textContent = 'Confirm — send to Alpaca PAPER';
      message('#alpaca-order-message', `Review: ${summary}. A real order on your Alpaca PAPER account (day-only, regular hours). Press again within 15 s to send it.`);
      orderArmTimer = window.setTimeout(() => { disarmOrder(); message('#alpaca-order-message', 'The order stayed in the drawer — the confirmation window closed.'); }, 15000);
      return;
    }
    busy = true;
    controls();
    message('#alpaca-order-message', 'Sending to Alpaca paper…');
    try {
      const body = { key_id: saved.key_id, secret_key: saved.secret_key, symbol, side, quantity: qty, order_type: type };
      if (type === 'limit') body.limit_price = limit;
      const answer = await request('/api/broker/alpaca/order', body);
      disarmOrder();
      const status = String((answer.order || {}).status || 'unknown').toLowerCase();
      message('#alpaca-order-message', `Sent to Alpaca paper: ${summary} — Alpaca's status: ${status}.` + (status === 'rejected' ? ' Alpaca refused it; the log will show it as-is.' : ''));
      await fetchOrders();
    } catch (error) {
      disarmOrder();
      message('#alpaca-order-message', error.message || 'Alpaca did not answer the order; nothing was confirmed.', true);
    } finally {
      busy = false;
      controls();
    }
  }

  async function verify() {
    const saved = load();
    if (!saved) {
      connected = false;
      statusTag();
      renderAccount(null);
      clearOrders();
      stopAutopilot();
      controls();
      return;
    }
    busy = true;
    connected = false;
    controls();
    message('#alpaca-message', 'Checking keys with Alpaca\'s paper endpoint…');
    try {
      const body = { key_id: saved.key_id, secret_key: saved.secret_key };
      const test = await request('/api/broker/alpaca/test', body);
      if (!test.ok) throw new Error(test.message || 'Alpaca did not confirm those keys.');
      connected = true;
      statusTag();
      const facts = await request('/api/broker/alpaca/account', body);
      renderAccount(facts);
      message('#alpaca-message', 'Keys verified — Alpaca confirmed this account on the paper endpoint.');
      fetchOrders();
    } catch (error) {
      stopAutopilot('Keys stopped verifying with Alpaca.');
      renderAccount(null);
      message('#alpaca-message', error.message || 'The Alpaca check failed.', true);
    } finally {
      busy = false;
      controls();
    }
  }

  $('#alpaca-keys-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (busy) return;
    const keyId = $('#alpaca-key-id').value.trim();
    const secretKey = $('#alpaca-secret-key').value.trim();
    if (!keyId || !secretKey) {
      message('#alpaca-message', 'Both a key ID and a secret key are needed.', true);
      return;
    }
    save({ key_id: keyId, secret_key: secretKey });
    $('#alpaca-key-id').value = '';
    $('#alpaca-secret-key').value = '';
    await verify();
  });

  $('#alpaca-clear').addEventListener('click', () => {
    if (busy) return;
    wipe();
    connected = false;
    statusTag();
    renderAccount(null);
    clearOrders();
    stopAutopilot('Keys were forgotten.');
    message('#alpaca-message', 'Keys forgotten — nothing stays in this browser.');
  });

  const orderForm = $('#alpaca-order-form');
  if (orderForm) {
    orderForm.addEventListener('submit', placeOrder);
    const typeEl = $('#alpaca-order-type'), limitWrap = $('#alpaca-order-limit-wrap'), limitEl = $('#alpaca-order-limit');
    if (typeEl && limitWrap) {
      const syncLimit = () => {
        limitWrap.hidden = typeEl.value !== 'limit';
        if (limitEl) limitEl.required = typeEl.value === 'limit';
      };
      typeEl.addEventListener('change', syncLimit);
      syncLimit();
    }
    const refresh = $('#alpaca-orders-refresh');
    if (refresh) refresh.addEventListener('click', (event) => { event.preventDefault(); if (!busy) fetchOrders(); });
  }

  const autoSwitch = $('#alpaca-autopilot-switch');
  if (autoSwitch) {
    autoSwitch.addEventListener('change', () => {
      if (autoSwitch.checked) startAutopilot();
      else stopAutopilot('the switch went off.');
    });
  }

  // Verify on arrival — but only when the stored keys changed since the last
  // check. A fingerprint on the key ID (not object identity) keeps repeat
  // visits from re-hitting Alpaca's endpoint without reason.
  window.addEventListener('hashchange', () => {
    if (viewActive() && !busy) {
      const saved = load();
      const fingerprint = saved ? saved.key_id : null;
      if (fingerprint && verifiedFor !== fingerprint) verify();
    }
  });

  statusTag();
  renderAccount(null);
  clearOrders();
  stopAutopilot();
  const savedOnInit = load();
  if (viewActive() && savedOnInit) {
    verifiedFor = savedOnInit.key_id;
    verify();
  }
  controls();
  // Debugging + verification handle (local testing only; the relay alone
  // decides what Alpaca accepts, so a faked `connected` flag in a console
  // still cannot move a single order).
  window.LokiAlpaca = {
    state: autopilot,
    start: startAutopilot,
    stop: stopAutopilot,
    tick: autopilotTick,
    _debug: { setConnected(value) { connected = !!value; } },
  };
})();
