/* Trained strategy book: renders the verified out-of-sample evidence card. */
'use strict';
(() => {
  const escapeHtml = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  const cardStyle =
    'display:inline-flex;flex-direction:column;gap:6px;min-width:200px;padding:16px 18px;border-radius:14px;' +
    'border:1px solid rgba(139,218,212,.22);background:rgba(10,18,32,.7);';

  const num = (value, digits = 1, suffix = '%') =>
    value === null || value === undefined || Number.isNaN(Number(value))
      ? '—'
      : `${Number(value).toFixed(digits)}${suffix}`;

  /** Hurdle verdict computed from the audited holdout itself: win ≥ 90%,
   * months ≥ 60%, PF ≥ 1.25, trades ≥ 5. Shows failures plainly — the
   * evidence is never dressed up. */
  const holdoutBadge = (holdout) => {
    const missed = [];
    if (Number(holdout.win_rate_pct) < 90) missed.push('win');
    if (Number(holdout.profitable_months_pct) < 60) missed.push('months');
    if (Number(holdout.profit_factor) < 1.25) missed.push('PF');
    if (Number(holdout.trades) < 5) missed.push('trades');
    const base = 'font-size:11.5px;border-radius:999px;padding:3px 10px;align-self:flex-start;';
    return missed.length === 0
      ? `<span style="${base}color:#b8f0d8;background:rgba(184,240,216,.12)">✓ all holdout hurdles met</span>`
      : `<span style="${base}color:#f0c98b;background:rgba(240,201,139,.1)">holdout below ${escapeHtml(missed.join(' + '))} hurdle${missed.length > 1 ? 's' : ''}</span>`;
  };

  const render = (book) => {
    const grid = document.getElementById('trained-book-grid');
    if (!grid) return;
    if (!book || !Array.isArray(book.symbols) || book.symbols.length === 0) {
      grid.closest('section').hidden = true;
      return;
    }
    const cards = book.symbols.map((entry) => {
      const holdout = entry.final_holdout || {};
      const holdoutLine =
        holdout.trades ?
          `<span style="color:#8bdad4;font-size:12px">Final 20% never touched by training:</span>
           <span style="color:#e7f0ff;font-size:12.5px">${escapeHtml(num(holdout.win_rate_pct))} win · ${escapeHtml(num(holdout.profitable_months_pct))} months · PF ${escapeHtml(num(holdout.profit_factor, 2, ''))}</span>` :
          '<span style="color:#7f93a8;font-size:12px">Holdout audit pending</span>';
      const badge = holdout.trades ? holdoutBadge(holdout) : '';
      // A profile can train cleanly and still miss a hurdle (too few
      // out-of-sample trades, profit factor under the floor). Saying so is the
      // difference between a research artifact and a claim.
      const hurdleLine = entry.good === false
        ? '<span style="color:#f0b8b8;font-size:12px">missed hurdles — research only, not a verified edge</span>'
        : '';
      return `<article style="${cardStyle}">
        <strong style="font-size:15px;color:#b8f0d8">${escapeHtml(entry.symbol)}</strong>
        ${badge}
        ${hurdleLine}
        <span style="font-size:13.5px"><strong>${escapeHtml(num(entry.win_rate_pct))}</strong> winning trades</span>
        <span style="font-size:13.5px"><strong>${escapeHtml(num(entry.profitable_months_pct))}</strong> profitable months</span>
        <span style="font-size:13px;color:#9fb0c2">profit factor ${escapeHtml(num(entry.profit_factor, 2, ''))} · ${escapeHtml(String(entry.trades ?? '—'))} verified trades</span>
        <span style="border-top:1px dashed rgba(139,218,212,.18);margin-top:4px;padding-top:6px;display:flex;flex-direction:column;gap:2px">${holdoutLine}</span>
      </article>`;
    });
    grid.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;margin:14px 0;';
    grid.innerHTML = cards.join('');
    const note = document.getElementById('trained-book-note');
    if (note) {
      const consensus = book.consensus_support_pct ? ` · cross-symbol agreement ${num(book.consensus_support_pct)}` : '';
      note.textContent = `Trained on ${book.period || '10y'} of history · refreshed ${book.generated_at ? String(book.generated_at).slice(0, 10) : ''}${consensus}. Historical evidence, never a guarantee.`;
    }
  };

  const init = async () => {
    try {
      const res = await fetch('/api/fusion/research-book', { cache: 'no-store' });
      if (!res.ok) return;
      render(await res.json());
    } catch {
      /* keep the card hidden — evidence must never be faked */
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
