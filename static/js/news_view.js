/* Market news desk (workspace view: #news).
 *
 * Reads /api/news — public headlines over the server's fixed topic basket —
 * and renders them with keyword chips. Nothing here is advice, nothing is
 * invented: an unreachable feed shows an honest empty state, and a partially
 * failed fetch says which terms failed next to the headlines that did answer.
 */
'use strict';
(() => {
  const viewActive = () => location.hash === '#news';
  const STALE_MS = 120000; // refetch at most every two minutes on view arrival
  const state = { loaded: false, busy: false, fetchedAt: 0 };

  const ago = (epochSeconds) => {
    const value = Number(epochSeconds);
    if (!Number.isFinite(value) || value <= 0) return 'date unknown';
    const diff = Date.now() / 1000 - value;
    if (diff < 90) return 'just now';
    if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return `${Math.round(diff / 86400)}d ago`;
  };

  function controls() {
    $('#news-refresh').disabled = state.busy;
  }

  function render(payload) {
    const list = $('#news-list');
    list.replaceChildren();
    $('#news-updated').textContent = `Checked the public feed at ${new Date().toLocaleTimeString()}.`;
    if (Array.isArray(payload.errors) && payload.errors.length) {
      list.append(element('p', `Some public queries failed right now (${payload.errors.join('; ')}). The list below is only what actually answered.`, 'caption'));
    }
    if (payload.mode === 'news-desk-degraded' || !Array.isArray(payload.items) || !payload.items.length) {
      list.append(element('p', 'No public headlines answered right now — nothing was invented to fill the page. Try again shortly.', 'muted'));
      return;
    }
    for (const item of payload.items) {
      const card = element('article', '', 'news-item');
      const title = element('h3', '', 'news-title');
      const link = element('a', item.title || 'Untitled headline', '');
      link.href = item.link;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      title.append(link);
      const tags = element('div', '', 'news-themes');
      for (const theme of item.themes || []) tags.append(element('span', theme, 'tag good'));
      for (const signal of item.signals || []) {
        if (!(item.themes || []).includes(signal)) tags.append(element('span', signal, 'tag'));
      }
      const meta = element('p', `${item.publisher || 'Unknown publisher'} · ${ago(item.published_at)}`, 'news-meta');
      card.append(title, tags, meta);
      list.append(card);
    }
    list.append(element('p', payload.note || 'Public headlines; keyword chips, not analysis; information, never advice.', 'caption'));
  }

  async function load(force = false) {
    if (state.busy) return;
    if (!force && state.loaded && Date.now() - state.fetchedAt < STALE_MS) return;
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
  window.addEventListener('hashchange', () => {
    if (viewActive()) load(false);
  });
  controls();
  if (viewActive() && !state.loaded) load(false);
})();
