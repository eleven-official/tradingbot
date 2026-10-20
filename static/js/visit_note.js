/* "Since your last visit" — a purely client-side diff of the Overview metrics and
   strategy-book count, kept in localStorage. Nothing leaves the browser. */
(() => {
  "use strict";
  const KEY = "loki_visit_snapshot";
  const METRICS = {
    return: "#return-metric",
    drawdown: "#drawdown-metric",
    winrate: "#winrate-metric",
    verdict: "#verdict-metric"
  };
  const PLACEHOLDER = new Set(["—", "Awaiting evidence", ""]);

  function readMetric(sel) {
    const el = document.querySelector(sel);
    if (!el) return "";
    const text = (el.textContent || "").replace(/\s+/g, " ").trim();
    return PLACEHOLDER.has(text) ? "" : text;
  }

  function grab() {
    const snap = {};
    for (const [k, sel] of Object.entries(METRICS)) snap[k] = readMetric(sel);
    snap.books = document.querySelectorAll("#trained-book-grid > *").length;
    return snap;
  }

  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  function describe(prev, now) {
    const bits = [];
    if (!prev.verdict && now.verdict) {
      bits.push(`first verdict in: "${now.verdict}"`);
    } else if (prev.verdict && prev.verdict !== now.verdict) {
      bits.push(`verdict moved "${prev.verdict}" → "${now.verdict}"`);
    }
    if (now.return && prev.return !== now.return) bits.push(`out-of-sample return now ${now.return}`);
    if (now.drawdown && prev.drawdown !== now.drawdown) bits.push(`max drawdown now ${now.drawdown}`);
    if (now.winrate && prev.winrate !== now.winrate) bits.push(`win rate now ${now.winrate}`);
    if (typeof prev.books === "number" && prev.books !== now.books) {
      bits.push(`${now.books} strategy card${now.books === 1 ? "" : "s"} on the book (was ${prev.books})`);
    }
    return bits;
  }

  let tries = 0;

  function tick() {
    const note = document.getElementById("visit-note");
    if (!note) return true; // template without the slot — stop retrying
    const snap = grab();
    if (!snap.verdict && !snap.return && !snap.books && tries < 20) return false; // numbers not rendered yet
    let prev = null;
    try { prev = JSON.parse(localStorage.getItem(KEY) || "null"); } catch { prev = null; }
    if (prev && !same(prev, snap)) {
      const bits = describe(prev, snap);
      if (bits.length) {
        note.textContent = "Since your last visit: " + bits.join(" · ") + ".";
        note.hidden = false;
      }
    }
    try { localStorage.setItem(KEY, JSON.stringify(snap)); } catch { /* storage off — fine */ }
    return true;
  }

  function start() {
    if (!document.getElementById("overview") && !document.getElementById("visit-note")) return;
    const timer = setInterval(() => {
      tries += 1;
      try { if (tick() || tries > 20) clearInterval(timer); }
      catch { clearInterval(timer); }
    }, 700);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
