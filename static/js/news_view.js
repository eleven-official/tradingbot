/* Market news desk (workspace view: #news).
 *
 * Reads /api/news — public headlines over the server's fixed topic basket —
 * and renders them with keyword chips. On top of the raw list sits a skim
 * layer that runs entirely in this browser: a text filter, topic chips, and
 * clickable keyword chips. Filtering is a skim of keyword matches, never an
 * analysis of the market, and the flag row says so. Nothing here is advice
 * and nothing is invented: an unreachable feed shows an honest empty state,
 * and a partially failed fetch says which terms failed next to the headlines
 * that did answer.
 */
'use strict';
(() => {
  const viewActive = () => location.hash === '#news';
  const STALE_MS = 120000; // refetch at most every two minutes on view arrival
  const SEEN_KEY = 'loki_news_seen_v1'; // last look timestamp, this browser only
  const state = {
    loaded: false,
    busy: false,
    fetchedAt: 0,
    payload: null, // the most recent successful fetch, re-skimmed client-side
    theme: '', // active topic chip ('' = all)
    text: '', // active text filter
  };

  const ago = (epochSeconds) => {
    const value = Number(epochSeconds);
    if (!Number.isFinite(value) || value <= 0) return 'date unknown';
    const diff = Date.now() / 1000 - value;
    if (diff < 90) return 'just now';
    if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  };

  const seenAt = () => {
    try {
      const raw = JSON.parse(localStorage.getItem(SEEN_KEY) || 'null');
      return raw && typeof raw.at === 'number' ? raw.at / 1000 : null;
    } catch {
      return null;
    }
  };

  const markSeen = () => {
    try {
      localStorage.setItem(SEEN_KEY, JSON.stringify({ at: Date.now() }));
    } catch { /* storage may refuse; the badge simply never shows */ }
  };

  const matches = (item, text) => {
    const hay = [
      item.title || '',
      item.publisher || '',
      ...(item.themes || []),
      ...(item.signals || []),
    ].join(' ').toLowerCase();
    return hay.includes(text);
  };

  function controls() {
    $('#news-refresh').disabled = state.busy;
  }

  function buildTopicChips() {
    const row = $('#news-topics');
    if (!row || !state.payload) return;
    const items = Array.isArray(state.payload.items) ? state.payload.items : [];
    const themes = [];
    for (const item of items) for (const theme of item.themes || []) if (!themes.includes(theme)) themes.push(theme);
    row.replaceChildren();
    const all = element('button', 'All topics', 'news-topic-chip');
    all.type = 'button';
    all.setAttribute('aria-pressed', String(!state.theme));
    all.title = 'Show every headline the public feed answered (chip row is a client-side skim).';
    all.addEventListener('click', () => { state.theme = ''; applyView(); });
    row.append(all);
    for (const theme of themes) {
      const chip = element('button', theme, 'news-topic-chip');
      chip.type = 'button';
      chip.setAttribute('aria-pressed', String(state.theme === theme));
      chip.title = `Skim the desk for the ${theme} topic — plain keyword matches, not analysis.`;
      chip.addEventListener('click', () => {
        state.theme = state.theme === theme ? '' : theme;
        applyView();
      });
      row.append(chip);
    }
  }

  function render(payload) {
    state.payload = payload;
    $('#news-updated').textContent = `Checked the public feed at ${new Date().toLocaleTimeString()}.`;
    if (payload.mode === 'news-desk-degraded' || !Array.isArray(payload.items) || !payload.items.length) {
      const list = $('#news-list');
      list.replaceChildren();
      if (Array.isArray(payload.errors) && payload.errors.length) {
        list.append(element('p', `Some public queries failed right now (${payload.errors.join('; ')}). The list below is only what actually answered.`, 'caption'));
      }
      list.append(element('p', 'No public headlines answered right now — nothing was invented to fill the page. Try again shortly.', 'muted'));
      buildTopicChips();
      count();
      controls();
      return;
    }
    applyView();
    markSeen();
    controls();
  }

  function count(shown, total) {
    const line = $('#news-count');
    if (!line) return;
    if (!total) {
      line.textContent = '';
      return;
    }
    line.textContent = `Showing ${shown} of ${total} public headlines. Filters run in this browser only — a skim of keyword matches, not analysis.`;
  }

  function applyView() {
    const payload = state.payload;
    if (!payload || !Array.isArray(payload.items)) return;
    const list = $('#news-list');
    list.replaceChildren();
    if (Array.isArray(payload.errors) && payload.errors.length) {
      list.append(element('p', `Some public queries failed right now (${payload.errors.join('; ')}). The list below is only what actually answered.`, 'caption'));
    }
    const total = payload.items.length;
    const text = state.text.trim().toLowerCase();
    const baseline = seenAt();
    let shown = 0;
    for (const item of payload.items) {
      if (state.theme && !(item.themes || []).includes(state.theme)) continue;
      if (text && !matches(item, text)) continue;
      shown += 1;
      const card = element('article', '', 'news-item');
      const title = element('h3', '', 'news-title');
      const link = element('a', item.title || 'Untitled headline', '');
      link.href = item.link;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      title.append(link);
      if (baseline && Number(item.published_at) > baseline) {
        card.append(element('span', 'new since your last look', 'news-new-flag'));
      }
      const tags = element('div', '', 'news-themes');
      for (const theme of item.themes || []) {
        const chip = element('button', theme, 'tag good');
        chip.type = 'button';
        chip.title = `Skim the desk for the ${theme} topic — plain keyword matches, not analysis.`;
        chip.addEventListener('click', () => { state.theme = state.theme === theme ? '' : theme; applyView(); });
        tags.append(chip);
      }
      for (const signal of item.signals || []) {
        if ((item.themes || []).includes(signal)) continue;
        const chip = element('button', signal, 'tag');
        chip.type = 'button';
        chip.title = `Skim the desk for “${signal}” — plain keyword matches, not analysis.`;
        chip.addEventListener('click', () => { state.text = state.text === signal ? '' : signal; $('#news-search').value = state.text; applyView(); });
        tags.append(chip);
      }
      const meta = element('p', `${item.publisher || 'Unknown publisher'} · ${ago(item.published_at)}`, 'news-meta');
      card.append(title, tags, meta);
      list.append(card);
    }
    if (!shown) {
      list.append(element('p', state.theme || text
        ? 'No headline in the current public basket matches this filter. That is a skim result, not a market verdict — clear the filter to see everything.'
        : 'No public headlines answered right now — nothing was invented to fill the page. Try again shortly.', 'muted'));
    }
    buildTopicChips();
    count(shown, total);
    list.append(element('p', payload.note || 'Public headlines; keyword chips, not analysis; information, never advice.', 'caption news-note'));
  }

  async function load(force = false) {
    if (state.busy) return;
    if (!force && state.loaded && Date.now() - state.fetchedAt < STALE_MS) {
      if (state.payload) {
        applyView(); // re-skim on view arrival; refreshes "new since your last look"
        markSeen();
      }
      return;
    }
    state.busy = true;
    controls();
    message('#news-message', 'Fetching public market news…');
    try {
      const response = await fetch('/api/news?limit=24', { cache: 'no-store' });
      const payload = await response.json();
      state.loaded = true;
      state.fetchedAt = Date.now();
      render(payload);
      message('#news-message', payload.mode === 'news-desk-degraded'
        ? 'The public news feed is unreachable right now — this page says so instead of pretending.'
        : '', payload.mode === 'news-desk-degraded');
    } catch (error) {
      message('#news-message', error.message || 'The public news feed could not be reached.', true);
    } finally {
      state.busy = false;
      controls();
    }
  }

  $('#news-refresh').addEventListener('click', () => load(true));
  const search = $('#news-search');
  if (search) search.addEventListener('input', () => { state.text = search.value; applyView(); });
  const erase = $('#news-clear-filters');
  if (erase) erase.addEventListener('click', () => {
    state.theme = '';
    state.text = '';
    const box = $('#news-search');
    if (box) box.value = '';
    applyView();
  });
  window.addEventListener('hashchange', () => {
    if (viewActive()) load(false);
  });
  controls();
  if (viewActive() && !state.loaded) load(false);
})();
