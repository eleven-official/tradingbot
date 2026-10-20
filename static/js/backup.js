/* Backup & restore of everything Loki keeps in this browser (localStorage).
   Writes a single JSON file the user stores wherever they like; import
   overwrites the same keys after an explicit confirm. Nothing is uploaded. */
'use strict';
(() => {
  const KEYS = [
    "loki-fusion-paper-v1",   // paper portfolio journal (workspace)
    "loki_ai_paper_v1",       // AI paper-trading journal
    "loki.paper-journal.v1",  // planner decision journal
    "loki.daily-risk-limit.v1",
    "loki_dive_best", "loki_dive_dives", "loki_dive_challenge",
    "loki_currency", "loki_visit_snapshot",
    "loki_steps_data", "loki_steps_run", "loki_steps_council", "loki_steps_journal",
    "loki-synthetic-market-v1",   // saved simulated-market practice session
    "loki_pinned_report_v1",  // pinned research run for compare
    "loki_guest"
  ];
  const $ = (id) => document.getElementById(id);

  const stamp = () => new Date().toISOString().slice(0, 10);

  const exportBackup = () => {
    const items = {};
    for (const key of KEYS) {
      const value = localStorage.getItem(key);
      if (value !== null) items[key] = value;
    }
    if (!Object.keys(items).length) {
      const msg = $("backup-message");
      if (msg) msg.textContent = "Nothing to back up yet — this browser has no saved journals.";
      return;
    }
    const payload = { app: "loki", kind: "browser-backup", version: 1, created: new Date().toISOString(), items };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `loki-browser-backup-${stamp()}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    const msg = $("backup-message");
    if (msg) msg.textContent = `Backup saved: ${Object.keys(items).length} journals written to the downloaded file.`;
  };

  const importBackup = async (file) => {
    const msg = $("backup-message");
    if (!msg) return;
    try {
      const parsed = JSON.parse(await file.text() || "null");
      if (!parsed || parsed.kind !== "browser-backup" || parsed.app !== "loki" || typeof parsed.items !== "object") {
        throw new Error("This file is not a Loki browser backup.");
      }
      const keys = Object.keys(parsed.items);
      if (!keys.length) throw new Error("The backup holds no journals.");
      if (!window.confirm(`Restore ${keys.length} journals from ${parsed.created ? parsed.created.slice(0, 10) : "the backup"}? This overwrites the current local journals: ${keys.join(", ")}.`)) {
        msg.textContent = "Restore cancelled — nothing was overwritten.";
        return;
      }
      let restored = 0;
      const failures = [];
      for (const key of keys) {
        if (!KEYS.includes(key)) { failures.push(`${key} (unknown)`); continue; }
        try {
          localStorage.setItem(key, String(parsed.items[key]));
          restored += 1;
        } catch { failures.push(key); }
      }
      msg.textContent = `Restored ${restored} journals. Reload completes the swap.` + (failures.length ? ` Skipped: ${failures.join(", ")}.` : "");
      setTimeout(() => window.location.reload(), 900);
    } catch (error) {
      msg.textContent = `Import failed: ${error.message}`;
    }
  };

  const bind = () => {
    if (!$("backup-export")) return;
    $("backup-export").addEventListener("click", exportBackup);
    const input = $("backup-file");
    if (input) {
      input.addEventListener("change", (event) => {
        const file = event.target.files?.[0];
        if (file) importBackup(file);
        event.target.value = "";
      });
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind, { once: true });
  } else {
    bind();
  }
})();
