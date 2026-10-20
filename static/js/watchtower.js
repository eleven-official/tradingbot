/* Watchtower: tracked public quotes plus a fixed market floor and headlines.
 *
 * Everything shown here comes from the /api/watch-* endpoints, which answer
 * with public data or an honest per-symbol failure. Nothing in this module
 * invents a price, hides a degraded card, or implies advice: chips are
 * labelled "public", unavailable symbols stay visibly unavailable, and the
 * panel can never send an order.
 *
 * Depends on the shared $ and element helpers that workspace.js defines.
 */
'use strict';
(() => {
  const STORAGE_KEY = 'loki_watchlist_v1';
  const MAX_SYMBOLS = 8;
  const INSTRUMENT = /^[A-Z0-9^.=\-/]{1,15}$/;
  const refreshCoin = 20000; // a list fetched moments ago does not refetch itself

  const watchCards = $('#watch-cards');
  const watchMessage = $('#watch-message');
  const watchSymbolsInput = $('#watch-symbol');
  const watchForm = $('#watch-form');
  const floorCategories = $('#floor-categories');
  const floorNote = $('#floor-note');
  const signalList = $('#signal-list');
  const signalTitle = $('#signal-title');

  let watchlist = loadWatchlist();
  let lastFeedSymbol = '';
  let watchBusy = false;
  let floorBusy = false;
  let lastWatchRefresh = 0;
  let lastWatchFingerprint = '';

  function loadWatchlist() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed
        .map((item) => String(item || '').trim().toUpperCase())
        .filter((symbol, index, list) => symbol && list.indexOf(symbol) === index)
        .slice(0, MAX_SYMBOLS);
    } catch (error) {
      return [];
    }
  }

  function saveWatchlist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(watchlist));
    } catch (error) {
      /* Storage can be blocked; the watchtower then simply does not persist. */
    }
  }

  function say(text, isError) {
    if (!watchMessage) return;
    watchMessage.textContent = text || '';
    watchMessage.toggleAttribute('data-error', Boolean(isError));
  }

  function formatPrice(value, currency) {
    if (value === null || value === undefined || !isFinite(value)) return '—';
    const magnitude = Math.abs(value);
    const digits = magnitude >= 1000 ? 2 : magnitude >= 1 ? 2 : 4;
    return (
      value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }) +
      (currency ? ' ' + currency : '')
    );
  }

  function changeChip(changePct) {
    if (changePct === null || changePct === undefined || !isFinite(changePct)) {
      return element('span', 'no daily change on record', 'chip flat-chip');
    }
    const direction = changePct >= 0 ? '▲' : '▼';
    const kind = changePct > 0.0001 ? 'up-chip' : changePct < -0.0001 ? 'down-chip' : 'flat-chip';
    const label = changePct >= 0 ? '+' + changePct.toFixed(2) + '%' : changePct.toFixed(2) + '%';
    return element('span', direction + ' ' + label + ' vs previous close', 'chip ' + kind);
  }

  function sparkline(points) {
    const namespace = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(namespace, 'svg');
    svg.setAttribute('viewBox', '0 0 120 34');
    svg.setAttribute('class', 'sparkline');
    svg.setAttribute('aria-hidden', 'true');
    const clean = (Array.isArray(points) ? points : []).map(Number).filter(isFinite);
    if (clean.length < 2) {
      const line = document.createElementNS(namespace, 'line');
      line.setAttribute('x1', '0');
      line.setAttribute('x2', '120');
      line.setAttribute('y1', '17');
      line.setAttribute('y2', '17');
      line.setAttribute('class', 'spark-path');
      svg.appendChild(line);
      return svg;
    }
    const high = Math.max.apply(null, clean);
    const low = Math.min.apply(null, clean);
    const span = high - low;
    const path = document.createElementNS(namespace, 'polyline');
    const coords = clean.map((value, index) => {
      const x = clean.length === 1 ? 60 : (index / (clean.length - 1)) * 120;
      const y = span === 0 ? 17 : 30 - ((value - low) / span) * 26;
      return x.toFixed(1) + ',' + y.toFixed(1);
    });
    path.setAttribute('points', coords.join(' '));
    const lastUp = clean[clean.length - 1] >= clean[0];
    path.setAttribute('class', 'spark-path ' + (span === 0 || lastUp ? 'up-stroke' : 'down-stroke'));
    svg.appendChild(path);
    return svg;
  }

  async function fetchQuotes(symbols) {
    const query = encodeURIComponent(symbols.join(','));
    const response = await fetch('/api/watch-quotes?symbols=' + query);
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error((payload && payload.detail) || 'The quote service answered ' + response.status + '.');
    }
    return payload;
  }

  function quoteCard(item) {
    const card = element('article', null, 'watch-card' + (item.ok === false ? ' degraded' : ''));
    const head = element('div', null, 'watch-head');
    head.append(
      element('p', String(item.label || item.symbol), 'watch-name'),
      element('p', item.symbol + ' · ' + (item.provider ? item.provider.replace(/ public (API|chart)/, ' public') : 'public feed'), 'watch-sub')
    );
    card.append(head);
    if (item.ok === false) {
      card.append(element('p', item.error, 'watch-error'));
      card.append(sparkline([]));
    } else {
      const body = element('div', null, 'watch-body');
      body.append(element('strong', formatPrice(item.price, item.currency), 'watch-price'), changeChip(item.change_pct));
      card.append(body);
      card.append(sparkline(Array.isArray(item.spark) ? item.spark : []));
    }
    const actions = element('div', null, 'row-actions');
    const remove = element('button', 'Remove', 'row-action');
    remove.type = 'button';
    remove.setAttribute('aria-label', 'Remove ' + item.symbol + ' from the watchtower');
    remove.addEventListener('click', () => {
      watchlist = watchlist.filter((symbol) => symbol !== item.symbol);
      saveWatchlist();
      void refreshQuotes(true);
    });
    actions.append(remove);
    const analyze = element('button', 'Quant lab feed ↗', 'row-action');
    analyze.type = 'button';
    analyze.addEventListener('click', () => sendToPlanner(item));
    actions.append(analyze);
    card.append(actions);
    return card;
  }

  function sendToPlanner(item) {
    const pair = String(item.symbol || '');
    const binancePair = /^[A-Z0-9]{2,10}\/[A-Z0-9]{2,10}$/.test(pair) ? pair.replace('/', '') : '';
    const frame = document.querySelector('#paper-planner iframe[data-src]');
    if (!binancePair || !frame) {
      if (!binancePair) {
        say(
          'Only crypto pairs have a live Binance candle feed, so ' + (item.symbol || 'this symbol') +
          ' cannot preview in the planner. The quote stays in the watchtower.',
          true
        );
      } else {
        say('The planner frame is not available on this page layout.', true);
      }
      return;
    }
    const target = '/paper-tools?symbol=' + encodeURIComponent(binancePair);
    frame.dataset.src = target;
    if (frame.getAttribute('src')) frame.src = target;
    location.hash = '#paper-planner';
    say(binancePair + ' handoff: the planner is loading the live ' + binancePair + ' feed.', false);
  }

  function renderQuotesLoading() {
    if (!watchCards) return;
    watchCards.replaceChildren();
    if (!watchlist.length) {
      const empty = element('div', null, 'empty-state compact');
      const title = element('h3', 'Nothing watched yet.');
      const body = element('p', 'Add an instrument above — a crypto pair (BTC/USDT) or any public ticker (AAPL, ^GSPC, GC=F). Quotes answer from public providers, or fail honestly.');
      empty.append(title, body);
      watchCards.append(empty);
      return;
    }
    watchlist.forEach((symbol) => {
      const card = element('article', null, 'watch-card loading');
      card.append(element('p', symbol, 'watch-name'), element('p', 'Fetching the public quote…', 'watch-sub'));
      watchCards.append(card);
    });
  }

  function renderQuotePayload(payload) {
    if (!watchCards) return;
    watchCards.replaceChildren();
    const items = Array.isArray(payload.items) ? payload.items : [];
    const bySymbol = new Map(items.map((item) => [item.symbol, item]));
    watchlist.forEach((symbol) => {
      const item = bySymbol.get(symbol);
      if (item) {
        watchCards.append(quoteCard(item));
      } else {
        const missing = element('article', null, 'watch-card degraded');
        missing.append(element('p', symbol, 'watch-name'), element('p', 'The quote service did not answer for this symbol.', 'watch-error'));
        watchCards.append(missing);
      }
    });
    if (payload.degraded) {
      say(payload.degraded + ' of ' + payload.count + ' instruments could not be answered — shown as unavailable above. Nothing was made up to fill the gap.', true);
    } else {
      say('Public quotes refreshed' + (items.length ? ' for ' + items.length : '') + '. Cached for about a minute per symbol; never advice.', false);
    }
  }

  async function refreshQuotes(force = false) {
    if (watchBusy) return;
    const fingerprint = watchlist.join(',') + ':' + watchlist.length;
    if (!force && fingerprint === lastWatchFingerprint && Date.now() - lastWatchRefresh < refreshCoin) {
      // Same list, fetched moments ago: the cards on screen are already the
      // freshest the ~75-second provider cache can offer. Buttons force.
      return;
    }
    watchBusy = true;
    toggleBusyButtons(true);
    renderQuotesLoading();
    try {
      if (!watchlist.length) {
        say('The watchtower is empty — add an instrument above to start tracking public quotes.', false);
        return;
      }
      lastWatchFingerprint = fingerprint;
      lastWatchRefresh = Date.now();
      const payload = await fetchQuotes(watchlist);
      renderQuotePayload(payload);
      const first = watchlist[0];
      if (first && first !== lastFeedSymbol) {
        lastFeedSymbol = first;
        await refreshSignalFeed(first);
      }
    } catch (error) {
      say('The quote service is unavailable right now: ' + (error && error.message ? error.message : 'try again shortly.'), true);
      renderQuotesLoading();
    } finally {
      watchBusy = false;
      toggleBusyButtons(false);
    }
  }

  function toggleBusyButtons(busy) {
    ['#watch-refresh', '#watch-clear', '#signal-refresh', '#floor-refresh'].forEach((selector) => {
      const button = $(selector);
      if (button) button.disabled = busy;
    });
  }

  async function addSymbol(event) {
    event.preventDefault();
    const entered = String((watchSymbolsInput && watchSymbolsInput.value) || '').trim().toUpperCase();
    if (!entered || !INSTRUMENT.test(entered)) {
      say('That does not look like a public instrument symbol. Use letters, digits, or ^ . = - / separators, up to 15 characters.', true);
      return;
    }
    if (watchlist.includes(entered)) {
      say(entered + ' is already on the watchtower.', false);
      watchSymbolsInput.value = '';
      return;
    }
    if (watchlist.length >= MAX_SYMBOLS) {
      say('The watchtower tracks ' + MAX_SYMBOLS + ' instruments at a time — remove one to add ' + entered + '.', true);
      return;
    }
    watchlist.push(entered);
    saveWatchlist();
    watchSymbolsInput.value = '';
    lastFeedSymbol = '';
    await refreshQuotes(true);
  }

  async function clearWatchlist() {
    if (!watchlist.length) {
      say('The watchtower is already empty.', false);
      return;
    }
    watchlist = [];
    saveWatchlist();
    lastFeedSymbol = '';
    say('Watchtower cleared. The empty state below is genuinely empty.', false);
    renderQuotesLoading();
    clearSignalFeed();
  }

  async function refreshSignalFeed(symbol) {
    if (!signalList) return;
    signalTitle.textContent = 'Headlines · ' + symbol;
    signalList.replaceChildren();
    const loading = element('li', null, 'feed-loading');
    loading.appendChild(element('p', 'Fetching public headlines for ' + symbol + '…', 'watch-sub'));
    signalList.append(loading);
    try {
      const response = await fetch('/api/signal-feed?symbol=' + encodeURIComponent(symbol) + '&limit=6');
      const payload = await response.json().catch(() => null);
      if (!payload) throw new Error('unreadable response');
      signalList.replaceChildren();
      if (payload.items && payload.items.length) {
        payload.items.forEach((item) => {
          const line = element('li', null, 'feed-item');
          const link = element('a', item.title, 'feed-link');
          link.href = item.link;
          link.target = '_blank';
          link.rel = 'noopener';
          const meta = element('p', [item.publisher, item.published_at ? new Date(item.published_at * 1000).toLocaleDateString() : 'no timestamp'].filter(Boolean).join(' · '), 'watch-sub');
          line.append(link, meta);
          signalList.append(line);
        });
      } else {
        signalList.append(element('li', payload.error || ('The public feed returned no headlines for ' + symbol + '.'), 'feed-item feed-empty'));
      }
    } catch (error) {
      signalList.replaceChildren();
      signalList.append(element('li', 'Headlines are unavailable right now — nothing was invented to fill this list. (' + (error.message || 'try again') + ')', 'feed-item feed-empty'));
    }
  }

  function clearSignalFeed() {
    if (!signalList) return;
    signalTitle.textContent = 'Headlines';
    signalList.replaceChildren();
    signalList.append(element('li', 'Headlines load with the first tracked instrument.', 'feed-item feed-empty'));
  }

  function renderFloorLoading() {
    if (!floorCategories) return;
    floorCategories.replaceChildren();
    ['Crypto majors', 'Mega-cap tech', 'US indices', 'Commodities', 'FX & havens'].forEach((label) => {
      const group = element('article', null, 'floor-cat loading');
      group.append(element('p', label, 'floor-title'), element('p', 'Asking the public feeds…', 'watch-sub'));
      floorCategories.append(group);
    });
  }

  function renderFloorPayload(payload) {
    if (!floorCategories) return;
    floorCategories.replaceChildren();
    const categories = Array.isArray(payload.categories) ? payload.categories : [];
    let degraded = 0;
    categories.forEach((category) => {
      const group = element('article', null, 'floor-cat');
      group.append(element('p', category.label, 'floor-title'));
      const tiles = element('div', null, 'floor-tiles');
      (category.items || []).forEach((item) => {
        const tile = element('div', null, 'floor-tile' + (item.ok === false ? ' degraded' : ''));
        tile.append(
          element('p', item.label || item.symbol, 'watch-sub'),
          element('strong', item.ok === false ? 'n/a' : formatPrice(item.price, item.currency), 'watch-price'),
          changeChip(item.change_pct)
        );
        if (item.ok === false) {
          tile.title = item.error || 'unavailable';
          degraded += 1;
        }
        tiles.append(tile);
      });
      group.append(tiles);
      floorCategories.append(group);
    });
    if (floorNote) {
      floorNote.textContent = degraded
        ? degraded + ' basket member(s) could not be answered and are shown as unavailable. Public data via Binance Spot and Yahoo Finance, cached minutes apart — context, never advice.'
        : 'A fixed public basket answered by Binance Spot and Yahoo Finance, cached for about a minute per symbol. Numbers can be minutes old — context, never advice.';
    }
  }

  async function refreshFloor() {
    if (floorBusy) return;
    floorBusy = true;
    const button = $('#floor-refresh');
    if (button) button.disabled = true;
    renderFloorLoading();
    try {
      const response = await fetch('/api/watch-heatmap');
      const payload = await response.json().catch(() => null);
      if (!payload || !Array.isArray(payload.categories)) throw new Error('unreadable response');
      renderFloorPayload(payload);
    } catch (error) {
      if (floorCategories) {
        floorCategories.replaceChildren();
        const empty = element('div', null, 'empty-state compact');
        empty.append(
          element('h3', 'The market floor could not load.'),
          element('p', 'The public quote providers did not answer this time: ' + (error.message || 'try again shortly.') + ' Nothing is shown rather than showing numbers pretending to be fresh.')
        );
        floorCategories.append(empty);
      }
    } finally {
      floorBusy = false;
      if (button) button.disabled = false;
    }
  }

  function activateForView() {
    const view = (location.hash || '#overview').toLowerCase();
    if (view === '#strategy-lab') {
      void refreshQuotes();
    } else if (view === '#overview') {
      refreshFloor();
    }
  }

  window.addEventListener('hashchange', activateForView);

  if (watchForm) {
    watchForm.addEventListener('submit', (event) => { void addSymbol(event); });
  }
  const watchRefresh = $('#watch-refresh');
  if (watchRefresh) watchRefresh.addEventListener('click', () => { void refreshQuotes(true); });
  const watchClear = $('#watch-clear');
  if (watchClear) watchClear.addEventListener('click', () => { void clearWatchlist(); });
  const signalRefresh = $('#signal-refresh');
  if (signalRefresh) {
    signalRefresh.addEventListener('click', () => {
      const symbol = watchlist[0];
      if (!symbol) {
        say('Track an instrument first — headlines answer for the first watched symbol.', true);
        return;
      }
      lastFeedSymbol = '';
      void refreshSignalFeed(symbol);
    });
  }
  const floorRefresh = $('#floor-refresh');
  if (floorRefresh) floorRefresh.addEventListener('click', () => { void refreshFloor(); });

  if (watchCards && !watchCards.children.length) renderQuotesLoading();
  if (signalList) clearSignalFeed();
  activateForView();
})();
