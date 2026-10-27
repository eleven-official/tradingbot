/* ==========================================================================
   LOKI — Aurora surface behaviour
   Presentation only. Never touches a data path, a fetch, or a stored value:
   it reads what the app already rendered and makes the transition visible.
   ========================================================================== */
'use strict';
(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const panelSelector = '.panel, .metric, .workflow-card, .workspace-launchers > a, .news-item, .analyst-card, .factor-card, .sim-quote, .integration-card';

  /* ---------- 1. staggered reveal ---------- */
  function wireReveal() {
    if (reduceMotion || !('IntersectionObserver' in window)) return;
    const nodes = [...document.querySelectorAll(panelSelector)].filter(node => !node.closest('[hidden]'));
    if (!nodes.length) return;

    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.04 });

    nodes.forEach((node, index) => {
      if (node.classList.contains('aurora-reveal')) return;
      node.classList.add('aurora-reveal');
      node.style.transitionDelay = `${Math.min(index % 6, 5) * 40}ms`;
      observer.observe(node);
    });

    // Views are toggled, not re-created: reveal anything that became visible late.
    document.addEventListener('loki:view', () => {
      requestAnimationFrame(() => {
        for (const node of document.querySelectorAll(panelSelector)) {
          if (node.closest('[hidden]') || node.classList.contains('is-visible')) continue;
          node.classList.add('aurora-reveal');
          observer.observe(node);
        }
      });
    });
  }

  /* ---------- 2. metric count-up ---------- */
  const NUMBER = /^([^0-9+\-]*)([+\-]?\d[\d,]*(?:\.\d+)?)([\s\S]*)$/;
  const lastValue = new WeakMap();
  const rafFor = new WeakMap();
  const pending = new Set();
  let flushQueued = false;

  function animateMetric(node) {
    const text = (node.textContent || '').trim();
    if (!text || text.length > 22) return;
    const match = text.match(NUMBER);
    if (!match) {
      lastValue.delete(node);
      return;
    }
    const [, prefix, rawNumber, suffix] = match;
    const target = Number(rawNumber.replace(/,/g, ''));
    if (!Number.isFinite(target)) return;

    const previous = lastValue.get(node);
    lastValue.set(node, target);
    if (reduceMotion || previous === undefined || previous === target) return;

    const decimals = (rawNumber.split('.')[1] || '').length;
    const grouped = rawNumber.includes(',');
    const started = performance.now();
    const duration = 620;
    const from = previous;

    const previousFrame = rafFor.get(node);
    if (previousFrame) cancelAnimationFrame(previousFrame);

    const render = (value) => {
      const body = grouped
        ? value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
        : value.toFixed(decimals);
      node.textContent = `${prefix}${body}${suffix}`;
    };

    const step = (now) => {
      const progress = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      render(from + (target - from) * eased);
      if (progress < 1) {
        rafFor.set(node, requestAnimationFrame(step));
      } else {
        render(target);
        rafFor.delete(node);
      }
    };
    rafFor.set(node, requestAnimationFrame(step));
  }

  function flushMetrics() {
    flushQueued = false;
    for (const node of pending) animateMetric(node);
    pending.clear();
  }

  function queueMetric(node) {
    pending.add(node);
    if (flushQueued) return;
    flushQueued = true;
    requestAnimationFrame(flushMetrics);
  }

  function wireCounters() {
    const metricHost = '.metric, .inline-metric, .sim-quote, .dive-end-depth, .council-decision h3';
    const observer = new MutationObserver((records) => {
      let budget = 40;
      for (const record of records) {
        if (budget-- <= 0) break;
        const host = record.target.nodeType === 1 ? record.target : record.target.parentElement;
        if (!host) continue;
        const target = host.closest(metricHost);
        if (!target) continue;
        const value = target.matches('strong, h3, .dive-end-depth') ? target : target.querySelector('strong');
        if (value) queueMetric(value);
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  }

  /* ---------- 3. hero aurora follows the pointer ---------- */
  function wireHeroSpotlight() {
    if (reduceMotion) return;
    for (const hero of document.querySelectorAll('.hero')) {
      let frame = 0;
      hero.addEventListener('pointermove', (event) => {
        if (frame) return;
        frame = requestAnimationFrame(() => {
          frame = 0;
          const box = hero.getBoundingClientRect();
          if (!box.width || !box.height) return;
          hero.style.setProperty('--mx', `${((event.clientX - box.left) / box.width) * 100}%`);
          hero.style.setProperty('--my', `${((event.clientY - box.top) / box.height) * 100}%`);
        });
      }, { passive: true });
    }
  }

  /* ---------- 4. boot ---------- */
  function boot() {
    wireReveal();
    wireCounters();
    wireHeroSpotlight();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
