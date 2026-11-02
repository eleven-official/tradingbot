/* The private room: passcode → chat with the memory-backed AI.
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
  const escapeHtml = (value) =>
    String(value ?? '').replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));

  let identity = { ok: false, name: '', admin: false };

  function showGate() {
    $('gate').hidden = false;
    $('room').hidden = true;
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
    refreshMemory();
  }

  function bubble(kind, text) {
    const div = document.createElement('div');
    if (kind === 'join') {
      div.className = 'join';
      div.textContent = text;
    } else {
      div.className = `bubble ${kind}`;
      if (kind === 'ai') {
        const who = document.createElement('b');
        who.className = 'who';
        who.textContent = 'LOKI';
        div.appendChild(who);
        div.appendChild(document.createTextNode(text));
      } else {
        div.textContent = text;
      }
    }
    $('stream').appendChild(div);
    $('stream').scrollTop = $('stream').scrollHeight;
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
        strong.style.color = fact.kind === 'admin' ? '#8bdad4' : '#c9b8ff';
        li.appendChild(strong);
        li.appendChild(document.createTextNode(` — ${fact.text}`));
        if (fact.source) {
          const small = document.createElement('small');
          small.append('source: ');
          const a = document.createElement('a');
          a.href = fact.source;
          a.rel = 'noreferrer noopener';
          a.target = '_blank';
          a.style.color = '#7f93a8';
          a.textContent = new URL(fact.source, 'https://example.invalid').hostname.slice(0, 40);
          small.appendChild(a);
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
        body: JSON.stringify({ name: $('gateName').value.trim(), code: $('gateCode').value })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        $('gateErr').textContent = String(data.detail || 'The door stays shut.').slice(0, 120);
        return;
      }
      identity = { ok: true, name: data.name, admin: !!data.admin };
      showRoom();
    } catch (error) {
      $('gateErr').textContent = 'Connection glitch — try again.';
    } finally {
      btn.disabled = false;
    }
  });

  $('msgForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = $('msgInput').value.trim();
    if (!text) return;
    const btn = $('sendBtn');
    btn.disabled = true;
    bubble('user', text);
    $('msgInput').value = '';
    try {
      const res = await fetch('/api/ai/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(25000),
        body: JSON.stringify({ text })
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        bubble('ai', String(data.detail || 'I glitched on that one — say it again?').slice(0, 200));
        return;
      }
      bubble('ai', String(data.text || ''));

      const learned = Array.isArray(data.learned) ? data.learned.filter((item) => item.fresh) : [];
      $('learnNote').textContent = learned.length
        ? `Learned ${learned.length} headline${learned.length === 1 ? '' : 's'} from the public internet just now.`
        : 'Internet sweeps refresh at most every 5 minutes — quiet until then.';
      if (learned.length) refreshMemory();
    } catch (error) {
      bubble('ai', 'The room went quiet on me — my internet or memory fetch stalled. Try once more.');
    } finally {
      btn.disabled = false;
    }
  });

  $('teachForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const fact = $('teachInput').value.trim();
    if (!fact) return;
    const res = await fetch('/api/ai/chat/teach', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(10000),
      body: JSON.stringify({ fact })
    });
    const data = await res.json().catch(() => ({}));
    $('adminNote').textContent = res.ok
      ? String(data.note || 'Fact stored.')
      : String(data.detail || 'Teach failed — admin only.');
    if (res.ok) {
      $('teachInput').value = '';
      refreshMemory();
    }
  });

  $('wipeBtn').addEventListener('click', async () => {
    if (!window.confirm('Wipe every fact and turn from Loki\'s memory? The wipe itself is journaled.')) return;
    const res = await fetch('/api/ai/chat/wipe', { method: 'POST', signal: AbortSignal.timeout(10000) });
    const data = await res.json().catch(() => ({}));
    $('adminNote').textContent = res.ok
      ? `Wiped ${data.wiped} rows.`
      : String(data.detail || 'Wipe failed — admin only.');
    if (res.ok) refreshMemory();
  });

  $('logoutBtn').addEventListener('click', async () => {
    await fetch('/api/ai/chat/logout', { method: 'POST', signal: AbortSignal.timeout(5000) }).catch(() => {});
    identity = { ok: false, name: '', admin: false };
    showGate();
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
