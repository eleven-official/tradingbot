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
    const seen = rateAt ? ` · updated ${new Intl.DateTimeFormat([], { hour: '2-digit', minute: '2-digit' }).format(rateAt)}` : '';
    const explainer = rateLive
      ? `Live rate${seen}`
      : `Fallback rate (rate service unreachable)${seen}`;
    const inline = document.getElementById('loki-fx-inline');
    if (!inline) return;
    inline.hidden = current !== 'AUD';
    inline.textContent = `US$1 → A$${rate.toFixed(2)}`;
    inline.title = `${explainer}. Market prices and paper math are always USD; the AUD option only converts what is displayed.`;
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
    // Decide the sign AFTER rounding: a sub-cent outflow (-0.001) is displayed
    // as US$0.00, not the misleading "-US$0.00".
    const roundedMagnitude = Math.round(Math.abs(converted) * 100) / 100;
    const symbol = current === 'AUD' ? 'A$' : 'US$';
    return (value < 0 && roundedMagnitude > 0 ? '-' : '') + symbol + body;
  };

  const buildSwitcher = () => {
    const bar = document.createElement('div');
    bar.className = 'loki-currency';
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', 'Display currency');
    bar.title = 'Market prices and paper math are always USD; the AUD option only converts what is displayed.';
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
    const rate = document.createElement('span');
    rate.className = 'cur-rate-inline';
    rate.id = 'loki-fx-inline';
    rate.setAttribute('aria-live', 'polite');
    bar.append(mk('AUD'), mk('USD'), rate);
    // It belongs in the topbar's right cluster, next to the mode controls —
    // never as a floating corner that fights the page for space.
    const slot = document.querySelector('.topbar .topbar-status') || document.querySelector('.topbar');
    if (slot) {
      bar.classList.add('in-topbar');
      slot.insertBefore(bar, slot.firstChild);
    } else {
      document.body.appendChild(bar);
    }
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