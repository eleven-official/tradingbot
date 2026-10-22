/* Loki Dive — a rare-answer trivia game (krillion-style), unlimited mode.
 * Pure vanilla JS, no console noise, pauses itself whenever the view is hidden.
 * Scoring is local: nothing about a player's answers leaves the browser.
 *
 * Spelling is forgiven: answers match through a Damerau-Levenshtein distance
 * with a small, length-aware tolerance, plus folded articles ("a parrot" ==
 * "parrot") and folded plurals ("gorgonzolas" == "gorgonzola"). When a typo
 * is fixed, the round says so. Prompt draws avoid recently seen prompts so
 * consecutive dives stay fresh until the pool runs low.
 */
"use strict";
(function () {
  const bank = window.LokiDiveBank;
  if (!bank || !Array.isArray(bank.prompts) || bank.prompts.length < 7) return;

  const ROUND_MS = 25000;
  const ROUNDS_PER_DIVE = 7;
  const POINTS_PER_METRE = 10;
  const CLEAN_SWEEP_BONUS = 50; // all seven rounds found
  const HOT_STREAK = 3;         // consecutive finds needed before the combo pays
  const COMBO_BONUS = 5;        // paid per find from the third in a row onward
  const MAX_STREAK_BONUS = (ROUNDS_PER_DIVE - HOT_STREAK + 1) * COMBO_BONUS; // 25 headroom
  const METER_MAX = ROUNDS_PER_DIVE * 100 * POINTS_PER_METRE
    + (CLEAN_SWEEP_BONUS + MAX_STREAK_BONUS) * POINTS_PER_METRE; // 7,750 m headroom
  const RECENT_LIMIT = 10; // remember this many prompts to keep dives fresh

  const els = {};
  const LS_BEST = "loki_dive_best";
  const LS_DIVES = "loki_dive_dives";
  const LS_RECENT = "loki_dive_recent";
  const LS_HISTORY = "loki_dive_history";
  const HISTORY_LIMIT = 10;

  const state = {
    phase: "idle", // idle | round | between | done
    order: [],
    cursor: 0,
    round: 0,
    points: 0,
    bonus: 0,
    streak: 0,
    streakBonus: 0,
    manualPaused: false,
    fixed: 0, // spelling corrections this dive
    rounds: [], // {prompt, tier|null, points, answer, fixed}
    current: null,
    deadline: 0,
    tLeft: ROUND_MS,
    accepted: false,
    sectionEl: null,
    best: 0,
    dives: 0,
    visible: true,
    running: false,
    rafId: 0
  };

  /* ---------- helpers ---------- */
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
    return s;
  }
  /* Fold articles and plurals so near-hits meet exactly before distances kick in. */
  function fold(text) {
    let s = normalize(text);
    if (!s) return "";
    s = s.replace(/^(a|an|the)\s+/, "").replace(/\s+/g, " ").trim();
    if (s.length > 3 && s.endsWith("s") && !s.endsWith("ss")) s = s.slice(0, -1);
    return s;
  }
  /* Length-aware tolerance: short words must be exact, long ones forgive two. */
  function toleranceFor(len) {
    if (len <= 4) return 0;
    if (len <= 7) return 1;
    return 2;
  }
  /* Damerau-Levenshtein (optimal string alignment) distance. */
  function damerauDistance(a, b) {
    const m = a.length;
    const n = b.length;
    if (!m || !n) return m + n;
    const d = [];
    for (let i = 0; i <= m; i += 1) { d.push([i]); d[i][0] = i; }
    for (let j = 0; j <= n; j += 1) d[0][j] = j;
    for (let i = 1; i <= m; i += 1) {
      for (let j = 1; j <= n; j += 1) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        let best = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          best = Math.min(best, d[i - 2][j - 2] + 1); // transposition
        }
        d[i][j] = best;
      }
    }
    return d[m][n];
  }
  /* Exact first, folded variants next, then closest bank entry inside tolerance. */
  function findAnswer(index, raw) {
    const key = normalize(raw);
    if (!key) return null;
    const exact = index.get(key);
    if (exact) return { hit: exact, fixed: false };
    const folded = fold(raw);
    if (folded && index.has(folded)) return { hit: index.get(folded), fixed: false };
    let best = null;
    let bestDist = Infinity;
    let bestKey = "";
    index.forEach((value, entryKey) => {
      const candidates = [entryKey];
      const alt = entryKey.replace(/^the\s+/, "");
      if (alt !== entryKey) candidates.push(alt);
      for (const cand of candidates) {
        if (cand === folded) return; // already checked exactly
        const dist = damerauDistance(folded, cand);
        const tol = toleranceFor(Math.max(folded.length, cand.length));
        if (dist <= tol && dist < bestDist) {
          bestDist = dist;
          best = value;
          bestKey = cand;
        }
      }
    });
    if (best) return { hit: best, fixed: true, via: bestKey };
    return null;
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
  function readRecent() {
    try {
      const raw = JSON.parse(window.localStorage.getItem(LS_RECENT) || "[]");
      return Array.isArray(raw) ? raw.filter((v) => Number.isInteger(v)) : [];
    } catch { return []; }
  }
  function pushRecent(indexes) {
    try {
      const recent = indexes.slice(-RECENT_LIMIT * 2);
      window.localStorage.setItem(LS_RECENT, JSON.stringify(recent));
    } catch { /* storage unavailable — freshness simply restarts */ }
  }
  function shuffle(list) {
    const out = list.slice();
    for (let i = out.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }
  function freshOrder() {
    const all = bank.prompts.map((_, i) => i);
    const recent = readRecent();
    const fresh = all.filter((i) => !recent.includes(i));
    const pool = fresh.length >= ROUNDS_PER_DIVE ? fresh : all;
    const order = shuffle(pool);
    return order.slice(0, ROUNDS_PER_DIVE);
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
    const depth = totalPoints() * POINTS_PER_METRE;
    const pct = Math.max(0, Math.min(100, (depth / METER_MAX) * 100));
    if (els["dive-depth-num"]) els["dive-depth-num"].textContent = fmtM(depth);
    if (els["dive-depthbar"]) els["dive-depthbar"].style.width = pct + "%";
    if (els["dive-score"]) els["dive-score"].textContent = totalPoints() + " pts";
    if (els["dive-combo"]) els["dive-combo"].textContent = state.streak >= HOT_STREAK ? "Streak ×" + state.streak + " · +5 per find" : "Streak " + state.streak + " / 3";
    if (els["dive-progress"]) {
      els["dive-progress"].innerHTML = Array.from({ length: ROUNDS_PER_DIVE }, (_, i) => {
        const row = state.rounds[i];
        const label = row ? (row.tier === null ? "missed" : "found") : i === state.round - 1 ? "current" : "upcoming";
        return `<span class="dive-step ${label}" aria-label="Round ${i + 1}: ${label}">${row ? (row.tier === null ? "−" : "✓") : i + 1}</span>`;
      }).join("");
    }
  }
  function totalPoints() { return state.points + state.bonus + state.streakBonus; }
  function renderBest() {
    if (els["dive-best"]) els["dive-best"].textContent = state.best ? "Best " + fmtM(state.best * POINTS_PER_METRE) : "No dive yet";
    if (els["dive-dives"]) els["dive-dives"].textContent = state.dives ? state.dives + (state.dives === 1 ? " dive" : " dives") : "Fresh waters";
  }

  /* ---------- game flow ---------- */
  function startRun() {
    state.manualPaused = false;
    els["dive-overlay"].hidden = true;
    els["dive-pause"].textContent = "Pause";
    els["dive-pause"].setAttribute("aria-pressed", "false");
    state.order = freshOrder();
    state.cursor = 0;
    state.round = 0;
    state.points = 0;
    state.bonus = 0;
    state.fixed = 0;
    state.streak = 0;
    state.streakBonus = 0;
    state.rounds = [];
    state.dives += 1;
    saveStorage(LS_DIVES, state.dives);
    renderBest();
    show("dive-play");
    nextRound();
    els["dive-play"].scrollIntoView({ block: "start" });
  }
  function nextRound() {
    if (state.round >= ROUNDS_PER_DIVE || state.cursor >= state.order.length) { endRun(); return; }
    const promptIdx = state.order[state.cursor];
    pushRecent(readRecent().concat(promptIdx));
    state.current = { prompt: bank.prompts[promptIdx], index: buildIndex(bank.prompts[promptIdx]) };
    state.cursor += 1;
    state.round += 1;
    state.accepted = false;
    els["dive-next"].hidden = true;
    els["dive-answer"].disabled = false;
    els["dive-submit"].disabled = false;
    els["dive-skip"].disabled = false;
    els["dive-pause"].disabled = false;
    els["dive-examples"].hidden = true;
    state.tLeft = ROUND_MS;
    state.deadline = performance.now() + ROUND_MS;
    els["dive-clock"].textContent = "25s";
    els["dive-timer"].style.width = "100%";
    els["dive-timer"].classList.remove("dive-low");

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
  const MISS_LINES = [
    "Not in this answer bank. Try another — the clock is still running.",
    "The bank doesn't know that one. Different angle?",
    "No match — the list stayed quiet. Something rarer, maybe.",
    "Not this time. The rarer names live further out.",
    "Nothing folded into that. Spin the idea again."
  ];
  function submit(ev) {
    if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
    if (state.manualPaused || !state.visible) return;
    if (state.phase === "between" && state.accepted) {
      // impatient divers can press Enter to surf to the next round immediately
      nextRound();
      return;
    }
    if (state.phase !== "round" || state.accepted) return;
    if (performance.now() >= state.deadline) { timeUp(); return; }
    const raw = els["dive-answer"] ? els["dive-answer"].value : "";
    const key = normalize(raw);
    if (!key) {
      feedback("Type one answer first — the clock is kind enough.", "warn");
      return;
    }
    const match = findAnswer(state.current.index, raw);
    if (match) {
      state.accepted = true;
      state.phase = "between";
      const tier = bank.tiers[match.hit.tier];
      const pts = tier.points;
      state.points += pts;
      state.streak += 1;
      let combo = 0;
      if (state.streak >= HOT_STREAK) {
        combo = COMBO_BONUS;
        state.streakBonus += combo;
      }
      const shown = match.fixed ? `${match.hit.answer} (spelling forgiven)` : match.hit.answer;
      if (match.fixed) state.fixed += 1;
      state.rounds.push({ q: state.current.prompt.q, tier: match.hit.tier, points: pts + combo, answer: shown, fixed: match.fixed });
      feedback("✓ " + shown + " — " + tier.name + "! +" + pts + " points · " + fmtM(pts * POINTS_PER_METRE)
        + (combo ? " 🔥 streak ×" + state.streak + " (+" + combo + ")" : ""), "good");
      renderDepth();
      finishRound(false);
    } else {
      const line = MISS_LINES[Math.floor(Math.random() * MISS_LINES.length)];
      feedback(line, "warn");
      if (els["dive-answer"]) { els["dive-answer"].select(); }
    }
  }
  function skipRound() {
    if (state.phase !== "round" || state.accepted || state.manualPaused || !state.visible) return;
    state.accepted = true;
    state.running = false;
    state.streak = 0;
    state.phase = "between";
    state.rounds.push({ q: state.current.prompt.q, tier: null, points: 0, answer: "", fixed: false });
    feedback("Round skipped. Discover a few answers below, then dive again.", "warn");
    finishRound(true);
  }
  function timeUp() {
    if (state.phase !== "round") return;
    state.accepted = true;
    state.running = false;
    state.streak = 0;
    state.phase = "between";
    state.rounds.push({ q: state.current.prompt.q, tier: null, points: 0, answer: "", fixed: false });
    feedback("Time's up. Here are a few answers to take into your next dive.", "warn");
    finishRound(true);
  }
  function finishRound(showExamples) {
    state.running = false;
    els["dive-answer"].disabled = true;
    els["dive-submit"].disabled = true;
    els["dive-skip"].disabled = true;
    els["dive-pause"].disabled = true;
    els["dive-next"].hidden = false;
    els["dive-next"].textContent = state.round === ROUNDS_PER_DIVE ? "See dive results →" : "Next round →";
    if (showExamples) {
      const samples = [0, 3, 5].map(t => state.current.prompt.a.find(a => a[1] === t)).filter(Boolean);
      els["dive-examples"].textContent = "Bank examples: " + samples.map(a => a[0] + " · " + bank.tiers[a[1]].name).join(" / ");
      els["dive-examples"].hidden = false;
    }
    renderDepth();
    els["dive-next"].focus({ preventScroll: true });
  }
  function togglePause() {
    if (state.phase !== "round") return;
    const now = performance.now();
    if (!state.manualPaused && now >= state.deadline) { timeUp(); return; }
    if (!state.manualPaused) state.tLeft = Math.max(0, state.deadline - now);
    state.manualPaused = !state.manualPaused;
    state.deadline = now + state.tLeft;
    els["dive-pause"].textContent = state.manualPaused ? "Resume" : "Pause";
    els["dive-pause"].setAttribute("aria-pressed", String(state.manualPaused));
    els["dive-overlay"].textContent = "Paused · your remaining time is saved. Press Resume when ready.";
    els["dive-overlay"].hidden = !state.manualPaused;
    els["dive-answer"].disabled = state.manualPaused;
    els["dive-submit"].disabled = state.manualPaused;
    els["dive-skip"].disabled = state.manualPaused;
    if (!state.manualPaused) els["dive-answer"].focus({ preventScroll: true });
  }
  function endRun() {
    if (state.rafId) { window.cancelAnimationFrame(state.rafId); state.rafId = 0; }
    state.phase = "done";
    state.running = false;
    const foundAll = state.rounds.length === ROUNDS_PER_DIVE && state.rounds.every((r) => r.tier !== null);
    if (foundAll && state.points > 0) {
      state.bonus = CLEAN_SWEEP_BONUS;
      if (els["dive-end-extra"]) {
        els["dive-end-extra"].textContent = "🧹 Clean sweep — every round found: +" + CLEAN_SWEEP_BONUS + " bonus points.";
      }
    } else if (els["dive-end-extra"]) {
      els["dive-end-extra"].textContent = "";
    }
    const depth = totalPoints() * POINTS_PER_METRE;
    const tally = {};
    state.rounds.forEach((r) => {
      if (r.tier !== null) tally[r.tier] = (tally[r.tier] || 0) + 1;
    });
    let rarestTier = -1;
    state.rounds.forEach((r) => { if (r.tier !== null && r.tier > rarestTier) rarestTier = r.tier; });
    const rarestLine = rarestTier >= 0
      ? "Deepest find: " + (state.rounds.filter((r) => r.tier === rarestTier)[0].answer || "—")
        + " (" + bank.tiers[rarestTier].name + ")."
      : "";
    const tallyLine = Object.keys(tally).map((t) => bank.tiers[t].name + " ×" + tally[t]).join(" · ");
    const spellingLine = state.fixed
      ? " The engine forgave " + state.fixed + (state.fixed === 1 ? " typo" : " typos") + " this dive."
      : "";
    const streakLine = state.streakBonus
      ? " Nested combo: a streak of finds paid +" + state.streakBonus + " extra."
      : "";
    if (els["dive-end-extra"] && rarestLine) {
      const extra = els["dive-end-extra"];
      extra.textContent = (extra.textContent ? extra.textContent + " " : "") + rarestLine
        + (tallyLine ? " Tally: " + tallyLine + "." : "") + spellingLine + streakLine;
    }
    const prevBest = state.best;
    const newBest = totalPoints() > state.best;
    if (newBest) {
      state.best = totalPoints();
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
    if (els["dive-end-points"]) els["dive-end-points"].textContent = totalPoints() + " points";
    if (els["dive-end-best"]) {
      els["dive-end-best"].textContent = newBest
        ? "New personal best — a full " + fmtM((totalPoints() - prevBest) * POINTS_PER_METRE) + " deeper than before!"
        : "Personal best: " + fmtM(state.best * POINTS_PER_METRE);
    }
    const verdict = depth >= 6500 ? "Abyssal. You think in trenches."
      : depth >= 4800 ? "Strong dive — well past the shelves."
        : depth >= 3000 ? "Solid mid-water. Worth another drop."
          : depth >= 1400 ? "Shore-ish. The crowd kept you floating."
            : "Surface swimming — try thinking like nobody else.";
    if (els["dive-end-verdict"]) els["dive-end-verdict"].textContent = verdict;
    if (els["dive-end-rows"]) els["dive-end-rows"].innerHTML = rows;
    try {
      const hist = JSON.parse(localStorage.getItem(LS_HISTORY) || "[]");
      hist.push({ p: totalPoints(), t: Date.now() });
      localStorage.setItem(LS_HISTORY, JSON.stringify(hist.slice(-HISTORY_LIMIT)));
    } catch { /* storage blocked — the trend line simply stays empty */ }
    renderDepth();
    show("dive-end");
    renderHistory();
    els["dive-again-btn"].focus({ preventScroll: true });
    if (!challenge.done && totalPoints() >= challenge.target) {
      challenge.done = true;
      try { localStorage.setItem(LS_CHALLENGE, JSON.stringify({ d: dayKey(), o: totalPoints() })); } catch { /* ignore */ }
      renderChallenge();
    }
    if (els["dive-copy"]) els["dive-copy"].textContent = "Copy result";
  }
  function copyResult(ev) {
    if (ev) ev.preventDefault();
    const depth = totalPoints() * POINTS_PER_METRE;
    const lines = state.rounds.map((r, i) => {
      const label = r.tier === null ? "missed" : bank.tiers[r.tier].name;
      return (i + 1) + ". " + r.q + " — " + (r.answer || "—") + " (" + label + ", +" + r.points + ")";
    });
    const bonusLine = state.bonus ? "\nClean sweep bonus: +" + state.bonus : "";
    const comboLine = state.streakBonus ? "\nStreak combo bonus: +" + state.streakBonus : "";
    const text = "🪂 Loki Dive — " + fmtM(depth) + " deep (" + totalPoints() + " pts)\n" + lines.join("\n")
      + bonusLine + comboLine + "\nUnlimited rare-answer trivia, only on this site.";
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
    if (inView !== state.visible) updatePause();
    if (!state.visible || state.manualPaused) return;
    state.tLeft = Math.max(0, state.deadline - ts);
    if (els["dive-timer"]) {
      const pct = Math.max(0, Math.min(100, (state.tLeft / ROUND_MS) * 100));
      els["dive-timer"].style.width = pct + "%";
      els["dive-timer"].classList.toggle("dive-low", state.tLeft < 6000);
    }
    if (els["dive-clock"]) els["dive-clock"].textContent = Math.ceil(state.tLeft / 1000) + "s";
    if (state.tLeft <= 0) { state.running = false; timeUp(); }
  }
  function updatePause() {
    const inView = !document.hidden && !!state.sectionEl && state.sectionEl.offsetParent !== null;
    if (inView === state.visible) return;
    const now = performance.now();
    if (!inView && state.running && !state.manualPaused) state.tLeft = Math.max(0, state.deadline - now);
    if (inView) state.deadline = now + state.tLeft;
    state.visible = inView;
  }

  /* ---------- daily challenge ---------- */
  const LS_CHALLENGE = "loki_dive_challenge";
  const CHALLENGE_STEPS = [110, 130, 150, 170, 120, 140, 160]; // target points per weekday (UTC)
  const challenge = { target: 0, done: false };
  function dayKey() { return new Date().toISOString().slice(0, 10); }
  function loadChallenge() {
    challenge.target = CHALLENGE_STEPS[new Date().getUTCDay()];
    let best = 0;
    try {
      const saved = JSON.parse(localStorage.getItem(LS_CHALLENGE) || "null");
      if (saved && saved.d === dayKey()) best = Number(saved.o) || 0;
    } catch { /* unreadable storage — the challenge simply resets */ }
    challenge.done = best >= challenge.target;
  }
  function renderChallenge() {
    const node = els["dive-challenge"];
    if (!node) return;
    node.textContent = challenge.done
      ? "🎯 Challenge done ✓"
      : "🎯 Today: " + challenge.target + "+ pts";
    node.title = challenge.done
      ? "Depth target cleared — a fresh one arrives tomorrow."
      : "Score " + challenge.target + "+ points in one dive today.";
  }

  /* ---------- dive history (start-screen trend) ---------- */
  function loadHistory() {
    try {
      const hist = JSON.parse(localStorage.getItem(LS_HISTORY) || "[]");
      return Array.isArray(hist) ? hist : [];
    } catch { return []; }
  }
  function renderHistory() {
    const node = els["dive-history"];
    if (!node) return;
    const hist = loadHistory();
    if (!hist.length) { node.textContent = ""; return; }
    // Points stay in the browser only; meters are just points × 10 rounded.
    const recent = hist.slice(-5).map((h) => String(Math.round((Number(h.p) || 0) * POINTS_PER_METRE)));
    const best = hist.reduce((mx, h) => Math.max(mx, Number(h.p) || 0), 0);
    let trend = "";
    if (hist.length >= 4) {
      const six = hist.slice(-6);
      const mid = Math.ceil(six.length / 2);
      const older = six.slice(0, mid).reduce((s, h) => s + (Number(h.p) || 0), 0) / mid;
      const newer = six.slice(mid).reduce((s, h) => s + (Number(h.p) || 0), 0) / (six.length - mid);
      trend = newer > older * 1.05 ? " ↗ trend up" : newer < older * 0.95 ? " ↘ trend down" : " → steady";
    }
    node.textContent = "Recent dives: " + recent.join(" · ") + " m — best " + fmtM(best * POINTS_PER_METRE) + trend;
  }

  /* ---------- init ---------- */
  function init() {
    ["dive-start", "dive-play", "dive-end", "dive-legend", "dive-form", "dive-answer", "dive-feedback",
      "dive-timer", "dive-clock", "dive-round", "dive-prompt", "dive-rules", "dive-best", "dive-dives",
      "dive-depth-num", "dive-depthbar", "dive-end-depth", "dive-end-points", "dive-end-best",
      "dive-end-verdict", "dive-end-rows", "dive-end-extra", "dive-copy", "dive-start-btn", "dive-again-btn",
      "dive-skip", "dive-count", "dive-history", "dive-overlay", "dive-pause", "dive-challenge",
      "dive-submit", "dive-next", "dive-examples", "dive-score", "dive-combo", "dive-progress"].forEach((id) => { els[id] = $(id); });
    if (!els["dive-start"] && !els["dive-play"]) return; // section missing — stay silent

    const promptsEl = els["dive-count"];
    if (promptsEl) {
      promptsEl.textContent = bank.prompts.length + " prompts · " + bank.prompts.reduce((sum, p) => sum + p.a.length, 0)
        + " banked answers · spelling forgiven";
    }

    state.best = storage(LS_BEST, 0);
    state.dives = storage(LS_DIVES, 0);
    loadChallenge();
    renderLegend();
    renderBest();
    renderChallenge();
    renderHistory();
    renderDepth();
    show("dive-start");

    state.visible = document.hidden ? false : true;
    if (els["dive-start-btn"]) els["dive-start-btn"].addEventListener("click", (ev) => { ev.preventDefault(); startRun(); });
    if (els["dive-again-btn"]) els["dive-again-btn"].addEventListener("click", (ev) => { ev.preventDefault(); startRun(); });
    if (els["dive-skip"]) els["dive-skip"].addEventListener("click", skipRound);
    if (els["dive-copy"]) els["dive-copy"].addEventListener("click", copyResult);
    if (els["dive-form"]) els["dive-form"].addEventListener("submit", submit);
    els["dive-next"].addEventListener("click", () => { if (state.phase === "between") nextRound(); });
    els["dive-pause"].addEventListener("click", togglePause);
    state.sectionEl = els["dive-start"].closest(".workspace-view");
    updatePause();
    document.addEventListener("visibilitychange", updatePause);
    window.addEventListener("hashchange", updatePause);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
  // Debugging + verification handle (exposes the pure matcher, not live answers).
  window.LokiDive = { state, normalize, fold, findAnswer, damerauDistance, tick: loop };
})();
