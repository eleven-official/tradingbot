'use strict';
(() => {
  const $ = id => document.getElementById(id);
  // Same allowlist as the server. Credentials and guest/login state are excluded.
  const keys = ['loki-fusion-paper-v1','loki_ai_paper_v1','loki.paper-journal.v1','loki.daily-risk-limit.v1','loki_dive_best','loki_dive_dives','loki_dive_challenge','loki_dive_recent','loki_dive_history','loki_currency','loki_visit_snapshot','loki_steps_data','loki_steps_run','loki_steps_council','loki_steps_journal','loki-synthetic-market-v1','loki_practice_stats_v1','loki_watchlist_v1','loki_pinned_report_v1','loki_council_history_v1','loki_news_seen_v1','loki_dive_badges','loki_dive_streak','loki_dive_challenge_wins'];
  const message = text => { $('account-message').textContent = text; };
  async function api(path, options = {}) {
    const response = await fetch(path, {cache:'no-store', ...options, headers:{'Content-Type':'application/json','X-Workspace-Owner':window.LokiStorageOwner, ...options.headers}});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The request was not accepted.');
    return data;
  }
  const busy = value => { $('cloud-save').disabled = value; $('cloud-load').disabled = value; };
  $('cloud-save').addEventListener('click', async () => {
    if (!confirm('Replace your cloud save with this account’s current browser workspace?')) return;
    busy(true);
    try {
      const items = {};
      for (const key of keys) { const value = localStorage.getItem(key); if (value !== null) items[key] = value; }
      if (!Object.keys(items).length) throw new Error('There is no workspace data in this account’s browser yet. Your cloud copy was not changed.');
      const result = await api('/api/account/workspace', {method:'PUT', body:JSON.stringify({items})});
      $('account-saved').textContent = 'Saved ' + new Date(result.updated_at).toLocaleString();
      message('Saved privately to your account.');
    } catch (error) { message(error.message); } finally { busy(false); }
  });
  $('cloud-load').addEventListener('click', async () => {
    busy(true);
    try {
      const data = await api('/api/account/workspace');
      if (!data.updated_at) throw new Error('You have no cloud save yet. Save a workspace first.');
      if (!confirm('Replace this account’s browser workspace with your cloud save?')) return;
      for (const key of keys) {
        if (typeof data.items[key] === 'string') localStorage.setItem(key, data.items[key]);
        else localStorage.removeItem(key);
      }
      message('Restored. Open the workspace to continue.');
    } catch (error) { message(error.message); } finally { busy(false); }
  });
  $('account-logout').addEventListener('click', async () => {
    try { await api('/api/auth/logout', {method:'POST'}); window.LokiAccountChanged?.(); location.href='/login'; }
    catch (error) { message(error.message); }
  });
  (async () => {
    try {
      const [member, workspace] = await Promise.all([api('/api/account/me'), api('/api/account/workspace')]);
      $('account-name').textContent = member.nickname + '’s space';
      $('account-email').textContent = member.email;
      $('account-best').textContent = member.dive ? member.dive.best_score.toLocaleString() + ' pts' : 'No score yet';
      $('account-dives').textContent = member.dive ? member.dive.dives + ' score publications · self-reported' : 'Finish a dive and publish to join the board.';
      $('account-saved').textContent = workspace.updated_at ? 'Saved ' + new Date(workspace.updated_at).toLocaleString() : 'No cloud save yet.';
      busy(false);
    } catch (error) { message(error.message); }
  })();
})();
