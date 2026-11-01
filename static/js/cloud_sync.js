/* Partial, owner-checked saves. Never upload credentials or a whole stale tab. */
'use strict';
(() => {
  const owner = window.LokiStorageOwner;
  if (!owner || owner === 'guest') return;
  const allowed = new Set(['loki-fusion-paper-v1','loki_ai_paper_v1','loki.paper-journal.v1','loki.daily-risk-limit.v1','loki_dive_best','loki_dive_dives','loki_dive_challenge','loki_dive_recent','loki_dive_history','loki_currency','loki_visit_snapshot','loki_steps_data','loki_steps_run','loki_steps_council','loki_steps_journal','loki-synthetic-market-v1','loki_practice_stats_v1','loki_watchlist_v1','loki_pinned_report_v1','loki_council_history_v1','loki_news_seen_v1','loki_dive_badges','loki_dive_streak','loki_dive_challenge_wins']);
  const dirty = new Set();
  let timer, saving = false, stopped = false, failures = 0;
  let state = {status:'idle', pending:0};
  const report = (status, detail='') => {
    state = {status, detail, pending:dirty.size};
    window.dispatchEvent(new CustomEvent('loki-cloud-sync', {detail:state}));
  };
  const schedule = (delay=2000) => {clearTimeout(timer);if(!stopped)timer=setTimeout(flush,delay);};
  async function flush() {
    if (saving || stopped || !dirty.size) return;
    saving = true;
    const batch = Array.from(dirty), items = {}, removed = [];
    try {
      for (const key of batch) {
        const value = localStorage.getItem(key);
        if (value === null) removed.push(key); else items[key] = value;
      }
      const body = JSON.stringify({items, removed});
      if (new TextEncoder().encode(body).length > 500000) {
        stopped = true;report('error','Cloud update too large. Local data is retained; export a backup.');return;
      }
      batch.forEach(key=>dirty.delete(key));
      report('saving');
      const response = await fetch('/api/account/workspace', {method:'PATCH', cache:'no-store',
        headers:{'Content-Type':'application/json','X-Workspace-Owner':owner}, body});
      if (!response.ok) {
        batch.forEach(key=>dirty.add(key));
        if ([401,409,400,413].includes(response.status)) stopped = true;
        throw new Error(response.status===401?'Sign in again to resume cloud saves.':response.status===409?'Account changed. Reload before saving.':'Cloud save unavailable; local data is retained.');
      }
      failures = 0;report(dirty.size?'pending':'saved');
    } catch (error) {
      batch.forEach(key=>dirty.add(key));
      failures++;report('error',error.message || 'Cloud save unavailable; local data is retained.');
    } finally {
      saving = false;
      if (dirty.size && !stopped) schedule(Math.min(60000,2000*Math.pow(2,Math.min(failures,5))));
    }
  }
  window.addEventListener('loki-storage-change', event=>{
    if (!allowed.has(event.detail?.key)) return;
    dirty.add(event.detail.key);report('pending');schedule();
  });
  window.addEventListener('online',()=>{if(!stopped)schedule(0);});
  window.addEventListener('beforeunload', event=>{
    if (dirty.size || saving) {event.preventDefault();event.returnValue='';}
  });
  window.LokiCloudSync = {flush, status:()=>({...state})};
})();
