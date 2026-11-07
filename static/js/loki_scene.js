/* LOKI SCENE — the opening experience.
 *
 * Presentation only: never touches trading data paths or stored state
 * (besides one sessionStorage flag so the intro plays once per visit).
 *
 *   <body data-loki-intro>                 → cinematic intro, once per session
 *   <body data-loki-scene="full">          → full-page animated market canvas
 *   <div data-loki-scene="hero">           → animated canvas behind one block
 *   <div id="loki-ticker">                 → live scrolling price tape
 *   <h1 data-reveal-words>                 → words rise in one by one
 *   .loki-glow elements                    → cursor-following light
 *
 * Everything respects prefers-reduced-motion and pauses in hidden tabs.
 */
'use strict';
(() => {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const body = document.body;
  const INTRO_KEY = 'loki_intro_seen_v1';
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ------------------------------------------------------------ intro */
  function playIntro() {
    let seen = false;
    try { seen = sessionStorage.getItem(INTRO_KEY) === '1'; } catch { /* storage blocked */ }
    if (!body.hasAttribute('data-loki-intro') || seen || reduce) { body.classList.add('scene-ready'); return; }
    try { sessionStorage.setItem(INTRO_KEY, '1'); } catch { /* storage blocked */ }
    const candles = Array.from({ length: 18 }, (_, i) => {
      const up = Math.sin(i * 1.7) + i * 0.12 > 0.1;
      const h = 14 + ((i * 37) % 40);
      const y = 70 - i * 2.6 - (up ? h : 0) + ((i * 13) % 12);
      return `<g class="ic" style="--d:${0.55 + i * 0.045}s"><line x1="${i * 14 + 7}" x2="${i * 14 + 7}" y1="${y - 8}" y2="${y + h + 8}"/><rect x="${i * 14 + 2}" y="${y}" width="10" height="${h}" rx="1.5" class="${up ? 'up' : 'down'}"/></g>`;
    }).join('');
    const intro = document.createElement('div');
    intro.className = 'loki-intro';
    intro.setAttribute('aria-hidden', 'true');
    intro.innerHTML =
      `<div class="li-grid"></div><div class="li-core">` +
      `<svg class="li-mark" viewBox="0 0 120 120"><rect class="li-box" x="6" y="6" width="108" height="108" rx="28"/><path class="li-l" d="M44 34 V84 H80"/></svg>` +
      `<div class="li-word">${'LOKI'.split('').map((ch, i) => `<span style="--i:${i}">${ch}</span>`).join('')}</div>` +
      `<div class="li-sub">TRADING INTELLIGENCE</div>` +
      `<svg class="li-chart" viewBox="0 0 252 120" preserveAspectRatio="none">${candles}<path class="li-trend" d="M0 96 C40 90 60 70 90 66 S150 40 180 34 S230 14 252 10"/></svg>` +
      `<div class="li-bar"><i></i></div><div class="li-skip">click or press any key to skip</div></div>`;
    body.appendChild(intro);
    body.classList.add('scene-intro');
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      intro.classList.add('li-out');
      body.classList.remove('scene-intro');
      body.classList.add('scene-ready');
      setTimeout(() => intro.remove(), 900);
      window.removeEventListener('keydown', finish);
    };
    intro.addEventListener('click', finish);
    window.addEventListener('keydown', finish);
    setTimeout(finish, 2600);
  }

  /* ----------------------------------------------------------- canvas */
  function makeScene(host, full) {
    const canvas = document.createElement('canvas');
    canvas.className = full ? 'loki-scene-canvas full' : 'loki-scene-canvas';
    canvas.setAttribute('aria-hidden', 'true');
    if (full) body.prepend(canvas); else host.prepend(canvas);
    const ctx = canvas.getContext('2d');
    let w = 0, h = 0, dpr = 1, t = 0, raf = 0, running = true;
    const mouse = { x: 0, y: 0, tx: 0, ty: 0 };

    // Seeded random walks so lines look like price series, not noise.
    let seed = 7;
    const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const walk = (n, vol, drift) => {
      const pts = [0];
      for (let i = 1; i < n; i++) pts.push(pts[i - 1] + (rnd() - 0.5 + drift) * vol);
      const min = Math.min(...pts), max = Math.max(...pts);
      return pts.map((v) => (v - min) / (max - min || 1));
    };
    const layers = [
      { pts: walk(260, 1, 0.04), speed: 0.10, amp: 0.30, base: 0.78, alpha: 0.10, width: 1 },
      { pts: walk(260, 1, 0.05), speed: 0.18, amp: 0.34, base: 0.72, alpha: 0.16, width: 1.2 },
      { pts: walk(260, 1, 0.06), speed: 0.30, amp: 0.38, base: 0.66, alpha: 0.26, width: 1.5 },
      { pts: walk(260, 1, 0.07), speed: 0.48, amp: 0.42, base: 0.60, alpha: 0.55, width: 2, front: true },
    ];
    const particles = Array.from({ length: full ? 70 : 38 }, () => ({ x: rnd(), y: rnd(), vx: (rnd() - 0.5) * 0.00025, vy: -0.0001 - rnd() * 0.00035, r: 0.6 + rnd() * 1.6 }));

    function resize() {
      const rect = full ? { width: window.innerWidth, height: window.innerHeight } : host.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      w = Math.max(1, rect.width); h = Math.max(1, rect.height);
      canvas.width = w * dpr; canvas.height = h * dpr;
      canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function lineY(layer, x, offset) {
      const n = layer.pts.length;
      const step = w / 90;
      const pos = (x + offset) / step;
      const i = Math.floor(pos) % n, j = (i + 1) % n, f = pos - Math.floor(pos);
      const v = layer.pts[(i + n) % n] * (1 - f) + layer.pts[(j + n) % n] * f;
      return h * layer.base - v * h * layer.amp;
    }

    function frame() {
      if (!running) return;
      t += 1;
      mouse.x += (mouse.tx - mouse.x) * 0.05;
      mouse.y += (mouse.ty - mouse.y) * 0.05;
      ctx.clearRect(0, 0, w, h);

      // particles + links
      for (const p of particles) {
        p.x += p.vx; p.y += p.vy;
        if (p.y < -0.05) { p.y = 1.05; p.x = Math.random(); }
        if (p.x < -0.05) p.x = 1.05; if (p.x > 1.05) p.x = -0.05;
      }
      ctx.lineWidth = 0.6;
      for (let a = 0; a < particles.length; a++) {
        const pa = particles[a];
        const ax = pa.x * w + mouse.x * 14, ay = pa.y * h + mouse.y * 14;
        for (let b = a + 1; b < particles.length; b++) {
          const pb = particles[b];
          const dx = ax - (pb.x * w + mouse.x * 14), dy = ay - (pb.y * h + mouse.y * 14);
          const d = dx * dx + dy * dy;
          if (d < 12000) {
            ctx.strokeStyle = `rgba(139,218,212,${0.12 * (1 - d / 12000)})`;
            ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(pb.x * w + mouse.x * 14, pb.y * h + mouse.y * 14); ctx.stroke();
          }
        }
        ctx.fillStyle = 'rgba(184,240,216,.55)';
        ctx.beginPath(); ctx.arc(ax, ay, pa.r, 0, Math.PI * 2); ctx.fill();
      }

      // price-line terrain, back to front, with parallax
      layers.forEach((layer, k) => {
        const offset = t * layer.speed * (1 + k * 0.2);
        const px = mouse.x * (6 + k * 8), py = mouse.y * (4 + k * 6);
        const grad = ctx.createLinearGradient(0, 0, w, 0);
        grad.addColorStop(0, `rgba(139,218,212,0)`);
        grad.addColorStop(0.25, `rgba(139,218,212,${layer.alpha})`);
        grad.addColorStop(1, `rgba(201,255,226,${layer.alpha})`);
        ctx.beginPath();
        for (let x = -20; x <= w + 20; x += 6) {
          const y = lineY(layer, x, offset) + py;
          if (x === -20) ctx.moveTo(x + px, y); else ctx.lineTo(x + px, y);
        }
        if (layer.front) {
          ctx.strokeStyle = `rgba(168,240,198,0.10)`; ctx.lineWidth = 9; ctx.stroke(); // soft glow pass
          // area fill under the front line
          ctx.lineTo(w + 20 + px, h); ctx.lineTo(-20 + px, h); ctx.closePath();
          const fill = ctx.createLinearGradient(0, h * 0.3, 0, h);
          fill.addColorStop(0, 'rgba(168,240,198,0.10)'); fill.addColorStop(1, 'rgba(168,240,198,0)');
          ctx.fillStyle = fill; ctx.fill();
          ctx.beginPath();
          for (let x = -20; x <= w + 20; x += 6) {
            const y = lineY(layer, x, offset) + py;
            if (x === -20) ctx.moveTo(x + px, y); else ctx.lineTo(x + px, y);
          }
        }
        ctx.strokeStyle = grad; ctx.lineWidth = layer.width; ctx.stroke();
        if (layer.front) {
          // the "live price" head with a pulsing ring
          const hx = w * 0.82, hy = lineY(layer, hx - px, offset) + py;
          const pulse = (t % 90) / 90;
          ctx.strokeStyle = `rgba(201,255,226,${0.6 * (1 - pulse)})`;
          ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(hx + px, hy, 4 + pulse * 18, 0, Math.PI * 2); ctx.stroke();
          ctx.fillStyle = '#c9ffe2';
          ctx.beginPath(); ctx.arc(hx + px, hy, 3.5, 0, Math.PI * 2); ctx.fill();
        }
      });
      raf = requestAnimationFrame(frame);
    }

    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', (e) => {
      mouse.tx = (e.clientX / window.innerWidth - 0.5) * 2;
      mouse.ty = (e.clientY / window.innerHeight - 0.5) * 2;
    }, { passive: true });
    document.addEventListener('visibilitychange', () => {
      running = !document.hidden;
      if (running) { cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
    });
    if (!full && 'IntersectionObserver' in window) {
      new IntersectionObserver(([entry]) => {
        running = entry.isIntersecting && !document.hidden;
        if (running) { cancelAnimationFrame(raf); raf = requestAnimationFrame(frame); }
      }).observe(host);
    }
    if (!full && 'ResizeObserver' in window) new ResizeObserver(resize).observe(host);
    if (reduce) { running = true; frame(); running = false; return; } // one static frame
    raf = requestAnimationFrame(frame);
  }

  /* ----------------------------------------------------------- ticker */
  async function fillTicker(el) {
    const fmt = (v, s) => {
      const d = /=X$/.test(s) ? 4 : v >= 1 ? 2 : 4;
      return Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
    };
    try {
      const res = await fetch('/api/markets/live', { cache: 'no-store', signal: AbortSignal.timeout(20000) });
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      const items = (data.categories || []).flatMap((c) => c.items).filter((i) => i.ok);
      if (!items.length) throw new Error('empty');
      const row = items.map((i) => {
        const up = (i.change_pct ?? 0) >= 0;
        return `<span class="lt-item"><b>${esc(i.label || i.symbol)}</b> ${esc(fmt(i.price, i.symbol))} <em class="${up ? 'up' : 'down'}">${up ? '▲' : '▼'} ${esc(Math.abs(i.change_pct ?? 0).toFixed(2))}%</em></span>`;
      }).join('');
      el.innerHTML = `<div class="lt-track"><div class="lt-row">${row}</div><div class="lt-row" aria-hidden="true">${row}</div></div>`;
      el.style.setProperty('--lt-duration', `${Math.max(40, items.length * 3.2)}s`);
      el.hidden = false;
    } catch {
      if (!el.innerHTML) el.hidden = true;
    }
  }

  /* ------------------------------------------------------ word reveal */
  function splitWords() {
    document.querySelectorAll('[data-reveal-words]').forEach((el) => {
      if (el.dataset.revealDone) return;
      el.dataset.revealDone = '1';
      let i = 0;
      const walkNode = (node) => {
        [...node.childNodes].forEach((child) => {
          if (child.nodeType === 3) {
            const frag = document.createDocumentFragment();
            child.textContent.split(/(\s+)/).forEach((part) => {
              if (!part) return;
              if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(part)); return; }
              const span = document.createElement('span');
              span.className = 'rw';
              span.style.setProperty('--i', String(i++));
              span.textContent = part;
              frag.appendChild(span);
            });
            child.replaceWith(frag);
          } else if (child.nodeType === 1 && child.tagName !== 'BR') {
            walkNode(child);
          }
        });
      };
      walkNode(el);
    });
  }

  /* ------------------------------------------------------- card glow */
  function wireGlow() {
    if (reduce) return;
    document.addEventListener('pointermove', (e) => {
      const card = e.target.closest && e.target.closest('.loki-glow');
      if (!card) return;
      const r = card.getBoundingClientRect();
      card.style.setProperty('--gx', `${e.clientX - r.left}px`);
      card.style.setProperty('--gy', `${e.clientY - r.top}px`);
    }, { passive: true });
  }

  function init() {
    splitWords();
    playIntro();
    if (body.dataset.lokiScene === 'full') makeScene(body, true);
    document.querySelectorAll('[data-loki-scene="hero"]').forEach((host) => makeScene(host, false));
    const ticker = document.getElementById('loki-ticker');
    if (ticker) { fillTicker(ticker); setInterval(() => { if (!document.hidden) fillTicker(ticker); }, 60000); }
    document.querySelectorAll('.workspace-launchers > a, .metric, .workflow-card, .peek-card').forEach((el) => el.classList.add('loki-glow'));
    wireGlow();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
