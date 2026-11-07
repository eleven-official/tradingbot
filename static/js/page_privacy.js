/* Privacy page data controls: export, delete account, clear this browser. */
'use strict';
(() => {
  const msg = document.getElementById('controls-msg');
  const say = (text) => { msg.textContent = text; };
  const owner = () => window.LokiStorageOwner && window.LokiStorageOwner !== 'guest' ? window.LokiStorageOwner : null;

  document.getElementById('export-data').addEventListener('click', async () => {
    if (!owner()) { say('Sign in first — without an account, Loki keeps nothing about you on the server.'); return; }
    say('Preparing your data…');
    try {
      const res = await fetch('/api/account/export', { cache: 'no-store' });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Export failed');
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement('a');
      a.href = url; a.download = 'loki-my-data.json'; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      say('Downloaded loki-my-data.json.');
    } catch (error) { say(error.message); }
  });

  document.getElementById('delete-account').addEventListener('click', async () => {
    const uid = owner();
    if (!uid) { say('Sign in to the account you want to delete first.'); return; }
    const typed = window.prompt('This permanently deletes your Loki account, saved workspace and published score. Type DELETE to confirm.');
    if (typed !== 'DELETE') { say('Nothing was deleted.'); return; }
    say('Deleting…');
    try {
      const res = await fetch('/api/account/delete', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Workspace-Owner': uid },
        body: JSON.stringify({ confirm: 'DELETE' })
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Deletion failed');
      say('Your account and its server data are deleted. Data in this browser remains until you clear it below.');
    } catch (error) { say(error.message); }
  });

  document.getElementById('clear-browser').addEventListener('click', async () => {
    if (!window.confirm('Remove all Loki data stored in this browser (paper journals, watchlists, chat history, saved broker keys, settings)? This cannot be undone.')) return;
    try { localStorage.clear(); } catch { /* storage blocked */ }
    try { sessionStorage.clear(); } catch { /* storage blocked */ }
    try { await fetch('/api/ai/chat/logout', { method: 'POST' }); } catch { /* offline */ }
    say('This browser no longer holds any Loki data. Your access to the site and any account stay as they are.');
  });
})();
