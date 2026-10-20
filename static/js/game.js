/* Loki Dive — a rare-answer trivia game (krillion-style), unlimited mode.
 * Pure vanilla JS, no console noise, pauses itself whenever the view is hidden.
 * Scoring is local: nothing about a player's answers leaves the browser.
 */
"use strict";
(function () {
  const bank = window.LokiDiveBank;
  if (!bank || !Array.isArray(bank.prompts) || bank.prompts.length < 7) return;

  const ROUND_MS = 25000;
  const ROUNDS_PER_DIVE = 7;
  const POINTS_PER_METRE = 10;
  const METER_MAX = ROUNDS_PER_DIVE * 100 * POINTS_PER_METRE; // 7,000 m, a perfect dive

  const els = {};
  const LS_BEST = "loki_dive_best";
  const LS_DIVES = "loki_dive_dives";

  const state = {
    phase: "idle", // idle | round | between | done
    order: [],
    cursor: 0,
    round: 0,
    points: 0,
    rounds: [], // {prompt, tier|null, points, answer}
    current: null,
    deadline: 0,
    tLeft: ROUND_MS,
    accepted: false,
    pausedAgo: false,
    flashTimer: 0,
    sectionEl: null,
    best: 0,
    dives: 0,
    visible: true,
    running: false,
    rafId: 0,
    nextTimer: 0
  };

  /* ---------- helpers ---------- */
  function flashResume() {
    state.pausedAgo = false;
    const node = els["dive-overlay"];
    if (!node) return;
    node.textContent = "⏸ Pause held — the clock kept its word. Full time resumes now.";
    node.hidden = false;
    window.clearTimeout(state.flashTimer);
    state.flashTimer = window.setTimeout(() => { node.hidden = true; }, 1600);
  }
  function $(id) { return document.getElementById(id); }
  function esc(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }
  function normalize(text) {
    if (typeof text !== "string") return "";
    let s = text.trim().toLowerCase();
    if (s.normalize) {
      s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    }
    s = s.replace(/&/g, " and ").replace(/[^a-z0-9\s']/g, " ").replace(/'/g, "").replace(/\s+/g, " ").trim();
    if (s === "the answer") return "";
    // drop a leading "a"/"an"/"the" for matching ("a parrot" == "parrot")    s = s.replace(/^(a|an|the)\s+/, "").replace(/\s+/g, " ").trim();
    return s;
  }
  function fmtM(m) { return Number(m).toLocaleString("en-AU") + " m"; }
  function storage(key, fallback) {
    try {
      const v = window.localStorage.getItem(key);
      return v === null ? fallback : Number(v) || 0;
    } catch { return fallback; }
  }
  function saveStorage(key, value) {
    try { window.localStorage.setItem(key, String(value)); } catch { /* private mode */ }
  }
  function shuffle(list) {
    const out = list.slice();
    for (let i = out.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }
  function tierClass(i) { return "dive-tier dive-tier-" + i; }

  /* ---------- answer index ---------- */
  function buildIndex(prompt) {
    const map = new Map();
    prompt.a.forEach(([answer, tier]) => {
      const key = normalize(answer);
      if (key && !map.has(key)) map.set(key, { tier, answer });
    });
    return map;
  }

  /* ---------- rendering ---------- */
  function show(screen) {
    ["dive-start", "dive-play", "dive-end"].forEach((id) => {
      const node = els[id];
      if (node) node.hidden = screen !== id;
    });
  }
  function renderLegend() {
    const host = els["dive-legend"];
    if (!host) return;
    host.innerHTML = bank.tiers.map((t, i) => (
      `<span class="${tierClass(i)}" title="${esc(t.note)}">${esc(t.name)} · ${t.points}</span>`
    )).join("");
  }
  function renderDepth() {
    const depth = state.points * POINTS_PER_METRE;
    const pct = Math.max(0, Math.min(100, (depth / METER_MAX) * 100));
    if (els["dive-depth-num"]) els["dive-depth-num"].textContent = fmtM(depth);
    if (els["dive-depthbar"]) els["dive-depthbar"].style.height = pct + "%";
  }
  function renderBest() {
    if (els["dive-best"]) els["dive-best"].textContent = state.best ? "Best " + fmtM(state.best * POINTS_PER_METRE) : "No dive yet";
    if (els["dive-dives"]) els["dive-dives"].textContent = state.dives ? state.dives + (state.dives === 1 ? " dive" : " dives") : "Fresh waters";
  }

  /* ---------- game flow ---------- */
  function startRun() {
    state.order = shuffle(bank.prompts.map((_, i) => i));
    state.cursor = 0;
    state.round = 0;
    state.points = 0;
    state.rounds = [];
    state.dives += 1;
    saveStorage(LS_DIVES, state.dives);
    renderBest();
    show("dive-play");
    nextRound();
  }
  function nextRound() {
    window.clearTimeout(state.nextTimer);
    if (state.round >= ROUNDS_PER_DIVE || state.cursor >= state.order.length) { endRun(); return; }
    const promptIdx = state.order[state.cursor];
    state.current = { prompt: bank.prompts[promptIdx], index: buildIndex(bank.prompts[promptIdx]) };
    state.cursor += 1;
    state.round += 1;
    state.accepted = false;
    state.tLeft = ROUND_MS;
    state.deadline = performance.now() + ROUND_MS;

    const p = state.current.prompt;
    if (els["dive-round"]) els["dive-round"].textContent = "Round " + state.round + " of " + ROUNDS_PER_DIVE;
    els["dive-prompt"].textContent = p.q;
    if (els["dive-rules"]) els["dive-rules"].textContent = p.rules || "";
    if (els["dive-answer"]) els["dive-answer"].value = "";
    feedback("", "");
    show("dive-play");
    renderDepth();
    if (state.visible) {
      try { els["dive-answer"].focus({ preventScroll: true }); } catch { /* older engines */ }
    }
    state.phase = "round";
    state.running = true;
    if (!state.rafId) loop(performance.now());
  }
  function feedback(text, cls) {
    const node = els["dive-feedback"];
    if (!node) return;
    node.hidden = !text;
    node.textContent = text || "";
    node.className = "dive-feedback" + (cls ? " " + cls : "");
  }
  function submit(ev) {
    if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
    if (state.phase !== "round" || state.accepted) return;
    const raw = els["dive-answer"] ? els["dive-answer"].value : "";
    const key = normalize(raw);
    if (!key) {
      feedback("Type one answer first — the clock is kind enough.", "warn");
      return;
    }
    const hit = state.current.index.get(key);
    if (hit) {
      state.accepted = true;
      state.phase = "between";
      const tier = bank.tiers[hit.tier];
      const pts = tier.points;
      state.points += pts;
      state.rounds.push({ q: state.current.prompt.q, tier: hit.tier, points: pts, answer: hit.answer });
      feedback("✓ “" + hit.answer + "” — " + tier.name + "! +" + pts + " points · " + fmtM(pts * POINTS_PER_METRE), "good");
      renderDepth();
      window.clearTimeout(state.nextTimer);
      state.nextTimer = window.setTimeout(nextRound, 2600);
      state.running = false; // clock stops between rounds
    } else {
      feedback("Not on the list. Keep the clock company — try another idea.", "warn");
      if (els["dive-answer"]) { els["dive-answer"].select(); }
    }
  }
  function timeUp() {
    if (state.phase !== "round") return;
    state.accepted = true;
    state.running = false;
    state.phase = "between";
    state.rounds.push({ q: state.current.prompt.q, tier: null, points: 0, answer: "" });
    feedback("Time's up for this round. The current moves on.", "warn");
    window.clearTimeout(state.nextTimer);
    state.nextTimer = window.setTimeout(nextRound, 1900);
  }
  function endRun() {
    window.clearTimeout(state.nextTimer);
    if (state.rafId) { window.cancelAnimationFrame(state.rafId); state.rafId = 0; }
    state.phase = "done";
    state.running = false;
    const depth = state.points * POINTS_PER_METRE;
    const prevBest = state.best;
    const newBest = state.points > state.best;
    if (newBest) {
      state.best = state.points;
      saveStorage(LS_BEST, state.best);
      renderBest();
    }
    const rows = state.rounds.map((r, i) => {
      const tier = r.tier === null ? null : bank.tiers[r.tier];
      return (`<div class="dive-result-row${tier ? "" : " dive-result-miss"}">`
        + `<span class="dive-result-n">${i + 1}</span>`
        + `<span class="dive-result-q">${esc(r.q)}</span>`
        + `<span class="dive-result-a">${esc(r.answer || "—")}</span>`
        + (tier
          ? `<span class="${tierClass(r.tier)}">${esc(tier.name)} +${r.points}</span>`
          : `<span class="dive-tier dive-tier-miss">missed · +0</span>`)
        + `</div>`);
    }).join("");
    if (els["dive-end-depth"]) els["dive-end-depth"].textContent = fmtM(depth);
    if (els["dive-end-points"]) els["dive-end-points"].textContent = state.points + " points";
    if (els["dive-end-best"]) {
      els["dive-end-best"].textContent = newBest
        ? "New personal best — a full " + fmtM((state.points - prevBest) * POINTS_PER_METRE) + " deeper than before!"
        : "Personal best: " + fmtM(state.best * POINTS_PER_METRE);
    }
    const verdict = depth >= 5000 ? "Abyssal. You think in trenches."
      : depth >= 3500 ? "Strong dive — well past the shelves."
        : depth >= 2000 ? "Solid mid-water. Worth another drop."
          : depth >= 900 ? "Shore-ish. The crowd kept you floating."
            : "Surface swimming — try thinking like nobody else.";
    if (els["dive-end-verdict"]) els["dive-end-verdict"].textContent = verdict;
    if (els["dive-end-rows"]) els["dive-end-rows"].innerHTML = rows;
    renderDepth();
    show("dive-end");
    if (els["dive-copy"]) els["dive-copy"].textContent = "Copy result";
  }
  function copyResult(ev) {
    if (ev) ev.preventDefault();
    const depth = state.points * POINTS_PER_METRE;
    const lines = state.rounds.map((r, i) => {
      const label = r.tier === null ? "missed" : bank.tiers[r.tier].name;
      return (i + 1) + ". " + r.q + " — " + (r.answer || "—") + " (" + label + ", +" + r.points + ")";
    });
    const text = "🪂 Loki Dive — " + fmtM(depth) + " deep (" + state.points + " pts)\n" + lines.join("\n")
      + "\nUnlimited rare-answer trivia, only on this site.";
    const ok = () => {
      if (els["dive-copy"]) els["dive-copy"].textContent = "Copied ✓";
    };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok, () => { fallbackCopy(text) ? ok() : null; });
      } else {
        fallbackCopy(text) ? ok() : null;
      }
    } catch { try { fallbackCopy(text) ? ok() : null; } catch { /* clipboard unavailable */ } }
  }
  function fallbackCopy(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      let done = false;
      try { done = document.execCommand("copy"); } catch { done = false; }
      ta.remove();
      return done;
    } catch { return false; }
  }

  /* ---------- loop & pause ---------- */
  function loop(ts) {
    state.rafId = window.requestAnimationFrame(loop);
    if (!state.running) return;
    const sec = state.sectionEl;
    const inView = !document.hidden && !!sec && sec.offsetParent !== null;
    if (inView !== state.visible) {
      if (!inView && state.running) state.pausedAgo = true;
      state.visible = inView;
      if (inView && state.pausedAgo) flashResume();
    }
    if (!state.visible) {
      state.deadline = ts + state.tLeft; // freeze the clock while out of sight
      return;
    }
    state.tLeft = Math.max(0, state.deadline - ts);
    if (els["dive-timer"]) {
      const pct = Math.max(0, Math.min(100, (state.tLeft / ROUND_MS) * 100));
      els["dive-timer"].style.width = pct + "%";
      els["dive-timer"].classList.toggle("dive-low", state.tLeft < 6000);
    }
    if (els["dive-clock"]) els["dive-clock"].textContent = Math.ceil(state.tLeft / 1000) + "s";
    if (state.tLeft <= 0) { state.running = false; timeUp(); }
  }

  /* ---------- init ---------- */
  function init() {
    ["dive-start", "dive-play", "dive-end", "dive-legend", "dive-form", "dive-answer", "dive-feedback",
      "dive-timer", "dive-clock", "dive-round", "dive-prompt", "dive-rules", "dive-best", "dive-dives",
      "dive-depth-num", "dive-depthbar", "dive-end-depth", "dive-end-points", "dive-end-best",
      "dive-end-verdict", "dive-end-rows", "dive-copy", "dive-start-btn", "dive-again-btn",
      "dive-overlay", "dive-pause"].forEach((id) => { els[id] = $(id); });
    if (!els["dive-start"] && !els["dive-play"]) return; // section missing — stay silent

    state.best = storage(LS_BEST, 0);
    state.dives = storage(LS_DIVES, 0);
    renderLegend();
    renderBest();
    renderDepth();
    show("dive-start");

    state.visible = document.hidden ? false : true;
    if (els["dive-start-btn"]) els["dive-start-btn"].addEventListener("click", (ev) => { ev.preventDefault(); startRun(); });
    if (els["dive-again-btn"]) els["dive-again-btn"].addEventListener("click", (ev) => { ev.preventDefault(); startRun(); });
    if (els["dive-copy"]) els["dive-copy"].addEventListener("click", copyResult);
    if (els["dive-form"]) els["dive-form"].addEventListener("submit", submit);
    state.sectionEl = els["dive-start"].closest(".workspace-view");
    const updatePause = () => {
      const sec = state.sectionEl;
      const inView = !document.hidden && !!sec && sec.offsetParent !== null;
      if (inView !== state.visible) {
        if (!inView && state.running) state.pausedAgo = true;
        state.visible = inView;
        if (inView && state.pausedAgo) flashResume();
      }
    };
    document.addEventListener("visibilitychange", updatePause);
    window.addEventListener("hashchange", updatePause);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
  window.LokiDive = { state, normalize, tick: loop }; // debugging + verification handle
})();
