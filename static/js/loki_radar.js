/* AI MARKET RADAR — the Portfolio AI's 21 markets on a live radar.
 *
 * Data: /api/fusion/ai/portfolio (each market's latest trend score, regime,
 * whether the tested book holds it, and its weight). Placement: angle by
 * asset group, distance from centre by trend score (strong uptrend = near
 * the core). Held markets glow and ping as the sweep passes. Presentation
 * only; honours reduced motion, the hero's Pause button and hidden tabs.
 */
'use strict';
(() => {
  const canvas = document.getElementById('ai-radar');
  if (!canvas) return;
  const instrument = canvas.closest('.signal-instrument');
  const tip = document.getElementById('radar-tip');
  const readout = document.getElementById('radar-readout');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ctx = canvas.getContext('2d');
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const GROUPS = [
    { label: 'STOCKS & INDEX ETFs', from: -170, to: -15, match: (s) => !s.endsWith('-USD') && !['GLD', 'TLT'].includes(s) },
    { label: 'HAVENS', from: -5, to: 35, match: (s) => ['GLD', 'TLT'].includes(s) },
    { label: 'CRYPTO', from: 45, to: 175, match: (s) => s.endsWith('-USD') },
  ];
  let size = 300, dpr = 1, cx = 150, cy = 150, R = 130;
  let blips = [];
  let sweep = -Math.PI / 2;
  let last = performance.now();
  let visible = true, raf = 0, hover = null, loadedAt = 0, failed = false;

  function resize() {
    const wrap = canvas.parentElement;
    const style = getComputedStyle(wrap);
    const inner = wrap.clientWidth - parseFloat(style.paddingLeft || 0) - parseFloat(style.paddingRight || 0);
    size = Math.max(180, Math.min(inner, 420));
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr; canvas.height = size * dpr;
    canvas.style.width = canvas.style.height = size + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx = cy = size / 2; R = size / 2 - 22;
  }

  function place(positions) {
    const prev = new Map(blips.map((b) => [b.symbol, b]));
    const out = [];
    for (const g of GROUPS) {
      const members = positions.filter((p) => g.match(p.symbol));
      members.forEach((p, i) => {
        const t = members.length === 1 ? 0.5 : i / (members.length - 1);
        const angle = ((g.from + (g.to - g.from) * t) * Math.PI) / 180;
        const score = Number.isFinite(Number(p.score)) ? Number(p.score) : 0;
        const radius = 0.14 + 0.82 * (1 - (score + 100) / 200);
        const old = prev.get(p.symbol);
        out.push({ ...p, angle, radius, score, held: p.weight > 0, cur: reduce ? radius : old ? old.cur : 0, ping: -1e9 });
      });
    }
    blips = out;
  }

  async function load() {
    try {
      const res = await fetch('/api/fusion/ai/portfolio', { cache: 'no-store', signal: AbortSignal.timeout(55000) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'radar feed unavailable');
      place(data.positions || []);
      const held = (data.positions || []).filter((p) => p.weight > 0).length;
      readout.innerHTML =
        `<span><b>${esc((data.positions || []).length)}</b> markets</span>` +
        `<span><b>${esc(held)}</b> held</span>` +
        `<span><b>${esc(Math.round((data.gross || 0) * 100))}%</b> invested</span>` +
        `<span class="muted">as of ${esc(data.as_of || '—')}</span>`;
      loadedAt = Date.now(); failed = false;
      if (reduce) draw(0);
    } catch (error) {
      failed = true;
      readout.innerHTML = `<span class="muted">Radar offline — ${esc(error.message)}. Retrying…</span>`;
    }
  }

  function draw(dt) {
    const paused = instrument && instrument.dataset.paused === 'true';
    if (!paused && !reduce) sweep += dt * (Math.PI * 2) / 5200;
    ctx.clearRect(0, 0, size, size);

    // dish
    const bg = ctx.createRadialGradient(cx, cy, 0, cx, cy, R + 10);
    bg.addColorStop(0, 'rgba(26,62,58,.55)'); bg.addColorStop(1, 'rgba(8,16,22,.2)');
    ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(cx, cy, R + 8, 0, Math.PI * 2); ctx.fill();

    // rings + labels
    ctx.lineWidth = 1;
    [0.25, 0.5, 0.75, 1].forEach((f, i) => {
      ctx.strokeStyle = `rgba(139,218,212,${i === 3 ? 0.35 : 0.14})`;
      ctx.beginPath(); ctx.arc(cx, cy, R * f, 0, Math.PI * 2); ctx.stroke();
    });
    ctx.strokeStyle = 'rgba(139,218,212,.08)';
    for (let a = 0; a < 12; a++) {
      const ang = (a * Math.PI) / 6;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(ang) * R, cy + Math.sin(ang) * R); ctx.stroke();
    }
    ctx.font = '9px ui-monospace, monospace'; ctx.textAlign = 'center';
    for (const g of GROUPS) {
      const mid = (((g.from + g.to) / 2) * Math.PI) / 180;
      ctx.save(); ctx.translate(cx + Math.cos(mid) * (R + 13), cy + Math.sin(mid) * (R + 13)); ctx.rotate(mid + Math.PI / 2);
      ctx.fillStyle = 'rgba(168,240,198,.6)'; ctx.fillText(g.label, 0, 3); ctx.restore();
    }

    // sweep trail
    if (ctx.createConicGradient) {
      const cg = ctx.createConicGradient(sweep - 1.1, cx, cy);
      cg.addColorStop(0, 'rgba(168,240,198,0)');
      cg.addColorStop(0.17, 'rgba(168,240,198,.28)');
      cg.addColorStop(0.175, 'rgba(168,240,198,0)');
      cg.addColorStop(1, 'rgba(168,240,198,0)');
      ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
    }
    ctx.strokeStyle = 'rgba(201,255,226,.85)'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(sweep) * R, cy + Math.sin(sweep) * R); ctx.stroke();

    // blips
    const now = performance.now();
    const placed = [];
    const label = (text, x, y, color) => {
      ctx.font = '9.5px ui-monospace, monospace'; ctx.textAlign = 'left';
      const w = ctx.measureText(text).width + 4, h = 11;
      let lx = x + 7, ly = y - 6;
      for (let tries = 0; tries < 6; tries++) {
        const hit = placed.some((r) => lx < r.x + r.w && lx + w > r.x && ly - h < r.y && ly > r.y - r.h);
        if (!hit) break;
        ly += tries % 2 ? -(h + 2) * (tries + 1) : (h + 2) * (tries + 1);
      }
      placed.push({ x: lx, y: ly, w, h });
      ctx.fillStyle = color; ctx.fillText(text, lx, ly);
    };
    for (const b of blips) {
      b.cur += (b.radius - b.cur) * Math.min(1, dt / 500); // deploy outward smoothly
      const x = cx + Math.cos(b.angle) * b.cur * R, y = cy + Math.sin(b.angle) * b.cur * R;
      b.x = x; b.y = y;
      let diff = ((sweep - b.angle) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2);
      if (diff < 0.06 && now - b.ping > 1000) b.ping = now;
      const since = now - b.ping;
      if (since < 1100) {
        const p = since / 1100;
        ctx.strokeStyle = b.held ? `rgba(168,240,198,${0.8 * (1 - p)})` : `rgba(139,218,212,${0.45 * (1 - p)})`;
        ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, 4 + p * (b.held ? 20 : 12), 0, Math.PI * 2); ctx.stroke();
      }
      const lit = since < 1600 ? 1 - since / 1600 : 0;
      if (b.held) {
        ctx.fillStyle = 'rgba(168,240,198,.18)'; ctx.beginPath(); ctx.arc(x, y, 9 + lit * 4, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#c9ffe2'; ctx.beginPath(); ctx.arc(x, y, 4.2, 0, Math.PI * 2); ctx.fill();
      } else {
        const color = b.score >= 0 ? `rgba(139,218,212,${0.45 + lit * 0.5})` : `rgba(255,179,167,${0.35 + lit * 0.5})`;
        ctx.strokeStyle = color; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(x, y, 3.4, 0, Math.PI * 2); ctx.stroke();
      }
      if (b.held || b === hover || lit > 0.3) {
        label(b.symbol.replace('-USD', ''), x, y, b.held ? 'rgba(220,255,236,.95)' : 'rgba(200,215,225,.8)');
      }
    }

    // core
    const pulse = reduce ? 0.5 : (Math.sin(now / 600) + 1) / 2;
    ctx.fillStyle = `rgba(168,240,198,${0.1 + pulse * 0.12})`; ctx.beginPath(); ctx.arc(cx, cy, 14 + pulse * 3, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#0a151e'; ctx.strokeStyle = '#a8f0c6'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(cx, cy, 10, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = '#c9ffe2'; ctx.font = 'bold 10px Inter, system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.fillText('L', cx, cy + 3.5);
    if (!blips.length) {
      ctx.fillStyle = 'rgba(162,181,196,.75)'; ctx.font = '11px ui-monospace, monospace';
      ctx.fillText(failed ? 'radar offline' : 'scanning…', cx, cy + 32);
    }
  }

  function frame(t) {
    const dt = Math.min(64, t - last); last = t;
    draw(dt);
    if (visible && !document.hidden && !reduce) raf = requestAnimationFrame(frame);
  }
  function start() { cancelAnimationFrame(raf); last = performance.now(); raf = requestAnimationFrame(frame); }

  canvas.addEventListener('pointermove', (e) => {
    const r = canvas.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    hover = blips.reduce((best, b) => { const d = Math.hypot(b.x - x, b.y - y); return d < 14 && (!best || d < best.d) ? { b, d } : best; }, null)?.b || null;
    if (!hover) { tip.hidden = true; canvas.style.cursor = ''; return; }
    canvas.style.cursor = 'pointer';
    tip.hidden = false;
    tip.style.left = `${Math.min(x + 14, r.width - 170)}px`; tip.style.top = `${y + 10}px`;
    tip.innerHTML = `<b>${esc(hover.symbol)}</b><span>trend score ${esc(hover.score >= 0 ? '+' : '')}${esc(hover.score)}</span>` +
      `<span>${esc((hover.regime || '').replace('_', ' ').toLowerCase() || '—')}</span>` +
      `<span>${hover.held ? `held · ${esc((hover.weight * 100).toFixed(1))}% of book${hover.entry_date ? ` · since ${esc(hover.entry_date)}` : ''}` : 'watching — not in an entry setup'}</span>`;
    if (reduce) draw(0);
  });
  canvas.addEventListener('pointerleave', () => { hover = null; tip.hidden = true; });
  canvas.addEventListener('click', () => { if (hover) location.hash = '#live-markets'; });

  resize();
  window.addEventListener('resize', () => { resize(); if (reduce) draw(0); });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (visible) start(); }).observe(canvas);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) start(); });
  draw(16);
  if (!reduce) start();
  load();
  setInterval(() => { if (!document.hidden && (failed || Date.now() - loadedAt > 10 * 60 * 1000)) load(); }, 60000);
})();
