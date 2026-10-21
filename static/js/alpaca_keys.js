/* Alpaca paper-key connection (read-only, browser-held keys).
 *
 * The keys live ONLY in this browser (localStorage: loki_alpaca_keys_v1) and
 * are sent per-request to Loki's read-only relay, which talks only to Alpaca's
 * PAPER endpoint for account facts. No orders, no storage server-side, and the
 * keys are deliberately kept OUT of the workspace backup export.
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
    target.append(element('p', 'Read-only facts from Alpaca\'s paper endpoint. This link never places orders.', 'caption'));
  }

  async function verify() {
    const saved = load();
    if (!saved) {
      connected = false;
      statusTag();
      renderAccount(null);
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
    } catch (error) {
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
    message('#alpaca-message', 'Keys forgotten — nothing stays in this browser.');
  });

  // Verify once per view arrival; never on page background.
  window.addEventListener('hashchange', () => {
    if (viewActive() && verifiedFor !== load() && !busy) {
      verifiedFor = load() || 'unchecked';
      if (load()) verify();
    }
  });

  statusTag();
  renderAccount(null);
  if (viewActive() && load()) {
    verifiedFor = 'init';
    verify();
  }
  controls();
})();
