/* Shared dive leaderboard (workspace view: #game).
 *
 * The board lists the best finished dive per board name, as people chose to
 * publish it from the game's end screen. Publishing is a click, never
 * automatic, and every score is self-reported: three storage modes exist and
 * the banner always names the one in use — a shared database when the
 * deployment has one, a file on this server when Loki runs as a personal
 * server, or nothing at all (ephemeral hosting) with the honest reason.
 */
'use strict';
(() => {
  const NAME_KEY = 'loki_dive_board_name'; // the name this browser publishes under
  const state = { loaded: false, busy: false, mode: '', entries: [], sessionNickname: '' };

  const $ = (id) => document.getElementById(id);
  const viewActive = () => location.hash === '#game';
  const esc = (text) => String(text ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  const localBest = () => Math.max(0, parseInt(localStorage.getItem('loki_dive_best') || '0', 10) || 0);

  function ago(iso) {
    const then = Date.parse(iso || '');
    if (!Number.isFinite(then)) return 'unknown time';
    const mins = Math.round((Date.now() - then) / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.round(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.round(hours / 24)}d ago`;
  }

  function boardName() {
    try { return (localStorage.getItem(NAME_KEY) || '').slice(0, 24); } catch { return ''; }
  }

  function saveBoardName(value) {
    try {
      const clean = String(value || '').trim().slice(0, 24);
      if (clean) localStorage.setItem(NAME_KEY, clean);
    } catch { /* storage refused: the name simply is not remembered */ }
  }

  /* Prefill once with the nickname of the signed-in account, if any — a
   * person who signs in should not have to retype their own name. */
  async function prefill() {
    const input = $('dive-board-name');
    if (!input) return;
    if (boardName()) { input.value = boardName(); return; }
    if (state.sessionNickname) input.value = state.sessionNickname;
  }

  function render() {
    const kind = $('dive-board-kind');
    const note = $('dive-board-note');
    const list = $('dive-board-list');
    const pub = $('dive-publish-form');
    if (!list) return;

    if (kind) {
      kind.textContent = state.mode === 'shared' ? 'Shared board · project database · the same rows for everyone'
        : state.mode === 'server-local' ? 'Server board · kept on this Loki server · shared by every browser using it'
          : 'No shared board on this deployment · your best dive stays in this browser';
    }

    if (note) {
      if (state.mode === 'unavailable') note.textContent = state.note || 'Nothing can be published here.';
      else note.textContent = '';
    }

    list.replaceChildren();
    if (state.entries.length) {
      const mine = boardName().trim().toLowerCase();
      state.entries.forEach((entry, index) => {
        const row = document.createElement('li');
        row.className = 'dive-board-row' + (mine && entry.nickname.toLowerCase() === mine ? ' dive-board-mine' : '');
        const rank = `<span class="dive-board-rank">${index + 1}</span>`;
        const name = `<span class="dive-board-name">${esc(entry.nickname)}</span>`;
        const best = `<span class="dive-board-best">${Math.round(entry.best)} pts</span>`;
        const dives = `<span class="dive-board-dives">${entry.dives} dive${entry.dives === 1 ? '' : 's'}</span>`;
        const when = `<span class="dive-board-when">${ago(entry.updated_at)}</span>`;
        row.innerHTML = rank + name + best + dives + when;
        list.append(row);
      });
    } else {
      const empty = document.createElement('li');
      empty.className = 'dive-board-empty muted';
      empty.textContent = state.mode === 'shared' && /not set up/i.test(state.note || '')
        ? state.note
        : 'No names on the board yet. Finish a dive, then publish your best from below.';
      list.append(empty);
    }

    if (pub) {
      const best = localBest();
      const showForm = state.mode === 'shared' || state.mode === 'server-local';
      pub.hidden = !(showForm && best > 0 && !/not set up/i.test(state.note || ''));
      const hint = $('dive-publish-note');
      if (hint && showForm) {
        hint.textContent = `Publishing is a click — the game never posts scores by itself. Your best finished dive here is ${best} points. The board trusts the name, not the person: two divers sharing a name share its row. Self-reported scores`;
      }
      prefill();
    }
  }

  async function refresh() {
    if (state.busy) return;
    state.busy = true;
    render();
    try {
      const response = await fetch('/api/dive/leaderboard', { cache: 'no-store' });
      const payload = await response.json();
      // a refusal (503: shared store not set up) arrives as {detail} — that
      // reason is the honest answer and must reach the reader, not vanish
      state.mode = payload.mode || (response.ok ? (state.mode || 'unavailable') : 'unavailable');
      state.note = payload.note || payload.detail || '';
      state.entries = Array.isArray(payload.entries) ? payload.entries : [];
      state.loaded = true;
    } catch (error) {
      state.mode = state.mode || 'unavailable';
      state.note = `The board could not be reached (${error.message || 'network'}).`;
      state.entries = [];
    } finally {
      state.busy = false;
      render();
    }
  }

  async function publish(event) {
    event.preventDefault();
    const message = $('dive-board-note');
    const input = $('dive-board-name');
    const button = $('dive-publish-form')?.querySelector('button[type=submit]');
    const name = (input?.value || '').trim();
    const best = localBest();
    if (!name || name.length < 2) { if (message) { message.textContent = 'Pick a board name first — 2 to 24 letters, numbers, spaces or dashes.'; } return; }
    if (best <= 0) { if (message) { message.textContent = 'Finish a dive before publishing — the board lists finished dives only.'; } return; }
    if (button) button.disabled = true;
    let verdict = '';
    try {
      const response = await fetch('/api/dive/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: name, best })
      });
      const payload = await response.json();
      if (response.ok) {
        state.mode = payload.mode;
        state.note = payload.note || '';
        // the name is remembered only once the board accepted the publish,
        // and only in the form the server actually cleaned
        saveBoardName(payload.nickname || name);
        verdict = `${payload.best ?? best} points stand under "${payload.nickname || name}" now (${payload.dives ?? '?'} dives on the board).`;
      } else {
        verdict = typeof payload.detail === 'string' ? payload.detail : 'The board refused the publish — nothing was recorded.';
      }
    } catch (error) {
      verdict = `Publishing failed (${error.message || 'network'}) — nothing was recorded.`;
    } finally {
      if (button) button.disabled = false;
      await refresh();
      // the final word lands after the refresh, so the board re-render can't clobber it
      if (message) message.textContent = verdict;
    }
  }

  function whenDiveEnds(points) {
    // Called by the game after every completed dive: refresh so a just-published
    // row moves, and keep the publish strip's best figure current.
    if (state.loaded) refresh(); else if (viewActive()) refresh();
    if (typeof points === 'number' && points > 0) {
      const strip = $('dive-board-just-finished');
      if (strip) strip.textContent = `Your dive just finished at ${points} points. Give it a name below to put it on the board.`;
    }
  }

  $('dive-publish-form')?.addEventListener('submit', publish);
  $('dive-board-refresh')?.addEventListener('click', () => refresh());

  window.addEventListener('hashchange', () => { if (viewActive()) refresh(); });
  if (viewActive() && !state.loaded) refresh();

  // Expose the one hook the game calls; nothing else.
  window.LokiDiveBoard = {
    diveEnded: (points) => { try { whenDiveEnds(points); } catch { /* the board never blocks the game */ } }
  };
})();
