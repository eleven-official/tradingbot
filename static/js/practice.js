/* Guided practice drills over the synthetic market.
 *
 * Each exercise resets the practice market with a fixed seed (reproducible),
 * explains what the scenario demonstrates, then counts candles to a recap of
 * what the user actually did. Recaps are computed from the live practice
 * account snapshot — nothing is invented, and nothing counts as real profit.
 *
 * Depends on the shared helpers ($, element, inlineMetrics, bulletList) that
 * workspace.js defines at top level, and on simulated_market.js being loaded
 * first for window.lokiSimulatedMarket.
 */
'use strict';
(() => {
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  const EXERCISES = {
    "ride-trend": {
      title: "Ride a trend",
      scenario: "uptrend",
      seed: 1731,
      target: 40,
      brief: "An uptrend is steady repeated demand with shallow pullbacks. The lesson: enter early, sit tight while the trend does the work, and let your exit rule — not your nerves — decide when to leave.",
      checklist: [
        "Buy near the start of the drill — a small quantity is enough.",
        "Hold through the pullbacks instead of selling every dip.",
        "Close the position when the trend structure breaks, not on the first wobble."
      ],
      recapNote: "For reference: doing nothing leaves you flat in cash while the trend pays the patient. A trader only beats cold cash when their entry and exit beat holding on and doing nothing at all."
    },
    "range-trap": {
      title: "Range trap",
      scenario: "range",
      seed: 2345,
      target: 45,
      brief: "A range chops between two edges and punishes both chasing breakouts and fading them too early. The discipline being trained: doing nothing is a position — and the cheapest one.",
      checklist: [
        "Watch each fake breakout and ask what happens before you tap buy.",
        "Try to trade as little as possible across the candles.",
        "Count every fee you paid — fewer fills is better range patience."
      ],
      recapNote: "For reference: an idle cash account keeps everything it starts with in a range, while every unnecessary round trip pays fees for nothing. Sometimes the professional move is watching."
    },
    "crash-drill": {
      title: "Crash drill",
      scenario: "crash",
      seed: 5137,
      target: 45,
      brief: "A flash crash followed by a recovery. Stops are circuit breakers, not insurance — a stop can fill well below its level when price gaps. The drill: size so a bad fill hurts less than it could.",
      checklist: [
        "Get in small before the crash window.",
        "Set a protective stop that caps a full-position loss to a modest paper amount.",
        "Watch how the stop actually filled — the gap is the lesson."
      ],
      recapNote: "For reference: an unprotected long would have ridden the whole crash down. Stops turn an uncapped bleed into a fast, capped loss — slippage and the gap included in the bill."
    }
  };

  let active = null; // {id, title, scenario, target, startStep}
  let pollTimer = null;

  const fmt = (value, digits = 2) =>
    new Intl.NumberFormat(undefined, { minimumFractionDigits: 0, maximumFractionDigits: digits }).format(Number(value) || 0);

  // Drill streak ledger: drills completed per local day, shown on the Bored?
  // page as a habit strip. It counts habits — it never measures skill.
  const STATS_KEY = "loki_practice_stats_v1";
  const localDay = (date) => {
    const value = new Date(date);
    value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
    return value.toISOString().slice(0, 10);
  };
  const readStats = () => {
    try {
      const parsed = JSON.parse(localStorage.getItem(STATS_KEY) || "{}");
      return parsed && typeof parsed === "object" && parsed.days ? parsed : { days: {} };
    } catch { return { days: {} }; }
  };
  const bumpDrill = () => {
    const stats = readStats();
    const day = localDay(new Date());
    stats.days[day] = (Number(stats.days[day]) || 0) + 1;
    try { localStorage.setItem(STATS_KEY, JSON.stringify(stats)); } catch { /* storage blocked: today's count lives in the recap only */ }
  };
  const streakInfo = () => {
    const stats = readStats();
    let streak = 0;
    const cursor = new Date();
    if (!(Number(stats.days[localDay(cursor)]) > 0)) cursor.setDate(cursor.getDate() - 1);
    while (Number(stats.days[localDay(cursor)]) > 0) { streak += 1; cursor.setDate(cursor.getDate() - 1); }
    const today = Number(stats.days[localDay(new Date())]) || 0;
    const total = Object.values(stats.days).reduce((sum, count) => sum + (Number(count) || 0), 0);
    return { today, streak, total };
  };
  const renderStreak = () => {
    const host = document.getElementById("practice-streak");
    if (!host) return;
    const { today, streak, total } = streakInfo();
    host.hidden = false;
    if (!total) {
      host.textContent = "No practice drills logged yet — when one finishes, this strip counts drills today and your day streak. Drills train habits, not performance.";
      return;
    }
    host.textContent = `Practice: ${today} drill${today === 1 ? "" : "s"} today · ${streak > 1 ? `${streak}-day streak` : "streak starts or continues today"} · ${total} logged in total. Habits compound; this strip counts them, it never grades skill.`;
  };
  window.addEventListener("hashchange", () => { if (location.hash === "#game") renderStreak(); });

  const snap = () => {
    const shot = window.lokiSimulatedMarket?.snapshot();
    return shot ? { state: shot.state, metrics: shot.metrics } : null;
  };

  const start = (key) => {
    const exercise = EXERCISES[key];
    if (!exercise) return;
    const reset = document.getElementById("sim-reset-form");
    if (!reset) return;
    reset.querySelector("[name=scenario]").value = exercise.scenario;
    reset.querySelector("[name=seed]").value = exercise.seed;
    reset.querySelector("[name=initial_capital]").value = 10000;
    active = { id: key, title: exercise.title, scenario: exercise.scenario, target: exercise.target, startStep: null };
    const recap = document.getElementById("practice-recap");
    if (recap) recap.hidden = true;
    renderBrief(exercise);
    // Route the reset through the practice market's own form so its engine,
    // saved state and rendering stay in sync.
    if (typeof reset.requestSubmit === "function") reset.requestSubmit();
    else reset.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    renderProgress(`Resetting the practice market for “${exercise.title}”…`);
    clearInterval(pollTimer);
    pollTimer = setInterval(stepCheck, 1500);
  };

  const renderBrief = (exercise) => {
    const host = document.getElementById("practice-brief");
    if (!host) return;
    host.hidden = false;
    host.replaceChildren();
    host.append(
      element("h3", `${exercise.title} — what this scenario demonstrates`),
      element("p", exercise.brief),
      element("p", "Your checklist:", "eyebrow"),
      bulletList(exercise.checklist)
    );
  };

  const renderProgress = (text) => {
    const host = document.getElementById("practice-progress");
    if (host) host.textContent = text;
  };

  const stepCheck = () => {
    if (!active) return;
    const shot = snap();
    if (!shot) return;
    const state = shot.state;
    if (state.scenario !== active.scenario) {
      clearInterval(pollTimer);
      pollTimer = null;
      active = null;
      renderProgress("Exercise stopped — the practice market was reset outside the drill.");
      return;
    }
    const step = Number(state.step) || 0;
    if (active.startStep === null) {
      // Fresh reset: the drill counts from the new session's first candle.
      active.startStep = step <= active.target ? 0 : step - active.target;
      renderProgress(`${active.title} — step 0 / ${active.target}. Press Play, or use +10 candles.`);
      return;
    }
    const done = Math.max(0, step - active.startStep);
    if (done < active.target) {
      renderProgress(`${active.title} — step ${done} / ${active.target}.`);
      return;
    }
    window.lokiSimulatedMarket?.pause?.();
    finish(shot, active);
  };

  const finish = (shot, exerciseRun) => {
    clearInterval(pollTimer);
    pollTimer = null;
    const exercise = EXERCISES[exerciseRun.id];
    const state = shot.state, metrics = shot.metrics;
    const trades = state.account?.trades || [];
    const fills = trades.length;
    const buys = trades.filter((trade) => trade.side === "BUY").length;
    const sells = fills - buys;
    const feesPaid = trades.reduce((sum, trade) => sum + (Number(trade.fees) || 0), 0);
    const realized = trades.reduce((sum, trade) => sum + (trade.pnl == null ? 0 : Number(trade.pnl)), 0);
    const openPositions = Object.keys(state.account?.positions || {}).length;
    const recap = document.getElementById("practice-recap");
    if (!recap) { active = null; return; }

    recap.hidden = false;
    recap.replaceChildren();
    if (typeof inlineMetrics === "function") {
      recap.append(inlineMetrics([
        ["Practice equity", `${fmt(metrics.equity)} USD`],
        ["Net practice P&L", `${fmt(metrics.total_pnl)} USD`],
        ["Closed positions", fmt(metrics.closed_trades, 0)],
        ["Fees paid", `${fmt(feesPaid)} USD`]
      ]));
    }
    recap.append(
      element("p", `Recap: ${fills} fill${fills === 1 ? "" : "s"} (${buys} buys, ${sells} sells), ${fmt(realized)} USD realized P&L.${openPositions ? ` ${openPositions} position${openPositions === 1 ? "" : "s"} still open on generated marks.` : " You finished flat."} This sample is far too small to judge skill — the drill trains habits, not performance.`, "muted"),
      element("p", `What you practiced: ${exercise.checklist[0]} ${exercise.checklist[1]}`),
      element("p", exercise.recapNote, "muted"),
      element("p", "Run the same drill with a different seed to see how results vary, and export the session before resetting if you want to keep it.", "caption")
    );
    bumpDrill();
    renderStreak();
    renderProgress(`${exercise.title} complete — recap above.`);
    active = null;
  };

  const bind = () => {
    if (!document.getElementById("practice-progress")) return;
    for (const button of $$(".practice-start")) {
      button.addEventListener("click", () => start(button.dataset.practice));
    }
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind, { once: true });
  else bind();
  if (location.hash === "#game") renderStreak();

  window.lokiPractice = { start, active: () => (active ? { ...active } : null), streak: streakInfo, renderStreak };
})();
