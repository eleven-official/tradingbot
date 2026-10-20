/* COMMAND PALETTE + KEYBOARD CHEAT SHEET — terminal-grade navigation.
   Every entry is a real view link or a real control already on this page.
   Actions imitate the same click a finger would make; nothing here places an
   order, edits the paper journal, or invents a service that is not running.
   '?' (when not typing) opens the cheat sheet; Ctrl/⌘+K opens the palette. */
(function () {
  const overlay = document.getElementById('command-palette');
  const sheet = document.getElementById('shortcut-sheet');
  const input = document.getElementById('palette-input');
  const list = document.getElementById('palette-list');
  const hint = document.getElementById('palette-hint');
  const chip = document.getElementById('open-palette');
  if (!overlay || !input || !list || !hint) return;
  // The label matches the actual binding on the user's own platform.
  if (chip && !/Mac|iPhone|iPad/.test(navigator.userAgent || '')) chip.textContent = 'Ctrl K';

  let entries = [];
  let active = -1;
  let lastFocus = null;

  function commands() {
    const items = [];
    document.querySelectorAll('a[data-view]').forEach((link) => {
      const label = (link.textContent || '').replace(/\s+/g, ' ').trim();
      if (label) items.push({ label, detail: 'Workspace view', go: () => link.click() });
    });
    const drillNames = { 'ride-trend': 'Start drill · Ride a trend', 'range-trap': 'Start drill · Range trap', 'crash-drill': 'Start drill · Crash drill' };
    document.querySelectorAll('[data-practice]').forEach((button) => {
      const name = drillNames[button.dataset.practice];
      if (!name) return;
      items.push({ label: name, detail: 'Simulated market', go: () => { const view = document.querySelector('a[href="#simulated-market"]'); if (view) view.click(); setTimeout(() => button.click(), 350); } });
    });
    const actions = [
      ['Run a fresh workspace backup', 'Browser data', () => { const b = document.getElementById('backup-export'); ready(b) ? b.click() : blocked("Backup export is on this page — plain 'Backup' below the side panel."); }],
      ['Refresh the paper snapshot', 'Paper journal', () => { const b = document.getElementById('refresh-portfolio'); ready(b) ? b.click() : blocked('The paper portfolio panel is on this main workspace page.'); }],
      ['Export the open research report', 'Quant lab', () => { const b = document.getElementById('download-report'); ready(b) && !b.disabled ? b.click() : blocked('Load or run a research report first.'); }]
    ];
    for (const [label, detail, go] of actions) items.push({ label, detail, go });
    items.push({ label: 'Open the keyboard cheat sheet', detail: 'Keys', go: () => closePalette(false) || openSheet() });
    return items;
  }

  function ready(button) { return !!(button && !button.disabled); }

  function blocked(reason) {
    hint.textContent = reason + ' The palette will not pretend an action ran.';
    setTimeout(() => { hint.textContent = 'Every entry is a real view or control on this site — nothing sends an order from here.'; }, 5200);
  }

  function matches(query) {
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter((entry) => (entry.label + ' ' + entry.detail).toLowerCase().includes(q));
  }

  function render(queryText) {
    const rows = matches(queryText);
    active = rows.length ? Math.max(active, 0) : -1;
    list.replaceChildren(...rows.map((entry, index) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.className = 'palette-item' + (index === active ? ' active' : '');
      const main = document.createElement('span'); main.className = 'palette-label'; main.textContent = entry.label;
      const side = document.createElement('span'); side.className = 'palette-detail'; side.textContent = entry.detail;
      li.append(main, side);
      li.addEventListener('click', () => choose(entry));
      return li;
    }));
    hint.textContent = rows.length ? `${rows.length} entr${rows.length === 1 ? 'y' : 'ies'} · ↑ ↓ choose · Enter go · Esc close` : 'Nothing on this site matches that. Try fewer letters.';
    return rows;
  }

  function choose(entry) {
    closePalette();
    entry.go();
  }

  function openPalette() {
    lastFocus = document.activeElement;
    entries = commands();
    active = 0;
    overlay.hidden = false;
    input.value = '';
    render('');
    input.focus();
  }

  function closePalette(andFocusBack = true) { overlay.hidden = true; if (andFocusBack && lastFocus && lastFocus.focus) lastFocus.focus(); }

  function openSheet() { lastFocus = document.activeElement; sheet.hidden = false; }

  function closeSheet() { sheet.hidden = true; if (lastFocus && lastFocus.focus) lastFocus.focus(); }

  function move(delta) {
    const rows = matches(input.value);
    if (!rows.length) return;
    active = (active + delta + rows.length) % rows.length;
    render(input.value);
    const current = list.children[active];
    if (current && current.scrollIntoView) current.scrollIntoView({ block: 'nearest' });
  }

  input.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); move(1); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); }
    else if (event.key === 'Enter') { event.preventDefault(); const rows = matches(input.value); const picked = active >= 0 && rows[active] ? rows[active] : rows[0]; if (picked) choose(picked); else { closePalette(); } }
    else if (event.key === 'Escape') { event.preventDefault(); closePalette(); }
  });
  input.addEventListener('input', () => { active = 0; render(input.value); });
  overlay.querySelectorAll('[data-palette-close]').forEach((el) => el.addEventListener('click', () => closePalette()));
  if (sheet) sheet.querySelectorAll('[data-sheet-close]').forEach((el) => el.addEventListener('click', closeSheet));
  if (chip) chip.addEventListener('click', openPalette);

  document.addEventListener('keydown', (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '') || document.activeElement?.isContentEditable;
    if ((event.ctrlKey || event.metaKey) && (event.key === 'k' || event.key === 'K')) {
      event.preventDefault();
      if (overlay.hidden) openPalette(); else closePalette();
      return;
    }
    if (event.key === 'Escape') {
      if (!overlay.hidden) { closePalette(); return; }
      if (sheet && !sheet.hidden) { closeSheet(); return; }
    }
    if (event.key === '?' && !typing) { event.preventDefault(); openSheet(); }
  });
})();
