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

  /** 10-20 year universal profiles vs buy-and-hold on the untouched holdout. */
  const renderUniversal = (block) => {
    const host = document.getElementById('universal-book');
    if (!host) return;
    if (!block || (!block.equity && !block.crypto)) { host.innerHTML = ''; return; }
    const pct = (v) => (v === null || v === undefined || Number.isNaN(Number(v)) ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(1)}%`);
    const tone = (v) => (Number(v) >= 0 ? '#b8f0d8' : '#ffb3a7');
    const card = (label, b) => {
      if (!b) return '';
      const p = b.holdout_pooled || {};
      const params = b.params || {};
      const since = b.windows && b.windows.holdout ? String(b.windows.holdout[0]).slice(0, 4) : '2023';
      const rows = (b.holdout || []).filter((h) => h.strategy && h.strategy.trades !== undefined).map((h) =>
        `<tr><td>${escapeHtml(h.symbol)}</td><td style="color:${tone(h.strategy.cagr_pct)}">${pct(h.strategy.cagr_pct)}</td><td>${num(h.strategy.max_dd_pct)}</td>` +
        `<td>${escapeHtml(h.strategy.trades)}</td><td>${num(h.strategy.profit_factor, 2, '')}</td><td style="color:#9fb0c2">${pct(h.buy_hold && h.buy_hold.cagr_pct)}</td><td style="color:#9fb0c2">${num(h.buy_hold && h.buy_hold.max_dd_pct)}</td></tr>`).join('');
      const status = b.verified
        ? '<span style="font-size:11.5px;border-radius:999px;padding:3px 10px;color:#b8f0d8;background:rgba(184,240,216,.12)">✓ made money on the holdout · live AI uses it</span>'
        : '<span style="font-size:11.5px;border-radius:999px;padding:3px 10px;color:#f0c98b;background:rgba(240,201,139,.1)">holdout not convincing · live AI keeps the older book</span>';
      return `<article style="${cardStyle}flex:1 1 420px;min-width:0">` +
        `<p style="letter-spacing:.14em;font-size:10.5px;color:#8bdad4">${escapeHtml(label)} · HOLDOUT ${escapeHtml(since)}→NOW</p>` +
        `<div style="display:flex;flex-wrap:wrap;gap:18px;align-items:baseline">` +
        `<span><strong style="font-size:22px;color:${tone(p.mean_cagr_pct)}">${pct(p.mean_cagr_pct)}</strong> <span class="caption">avg / year</span></span>` +
        `<span><strong style="font-size:18px">${escapeHtml(p.profitable_symbols ?? '—')}/${escapeHtml(p.symbols ?? '—')}</strong> <span class="caption">symbols profitable</span></span>` +
        `<span><strong style="font-size:18px">${num(p.mean_max_dd_pct)}</strong> <span class="caption">avg worst drawdown</span></span></div>` +
        `<p class="caption">Buy &amp; hold, same symbols and dates: ${pct(p.buy_hold_mean_cagr_pct)} / year, ${num(p.buy_hold_mean_max_dd_pct)} worst drawdown · ${escapeHtml(p.total_trades ?? 0)} trades after ${escapeHtml(block.fees_bps_per_side ?? 10)} bps fees + ${escapeHtml(block.slippage_bps_per_side ?? 5)} bps slippage per side.</p>` +
        status +
        (b.learning_from_mistakes ? `<p class="caption">Learning from mistakes: ${b.learning_from_mistakes.kept
          ? `on — trained on ${escapeHtml(b.learning_from_mistakes.lessons_final)} past trades, skips setups that won less than ${escapeHtml(Math.round(b.learning_from_mistakes.threshold * 100))}% of the time.`
          : `off — ${escapeHtml(b.learning_from_mistakes.reason || 'did not beat the plain rules')}.`}</p>` : '') +
        `<details><summary class="caption">Per-symbol results · rules: ${escapeHtml(params.factor_preset || '')}, entry ≥ ${escapeHtml(params.signal_threshold)}, stop ${escapeHtml(params.stop_loss_atr)} ATR${Number(params.trailing_stop_atr) > 0 ? `, trailing ${escapeHtml(params.trailing_stop_atr)} ATR` : ''}, ${escapeHtml(params.target_vol_pct)}% vol target, ${params.exit_mode === 'trend' ? 'exit when price breaks its 200-day average' : 'exit on a SELL signal'}</summary>` +
        `<div class="table-scroll"><table style="font-size:12.5px;width:100%"><thead><tr><th>Symbol</th><th>AI / yr</th><th>AI max DD</th><th>Trades</th><th>PF</th><th>B&amp;H / yr</th><th>B&amp;H max DD</th></tr></thead><tbody>${rows}</tbody></table></div></details>` +
        `</article>`;
    };
    const pf = block.portfolio;
    let pfHtml = '';
    if (pf && pf.holdout) {
      const curve = (rows) => {
        const pts = (rows || []).map((r) => Number(r[1])).filter(Number.isFinite);
        if (pts.length < 2) return '';
        return pts;
      };
      const a = curve(pf.holdout_curve), b = curve(pf.holdout_curve_buy_hold);
      let svg = '';
      if (a && b) {
        const lo = Math.min(...a, ...b), hi = Math.max(...a, ...b), span = hi - lo || 1;
        const path = (pts) => pts.map((v, i) => `${i ? 'L' : 'M'}${(i / (pts.length - 1) * 600).toFixed(1)},${(150 - (v - lo) / span * 140).toFixed(1)}`).join(' ');
        svg = `<svg viewBox="0 0 600 160" preserveAspectRatio="none" style="width:100%;height:150px;margin-top:8px" aria-label="Portfolio AI versus buy and hold since 2023">` +
          `<path d="${path(b)}" fill="none" stroke="#7f93a8" stroke-width="1.5" stroke-dasharray="4 4"/>` +
          `<path d="${path(a)}" fill="none" stroke="#a8f0c6" stroke-width="2.5"/></svg>` +
          `<p class="caption"><span style="color:#a8f0c6">━ Portfolio AI</span> &nbsp; <span style="color:#7f93a8">┅ equal-weight buy &amp; hold</span> · growth of $1 since Jan 2023 (weekly)</p>`;
      }
      const h = pf.holdout, bh = pf.holdout_buy_hold || {};
      pfHtml = `<article style="${cardStyle}width:100%;margin-top:12px;border-color:rgba(168,240,198,.4)">` +
        `<p style="letter-spacing:.14em;font-size:10.5px;color:#a8f0c6">PORTFOLIO AI · 21 MARKETS AT ONCE · HOLDOUT 2023→NOW</p>` +
        `<div style="display:flex;flex-wrap:wrap;gap:22px;align-items:baseline">` +
        `<span><strong style="font-size:26px;color:${tone(h.cagr_pct)}">${pct(h.cagr_pct)}</strong> <span class="caption">avg / year</span></span>` +
        `<span><strong style="font-size:20px">${escapeHtml(Number(h.sharpe).toFixed(2))}</strong> <span class="caption">Sharpe (buy &amp; hold ${escapeHtml(Number(bh.sharpe).toFixed(2))})</span></span>` +
        `<span><strong style="font-size:20px">${num(h.max_dd_pct)}</strong> <span class="caption">worst drop (buy &amp; hold ${num(bh.max_dd_pct)})</span></span>` +
        `<span><strong style="font-size:20px">${escapeHtml(Number(h.profitable_months_pct).toFixed(0))}%</strong> <span class="caption">months profitable</span></span></div>` +
        svg + `<p class="caption">Every market runs its verified rules; capital is shared equally and the book is scaled to ${escapeHtml(pf.target_vol_pct)}% yearly volatility (chosen on 2005–2022 only), never above 100% invested. <a class="text-link" href="#ai-trading">Run it with paper money →</a></p></article>`;
    }
    host.innerHTML = pfHtml + `<div style="display:flex;flex-wrap:wrap;gap:12px;margin:12px 0">${card('STOCKS & ETFS', block.equity)}${card('CRYPTO', block.crypto)}</div>` +
      `<p class="caption">Trained ${escapeHtml(String(block.generated_at || '').slice(0, 10))} on data through ${escapeHtml((block.equity || block.crypto || {}).data_through || '—')}. Past results on historical data, never a promise about the next trade.</p>`;
  };

  const init = async () => {
    try {
      const res = await fetch('/api/fusion/research-book', { cache: 'no-store' });
      if (!res.ok) return;
      const book = await res.json();
      renderUniversal(book.universal);
      render(book);
    } catch {
      /* keep the card hidden — evidence must never be faked */
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
