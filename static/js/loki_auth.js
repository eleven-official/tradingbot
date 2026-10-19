/* Personalized workspace: session check + nickname greeting. */
'use strict';
(() => {
  const init = async () => {
    let session = null;
    try {
      const res = await fetch('/api/auth/session', { cache: 'no-store' });
      if (res.status === 401) {
        window.location.href = '/login';
        return;
      }
      if (res.ok) {
        const data = await res.json();
        if (data && data.enabled === false) return; // accounts not configured: open guest experience
        session = data;
      } else {
        return; // server hiccup: keep the workspace usable
      }
    } catch {
      return;
    }
    if (!session) return;

    const pill = document.createElement('div');
    pill.className = 'loki-user-pill';
    pill.style.cssText =
      'position:fixed;left:18px;bottom:18px;z-index:70;display:flex;align-items:center;gap:10px;' +
      'padding:9px 14px;border-radius:999px;background:rgba(14,22,36,.92);color:#e7f0ff;border:1px solid rgba(139,218,212,.3);' +
      'box-shadow:0 10px 30px rgba(0,0,0,.4);font:600 13px Inter,system-ui,sans-serif;';
    const label = document.createElement('span');
    const nick = session.nickname || (session.email || '').split('@')[0];
    label.innerHTML = `<span style="color:#8bdad4" aria-hidden="true">◈</span> Hi, <strong style="color:#b8f0d8">${escapeHtml(nick)}</strong>`;
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Sign out';
    button.setAttribute('aria-label', 'Sign out');
    button.style.cssText =
      'border:0;background:transparent;color:#7f93a8;font:600 12px Inter,system-ui,sans-serif;cursor:pointer;padding:2px 4px;border-radius:6px;';
    button.addEventListener('mouseenter', () => { button.style.color = '#ff9d9d'; });
    button.addEventListener('mouseleave', () => { button.style.color = '#7f93a8'; });
    button.addEventListener('click', async () => {
      button.disabled = true;
      try { await fetch('/api/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
      window.location.href = '/login';
    });
    pill.append(label, button);
    document.body.appendChild(pill);
  };

  const escapeHtml = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
