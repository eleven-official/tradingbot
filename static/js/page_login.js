/* Extracted from templates/login.html so the Content-Security-Policy can forbid inline scripts. */
'use strict';
document.getElementById('guest-link').addEventListener('click', (event) => {
  event.preventDefault();
  try { localStorage.setItem('loki_guest', '1'); } catch { /* ignore */ }
  window.location.href = '/#overview';
});
let mode = 'login';
const $ = (id) => document.getElementById(id);
const msg = $('msg');
const toggle = $('toggle');
toggle.addEventListener('click', () => {
  mode = mode === 'login' ? 'signup' : 'login';
  $('nick-field').hidden = mode !== 'signup';
  $('nick-callout').hidden = mode !== 'signup';
  $('age-field').hidden = mode !== 'signup';
  $('primary').textContent = mode === 'login' ? 'Sign in ↗' : 'Create my account ↗';
  toggle.textContent = mode === 'login' ? 'New here? Create an account →' : '← I already have an account';
  msg.textContent = '';
});
$('auth-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const btn = $('primary');
  if (mode === 'signup' && !$('age-ok').checked) {
    msg.className = ''; msg.textContent = 'Accounts are for adults: tick the box to confirm you are 18 or older.';
    return;
  }
  btn.disabled = true;
  msg.className = ''; msg.textContent = mode === 'login' ? 'Signing in…' : 'Creating your account…';
  try {
    const res = await fetch(mode === 'login' ? '/api/auth/login' : '/api/auth/sign-up', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: $('email').value.trim(),
        password: $('password').value,
        nickname: $('nickname').value.trim() || null,
        ...(mode === 'signup' ? { age_confirmed: $('age-ok').checked } : {})
      })
    });
    if (!res.ok) {
      const raw = await res.text().catch(() => "");
      let data = null;
      try { data = JSON.parse(raw) || null; } catch { data = null; }
      const detail = (data && data.detail) || null;
      const looksLikeVercelWall = !detail && (/^(<!|<)/.test(raw.trim()) || /vercel/i.test(raw.slice(0, 400)));
      if (detail) {
        msg.textContent = detail;
      } else if (res.status === 401 || res.status === 403 || looksLikeVercelWall) {
        msg.textContent = "Vercel's visitor wall answered instead of Loki — open the site again and log in to Vercel once (or use your shareable link), then sign in here.";
      } else if (res.status === 503 || res.status === 404 || res.status >= 500) {
        msg.textContent = "The account service is waking up — give it a minute and try again.";
      } else {
        msg.textContent = "Something went wrong. Try again.";
      }
      btn.disabled = false;
      return;
    }
    const rawOk = await res.text().catch(() => "");
    let okData = null;
    try { okData = JSON.parse(rawOk) || null; } catch { okData = null; }
    if (!okData || !okData.email) {
      msg.textContent = "That reply wasn't Loki — Vercel's visitor wall probably stepped in. Open the site again, log in to Vercel once, then sign in here.";
      btn.disabled = false;
      return;
    }
    try { localStorage.removeItem('loki_guest'); } catch { /* ignore */ }
    msg.className = 'ok'; msg.textContent = 'Welcome in…';
    window.LokiAccountChanged?.();
    window.location.href = '/#overview';
  } catch (err) {
    msg.textContent = 'Connection hiccup — check the internet and try again.';
    btn.disabled = false;
  }
});
(async () => {
  try {
    const res = await fetch('/api/auth/session', { cache: 'no-store' });
    if (res.ok) {
      const me = await res.json();
      if (me.enabled && (me.email || me.nickname)) {
        msg.className = 'ok';
        msg.textContent = `Already signed in as ${me.nickname || me.email} — opening the workspace…`;
        setTimeout(() => { window.location.href = '/#overview'; }, 900);
      } else if (me.enabled === false) {
        // Guest-mode deployment (no Supabase credentials): say so up front
        // instead of letting the first sign-in attempt read as "broken".
        msg.className = 'ok';
        msg.textContent = 'Accounts are not configured on this deployment — the workspace works as a guest meanwhile, and the guest button below still opens everything.';
      }
    }
  } catch { /* not signed in; show the form */ }
})();
