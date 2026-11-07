/* Daily AI briefing: the Portfolio AI's self-check, this week's moves and honest uncertainty. */
'use strict';
(() => {
  const root = document.getElementById('ai-briefing');
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = (v) => (Number.isFinite(Number(v)) ? `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(1)}%` : '—');
  const STATUS = {
    normal: ['Healthy', 'good', 'Behaving normally'],
    below_range: ['Below range', 'warn', 'Weaker than usual'],
    above_range: ['Above range', 'info', 'Unusually strong'],
    unknown: ['Unknown', '', 'Not enough history'],
  };
  async function load() {
    try {
      const res = await fetch('/api/fusion/ai/portfolio', { cache: 'no-store', signal: AbortSignal.timeout(55000) });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(d.detail || 'briefing unavailable');
      const h = d.health || { status: 'unknown' };
      const [tag, tone, headline] = STATUS[h.status] || STATUS.unknown;
      const badge = $('brief-health');
      badge.textContent = tag; badge.className = `tag brief-${tone}`;
      $('brief-health-text').textContent = headline;
      const p = Number(h.percentile_vs_history);
      if (Number.isFinite(p)) {
        $('brief-meter-fill').style.width = `${p}%`;
        $('brief-meter-dot').style.left = `${p}%`;
      }
      $('brief-health-detail').textContent = h.last_year_sharpe !== undefined
        ? `Last 12 months: Sharpe ${Number(h.last_year_sharpe).toFixed(2)}, worst drop ${pct(h.last_year_worst_drop_pct)} — better than ${Number.isFinite(p) ? Math.round(p) : '—'}% of its 2005–2022 years. It is ${h.detail}.`
        : 'Not enough replay history to judge yet.';
      const changes = (d.changes || []).slice(0, 7);
      $('brief-changes').innerHTML = changes.length
        ? changes.map((c) => `<li><span class="brief-act ${c.action === 'entered' ? 'in' : 'out'}">${c.action === 'entered' ? '▲ Entered' : '▼ Exited'}</span> <b>${esc(c.symbol)}</b> <time>${esc(c.date)}</time></li>`).join('')
        : '<li class="muted">No entries or exits in the last few sessions — holding steady.</li>';
      const held = (d.positions || []).filter((x) => x.weight > 0);
      $('brief-changes').insertAdjacentHTML('beforeend', `<li class="muted brief-hold">Now holding ${held.length} market${held.length === 1 ? '' : 's'}, ${Math.round((d.gross || 0) * 100)}% invested · as of ${esc(d.as_of)}</li>`);
      const ci = d.holdout_ci || {};
      if (ci.cagr_pct) {
        $('brief-ci').textContent = `${pct(ci.cagr_pct[0])} to ${pct(ci.cagr_pct[1])} / yr`;
        $('brief-ci-detail').textContent = `The simulated 2023→now result (${pct(d.holdout && d.holdout.cagr_pct)} a year) could plausibly have been anywhere in this ${Math.round((ci.level || 0.9) * 100)}% range by luck alone. Profitable in ${Math.min(99.9, (ci.probability_profitable || 0) * 100).toFixed(1)}% of resampled histories. Hypothetical results, not a promise.`;
      }
    } catch (error) {
      $('brief-health').textContent = 'Offline';
      $('brief-health-text').textContent = 'Briefing unavailable right now';
      $('brief-changes').innerHTML = `<li class="muted">${esc(error.message)} — retrying in a minute.</li>`;
      setTimeout(load, 60000);
    }
  }
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); load(); } });
    io.observe(root);
  } else load();
})();
