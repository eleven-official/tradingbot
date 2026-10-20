/* "Next steps" guide on Overview — tracks the four-step research path with
   markers written by the other modules at the moment each action succeeds. */
'use strict';
(() => {
  const MARKS = [
    ["data", "Imported your own history"],
    ["run", "Walk-forward replay complete"],
    ["council", "Council review complete"],
    ["journal", "Paper decision recorded"]
  ];

  const read = (key) => {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return Number.isFinite(parsed?.at) ? parsed : null;
    } catch { return null; }
  };

  const stamp = (ms) => new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
  }).format(new Date(ms));

  function render() {
    const panel = document.getElementById("next-steps-panel");
    if (!panel || panel.offsetParent === null) return; // not on Overview right now
    let done = 0;
    for (const [key, label] of MARKS) {
      const mark = read(`loki_steps_${key}`);
      const host = panel.querySelector(`[data-step-mark="${key}"]`);
      const item = panel.querySelector(`li[data-step="${key}"]`);
      if (!host || !item) continue;
      if (mark) {
        done += 1;
        host.textContent = ` · done ${stamp(mark.at)}`;
        host.title = label;
        item.classList.add("done");
        const check = item.querySelector(".step-check");
        if (check) check.textContent = "✓";
      } else {
        host.textContent = "";
        item.classList.remove("done");
        const check = item.querySelector(".step-check");
        if (check) check.textContent = "○";
      }
    }
    const score = document.getElementById("next-steps-score");
    if (score) score.textContent = `${done} of 4 done`;
    const time = document.getElementById("data-context-time");
    if (time) {
      const last = read("loki_steps_run") ? stamp(read("loki_steps_run").at)
        : markReadAny();
      time.textContent = last || "—";
    }
  }

  function markReadAny() {
    const data = read("loki_steps_data");
    return data ? stamp(data.at) : null;
  }

  const start = () => {
    render();
    window.addEventListener("hashchange", render);
    window.addEventListener("storage", render);
    setInterval(render, 5000);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
