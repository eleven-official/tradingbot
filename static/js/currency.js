/* Display currency switcher (AUD | USD).
 *
 * AUD is the default and the choice persists. The trading ledger itself
 * always stays in USD (market prices are USD quotations); this module only
 * converts what is DISPLAYED, so paper P&L math is never mixed.
 * Fetches a live reference rate once per page view (frankfurter.app), with
 * a fixed fallback if the rate service is unreachable.
 */
'use strict';
(() => {
  const STORAGE_KEY = 'loki_currency';
  const FALLBACK_RATE = 1.53; // AUD per 1 USD, used until a rate loads

  let current = 'AUD';
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'AUD' || saved === 'USD') current = saved;
  } catch { /* storage blocked: stay on the default */ }

  let rate = FALLBACK_RATE;
  let rateLive = false;

  const listeners = new Set();

  const emit = () => {
    document.dispatchEvent(new CustomEvent('loki:currency', { detail: get() }));
    updateFxNote();
  };

  const loadRate = async () => {
    // Rates are fetched server-side (cached 30 min) so the browser never
    // makes cross-origin FX requests and never logs CORS noise.
    try {
      const res = await fetch('/api/fx/rate', { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        const aud = Number(data.rate);
        if (aud > 0) {
          rate = aud;
          rateLive = data.live === true;
          rateAt = new Date();
          emit();
        }
      }
    } catch { /* keep the fallback rate */ }
  };

  let rateAt = null;

  const updateFxNote = () => {
    const note = document.getElementById('loki-fx-note');
    if (!note) return;
    const when = rateAt ? ` · updated ${new Intl.DateTimeFormat([], { hour: '2-digit', minute: '2-digit' }).format(rateAt)}` : '';
    note.textContent = current === 'AUD'
      ? `US$1 → A$${rate.toFixed(2)} · ${rateLive ? 'live rate' : 'fallback rate'}${when}`
      : 'Ledger stays in US$ · showing plain USD';
    note.title = 'Market prices and paper math are always USD. The AUD option only converts what is displayed.';
  };

  const get = () => ({ code: current, rate, rateLive });

  const set = (code) => {
    if (code !== 'AUD' && code !== 'USD') return;
    if (code === current) return;
    current = code;
    try { localStorage.setItem(STORAGE_KEY, code); } catch { /* ignore */ }
    updateButtons();
    emit();
  };

  /** Convert a USD amount into the display currency string. */
  const format = (usdValue) => {
    const value = Number(usdValue) || 0;
    const converted = current === 'AUD' ? value * rate : value;
    const body = Math.abs(converted).toLocaleString('en-AU', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
    const symbol = current === 'AUD' ? 'A$' : 'US$';
    return (value < 0 ? '-' : '') + symbol + body;
  };

  const buildSwitcher = () => {
    const bar = document.createElement('div');
    bar.className = 'loki-currency';
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', 'Display currency');
    const mk = (code) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cur-opt';
      button.dataset.cur = code;
      button.textContent = code;
      button.setAttribute('aria-pressed', 'false');
      button.addEventListener('click', () => set(code));
      return button;
    };
    bar.append(mk('AUD'), mk('USD'));
    const note = document.createElement('span');
    note.className = 'cur-rate-note';
    note.id = 'loki-fx-note';
    note.setAttribute('aria-live', 'polite');
    bar.append(note);
    document.body.appendChild(bar);
    updateButtons();
    updateFxNote();
  };

  function updateButtons() {
    document.querySelectorAll('.loki-currency .cur-opt').forEach((button) => {
      const active = button.dataset.cur === current;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  window.LokiCurrency = { get, set, format, subscribe: (fn) => (listeners.add(fn), () => listeners.delete(fn)) };
  document.addEventListener('DOMContentLoaded', buildSwitcher);
  loadRate();
})();