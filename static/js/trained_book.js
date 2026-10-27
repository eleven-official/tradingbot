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

  /** Judge the final-20% audit segment against the thresholds the trainer
   * actually used (published as `hurdle_targets`), with the historic
   * 90/60/1.25/5 set as the fallback for books that predate it.
   *
   * It is treated as its own segment on purpose. A profile can clear the gate
   * — hurdle set, every trailing window, every bootstrapped tape — and still
   * lose money in this tail; that is a finding, not a contradiction, so the
   * chip names the segment instead of implying the verified claim was unearned. */
  const holdoutAudit = (holdout, hurdles) => {
    const t = hurdles || {};
    const under = (value, key, fallback) => Number(value) < Number(t[key] ?? fallback);
    const missed = [];
    if (under(holdout.win_rate_pct, 'win_rate_pct', 90)) missed.push('win');
    if (under(holdout.profitable_months_pct, 'month_profit_rate_pct', 60)) missed.push('months');
    if (under(holdout.profit_factor, 'profit_factor', 1.25)) missed.push('PF');
    if (under(holdout.trades, 'trades', 5)) missed.push('trades');
    const n = Number(holdout.trades) || 0;
    return { missed, sample: `${num(holdout.win_rate_pct)} win over ${n} trade${n === 1 ? '' : 's'}` };
  };

  const holdoutBadge = (holdout, hurdles) => {
    const audit = holdoutAudit(holdout, hurdles);
    const base = 'font-size:11.5px;border-radius:999px;padding:3px 10px;align-self:flex-start;';
    return audit.missed.length === 0
      ? `<span style="${base}color:#b8f0d8;background:rgba(184,240,216,.12)">✓ final 20%: ${audit.sample} — every hurdle cleared</span>`
      : `<span style="${base}color:#f0c98b;background:rgba(240,201,139,.1)">final 20%: ${audit.sample} — below ${escapeHtml(audit.missed.join(' + '))} hurdle${audit.missed.length > 1 ? 's' : ''}</span>`;
  };

  /** Robustness: the same parameter set re-run on trailing 5/7/10y slices and
   * on tapes bootstrapped from the symbol's own returns. `null` means the
   * profile predates the gate — never rendered as a pass. */
  const robustnessBadge = (entry) => {
    const hasWindow = entry.windows_passed === true || entry.windows_passed === false;
    const hasSynthetic = entry.synthetic_passed === true || entry.synthetic_passed === false;
    if (!hasWindow && !hasSynthetic) return '';
    const base = 'font-size:11.5px;border-radius:999px;padding:3px 10px;align-self:flex-start;';
    if (entry.windows_passed === true && entry.synthetic_passed === true) {
      const pf = num(entry.synthetic_profit_factor, 2, '');
      const share = Number(entry.synthetic_profitable_share);
      const detail = Number.isFinite(share) && pf !== '—'
        ? ` · simulated PF ${escapeHtml(pf)}, ${escapeHtml(num(share * 100, 0))} profitable`
        : '';
      return `<span style="${base}color:#b8f0d8;background:rgba(184,240,216,.12)">✓ 5/7/10y windows + simulated tapes${detail}</span>`;
    }
    // Insufficient evidence is a different finding from a failed edge, and a
    // wide target against a wide stop produces it routinely: the tapes ran but
    // never filled enough orders to judge. Keep it visually distinct so a
    // reader does not mistake "untested" for "loses money".
    if (entry.verdict === 'untested') {
      return `<span style="${base}color:#cbd8ff;background:rgba(203,216,255,.1)">not enough simulated fills to judge — untested, not disproven</span>`;
    }
    const missed = [];
    if (entry.windows_passed === false) missed.push('a trailing window');
    if (entry.synthetic_passed === false) missed.push('the simulated tape');
    return `<span style="${base}color:#f0c98b;background:rgba(240,201,139,.1)">fails ${escapeHtml(missed.join(' + ') || 'the robustness gate')} — regime or path dependent</span>`;
  };

  /** Selection: how the winner was picked out of the grid sweep. Only rendered
   * when the trainer actually re-ranked finalists on forward folds. */
  const selectionBadge = (entry) => {
    const wf = entry.walk_forward || {};
    if (entry.selection !== 'walk_forward' || !wf || wf.folds === undefined) return '';
    const base = 'font-size:11.5px;border-radius:999px;padding:3px 10px;align-self:flex-start;';
    const pf = num(wf.worst_fold_pf, 2, '');
    const mean = num(wf.mean_return_pct, 2);
    const detail = pf === '—' ? '' : ` · worst fold PF ${escapeHtml(pf)}, mean ${escapeHtml(mean)}`;
    return `<span style="${base}color:#cbd8ff;background:rgba(203,216,255,.1)">picked by walk-forward${detail}</span>`;
  };

  /** Expectancy: mean return per verified trade. This is the number the trainer
   * ranks on, so it belongs next to the hit rate rather than behind it. */
  const expectancyLine = (entry) => {
    const trades = Number(entry.trades);
    const ret = Number(entry.return_pct);
    if (!Number.isFinite(trades) || trades <= 0 || !Number.isFinite(ret)) return '';
    const value = ret / trades;
    const tone = value > 0 ? '#b8f0d8' : '#f0b8b8';
    return `<span style="font-size:13px;color:#9fb0c2">expectancy <strong style="color:${tone}">${value >= 0 ? '+' : ''}${value.toFixed(2)}%</strong> per trade</span>`;
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
      const hasAudit = holdout.trades !== null && holdout.trades !== undefined
        && Number.isFinite(Number(holdout.trades));
      // The badge carries win rate and the sample size; this line carries the
      // other two audited numbers. No number is printed twice.
      const holdoutLine =
        hasAudit ?
          `<span style="color:#8bdad4;font-size:12px">Final 20% never touched by training:</span>
           <span style="color:#e7f0ff;font-size:12.5px">${escapeHtml(num(holdout.profitable_months_pct))} profitable months · PF ${escapeHtml(num(holdout.profit_factor, 2, ''))}</span>` :
          '<span style="color:#7f93a8;font-size:12px">Holdout audit pending</span>';
      // The final audit is distinct from development and robustness checks.
      const badge = hasAudit ? holdoutBadge(holdout, book.hurdle_targets) : '';
      const robustness = robustnessBadge(entry);
      const selection = selectionBadge(entry);
      const expectancy = expectancyLine(entry);
      // A profile can train cleanly and still miss a hurdle (too few
      // out-of-sample trades, profit factor under the floor). Saying so is the
      // difference between a research artifact and a claim. "Untested" means
      // the gate never got to measure the edge, so it must not read as a loss.
      let hurdleLine = '';
      if (entry.good === false && entry.verdict === 'untested') {
        hurdleLine = '<span style="color:#cbd8ff;font-size:12px">not promoted — simulated tapes never reached the fill floor</span>';
      } else if (entry.good === false) {
        hurdleLine = '<span style="color:#f0b8b8;font-size:12px">missed hurdles — research only, not a verified edge</span>';
      } else if (hasAudit && holdoutAudit(holdout, book.hurdle_targets).missed.length) {
        // Missing a trade-count or win-rate hurdle does not imply a net loss.
        hurdleLine = '<span style="color:#f0c98b;font-size:12px">development checks passed; final holdout below audit thresholds</span>';
      }
      return `<article style="${cardStyle}">
        <strong style="font-size:15px;color:#b8f0d8">${escapeHtml(entry.symbol)}</strong>
        ${badge}
        ${robustness}
        ${selection}
        ${hurdleLine}
        <span style="font-size:13.5px"><strong>${escapeHtml(num(entry.win_rate_pct))}</strong> winning trades</span>
        <span style="font-size:13.5px"><strong>${escapeHtml(num(entry.profitable_months_pct))}</strong> profitable months</span>
        ${expectancy}
        <span style="font-size:13px;color:#9fb0c2">profit factor ${escapeHtml(num(entry.profit_factor, 2, ''))} · ${escapeHtml(String(entry.trades ?? '—'))} verified trades</span>
        <span style="border-top:1px dashed rgba(139,218,212,.18);margin-top:4px;padding-top:6px;display:flex;flex-direction:column;gap:2px">${holdoutLine}</span>
      </article>`;
    });
    grid.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;margin:14px 0;';
    grid.innerHTML = cards.join('');
    const note = document.getElementById('trained-book-note');
    if (note) {
      const consensus = book.consensus_support_pct ? ` · cross-symbol agreement ${num(book.consensus_support_pct)}` : '';
      const protocol = book.evaluation_protocol && book.evaluation_protocol.rank_objective
        ? ` · ranked on ${book.evaluation_protocol.rank_objective}${book.evaluation_protocol.finalist_selection === 'walk_forward' ? ', finalists re-ranked on forward folds' : ''}`
        : '';
      const robust = book.robustness && book.robustness.enabled
        ? ` · verified profiles also cleared ${(book.robustness.windows || []).join('/')}y windows and ${(book.robustness.synthetic_seeds || []).length} simulated tapes`
        : '';
      note.textContent = `Trained on ${book.period || '10y'} of history · refreshed ${book.generated_at ? String(book.generated_at).slice(0, 10) : ''}${consensus}${protocol}${robust}. Historical evidence, never a guarantee.`;
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
