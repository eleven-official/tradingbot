/* Loki Dive — a rare-answer trivia game (krillion-style), unlimited mode.
 * Pure vanilla JS, no console noise, pauses itself whenever the view is hidden.
 * Scoring is local: nothing about a player's answers leaves the browser.
 *
 * Spelling is forgiven: answers match through a Damerau-Levenshtein distance
 * with a small, length-aware tolerance, plus folded articles ("a parrot" ==
 * "parrot") and folded plurals ("gorgonzolas" == "gorgonzola"). When a typo
 * is fixed, the round says so. Prompt draws avoid recently seen prompts so
 * consecutive dives stay fresh until the pool runs low.
 */
"use strict";
(function () {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initWordle, { once: true });
  } else {
    initWordle();
  }
  const bank = window.LokiDiveBank;
  if (!bank || !Array.isArray(bank.prompts) || bank.prompts.length < 7) return;

  const ROUND_MS = 25000;
  const ROUNDS_PER_DIVE = 7;
  const POINTS_PER_METRE = 10;
  const CLEAN_SWEEP_BONUS = 50; // all seven rounds found
  const HOT_STREAK = 3;         // consecutive finds needed before the combo pays
  const COMBO_BONUS = 5;        // paid per find from the third in a row onward
  const MAX_STREAK_BONUS = (ROUNDS_PER_DIVE - HOT_STREAK + 1) * COMBO_BONUS; // 25 headroom
  const METER_MAX = ROUNDS_PER_DIVE * 100 * POINTS_PER_METRE
    + (CLEAN_SWEEP_BONUS + MAX_STREAK_BONUS) * POINTS_PER_METRE; // 7,750 m headroom
  const RECENT_LIMIT = 10; // remember this many prompts to keep dives fresh
  const MISS_LIMIT = 2;           // endless waters: two unanswered rounds end the dive
  const ROUND_MS_FLOOR = 14000;   // endless: the clock tightens but never below this
  const ENDLESS_TIGHTEN_MS = 500; // endless: shave this much per completed round
  const LS_BEST_ENDLESS = "loki_dive_best_endless"; // endless best, this browser only
  const LS_MODE = "loki_dive_mode";       // last mode picked, restored on arrival
  const LS_JOURNAL = "loki_dive_journal"; // per-prompt personal bests, never published
  const LS_SOUND = "loki_dive_sound";     // 1/0 through the numeric helpers; blips are a taste

  const els = {};
  const LS_BEST = "loki_dive_best";
  const LS_DIVES = "loki_dive_dives";
  const LS_RECENT = "loki_dive_recent";
  const LS_HISTORY = "loki_dive_history";
  const LS_BADGES = "loki_dive_badges";   // earned milestone ids (this browser only)
  const LS_STREAK = "loki_dive_streak";   // { last: 'YYYY-MM-DD', count } — consecutive dive days
  const LS_CH_WINS = "loki_dive_challenge_wins"; // how many daily targets cleared, lifetime
  const LS_LIFETIME = "loki_dive_lifetime"; // total points banked over every dive — drives levels
  const LEVEL_STEP = 500; // each level is 500 lifetime points deeper than the last
  const HISTORY_LIMIT = 10;

  const state = {
    phase: "idle", // idle | round | between | done
    order: [],
    cursor: 0,
    round: 0,
    points: 0,
    bonus: 0,
    streak: 0,
    streakBonus: 0,
    manualPaused: false,
    fixed: 0, // spelling corrections this dive
    mode: "classic", // classic (7 fixed rounds) | endless (miss twice, tightening clock) | daily (the shared seven)
    maxStreak: 0,
    misses: 0,       // endless: unanswered rounds so far this dive
    roundMs: ROUND_MS,
    bestEndless: 0,  // endless personal best, kept locally
    surfaced: false, // endless: true when the diver chose to surface mid-round
    sonarUsed: false, // one ping per dive, classic or endless alike
    rounds: [], // {prompt, tier|null, points, answer, fixed}
    current: null,
    deadline: 0,
    tLeft: ROUND_MS,
    accepted: false,
    sectionEl: null,
    best: 0,
    dives: 0,
    visible: true,
    running: false,
    rafId: 0
  };

  // Wordle game
  function initWordle() {
    const wordleGame = document.getElementById('wordle-game');
    if (!wordleGame) return;

    const WORDS = [
      'SLATE', 'CRANE', 'ADIEU', 'ARISE', 'RAISE', 'IRATE', 'ABOUT', 'ABOVE', 'ABUSE', 'ACTOR',
      'ACUTE', 'ADMIT', 'ADOPT', 'ADORE', 'ADULT', 'AFTER', 'AGAIN', 'AGENT', 'AGREE', 'AHEAD',
      'ALARM', 'ALBUM', 'ALERT', 'ALIKE', 'ALIVE', 'ALLOW', 'ALONE', 'ALONG', 'ALTER', 'AMBER',
      'AMEND', 'AMONG', 'ANGER', 'ANGLE', 'ANGRY', 'APART', 'APPLE', 'APPLY', 'ARENA', 'ARGUE',
      'ARISE', 'ARMOR', 'ARRAY', 'ASIDE', 'ASSET', 'AVOID', 'AWAKE', 'AWFUL', 'BADGE', 'BAKER',
      'BASIS', 'BEACH', 'BEGAN', 'BEGIN', 'BEGUN', 'BEING', 'BELOW', 'BENCH', 'BILLY', 'BIRTH',
      'BLACK', 'BLAME', 'BLANK', 'BLAST', 'BLEAK', 'BLEND', 'BLESS', 'BLIND', 'BLINK', 'BLISS',
      'BLOCK', 'BLOOD', 'BLOOM', 'BLOWN', 'BLUER', 'BLUNT', 'BOARD', 'BOAST', 'BONUS', 'BOOST',
      'BOOTH', 'BOUND', 'BRAIN', 'BRAKE', 'BRAND', 'BRASS', 'BRAVE', 'BREAD', 'BREAK', 'BREED',
      'BRIEF', 'BRING', 'BRINK', 'BRISK', 'BROAD', 'BROKE', 'BROWN', 'BUILD', 'BUILT', 'BUYER',
      'CABLE', 'CALIF', 'CARRY', 'CATCH', 'CAUSE', 'CHAIN', 'CHAIR', 'CHART', 'CHASE', 'CHEAP',
      'CHECK', 'CHEEK', 'CHEER', 'CHESS', 'CHEST', 'CHICK', 'CHIEF', 'CHILD', 'CHINA', 'CHOSE',
      'CIVIL', 'CLAIM', 'CLASS', 'CLEAN', 'CLEAR', 'CLICK', 'CLIMB', 'CLOCK', 'CLOSE', 'CLOUD',
      'COACH', 'COAST', 'COULD', 'COUNT', 'COURT', 'COVER', 'CRAFT', 'CRASH', 'CREAM', 'CRIME',
      'CROSS', 'CROWD', 'CROWN', 'CRUDE', 'CURVE', 'CYCLE', 'DAILY', 'DANCE', 'DATED', 'DEALT',
      'DEATH', 'DEBUT', 'DELAY', 'DEPTH', 'DOING', 'DOUBT', 'DOZEN', 'DRAFT', 'DRAMA', 'DRAWN',
      'DREAM', 'DRESS', 'DRILL', 'DRINK', 'DRIVE', 'DROVE', 'DYING', 'EAGER', 'EARLY', 'EARTH',
      'EIGHT', 'ELITE', 'EMPTY', 'ENEMY', 'ENJOY', 'ENTER', 'ENTRY', 'EQUAL', 'ERROR', 'EVENT',
      'EVERY', 'EXACT', 'EXIST', 'EXTRA', 'FAITH', 'FALSE', 'FAULT', 'FIBER', 'FIELD', 'FIFTH',
      'FIFTY', 'FIGHT', 'FINAL', 'FIRST', 'FIXED', 'FLAME', 'FLASH', 'FLEET', 'FLOOR', 'FLUID',
      'FOCUS', 'FORCE', 'FORTH', 'FORTY', 'FORUM', 'FOUND', 'FRAME', 'FRANK', 'FRAUD', 'FRESH',
      'FRONT', 'FRUIT', 'FULLY', 'FUNNY', 'GIANT', 'GIVEN', 'GLASS', 'GLOBE', 'GOING', 'GRACE',
      'GRADE', 'GRAND', 'GRANT', 'GRASS', 'GREAT', 'GREEN', 'GROSS', 'GROUP', 'GROWN', 'GUARD',
      'GUESS', 'GUEST', 'GUIDE', 'HAPPY', 'HARRY', 'HEART', 'HEAVY', 'HENCE', 'HENRY', 'HORSE',
      'HOTEL', 'HOUSE', 'HUMAN', 'IDEAL', 'IMAGE', 'INDEX', 'INNER', 'INPUT', 'ISSUE', 'JAPAN',
      'JIMMY', 'JOINT', 'JONES', 'JUDGE', 'KNOWN', 'LABEL', 'LARGE', 'LASER', 'LATER', 'LAUGH',
      'LAYER', 'LEARN', 'LEASE', 'LEAST', 'LEAVE', 'LEGAL', 'LEVEL', 'LEWIS', 'LIGHT', 'LIMIT',
      'LINKS', 'LIVES', 'LOCAL', 'LOGIC', 'LOOSE', 'LOWER', 'LUCKY', 'LUNCH', 'LYING', 'MAGIC',
      'MAJOR', 'MAKER', 'MARCH', 'MARIA', 'MATCH', 'MAYBE', 'MAYOR', 'MEANT', 'MEDIA', 'METAL',
      'MIGHT', 'MINOR', 'MINUS', 'MIXED', 'MODEL', 'MONEY', 'MONTH', 'MORAL', 'MOTOR', 'MOUNT',
      'MOUSE', 'MOUTH', 'MOVIE', 'MUSIC', 'NEEDS', 'NEVER', 'NEWLY', 'NIGHT', 'NOISE', 'NORTH',
      'NOTED', 'NOVEL', 'NURSE', 'OCCUR', 'OCEAN', 'OFFER', 'OFTEN', 'ORDER', 'OTHER', 'OUGHT',
      'PAINT', 'PANEL', 'PAPER', 'PARTY', 'PEACE', 'PETER', 'PHASE', 'PHONE', 'PHOTO', 'PIECE',
      'PILOT', 'PITCH', 'PLACE', 'PLAIN', 'PLANE', 'PLANT', 'PLATE', 'POINT', 'POUND', 'POWER',
      'PRESS', 'PRICE', 'PRIDE', 'PRIME', 'PRINT', 'PRIOR', 'PRIZE', 'PROOF', 'PROUD', 'PROVE',
      'QUEEN', 'QUICK', 'QUIET', 'QUITE', 'RADIO', 'RAISE', 'RANGE', 'RAPID', 'RATIO', 'REACH',
      'READY', 'REALM', 'REBEL', 'REFER', 'RELAX', 'REPAY', 'REPLY', 'RIGHT', 'RIGID', 'RIVAL',
      'RIVER', 'ROBIN', 'ROGER', 'ROMAN', 'ROUGH', 'ROUND', 'ROUTE', 'ROYAL', 'RURAL', 'SCALE',
      'SCENE', 'SCOPE', 'SCORE', 'SENSE', 'SERVE', 'SETUP', 'SEVEN', 'SHALL', 'SHAPE', 'SHARE',
      'SHARP', 'SHEET', 'SHELF', 'SHELL', 'SHIFT', 'SHIRT', 'SHOCK', 'SHOOT', 'SHORT', 'SHOWN',
      'SIGHT', 'SINCE', 'SIXTH', 'SIXTY', 'SIZED', 'SKILL', 'SLEEP', 'SLIDE', 'SMALL', 'SMART',
      'SMILE', 'SMITH', 'SMOKE', 'SOLID', 'SOLVE', 'SORRY', 'SOUND', 'SOUTH', 'SPACE', 'SPARE',
      'SPEAK', 'SPEED', 'SPEND', 'SPENT', 'SPLIT', 'SPOKE', 'SPORT', 'STAFF', 'STAGE', 'STAKE',
      'STAND', 'START', 'STATE', 'STEAM', 'STEEL', 'STEEP', 'STEER', 'STICK', 'STILL', 'STOCK',
      'STONE', 'STOOD', 'STORE', 'STORM', 'STORY', 'STRIP', 'STUCK', 'STUDY', 'STUFF', 'STYLE',
      'SUGAR', 'SUITE', 'SUPER', 'SWEET', 'TABLE', 'TAKEN', 'TASTE', 'TAXES', 'TEACH', 'TEETH',
      'TERRY', 'TEXAS', 'THANK', 'THEFT', 'THEIR', 'THEME', 'THERE', 'THESE', 'THICK', 'THING',
      'THINK', 'THIRD', 'THOSE', 'THREE', 'THREW', 'THROW', 'THUMB', 'TIGHT', 'TIRED', 'TITLE',
      'TODAY', 'TOPIC', 'TOTAL', 'TOUCH', 'TOUGH', 'TOWER', 'TRACK', 'TRADE', 'TRAIN', 'TREAT',
      'TREND', 'TRIAL', 'TRIED', 'TRIES', 'TRUCK', 'TRULY', 'TRUST', 'TRUTH', 'TWICE', 'UNDER',
      'UNDUE', 'UNION', 'UNITY', 'UNTIL', 'UPPER', 'UPSET', 'URBAN', 'USAGE', 'USUAL', 'VALID',
      'VALUE', 'VIDEO', 'VIRUS', 'VISIT', 'VITAL', 'VOCAL', 'WASTE', 'WATCH', 'WATER', 'WHEEL',
      'WHERE', 'WHICH', 'WHILE', 'WHITE', 'WHOLE', 'WHOSE', 'WOMAN', 'WOMEN', 'WORLD', 'WORRY',
      'WORSE', 'WORST', 'WORTH', 'WOULD', 'WRITE', 'WRONG', 'WROTE', 'YIELD', 'YOUNG', 'YOUTH'
    ];

    const boardEl = document.getElementById('wordle-board');
    const keyboardEl = document.getElementById('wordle-keyboard');
    const messageEl = document.getElementById('wordle-message');
    const newGameBtn = document.getElementById('wordle-new-game');

    if (!boardEl || !keyboardEl || !messageEl || !newGameBtn) return;

    let solution = WORDS[Math.floor(Math.random() * WORDS.length)];
    let currentRow = 0;
    let currentCol = 0;
    let gameOver = false;
    const guesses = Array(6).fill().map(() => Array(5).fill(''));

    // Create board
    boardEl.innerHTML = '';
    for (let i = 0; i < 6; i++) {
      for (let j = 0; j < 5; j++) {
        const tile = document.createElement('div');
        tile.className = 'wordle-tile';
        tile.setAttribute('data-row', i);
        tile.setAttribute('data-col', j);
        tile.setAttribute('aria-label', `Row ${i + 1}, letter ${j + 1}: empty`);
        boardEl.appendChild(tile);
      }
    }

    // Create keyboard
    const keys = [
      ['Q','W','E','R','T','Y','U','I','O','P'],
      ['A','S','D','F','G','H','J','K','L'],
      ['ENTER','Z','X','C','V','B','N','M','BACK']
    ];
    keyboardEl.innerHTML = '';
    keys.forEach(row => {
      const rowEl = document.createElement('div');
      rowEl.className = 'wordle-key-row';
      row.forEach(key => {
        const keyEl = document.createElement('button');
        keyEl.type = 'button';
        keyEl.className = 'wordle-key';
        keyEl.textContent = key === 'BACK' ? '⌫' : key;
        keyEl.dataset.key = key;
        keyEl.setAttribute('aria-label', key === 'BACK' ? 'Delete letter' : key);
        keyEl.addEventListener('click', () => {
          handleKey(key);
          wordleGame.focus({ preventScroll: true });
        });
        rowEl.appendChild(keyEl);
      });
      keyboardEl.appendChild(rowEl);
    });

    function updateBoard() {
      for (let i = 0; i < 6; i++) {
        for (let j = 0; j < 5; j++) {
          const tile = boardEl.querySelector(`.wordle-tile[data-row="${i}"][data-col="${j}"]`);
          if (tile) {
            tile.textContent = guesses[i][j];
            if (i >= currentRow) tile.setAttribute('aria-label', `Row ${i + 1}, letter ${j + 1}: ${guesses[i][j] || 'empty'}`);
          }
        }
      }
    }

    function handleKey(key) {
      if (gameOver) return;
      messageEl.textContent = '';
      if (key === 'ENTER') {
        submitGuess();
      } else if (key === 'BACK') {
        if (currentCol > 0) {
          currentCol--;
          guesses[currentRow][currentCol] = '';
          updateBoard();
        }
      } else if (currentCol < 5 && /^[A-Z]$/.test(key)) {
        guesses[currentRow][currentCol] = key;
        currentCol++;
        updateBoard();
      }
    }

    function submitGuess() {
      if (currentCol < 5) {
        messageEl.textContent = 'Not enough letters';
        return;
      }
      const guess = guesses[currentRow].join('');
      if (!WORDS.includes(guess)) {
        messageEl.textContent = 'Not in word list';
        return;
      }

      const solutionArray = solution.split('');
      const guessArray = guess.split('');
      const result = Array(5).fill('absent');
      const solutionCopy = [...solutionArray];

      // Check correct positions
      for (let i = 0; i < 5; i++) {
        if (guessArray[i] === solutionCopy[i]) {
          result[i] = 'correct';
          solutionCopy[i] = null;
        }
      }
      // Check present positions
      for (let i = 0; i < 5; i++) {
        if (result[i] === 'correct') continue;
        const idx = solutionCopy.indexOf(guessArray[i]);
        if (idx !== -1) {
          result[i] = 'present';
          solutionCopy[idx] = null;
        }
      }

      // Apply colors
      for (let i = 0; i < 5; i++) {
        const tile = boardEl.querySelector(`.wordle-tile[data-row="${currentRow}"][data-col="${i}"]`);
        if (tile) {
          tile.classList.add(result[i]);
          tile.setAttribute('aria-label', `${guessArray[i]}: ${result[i]}`);
        }
        const keyEl = keyboardEl.querySelector(`.wordle-key[data-key="${guessArray[i]}"]`);
        if (keyEl) {
          if (result[i] === 'correct') {
            keyEl.classList.add('correct');
            keyEl.classList.remove('present', 'absent');
          } else if (result[i] === 'present' && !keyEl.classList.contains('correct')) {
            keyEl.classList.remove('absent');
            keyEl.classList.add('present');
          } else if (result[i] === 'absent' && !keyEl.classList.contains('correct') && !keyEl.classList.contains('present')) {
            keyEl.classList.add('absent');
          }
        }
      }

      if (guess === solution) {
        messageEl.textContent = 'You got it!';
        gameOver = true;
        return;
      }

      currentRow++;
      currentCol = 0;
      messageEl.textContent = `${guess}: ${result.map((status, i) => `${guessArray[i]} ${status}`).join(', ')}. Guess ${currentRow + 1} of 6.`;
      if (currentRow >= 6) {
        messageEl.textContent = `The word was ${solution}`;
        gameOver = true;
      }
    }

    // Keep typing in the Dive, command palette and account forms independent.
    wordleGame.addEventListener('keydown', (e) => {
      if (wordleGame.closest('[hidden]') || gameOver || e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
      if (e.target.closest('input, textarea, select, [contenteditable="true"]')) return;
      if (e.key === 'Enter' && e.target.closest('button')) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        handleKey('ENTER');
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        handleKey('BACK');
      } else if (/^[A-Za-z]$/.test(e.key)) {
        e.preventDefault();
        handleKey(e.key.toUpperCase());
      }
    });
    boardEl.addEventListener('click', () => wordleGame.focus({ preventScroll: true }));

    newGameBtn.addEventListener('click', () => {
      const choices = WORDS.filter(word => word !== solution);
      solution = choices[Math.floor(Math.random() * choices.length)];
      currentRow = 0;
      currentCol = 0;
      gameOver = false;
      for (let i = 0; i < 6; i++) {
        for (let j = 0; j < 5; j++) {
          guesses[i][j] = '';
          const tile = boardEl.querySelector(`.wordle-tile[data-row="${i}"][data-col="${j}"]`);
          if (tile) {
            tile.textContent = '';
            tile.classList.remove('correct', 'present', 'absent');
            tile.setAttribute('aria-label', `Row ${i + 1}, letter ${j + 1}: empty`);
          }
        }
      }
      keyboardEl.querySelectorAll('.wordle-key').forEach(keyEl => {
        keyEl.classList.remove('correct', 'present', 'absent');
      });
      messageEl.textContent = '';
      wordleGame.focus({ preventScroll: true });
    });
  }

  /* ---------- helpers ---------- */
  function $(id) { return document.getElementById(id); }
  function esc(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }
  function normalize(text) {
    if (typeof text !== "string") return "";
    let s = text.trim().toLowerCase();
    if (s.normalize) {
      s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    }
    s = s.replace(/&/g, " and ").replace(/[^a-z0-9\s']/g, " ").replace(/'/g, "").replace(/\s+/g, " ").trim();
    if (s === "the answer") return "";
    return s;
  }
  /* Fold articles and plurals so near-hits meet exactly before distances kick in. */
  function fold(text) {
    let s = normalize(text);
    if (!s) return "";
    s = s.replace(/^(a|an|the)\s+/, "").replace(/\s+/g, " ").trim();
    if (s.length > 3 && s.endsWith("s") && !s.endsWith("ss")) s = s.slice(0, -1);
    return s;
  }
  /* Length-aware tolerance: short words must be exact, long ones forgive two. */
  function toleranceFor(len) {
    if (len <= 4) return 0;
    if (len <= 7) return 1;
    return 2;
  }
  /* Damerau-Levenshtein (optimal string alignment) distance. */
  function damerauDistance(a, b) {
    const m = a.length;
    const n = b.length;
    if (!m || !n) return m + n;
    const d = [];
    for (let i = 0; i <= m; i += 1) { d.push([i]); d[i][0] = i; }
    for (let j = 0; j <= n; j += 1) d[0][j] = j;
    for (let i = 1; i <= m; i += 1) {
      for (let j = 1; j <= n; j += 1) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        let best = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          best = Math.min(best, d[i - 2][j - 2] + 1); // transposition
        }
        d[i][j] = best;
      }
    }
    return d[m][n];
  }
  /* Exact first, folded variants next, then closest bank entry inside tolerance. */
  function findAnswer(index, raw) {
    const key = normalize(raw);
    if (!key) return null;
    const exact = index.get(key);
    if (exact) return { hit: exact, fixed: false };
    const folded = fold(raw);
    if (folded && index.has(folded)) return { hit: index.get(folded), fixed: false };
    let best = null;
    let bestDist = Infinity;
    let bestKey = "";
    index.forEach((value, entryKey) => {
      const candidates = [entryKey];
      const alt = entryKey.replace(/^the\s+/, "");
      if (alt !== entryKey) candidates.push(alt);
      for (const cand of candidates) {
        if (cand === folded) return; // already checked exactly
        const dist = damerauDistance(folded, cand);
        const tol = toleranceFor(Math.max(folded.length, cand.length));
        if (dist <= tol && dist < bestDist) {
          bestDist = dist;
          best = value;
          bestKey = cand;
        }
      }
    });
    if (best) return { hit: best, fixed: true, via: bestKey };
    return null;
  }
  function fmtM(m) { return Number(m).toLocaleString("en-AU") + " m"; }
  function storage(key, fallback) {
    try {
      const v = window.localStorage.getItem(key);
      return v === null ? fallback : Number(v) || 0;
    } catch { return fallback; }
  }
  function saveStorage(key, value) {
    try { window.localStorage.setItem(key, String(value)); } catch { /* private mode */ }
  }

  /* ---------- level ladder: lifetime points → diver level ---------- */
  function diverLevel(total) {
    // floor(total / 500) + 1 — level 1 at 0, level 2 at 500, level 99 at 49,000+
    return Math.floor(Math.max(0, Number(total) || 0) / LEVEL_STEP) + 1;
  }
  function readLifetime() {
    return storage(LS_LIFETIME, 0);
  }
  function bankLifetime(runPoints) {
    const banked = readLifetime() + Math.max(0, Number(runPoints) || 0);
    saveStorage(LS_LIFETIME, banked); // the run already rides under MAX_SCORE locally
    return banked;
  }
  function renderLevel() {
    const node = els["dive-level"];
    if (!node) return;
    const total = readLifetime();
    const level = diverLevel(total);
    const toNext = LEVEL_STEP - (total % LEVEL_STEP);
    node.textContent = "Depth level " + level + " · " + toNext + " pts to level " + (level + 1);
    node.title = "Levels rise as lifetime points bank locally in this browser — 500 points per level. Never published anywhere.";
  }

  /* ---------- autosave: the browser's own facts, saved to this device ---------- */
  /* One snapshot of this browser's Loki Dive state, written to this device
   * every time the game is opened (and updated after every run). Nothing here
   * is ever sent to the server — the snapshot lives beside the other keys in
   * localStorage and is meant to survive a browser restart / disk tidy-up. */
  const LS_AUTOSAVE = "loki_dive_last_open"; // snapshot of this browser's own info, this device only
  const AUTOSAVE_JOURNAL_MAX = 120;  // journal entries kept in the snapshot
  const AUTOSAVE_HISTORY_MAX = 10;   // history summary rides raw — same bound as the history key
  const AUTOSAVE_BYTES_MAX = 20000;  // larger snapshots would hint at drift; skip them

  function autosaveSnapshot() {
    try {
      const readJSON = (key, fallback) => {
        try {
          const raw = JSON.parse(window.localStorage.getItem(key) || "null");
          return raw === null || raw === undefined ? fallback : raw;
        } catch { return fallback; }
      };
      const journal = readJSON(LS_JOURNAL, {});
      if (journal && typeof journal === "object" && !Array.isArray(journal)) {
        const keys = Object.keys(journal).sort().slice(-AUTOSAVE_JOURNAL_MAX);
        const bounded = {};
        keys.forEach((k) => { bounded[k] = journal[k]; });
        journal = bounded;
      }
      const streak = readJSON(LS_STREAK, { last: "", count: 0 });
      const snapshot = {
        when: new Date().toISOString(),        // UTC — saved-on-device note uses this
        mode: state.mode,
        best: storage(LS_BEST, 0),
        best_endless: storage(LS_BEST_ENDLESS, 0),
        dives: storage(LS_DIVES, 0),
        challenge_wins: storage(LS_CH_WINS, 0),
        lifetime: readLifetime(),
        level: diverLevel(readLifetime()),
        badges: readJSON(LS_BADGES, []),
        journal,
        streak: {
          last: streak && streak.last ? String(streak.last) : "",
          count: Math.max(0, Number(streak && streak.count) || 0),
        },
        history: readJSON(LS_HISTORY, []).slice(-AUTOSAVE_HISTORY_MAX),
        recent: readJSON(LS_RECENT, []).slice(-RECENT_LIMIT * 2),
        note: "saved automatically on this device when Loki Dive was opened",
      };
      const body = JSON.stringify(snapshot);
      if (body.length > AUTOSAVE_BYTES_MAX) return false; // bounded; something's off upstream — skip writing
      window.localStorage.setItem(LS_AUTOSAVE, body);
      return true;
    } catch { /* storage refused (private mode, disk full) — the game still plays */ return false; }
  }

  function readAutosave() {
    try {
      const raw = JSON.parse(window.localStorage.getItem(LS_AUTOSAVE) || "null");
      return raw && typeof raw === "object" && raw.when && raw.note ? raw : null;
    } catch { return null; }
  }

  function exportData() {
    /* Good-citizen export: shows the exact snapshot this browser keeps. */
    const snap = readAutosave();
    return snap ? { saved_locally_on_this_device: true, snapshot: snap } : { saved_locally_on_this_device: false, snapshot: null };
  }

  /* ---------- tiny synth blips (no assets, no network; a toggle lives in the tools row) ---------- */
  let audioCtx = null;
  function soundOn() {
    try { return Number(storage(LS_SOUND, 1)) !== 0; } catch { return true; } // default: sound leads the dive
  }
  function playTone(freq, ms, type, vol) {
    if (!soundOn()) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      if (!audioCtx) return;
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = type || "sine";
      osc.frequency.value = freq;
      const started = audioCtx.currentTime;
      gain.gain.setValueAtTime(vol || 0.04, started);
      gain.gain.exponentialRampToValueAtTime(0.0001, started + ms / 1000); // quick release, no click
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(started);
      osc.stop(started + ms / 1000);
    } catch { /* audio blocked — the dive rolls on silently */ }
  }
  function playFind() {
    playTone(660, 0.14);
    window.setTimeout(() => playTone(880, 0.16), 90);
  }
  function playMiss() { playTone(170, 0.22, "triangle", 0.05); }
  function playPing() { playTone(1040, 0.09, "sine", 0.05); }
  function playEnd() {
    playTone(494, 0.16);
    window.setTimeout(() => playTone(659, 0.22), 130);
    window.setTimeout(() => playTone(784, 0.3), 280);
  }
  function toggleSound() {
    const next = soundOn() ? 0 : 1;
    saveStorage(LS_SOUND, next);
    if (els["dive-sound-btn"]) {
      els["dive-sound-btn"].setAttribute("aria-pressed", String(next === 1));
      els["dive-sound-btn"].textContent = next === 1 ? "Sound on" : "Sound off";
    }
    if (next) playTone(660, 0.1); // audible confirmation the toggle took
  }
  function bumpScore() {
    const node = els["dive-score"];
    if (!node) return;
    node.classList.remove("dive-bump");
    void node.offsetWidth; // restart the animation on consecutive finds
    node.classList.add("dive-bump");
    window.setTimeout(() => { node.classList.remove("dive-bump"); }, 340);
  }
  function readRecent() {
    try {
      const raw = JSON.parse(window.localStorage.getItem(LS_RECENT) || "[]");
      return Array.isArray(raw) ? raw.filter((v) => Number.isInteger(v)) : [];
    } catch { return []; }
  }
  function pushRecent(indexes) {
    try {
      const recent = indexes.slice(-RECENT_LIMIT * 2);
      window.localStorage.setItem(LS_RECENT, JSON.stringify(recent));
    } catch { /* storage unavailable — freshness simply restarts */ }
  }
  function shuffle(list) {
    const out = list.slice();
    for (let i = out.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }
  function freshOrder() {
    const all = bank.prompts.map((_, i) => i);
    const recent = readRecent();
    const fresh = all.filter((i) => !recent.includes(i));
    const pool = fresh.length >= ROUNDS_PER_DIVE ? fresh : all;
    const order = shuffle(pool);
    return order.slice(0, ROUNDS_PER_DIVE);
  }
  function tierClass(i) { return "dive-tier dive-tier-" + i; }

  /* ---------- answer index ---------- */
  function buildIndex(prompt) {
    const map = new Map();
    prompt.a.forEach(([answer, tier]) => {
      const key = normalize(answer);
      if (key && !map.has(key)) map.set(key, { tier, answer });
    });
    return map;
  }

  /* ---------- rendering ---------- */
  function show(screen) {
    ["dive-start", "dive-play", "dive-end"].forEach((id) => {
      const node = els[id];
      if (node) node.hidden = screen !== id;
    });
  }
  function renderLegend() {
    const host = els["dive-legend"];
    if (!host) return;
    host.innerHTML = bank.tiers.map((t, i) => (
      `<span class="${tierClass(i)}" title="${esc(t.note)}">${esc(t.name)} · ${t.points}</span>`
    )).join("");
  }
  function renderDepth() {
    const depth = totalPoints() * POINTS_PER_METRE;
    const pct = Math.max(0, Math.min(100, (depth / METER_MAX) * 100));
    if (els["dive-depth-num"]) els["dive-depth-num"].textContent = fmtM(depth);
    if (els["dive-depthbar"]) els["dive-depthbar"].style.width = pct + "%";
    if (els["dive-score"]) els["dive-score"].textContent = totalPoints() + " pts";
    if (els["dive-combo"]) els["dive-combo"].textContent = state.streak >= HOT_STREAK ? "Streak ×" + state.streak + " · +5 per find" : "Streak " + state.streak + " / 3";
    if (els["dive-progress"]) {
      els["dive-progress"].innerHTML = Array.from({ length: ROUNDS_PER_DIVE }, (_, i) => {
        const row = state.rounds[i];
        const label = row ? (row.tier === null ? "missed" : "found") : i === state.round - 1 ? "current" : "upcoming";
        return `<span class="dive-step ${label}" aria-label="Round ${i + 1}: ${label}">${row ? (row.tier === null ? "−" : "✓") : i + 1}</span>`;
      }).join("");
    }
    renderSky();
  }
  function totalPoints() { return state.points + state.bonus + state.streakBonus; }
  function renderBest() {
    const endless = state.mode === "endless";
    const shown = endless ? state.bestEndless : state.best;
    const label = endless ? "Endless best" : "Best";
    if (els["dive-best"]) els["dive-best"].textContent = shown ? label + " " + fmtM(shown * POINTS_PER_METRE) : (endless ? "No endless dive yet" : "No dive yet");
    if (els["dive-dives"]) els["dive-dives"].textContent = state.dives ? state.dives + (state.dives === 1 ? " dive" : " dives") : "Fresh waters";
  }

  /* ---------- game flow ---------- */
  function startRun() {
    state.manualPaused = false;
    els["dive-overlay"].hidden = true;
    els["dive-pause"].textContent = "Pause";
    els["dive-pause"].setAttribute("aria-pressed", "false");
    state.cursor = 0;
    state.round = 0;
    state.points = 0;
    state.bonus = 0;
    state.fixed = 0;
    state.streak = 0;
    state.streakBonus = 0;
    state.rounds = [];
    state.misses = 0;
    state.maxStreak = 0;
    state.dailyAnswers = []; // one raw answer per position, for server verification
    state.dailyDate = "";
    state.surfaced = false;
    state.sonarUsed = false;
    state.roundMs = ROUND_MS;
    if (els["dive-surface-btn"]) els["dive-surface-btn"].hidden = state.mode !== "endless";
    if (els["dive-sonar-btn"]) els["dive-sonar-btn"].disabled = false; // one fresh ping per dive
    if (state.mode === "daily") { startDailyRun(); return; } // order comes from the server; fetch first
    state.order = freshOrder();
    beginRun();
  }
  function startDailyRun() {
    /* Daily mode: one shared run per day, prompts issued by the server so a
     * run can later be replayed and verified. No server, no daily dive —
     * the honest message says so and the start screen stays put. */
    if (typeof window.fetch !== "function") { dailyOffline(); return; }
    window.fetch("/api/dive/challenge/order", { method: "GET" }).then((res) => {
      if (!res.ok) throw new Error("daily order unavailable");
      return res.json();
    }).then((data) => {
      if (!data || !Array.isArray(data.order) || data.order.length !== ROUNDS_PER_DIVE) throw new Error("bad order");
      state.order = data.order.slice(0, ROUNDS_PER_DIVE);
      state.dailyDate = data.date || "";
      beginRun();
    }).catch(dailyOffline);
  }
  function dailyOffline() {
    if (els["dive-status-note"]) els["dive-status-note"].textContent =
      "The shared daily order couldn't load right now — that needs a connection to the server. Classic and Endless still dive offline.";
    state.mode = "classic";
    pickMode("classic");
  }
  function beginRun() {
    state.dives += 1;
    saveStorage(LS_DIVES, state.dives);
    renderBest();
    refreshSky();
    renderSky();
    show("dive-play");
    nextRound();
    els["dive-play"].scrollIntoView({ block: "start" });
  }
  function moreOrder() {
    const all = bank.prompts.map((_, i) => i);
    const recent = readRecent();
    const fresh = all.filter((i) => !recent.includes(i));
    return shuffle(fresh.length ? fresh : all); // same honesty as freshOrder: stale prompts only when the pool runs low
  }
  function nextRound() {
    if (state.mode === "endless") {
      if (state.misses >= MISS_LIMIT) { endRun(); return; }
      if (state.cursor >= state.order.length) state.order = state.order.concat(moreOrder()); // endless waters turn over
    } else if (state.round >= ROUNDS_PER_DIVE || state.cursor >= state.order.length) { endRun(); return; }
    const promptIdx = state.order[state.cursor];
    pushRecent(readRecent().concat(promptIdx));
    state.current = { prompt: bank.prompts[promptIdx], index: buildIndex(bank.prompts[promptIdx]) };
    state.cursor += 1;
    state.round += 1;
    state.accepted = false;
    els["dive-next"].hidden = true;
    els["dive-answer"].disabled = false;
    els["dive-submit"].disabled = false;
    els["dive-skip"].disabled = false;
    els["dive-pause"].disabled = false;
    els["dive-examples"].hidden = true;
    hideReportButton();
    if (els["dive-progress"]) els["dive-progress"].hidden = state.mode === "endless"; // the fixed 7-dot ladder reads classic only
    state.roundMs = state.mode === "endless"
      ? Math.max(ROUND_MS_FLOOR, ROUND_MS - (state.round - 1) * ENDLESS_TIGHTEN_MS)
      : ROUND_MS;
    state.tLeft = state.roundMs;
    state.deadline = performance.now() + state.roundMs;
    els["dive-clock"].textContent = Math.round(state.roundMs / 1000) + "s";
    els["dive-timer"].style.width = "100%";
    els["dive-timer"].classList.remove("dive-low");

    const p = state.current.prompt;
    if (els["dive-round"]) els["dive-round"].textContent = state.mode === "endless"
      ? "Endless · round " + state.round + " · pressure " + state.misses + "/" + MISS_LIMIT
      : "Round " + state.round + " of " + ROUNDS_PER_DIVE;
    els["dive-prompt"].textContent = p.q;
    if (els["dive-rules"]) els["dive-rules"].textContent = p.rules || "";
    if (els["dive-answer"]) els["dive-answer"].value = "";
    feedback("", "");
    if (state.mode === "endless" && state.round > 1 && state.round % 5 === 0) {
      feedback("Round " + state.round + " — past the crowd. The trench lights up.", "info");
    }
    show("dive-play");
    renderDepth();
    if (state.visible) {
      try { els["dive-answer"].focus({ preventScroll: true }); } catch { /* older engines */ }
    }
    state.phase = "round";
    state.running = true;
    if (!state.rafId) loop(performance.now());
  }
  function feedback(text, cls) {
    const node = els["dive-feedback"];
    if (!node) return;
    node.hidden = !text;
    node.textContent = text || "";
    node.className = "dive-feedback" + (cls ? " " + cls : "");
  }
  const MISS_LINES = [
    "Not in this answer bank. Try another — the clock is still running.",
    "The bank doesn't know that one. Different angle?",
    "No match — the list stayed quiet. Something rarer, maybe.",
    "Not this time. The rarer names live further out.",
    "Nothing folded into that. Spin the idea again."
  ];
  function submit(ev) {
    if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
    if (state.manualPaused || !state.visible) return;
    if (state.phase === "between" && state.accepted) {
      // impatient divers can press Enter to surf to the next round immediately
      nextRound();
      return;
    }
    if (state.phase !== "round" || state.accepted) return;
    if (performance.now() >= state.deadline) { timeUp(); return; }
    const raw = els["dive-answer"] ? els["dive-answer"].value : "";
    const key = normalize(raw);
    if (!key) {
      feedback("Type one answer first — the clock is kind enough.", "warn");
      return;
    }
    if (state.mode === "daily") state.dailyAnswers[state.round - 1] = raw; // kept for server replay
    const match = findAnswer(state.current.index, raw);
    if (match) {
      state.accepted = true;
      state.phase = "between";
      const tier = bank.tiers[match.hit.tier];
      const pts = tier.points;
      state.points += pts;
      state.streak += 1;
      state.maxStreak = Math.max(state.maxStreak, state.streak);
      let combo = 0;
      if (state.streak >= HOT_STREAK) {
        combo = COMBO_BONUS;
        state.streakBonus += combo;
      }
      const shown = match.fixed ? `${match.hit.answer} (spelling forgiven)` : match.hit.answer;
      if (match.fixed) state.fixed += 1;
      state.rounds.push({ q: state.current.prompt.q, tier: match.hit.tier, points: pts + combo, answer: shown, fixed: match.fixed });
      playFind();
      bumpScore();
      if (state.streak === 5) awardBadge("streak-flame"); // paid the moment the fifth land hits — no waiting
      feedback("✓ " + shown + " — " + tier.name + "! +" + pts + " points · " + fmtM(pts * POINTS_PER_METRE)
        + (combo ? " 🔥 streak ×" + state.streak + " (+" + combo + ")" : ""), "good");
      renderDepth();
      finishRound(false);
    } else {
      const deepest = state.current.prompt.a.reduce((mx, a) => Math.max(mx, a[1]), 0);
      const shelf = bank.tiers[deepest];
      const line = MISS_LINES[Math.floor(Math.random() * MISS_LINES.length)];
      /* the line teaches the ladder honestly: the deepest shelf's real value from the bank */
      feedback(line + " The deepest shelf here pays " + shelf.points + " pts (" + shelf.name + ").", "warn");
      state.lastMissRaw = raw; // kept so "my answer should count" knows what was typed
      showReportButton();
      playMiss();
      if (els["dive-answer"]) { els["dive-answer"].select(); }
    }
  }
  function runSonar() {
    if (state.phase !== "round" || state.accepted || state.sonarUsed) return;
    const ranked = state.current.prompt.a.slice().sort((x, y) => y[1] - x[1]);
    const deepest = ranked[0];
    if (!deepest) return;
    state.sonarUsed = true;
    if (els["dive-sonar-btn"]) els["dive-sonar-btn"].disabled = true;
    const words = deepest[0].trim().split(/\s+/).length;
    const letters = deepest[0].replace(/\s/g, "").length;
    const letter = deepest[0].charAt(0).toUpperCase(); // shape only — the sonar never names the answer
    playPing();
    feedback("Sonar: the deepest find here is " + words + " word" + (words === 1 ? "" : "s")
      + " · " + letters + " letters · starts with \"" + letter + "\". One ping per dive.", "info");
  }
  function skipRound() {
    if (state.phase !== "round" || state.accepted || state.manualPaused || !state.visible) return;
    state.accepted = true;
    state.running = false;
    state.streak = 0;
    state.phase = "between";
    state.rounds.push({ q: state.current.prompt.q, tier: null, points: 0, answer: "", fixed: false });
    if (state.mode === "daily") state.dailyAnswers[state.round - 1] = ""; // a skip is exactly that: no answer
    if (state.mode === "endless") state.misses += 1;
    playMiss();
    feedback("Round skipped. Discover a few answers below, then dive again.", "warn");
    finishRound(true);
  }
  function timeUp() {
    if (state.phase !== "round") return;
    state.accepted = true;
    state.running = false;
    state.streak = 0;
    state.phase = "between";
    state.rounds.push({ q: state.current.prompt.q, tier: null, points: 0, answer: "", fixed: false });
    if (state.mode === "daily") { if (state.dailyAnswers[state.round - 1] === undefined) state.dailyAnswers[state.round - 1] = ""; }
    if (state.mode === "endless") state.misses += 1;
    feedback(state.mode === "endless" && state.misses >= MISS_LIMIT
      ? "Time's up — pressure " + state.misses + "/" + MISS_LIMIT + " ends the endless dive."
      : "Time's up. Here are a few answers to take into your next dive.", "warn");
    playMiss();
    finishRound(true);
  }
  function finishRound(showExamples) {
    state.running = false;
    els["dive-answer"].disabled = true;
    els["dive-submit"].disabled = true;
    els["dive-skip"].disabled = true;
    els["dive-pause"].disabled = true;
    els["dive-next"].hidden = false;
    els["dive-next"].textContent = state.mode === "endless" && state.misses >= MISS_LIMIT
      ? "See the dive results →"
      : state.mode === "endless" ? "Next round →"
        : state.round === ROUNDS_PER_DIVE ? "See dive results →" : "Next round →";
    if (showExamples) {
      const samples = [0, 3, 5].map(t => state.current.prompt.a.find(a => a[1] === t)).filter(Boolean);
      els["dive-examples"].textContent = "Bank examples: " + samples.map(a => a[0] + " · " + bank.tiers[a[1]].name).join(" / ");
      els["dive-examples"].hidden = false;
    }
    renderDepth();
    els["dive-next"].focus({ preventScroll: true });
  }
  function togglePause() {
    if (state.phase !== "round") return;
    const now = performance.now();
    if (!state.manualPaused && now >= state.deadline) { timeUp(); return; }
    if (!state.manualPaused) state.tLeft = Math.max(0, state.deadline - now);
    state.manualPaused = !state.manualPaused;
    state.deadline = now + state.tLeft;
    els["dive-pause"].textContent = state.manualPaused ? "Resume" : "Pause";
    els["dive-pause"].setAttribute("aria-pressed", String(state.manualPaused));
    els["dive-overlay"].textContent = "Paused · your remaining time is saved. Press Resume when ready.";
    els["dive-overlay"].hidden = !state.manualPaused;
    els["dive-answer"].disabled = state.manualPaused;
    els["dive-submit"].disabled = state.manualPaused;
    els["dive-skip"].disabled = state.manualPaused;
    if (!state.manualPaused) els["dive-answer"].focus({ preventScroll: true });
  }
  function endRun() {
    if (state.rafId) { window.cancelAnimationFrame(state.rafId); state.rafId = 0; }
    state.phase = "done";
    state.running = false;
    playEnd();
    const foundAll = state.mode !== "endless" && state.rounds.length === ROUNDS_PER_DIVE && state.rounds.every((r) => r.tier !== null);
    if (foundAll && state.points > 0) {
      state.bonus = CLEAN_SWEEP_BONUS;
      if (els["dive-end-extra"]) {
        els["dive-end-extra"].textContent = "🧹 Clean sweep — every round found: +" + CLEAN_SWEEP_BONUS + " bonus points.";
      }
    } else if (els["dive-end-extra"]) {
      els["dive-end-extra"].textContent = state.mode === "endless"
        ? "Endless waters — the dive ended at round " + state.round
          + (state.surfaced ? " (surfaced early, answer pending)." : " under pressure " + state.misses + "/" + MISS_LIMIT + ".")
        : "";
    }
    const depth = totalPoints() * POINTS_PER_METRE;
    const tally = {};
    state.rounds.forEach((r) => {
      if (r.tier !== null) tally[r.tier] = (tally[r.tier] || 0) + 1;
    });
    let rarestTier = -1;
    state.rounds.forEach((r) => { if (r.tier !== null && r.tier > rarestTier) rarestTier = r.tier; });
    const rarestLine = rarestTier >= 0
      ? "Deepest find: " + (state.rounds.filter((r) => r.tier === rarestTier)[0].answer || "—")
        + " (" + bank.tiers[rarestTier].name + ")."
      : "";
    const tallyLine = Object.keys(tally).map((t) => bank.tiers[t].name + " ×" + tally[t]).join(" · ");
    const spellingLine = state.fixed
      ? " The engine forgave " + state.fixed + (state.fixed === 1 ? " typo" : " typos") + " this dive."
      : "";
    const streakLine = state.streakBonus
      ? " Nested combo: a streak of finds paid +" + state.streakBonus + " extra."
      : "";
    if (els["dive-end-extra"] && rarestLine) {
      const extra = els["dive-end-extra"];
      extra.textContent = (extra.textContent ? extra.textContent + " " : "") + rarestLine
        + (tallyLine ? " Tally: " + tallyLine + "." : "") + spellingLine + streakLine;
    }
    const endless = state.mode === "endless";
    const bestKey = endless ? LS_BEST_ENDLESS : LS_BEST;
    const prevBest = endless ? state.bestEndless : state.best;
    const newBest = totalPoints() > prevBest;
    if (newBest) {
      if (endless) state.bestEndless = totalPoints();
      else state.best = totalPoints();
      saveStorage(bestKey, totalPoints());
      renderBest();
    }
    const rows = state.rounds.map((r, i) => {
      const tier = r.tier === null ? null : bank.tiers[r.tier];
      return (`<div class="dive-result-row${tier ? "" : " dive-result-miss"}">`
        + `<span class="dive-result-n">${i + 1}</span>`
        + `<span class="dive-result-q">${esc(r.q)}</span>`
        + `<span class="dive-result-a">${esc(r.answer || "—")}</span>`
        + (tier
          ? `<span class="${tierClass(r.tier)}">${esc(tier.name)} +${r.points}</span>`
          : `<span class="dive-tier dive-tier-miss">missed · +0</span>`)
        + `</div>`);
    }).join("");
    if (els["dive-end-depth"]) els["dive-end-depth"].textContent = fmtM(depth);
    if (els["dive-end-points"]) els["dive-end-points"].textContent = totalPoints() + " points";
    if (els["dive-end-best"]) {
      const bestLine = newBest
        ? "New personal best — a full " + fmtM((totalPoints() - prevBest) * POINTS_PER_METRE) + " deeper than before!"
        : "Personal best: " + fmtM((endless ? state.bestEndless : state.best) * POINTS_PER_METRE);
      els["dive-end-best"].textContent = endless ? bestLine + " · the shared board ranks classic dives only." : bestLine;
    }
    const verdict = depth >= 6500 ? "Abyssal. You think in trenches."
      : depth >= 4800 ? "Strong dive — well past the shelves."
        : depth >= 3000 ? "Solid mid-water. Worth another drop."
          : depth >= 1400 ? "Shore-ish. The crowd kept you floating."
            : "Surface swimming — try thinking like nobody else.";
    if (els["dive-end-verdict"]) els["dive-end-verdict"].textContent = endless ? verdict + " · surfaced from endless waters." : verdict;
    if (els["dive-end-rows"]) els["dive-end-rows"].innerHTML = rows;
    try {
      const hist = JSON.parse(localStorage.getItem(LS_HISTORY) || "[]");
      hist.push({ p: totalPoints(), t: Date.now() });
      localStorage.setItem(LS_HISTORY, JSON.stringify(hist.slice(-HISTORY_LIMIT)));
    } catch { /* storage blocked — the trend line simply stays empty */ }
    renderDepth();
    show("dive-end");
    renderHistory();
    renderSpark();
    if (
      state.mode === "daily"
      && typeof window.fetch === "function"
      && state.order.length === ROUNDS_PER_DIVE
    ) {
      verifyDailyRun(); // server replay decides the verified card; the end card shows regardless
    } else if (els["dive-end-verified"]) {
      els["dive-end-verified"].hidden = true;
      els["dive-end-verified"].textContent = "";
    }
    if (state.mode !== "endless" && window.LokiDiveBoard && typeof window.LokiDiveBoard.diveEnded === "function") {
      window.LokiDiveBoard.diveEnded(totalPoints());
    }
    // motivation meta: streak, badges — all earned from this browser's own facts
    bumpStreak();
    state.rounds.forEach((r) => {
      if (r.tier >= 3) awardBadge("rare-hunter");
      if (r.tier >= 4) awardBadge("deep-cut");
      if (r.tier >= 5) awardBadge("zillion");
    });
    if (state.streak >= 5 || state.maxStreak >= 5) awardBadge("streak-flame"); // belt-braces: best streak this dive counts too
    if (endless && state.rounds.length >= 15) awardBadge("survivor"); // endured the tightening waters
    recordJournal();
    syncDerivedBadges(depth);
    const banked = bankLifetime(totalPoints()); // level ladder banks this run too
    if (els["dive-end-extra"] && banked) {
      const extra = els["dive-end-extra"];
      extra.textContent = extra.textContent
        + ` Depth level ${diverLevel(banked)} — next at ${(diverLevel(banked)) * LEVEL_STEP + LEVEL_STEP} lifetime pts.`;
    }
    renderLevel();
    autosaveSnapshot(); // the run's outcomes refresh the on-device snapshot immediately
    els["dive-again-btn"].focus({ preventScroll: true });
    if (!challenge.done && totalPoints() >= challenge.target) {
      challenge.done = true;
      try { localStorage.setItem(LS_CHALLENGE, JSON.stringify({ d: dayKey(), o: totalPoints() })); } catch { /* ignore */ }
      try {
        const wins = Math.min(100000, (parseInt(localStorage.getItem(LS_CH_WINS) || "0", 10) || 0) + 1);
        localStorage.setItem(LS_CH_WINS, String(wins));
        if (wins >= 5) awardBadge("devotee");
      } catch { /* wins counter is decorative only */ }
      renderChallenge();
    }
    if (els["dive-copy"]) els["dive-copy"].textContent = "Copy result";
  }
  /* ---------- daily verification + verified publish (server replays the run) ---------- */
  function dailyPayload() {
    return {
      date: state.dailyDate || undefined,
      rounds: state.order.map((idx, pos) => ({ i: idx, a: state.dailyAnswers[pos] || "" })),
    };
  }
  function verifyDailyRun() {
    const card = els["dive-end-verified"];
    if (!card) return;
    card.hidden = false;
    card.textContent = "Checking this daily run against the shared order…";
    if (els["dive-publish-daily"]) els["dive-publish-daily"].hidden = true;
    window.fetch("/api/dive/challenge/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dailyPayload()),
    }).then((res) => {
      if (!res.ok) return res.json().then((b) => { throw new Error(b.detail || "not verifiable"); }, () => { throw new Error("not verifiable"); });
      return res.json();
    }).then((v) => {
      if (!v || !v.verified) throw new Error("not verifiable");
      state.verified = {
        date: v.date, total: v.total_points, found: v.found_count,
        base: v.base_points, streak: v.streak_bonus, sweep: v.clean_sweep,
      };
      card.textContent = "✅ Verified by the server — replayed against the same bank: "
        + v.total_points + " pts · " + v.found_count + "/7 found"
        + (v.clean_sweep ? " · clean sweep" : "") + (v.streak_bonus ? " · streak combo +" + v.streak_bonus : "");
      if (els["dive-publish-daily"]) els["dive-publish-daily"].hidden = v.total_points <= 0;
    }).catch(() => {
      state.verified = null;
      card.textContent = "Daily run not verified: the server couldn't replay this run against today's shared order, so it can't go to the board as verified.";
      if (els["dive-publish-daily"]) els["dive-publish-daily"].hidden = true;
    });
  }
  function publishVerified(ev) {
    if (ev) ev.preventDefault();
    const btn = els["dive-publish-daily"];
    if (btn) btn.disabled = true;
    window.fetch("/api/dive/challenge/publish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nickname: (els["dive-board-name"] && els["dive-board-name"].value) || "", date: state.dailyDate, rounds: dailyPayload().rounds }),
    }).then((res) => {
      if (res.status === 429) throw new Error("One board publish per 20 seconds — give it a breath.");
      if (!res.ok) return res.json().then((b) => { throw new Error(b.detail || "publish refused"); }, () => { throw new Error("publish refused"); });
      return res.json();
    }).then(() => {
      awardBadge("broadcaster");
      if (card2()) card2().textContent = "✅ Published to the board with the verified mark.";
    }).catch((err) => {
      if (card2()) card2().textContent = "Publish refused: " + (err.message || "try again shortly.");
    }).finally(() => { if (btn) btn.disabled = false; });
    function card2() { return document.getElementById("dive-publish-note"); }
  }
  /* ---------- miss reports ("my answer should count") ---------- */
  const LS_REPORTS = "loki_dive_reports"; // queued suggestions, this browser until sent
  const REPORT_LIMIT = 200;
  function readReports() {
    try {
      const raw = JSON.parse(window.localStorage.getItem(LS_REPORTS) || "[]");
      return Array.isArray(raw) ? raw : [];
    } catch { return []; }
  }
  function queueReport(promptText, rawAnswer) {
    try {
      const reports = readReports();
      reports.push({ q: promptText, a: rawAnswer, t: new Date().toISOString() });
      window.localStorage.setItem(LS_REPORTS, JSON.stringify(reports.slice(-REPORT_LIMIT)));
    } catch { /* storage refused — the report simply stays unlogged */ }
  }
  function showReportButton(fontSizeUnused) {
    const btn = els["dive-report-btn"];
    if (!btn) return;
    btn.hidden = false;
    btn.textContent = "My answer should count";
  }
  function hideReportButton() {
    const btn = els["dive-report-btn"];
    if (btn) btn.hidden = true;
  }
  function onReportClick() {
    const raw = state.lastMissRaw || "";
    const promptText = state.current && state.current.prompt ? state.current.prompt.q : "";
    if (!raw || !promptText) return;
    queueReport(promptText, raw);
    hideReportButton();
    feedback("Logged on this device (" + readReports().length + " queued): stays in your browser unless you choose to send it. Thanks for the tip.", "info");
  }
  function copyResult(ev) {
    if (ev) ev.preventDefault();
    const depth = totalPoints() * POINTS_PER_METRE;
    const lines = state.rounds.map((r, i) => {
      const label = r.tier === null ? "missed" : bank.tiers[r.tier].name;
      return (i + 1) + ". " + r.q + " — " + (r.answer || "—") + " (" + label + ", +" + r.points + ")";
    });
    const bonusLine = state.bonus ? "\nClean sweep bonus: +" + state.bonus : "";
    const comboLine = state.streakBonus ? "\nStreak combo bonus: +" + state.streakBonus : "";
    const text = "🪂 Loki Dive — " + fmtM(depth) + " deep (" + totalPoints() + " pts)\n" + lines.join("\n")
      + bonusLine + comboLine + "\nUnlimited rare-answer trivia, only on this site.";
    const ok = () => {
      if (els["dive-copy"]) els["dive-copy"].textContent = "Copied ✓";
    };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok, () => { fallbackCopy(text) ? ok() : null; });
      } else {
        fallbackCopy(text) ? ok() : null;
      }
    } catch { try { fallbackCopy(text) ? ok() : null; } catch { /* clipboard unavailable */ } }
  }
  function fallbackCopy(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      let done = false;
      try { done = document.execCommand("copy"); } catch { done = false; }
      ta.remove();
      return done;
    } catch { return false; }
  }

  /* ---------- loop & pause ---------- */
  function loop(ts) {
    state.rafId = window.requestAnimationFrame(loop);
    if (!state.running) return;
    const sec = state.sectionEl;
    const inView = !document.hidden && !!sec && sec.offsetParent !== null;
    if (inView !== state.visible) updatePause();
    if (!state.visible || state.manualPaused) return;
    state.tLeft = Math.max(0, state.deadline - ts);
    if (els["dive-timer"]) {
      const pct = Math.max(0, Math.min(100, (state.tLeft / (state.roundMs || ROUND_MS)) * 100));
      els["dive-timer"].style.width = pct + "%";
      els["dive-timer"].classList.toggle("dive-low", state.tLeft < 6000);
    }
    if (els["dive-clock"]) els["dive-clock"].textContent = Math.ceil(state.tLeft / 1000) + "s";
    if (state.tLeft <= 0) { state.running = false; timeUp(); }
  }
  function updatePause() {
    const inView = !document.hidden && !!state.sectionEl && state.sectionEl.offsetParent !== null;
    if (inView === state.visible) return;
    const now = performance.now();
    if (!inView && state.running && !state.manualPaused) state.tLeft = Math.max(0, state.deadline - now);
    if (inView) state.deadline = now + state.tLeft;
    state.visible = inView;
  }

  /* ---------- daily challenge ---------- */
  const LS_CHALLENGE = "loki_dive_challenge";
  const CHALLENGE_STEPS = [110, 130, 150, 170, 120, 140, 160]; // target points per weekday (UTC)
  const challenge = { target: 0, done: false };
  function dayKey() { return new Date().toISOString().slice(0, 10); }
  function loadChallenge() {
    challenge.target = CHALLENGE_STEPS[new Date().getUTCDay()];
    let best = 0;
    try {
      const saved = JSON.parse(localStorage.getItem(LS_CHALLENGE) || "null");
      if (saved && saved.d === dayKey()) best = Number(saved.o) || 0;
    } catch { /* unreadable storage — the challenge simply resets */ }
    challenge.done = best >= challenge.target;
  }
  function renderChallenge() {
    const node = els["dive-challenge"];
    if (!node) return;
    node.textContent = challenge.done
      ? "🎯 Challenge done ✓"
      : "🎯 Today: " + challenge.target + "+ pts";
    node.title = challenge.done
      ? "Depth target cleared — a fresh one arrives tomorrow."
      : "Score " + challenge.target + "+ points in one dive today.";
  }

  /* ---------- field journal & dive modes (life collection; answers never leave the browser) ---------- */
  function loadJournal() {
    try {
      const raw = JSON.parse(localStorage.getItem(LS_JOURNAL) || "{}");
      if (raw && typeof raw === "object" && !Array.isArray(raw)) return raw;
    } catch { /* unreadable storage — every water simply reads unchartered */ }
    return {};
  }
  function recordJournal() {
    try {
      const journal = loadJournal();
      state.rounds.forEach((r) => {
        if (r.tier === null) return; // only found rounds are chartered; misses write nothing
        const cur = journal[r.q];
        const prevBest = cur && typeof cur.best === "number" ? cur.best : -1;
        journal[r.q] = { best: Math.max(prevBest, r.tier), times: (cur && cur.times ? cur.times : 0) + 1 };
      });
      localStorage.setItem(LS_JOURNAL, JSON.stringify(journal));
    } catch { /* journal is a keepsake, not a scoreboard — a blocked disk simply dims it */ }
    const journal = loadJournal();
    const met = Object.keys(journal).length;
    if (met >= 30) awardBadge("naturalist");
    if (met >= bank.prompts.length) awardBadge("cartographer");
    renderJournal();
  }
  function renderJournal() {
    const host = els["dive-journal-list"];
    if (!host) return;
    const journal = loadJournal();
    // Met waters show the prompt and the personal tier found there — never the answer words.
    // Unseen waters show nothing but a marker; the bank's answers are nobody's to print.
    host.innerHTML = bank.prompts.map((p) => {
      const entry = journal[p.q];
      if (entry && typeof entry.best === "number" && entry.best >= 0 && bank.tiers[entry.best]) {
        return `<div class="dive-journal-row"><span class="dive-journal-q">${esc(p.q)}</span>`
          + `<span class="${tierClass(entry.best)}">${esc(bank.tiers[entry.best].name)} · ×${entry.times}</span></div>`;
      }
      return `<div class="dive-journal-row dive-journal-unseen"><span class="dive-journal-q">${esc(p.q)}</span>`
        + `<span class="dive-journal-unknown">not chartered yet</span></div>`;
    }).join("");
    if (els["dive-journal-head"]) {
      const met = Object.keys(journal).length;
      els["dive-journal-head"].textContent = "Field journal — " + met + " of " + bank.prompts.length
        + " waters chartered (your finds, this browser only)";
    }
  }
  function pickMode(mode) {
    state.mode = mode === "daily" ? "daily" : mode === "endless" ? "endless" : "classic";
    try { localStorage.setItem(LS_MODE, state.mode); } catch { /* the choice simply resets next visit */ }
    if (els["dive-mode-classic"]) els["dive-mode-classic"].setAttribute("aria-pressed", String(state.mode === "classic"));
    if (els["dive-mode-endless"]) els["dive-mode-endless"].setAttribute("aria-pressed", String(state.mode === "endless"));
    if (els["dive-mode-daily"]) els["dive-mode-daily"].setAttribute("aria-pressed", String(state.mode === "daily"));
    renderBest();
  }

  /* ---------- dive history (start-screen trend) ---------- */
  function loadHistory() {
    try {
      const hist = JSON.parse(localStorage.getItem(LS_HISTORY) || "[]");
      return Array.isArray(hist) ? hist : [];
    } catch { return []; }
  }
  function renderHistory() {
    const node = els["dive-history"];
    if (!node) return;
    const hist = loadHistory();
    if (!hist.length) { node.textContent = ""; return; }
    // Points stay in the browser only; meters are just points × 10 rounded.
    const recent = hist.slice(-5).map((h) => String(Math.round((Number(h.p) || 0) * POINTS_PER_METRE)));
    const best = hist.reduce((mx, h) => Math.max(mx, Number(h.p) || 0), 0);
    let trend = "";
    if (hist.length >= 4) {
      const six = hist.slice(-6);
      const mid = Math.ceil(six.length / 2);
      const older = six.slice(0, mid).reduce((s, h) => s + (Number(h.p) || 0), 0) / mid;
      const newer = six.slice(mid).reduce((s, h) => s + (Number(h.p) || 0), 0) / (six.length - mid);
      trend = newer > older * 1.05 ? " ↗ trend up" : newer < older * 0.95 ? " ↘ trend down" : " → steady";
    }
    node.textContent = "Recent dives: " + recent.join(" · ") + " m — best " + fmtM(best * POINTS_PER_METRE) + trend;
  }

  /* ---------- badges (earned in this browser, never sent anywhere) ---------- */
  const BADGES = [
    { id: "first-drop",    icon: "🪂", name: "First Drop",      how: "Finish your first dive." },
    { id: "rare-hunter",   icon: "🎣", name: "Rare Hunter",     how: "Land a Rare (60) find or better in one dive." },
    { id: "deep-cut",      icon: "✂️", name: "Deep Cut Club",   how: "Land a Deep Cut (85) answer." },
    { id: "zillion",       icon: "🐆", name: "One in a Zillion", how: "Land a 100-point find. The rarest club." },
    { id: "clean-sweep",   icon: "🧹", name: "Clean Sweep",     how: "Find every round in one dive." },
    { id: "streak-flame",  icon: "🔥", name: "Streak Flame",    how: "Chain five finds without a miss or skip." },
    { id: "abyssal",       icon: "🌊", name: "Abyssal",         how: "Take a single dive past 6,000 m." },
    { id: "regular",       icon: "⚓", name: "Regular",         how: "Finish 25 dives." },
    { id: "devotee",       icon: "📅", name: "Devotee",         how: "Clear 5 daily depth targets." },
    { id: "broadcaster",   icon: "📻", name: "Broadcaster",     how: "Publish your best to the shared board." },
    { id: "survivor",      icon: "🛟", name: "Pressure Swimmer", how: "Endure 15 rounds in one endless dive." },
    { id: "naturalist",    icon: "📖", name: "Field Naturalist", how: "Charter 30 different prompt waters in your journal." },
    { id: "cartographer",  icon: "🗺️", name: "Chief Cartographer", how: "Charter every prompt in the bank." }
  ];
  function readBadges() {
    try {
      const raw = JSON.parse(localStorage.getItem(LS_BADGES) || "[]");
      return Array.isArray(raw) ? raw.filter((v) => typeof v === "string") : [];
    } catch { return []; }
  }
  function saveBadges(ids) {
    try { localStorage.setItem(LS_BADGES, JSON.stringify(ids.slice(0, BADGES.length))); } catch { /* storage refused */ }
  }
  function awardBadge(id) {
    const owned = readBadges();
    if (!BADGES.some((b) => b.id === id) || owned.includes(id)) return false;
    owned.push(id);
    saveBadges(owned);
    renderBadges();
    return true;
  }
  function renderBadges() {
    const host = els["dive-badges"];
    if (!host) return;
    const owned = readBadges();
    host.innerHTML = "<span class=\"dive-badges-title\">Badges — earned in this browser, sent nowhere:</span>"
      + BADGES.map((b) => {
        const won = owned.includes(b.id);
        return `<span class="dive-badge ${won ? "dive-badge-won" : "dive-badge-locked"}" title="${esc(b.how)}">`
          + `${b.icon} ${esc(b.name)}${won ? "" : " · not yet"}</span>`;
      }).join("");
  }
  /* Milestones the counters can prove on their own (a stale badge can't lie). */
  function syncDerivedBadges(depth) {
    if (state.dives >= 1) awardBadge("first-drop");
    if (state.dives >= 25) awardBadge("regular");
    if (depth >= 6000) awardBadge("abyssal");
    renderBadges();
  }

  /* ---------- dive-day streak (browser clock; a skipped day resets) ---------- */
  function loadStreak() {
    try {
      const raw = JSON.parse(localStorage.getItem(LS_STREAK) || "null");
      if (raw && raw.last && raw.count >= 0) return { last: String(raw.last), count: Number(raw.count) || 0 };
    } catch { /* unreadable — the streak simply starts over */ }
    return { last: "", count: 0 };
  }
  function renderStreak() {
    const node = els["dive-streak"];
    if (!node) return;
    const streak = loadStreak();
    if (streak.count < 2) { node.hidden = true; node.textContent = ""; return; } // bragging needs two days
    node.hidden = false;
    node.textContent = "🔥 " + streak.count + "-day streak";
    node.title = "Consecutive days with a finished dive (your browser's clock). Miss a day and it resets.";
  }
  function bumpStreak() {
    const today = dayKey();
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    const streak = loadStreak();
    streak.count = streak.last === today ? streak.count : streak.last === yesterday ? streak.count + 1 : 1;
    streak.last = today;
    try { localStorage.setItem(LS_STREAK, JSON.stringify(streak)); } catch { /* streak lives only today — fine */ }
    renderStreak();
  }

  /* ---------- chase-the-board HUD (info only; nothing auto-submits) ---------- */
  const sky = { top: 0, mine: null, count: 0, live: false };
  function refreshSky() {
    const api = window.LokiDiveBoard;
    if (api && typeof api.skyInfo === "function") {
      try {
        const info = api.skyInfo();
        sky.top = Number(info && info.top) || 0;
        sky.mine = info && typeof info.mine === "number" ? info.mine : null;
        sky.count = Number(info && info.count) || 0;
        sky.live = (info && info.mode === "shared") || (info && info.mode === "server-local") || false;
        return;
      } catch { /* board hiccup — the HUD still shows the personal line */ }
    }
    sky.live = false;
  }
  function renderSky() {
    const node = els["dive-sky"];
    if (!node) return;
    const pts = totalPoints();
    const mine = sky.mine === null ? state.best : Math.max(state.best, sky.mine);
    const bits = [];
    if (sky.live && sky.top > 0) {
      bits.push(`🥇 board best ${fmtM(sky.top * POINTS_PER_METRE)} deep`);
      if (sky.count && sky.count > 1) bits.push(`${sky.count} names on the board`);
    } else if (!sky.live) {
      bits.push("No board to chase — beat your own depth");
    }
    bits.push(`your best ${fmtM(mine * POINTS_PER_METRE)}`);
    if (state.phase === "round" || state.phase === "between") {
      if (mine > 0 && pts > mine) bits.pop();
      if (mine > 0 && pts > mine) bits.push(`↗ past your best at ${fmtM(pts * POINTS_PER_METRE)}!`);
      else if (mine > 0 && pts / mine >= 0.75) bits.push(`rising — ${fmtM(pts * POINTS_PER_METRE)} and climbing`);
    }
    node.textContent = bits.join(" · ");
  }


  /* ---------- end-screen depth sparkline (browser history only) ---------- */
  function renderSpark() {
    const node = els["dive-spark"];
    if (!node) return;
    const hist = loadHistory().slice(-10);
    if (hist.length < 2) { node.hidden = true; node.replaceChildren(); return; } // a line needs two points
    node.hidden = false;
    const points = hist.map((h) => Math.max(0, Number(h.p) || 0));
    const maxPt = Math.max(Math.max(...points), 1);
    const step = 100 / (points.length - 1);
    const yFor = (p) => (100 - (p / maxPt) * 92 - 4).toFixed(1);
    const coords = points.map((p, i) => `${(i * step).toFixed(1)},${yFor(p)}`);
    const dots = points.map((p, i) =>
      `<circle cx="${(i * step).toFixed(1)}" cy="${yFor(p)}" r="2.2"><title>${Math.round(p * POINTS_PER_METRE)} m deep</title></circle>`);
    node.innerHTML =
      '<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">'
        + `<polyline fill="none" stroke="currentColor" stroke-width="1.6" points="${coords.join(" ")}"/>`
        + dots.join("")
      + '</svg>'
      + `<span class="dive-spark-label">Last ${points.length} dives — your browser's history, sent nowhere.</span>`;
  }

  function init() {
    ["dive-start", "dive-play", "dive-end", "dive-legend", "dive-form", "dive-answer", "dive-feedback",
      "dive-timer", "dive-clock", "dive-round", "dive-prompt", "dive-rules", "dive-best", "dive-dives",
      "dive-depth-num", "dive-depthbar", "dive-end-depth", "dive-end-points", "dive-end-best",
      "dive-end-verdict", "dive-end-rows", "dive-end-extra", "dive-copy", "dive-start-btn", "dive-again-btn",
      "dive-skip", "dive-count", "dive-history", "dive-overlay", "dive-pause", "dive-challenge",
      "dive-submit", "dive-next", "dive-examples", "dive-score", "dive-combo", "dive-progress",
      "dive-badges", "dive-streak", "dive-sky", "dive-spark",
      "dive-mode-classic", "dive-mode-endless", "dive-mode-daily", "dive-surface-btn",
      "dive-sonar-btn", "dive-sound-btn", "dive-report-btn", "dive-end-verified", "dive-publish-daily", "dive-level",
      "dive-journal", "dive-journal-head", "dive-journal-list"].forEach((id) => { els[id] = $(id); });
    if (!els["dive-start"] && !els["dive-play"]) return; // section missing — stay silent

    const promptsEl = els["dive-count"];
    if (promptsEl) {
      promptsEl.textContent = bank.prompts.length + " prompts · " + bank.prompts.reduce((sum, p) => sum + p.a.length, 0)
        + " banked answers · spelling forgiven";
    }

    state.best = storage(LS_BEST, 0);
    state.bestEndless = storage(LS_BEST_ENDLESS, 0);
    state.dives = storage(LS_DIVES, 0);
    let savedMode = "classic";
    try {
      const rawMode = localStorage.getItem(LS_MODE);
      if (rawMode === "endless" || rawMode === "daily") savedMode = rawMode; // string stored as string — numeric helpers never see it
    } catch { /* storage blocked — classic is the landing mode */ }
    state.mode = savedMode;
    if (els["dive-mode-classic"]) els["dive-mode-classic"].setAttribute("aria-pressed", String(state.mode === "classic"));
    if (els["dive-mode-endless"]) els["dive-mode-endless"].setAttribute("aria-pressed", String(state.mode === "endless"));
    if (els["dive-mode-daily"]) els["dive-mode-daily"].setAttribute("aria-pressed", String(state.mode === "daily"));
    loadChallenge();
    renderLegend();
    renderBest();
    renderChallenge();
    renderHistory();
    renderBadges();
    renderStreak();
    renderJournal();
    renderDepth();
    renderLevel();
    show("dive-start");
    autosaveSnapshot(); // opening the game saves this browser's own info to this device

    state.visible = document.hidden ? false : true;
    if (els["dive-start-btn"]) els["dive-start-btn"].addEventListener("click", (ev) => { ev.preventDefault(); startRun(); });
    if (els["dive-again-btn"]) els["dive-again-btn"].addEventListener("click", (ev) => { ev.preventDefault(); startRun(); });
    if (els["dive-skip"]) els["dive-skip"].addEventListener("click", skipRound);
    if (els["dive-mode-classic"]) els["dive-mode-classic"].addEventListener("click", () => { pickMode("classic"); });
    if (els["dive-mode-endless"]) els["dive-mode-endless"].addEventListener("click", () => { pickMode("endless"); });
    if (els["dive-mode-daily"]) els["dive-mode-daily"].addEventListener("click", () => { pickMode("daily"); });
    if (els["dive-report-btn"]) els["dive-report-btn"].addEventListener("click", onReportClick);
    if (els["dive-publish-daily"]) els["dive-publish-daily"].addEventListener("click", publishVerified);
    if (els["dive-surface-btn"]) els["dive-surface-btn"].addEventListener("click", () => {
      if (state.mode === "endless" && (state.phase === "round" || state.phase === "between")) {
        if (state.phase === "round") state.surfaced = true; // an unanswered round isn't scored; say so on the end card
        state.accepted = true;
        endRun();
      }
    });
    if (els["dive-sonar-btn"]) els["dive-sonar-btn"].addEventListener("click", runSonar);
    if (els["dive-sound-btn"]) {
      els["dive-sound-btn"].addEventListener("click", toggleSound);
      const on = soundOn();
      els["dive-sound-btn"].setAttribute("aria-pressed", String(on));
      els["dive-sound-btn"].textContent = on ? "Sound on" : "Sound off"; // honest state before the first blip
    }
    if (els["dive-copy"]) els["dive-copy"].addEventListener("click", copyResult);
    if (els["dive-form"]) els["dive-form"].addEventListener("submit", submit);
    els["dive-next"].addEventListener("click", () => { if (state.phase === "between") nextRound(); });
    els["dive-pause"].addEventListener("click", togglePause);
    state.sectionEl = els["dive-start"] ? els["dive-start"].closest(".workspace-view") : null;
    updatePause();
    document.addEventListener("visibilitychange", updatePause);
    window.addEventListener("hashchange", updatePause);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
  // Debugging + verification handle (exposes the pure matcher, not live answers).
  window.LokiDive = { state, normalize, fold, findAnswer, damerauDistance, tick: loop,
    award: (id) => { try { return awardBadge(id); } catch { return false; } },
    badges: () => readBadges(),
    mode: () => state.mode,
    journal: () => loadJournal(),
    exportData,
    autosave: () => autosaveSnapshot(),
    lastSaved: () => readAutosave(),
    refreshSky: () => { try { refreshSky(); renderSky(); } catch { /* HUD never blocks play */ } } };
})();
