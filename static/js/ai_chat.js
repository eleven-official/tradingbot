/* The room: a name → chat with the memory-backed AI. No passcode by default;
 * operators can still gate it with LOKI_CHAT_CODE and the door re-locks.
 *
 * Server contract (loki/api/ai_chat.py):
 *   POST /api/ai/chat/access   {name, code} → signed cookie, admin claim by name
 *   GET  /api/ai/chat/whoami   → {ok, name, admin}
 *   POST /api/ai/chat/message  {text} → {text, learned, quote, facts_used, admin}
 *   GET  /api/ai/chat/memory   → {facts, turns, admin, name}
 *   POST /api/ai/chat/teach    {fact}   (admin only)
 *   POST /api/ai/chat/wipe     (admin only, journaled)
 * The browser renders only what the server learned and said — it never
 * invents replies, and nothing here places orders.
 */
'use strict';
(() => {
  const $ = (id) => document.getElementById(id);

  let identity = { ok: false, name: '', admin: false };

  const NAME_KEY = 'loki_chat_name';   // remembered on-device to skip gate friction — never a credential
  const DRAFT_KEY = 'loki_chat_draft'; // a half-typed message survives a reload
  const DRAFT_MAX = 500;

  function rememberedName() {
    try { return String(window.localStorage.getItem(NAME_KEY) || '').slice(0, 24); } catch { return ''; }
  }
  function rememberName(value) {
    try { if (value) window.localStorage.setItem(NAME_KEY, String(value).slice(0, 24)); } catch { /* private mode */ }
  }
  function saveDraft(value) {
    try { window.localStorage.setItem(DRAFT_KEY, String(value || '').slice(0, DRAFT_MAX)); } catch { /* private mode */ }
  }
  function restoreDraft() {
    try { return String(window.localStorage.getItem(DRAFT_KEY) || '').slice(0, DRAFT_MAX); } catch { return ''; }
  }
  function clearDraft() {
    try { window.localStorage.removeItem(DRAFT_KEY); } catch { /* private mode */ }
  }

  function showGate() {
    $('gate').hidden = false;
    $('room').hidden = true;
    const prior = rememberedName();
    if (prior && !$('gateName').value) {
      $('gateName').value = prior;
      $('gateHint').textContent = `Welcome back, ${prior} — name prefilled from this device.`;
      $('gateHint').hidden = false;
    }
  }

  function showRoom() {
    $('gate').hidden = true;
    $('room').hidden = false;
    $('whoName').textContent = identity.name ? `in as ${identity.name}` : '';
    const badge = $('whoBadge');
    if (identity.admin) {
      badge.textContent = 'ADMIN · JOSHUA';
      $('adminBox').style.display = 'block';
    } else {
      badge.textContent = 'MEMBER';
      $('adminBox').style.display = 'none';
    }
    bubble('join', identity.admin
      ? 'Loki: admin recognized — memory and teaching unlocked.'
      : 'Loki: unlocked. Ask me anything about the tape — I remember this room.');
    const draft = restoreDraft();
    if (draft) { $('msgInput').value = draft; }
    $('msgInput').focus();
    refreshMemory();
  }

  function bubble(kind, text, withCopy) {
    const div = document.createElement('div');
    if (kind === 'join') {
      div.className = 'join';
      div.textContent = text;
      $('stream').appendChild(div);
      $('stream').scrollTop = $('stream').scrollHeight;
      return div;
    }
    div.className = `bubble ${kind}`;
    if (kind === 'ai') {
      const who = document.createElement('b');
      who.className = 'who';
      who.textContent = 'LOKI';
      div.appendChild(who);
      div.appendChild(document.createTextNode(text));
      if (withCopy !== false) {
        const copy = document.createElement('button');
        copy.className = 'copy';
        copy.type = 'button';
        copy.textContent = 'copy';
        copy.addEventListener('click', async () => {
          try { await navigator.clipboard.writeText(text); copy.textContent = 'copied'; }
          catch (error) { copy.textContent = 'copy failed'; }
          setTimeout(() => { copy.textContent = 'copy'; }, 1400);
        });
        div.appendChild(copy);
      }
    } else {
      div.textContent = text;
    }
    $('stream').appendChild(div);
    $('stream').scrollTop = $('stream').scrollHeight;
    return div;
  }

  async function refreshMemory() {
    try {
      const res = await fetch('/api/ai/chat/memory', { signal: AbortSignal.timeout(10000) });
      if (!res.ok) return;
      const data = await res.json();
      const list = $('factList');
      list.innerHTML = '';
      const facts = Array.isArray(data.facts) ? data.facts : [];
      if (!facts.length) {
        const li = document.createElement('li');
        li.textContent = 'Memory is empty — sweep the internet by naming a ticker, or teach a fact.';
        list.appendChild(li);
      }
      for (const fact of facts.slice(0, 12)) {
        const li = document.createElement('li');
        const strong = document.createElement('b');
        strong.textContent = fact.kind === 'admin' ? 'taught' : 'internet';
        strong.style.color = 'var(--green)';
        li.appendChild(strong);
        li.appendChild(document.createTextNode(` — ${fact.text}`));
        if (fact.source) {
          const small = document.createElement('small');
          small.append('source: ');
          try {
            const url = new URL(fact.source);
            if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Unsupported source');
            const a = document.createElement('a');
            a.href = url.href;
            a.rel = 'noreferrer noopener';
            a.target = '_blank';
            a.style.color = 'var(--green)';
            a.textContent = url.hostname.slice(0, 40);
            small.appendChild(a);
          } catch {
            small.append(String(fact.source).slice(0, 300));
          }
          li.appendChild(small);
        }
        list.appendChild(li);
      }
      // Replay the room's last turns so history survives page reloads.
      const turns = Array.isArray(data.turns) ? data.turns : [];
      $('stream').innerHTML = '';
      for (const turn of turns) {
        if (String(turn.text || '').startsWith('[joined')) {
          bubble('join', turn.text);
        } else if (turn.role === 'ai') {
          bubble('ai', turn.text);
        } else {
          bubble('user', turn.text);
        }
      }
    } catch (error) {
      /* memory panel is best-effort; chat still works */
    }
  }

  $('gateForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const btn = $('gateBtn');
    btn.disabled = true;
    $('gateErr').textContent = '';
    try {
      const res = await fetch('/api/ai/chat/access', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(10000),
        body: JSON.stringify({ name: $('gateName').value.trim(), code: $('operatorCode').value || $('gateCode').value })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        $('gateErr').textContent = String(data.detail || 'The door stays shut.').slice(0, 120);
        return;
      }
      identity = { ok: true, name: data.name, admin: !!data.admin };
      rememberName($('gateName').value.trim());
      showRoom();
    } catch (error) {
      $('gateErr').textContent = 'Connection glitch — try again.';
    } finally {
      btn.disabled = false;
    }
  });

  $('msgInput').addEventListener('input', () => saveDraft($('msgInput').value));

  const composerSubmit = async (rawText) => {
    const text = String(rawText == null ? $('msgInput').value : rawText).trim();
    if (!text) return;
    const btn = $('sendBtn');
    if (btn.disabled) return;
    btn.disabled = true;
    bubble('user', text);
    $('msgInput').value = '';
    saveDraft(text);
    const restoreFailedMessage = () => {
      if (!$('msgInput').value) { $('msgInput').value = text; saveDraft(text); }
    };
    try {
      const res = await fetch('/api/ai/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(25000),
        body: JSON.stringify({ text })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        restoreFailedMessage();
        bubble('ai', String(data.detail || 'I glitched on that one — say it again?').slice(0, 200));
        return;
      }
      bubble('ai', String(data.text || ''));
      if (!$('msgInput').value) clearDraft();

      const learned = Array.isArray(data.learned) ? data.learned.filter((item) => item.fresh) : [];
      $('learnNote').textContent = learned.length
        ? `Learned ${learned.length} headline${learned.length === 1 ? '' : 's'} from the public internet just now.`
        : 'Internet sweeps refresh at most every 5 minutes — quiet until then.';
      if (learned.length) refreshMemory();
    } catch (error) {
      restoreFailedMessage();
      bubble('ai', 'The room went quiet on me — my internet or memory fetch stalled. Try once more.');
    } finally {
      btn.disabled = false;
    }
  };
  $('msgForm').addEventListener('submit', (event) => { event.preventDefault(); composerSubmit($('msgInput').value); });
  document.querySelectorAll('#chips [data-ask]').forEach((chip) => {
    chip.addEventListener('click', () => composerSubmit(chip.dataset.ask));
  });

  let adminPending = false;
  async function adminAction(path, body) {
    if (adminPending) return null;
    adminPending = true;
    const buttons = [...$('adminBox').querySelectorAll('button')];
    buttons.forEach((button) => { button.disabled = true; });
    try {
      const res = await fetch(`/api/ai/chat/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(10000),
        body: body ? JSON.stringify(body) : undefined
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(String(data.detail || 'Action failed.'));
      $('adminNote').textContent = String(data.note || 'Saved.');
      await refreshMemory();
      return data;
    } catch (error) {
      $('adminNote').textContent = error.name === 'TypeError' || error.name === 'TimeoutError'
        ? 'Connection interrupted. Refresh memory before retrying; the action may have completed.'
        : String(error.message || 'Action failed.').slice(0, 200);
      return null;
    } finally {
      adminPending = false;
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  $('teachForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const fact = $('teachInput').value.trim();
    if (!fact) return;
    if (await adminAction('teach', { fact })) {
      $('teachInput').value = '';
    }
  });

  $('wipeBtn').addEventListener('click', async () => {
    if (!window.confirm('Wipe every fact and turn from Loki\'s memory? The wipe itself is journaled.')) return;
    await adminAction('wipe');
  });

  $('logoutBtn').addEventListener('click', async () => {
    const button = $('logoutBtn');
    if (button.disabled) return;
    button.disabled = true;
    try {
      const res = await fetch('/api/ai/chat/logout', { method: 'POST', signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error('Logout failed');
      identity = { ok: false, name: '', admin: false };
      $('stream').replaceChildren();
      $('msgInput').value = '';
      $('operatorCode').value = '';
      clearDraft();
      showGate();
    } catch {
      bubble('ai', 'Sign-out was not confirmed. Check your connection and try leaving again.', false);
    } finally {
      button.disabled = false;
    }
  });

  (async function init() {
    try {
      const res = await fetch('/api/ai/chat/whoami', { signal: AbortSignal.timeout(8000) });
      const data = await res.json().catch(() => ({}));
      if (data && data.ok) {
        identity = { ok: true, name: data.name, admin: !!data.admin };
        showRoom();
      } else {
        showGate();
      }
    } catch (error) {
      showGate();
    }
  })();
})();
