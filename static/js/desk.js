/**
 * The trading desk view: five agents, one pipeline, JSON handoffs.
 *
 * The server (loki/api/trading_desk.py) computes everything from public
 * data — this file renders the trace and, at the very end, offers the
 * approved proposal to the browser-held Alpaca PAPER rail. Keys stay in
 * this browser; orders go only when the user clicks, armed then confirmed;
 * ten desk orders per session is a hard ceiling in code (no persistence —
 * a reload clears the count and everything else).
 */
(function () {
  'use strict';

  const DESK_MAX_ORDERS = 10;
  const ARM_WINDOW_MS = 15000;

  const section = () => document.querySelector('#trading-desk');
  const viewActive = () => !!(section() && !section().hidden);

  let currentRun = null;
  let deskBusy = false;
  let deskArmed = null;
  let armTimer = null;
  let sessionOrders = 0;

  function updateOrderCount() {
    const target = document.querySelector('#desk-count');
    if (target) {
      target.textContent = `Desk orders this session: ${sessionOrders}/${DESK_MAX_ORDERS} — a reload clears the count.`;
    }
  }

  function logLine(text, isError) {
    const target = document.querySelector('#desk-log');
    if (!target) return;
    const row = element('p', String(text), 'desk-log-row');
    if (isError) row.classList.add('error');
    target.prepend(row);
    // The log itself stays in this browser's session only: no saving, no
    // pretending events happened hours ago.
  }

  const STATUS_LABELS = {
    ok: 'answered',
    abstain: 'abstained',
    stand_down: 'stands down',
    hold: 'proposes a hold',
    approved: 'approved',
    veto: 'vetoed',
    no_action: 'nothing to execute',
  };

  function agentCard(row) {
    const name = String(row.agent || 'agent');
    const card = element('article', null, 'desk-agent');
    const head = element('div', null, 'desk-agent-head');
    head.append(
      element('p', name.toUpperCase(), 'eyebrow'),
      element('strong', STATUS_LABELS[String(row.status)] || String(row.status || ''))
    );
    card.append(head);
    const method = row.method || row.reason || row.error || '';
    if (method) card.append(element('p', String(method), 'desk-agent-method'));
    const facts = row.facts ? row.facts : null;
    if (facts) {
      const factsRow = element('p', null, 'desk-facts');
      Object.entries(facts).forEach(([key, value]) => {
        factsRow.append(element('small', `${key.replace(/_/g, ' ')}: ${value == null ? '—' : value}`));
      });
      card.append(factsRow);
    }
    if (Array.isArray(row.top)) {
      const list = element('ul', null, 'desk-headlines');
      row.top.forEach((headline) => {
        list.append(
          element('li', null, null),
        );
        const item = list.lastChild;
        item.append(
          element('strong', `${headline.score >= 0 ? '+' : ''}${headline.score} `),
          element('span', `${headline.title} — ${headline.publisher}`)
        );
      });
      card.append(list);
    }
    if (Array.isArray(row.reasons)) {
      const list = element('ul', null, 'desk-reasons');
      row.reasons.forEach((reason) => list.append(element('li', String(reason))));
      card.append(list);
    }
    if (Array.isArray(row.checks)) {
      const checksList = element('ul', null, 'desk-checks');
      row.checks.forEach((check) => {
        const item = element('li', null, check.passed ? 'passed' : 'failed');
        item.append(
          element('strong', `${check.passed ? '✓' : '✕'} ${check.gate}: `),
          element('span', String(check.detail))
        );
        checksList.append(item);
      });
      card.append(checksList);
    }
    card.append(detailsJSON(row, `Inspect the ${name} agent's full JSON`));
    return card;
  }

  function renderTrace(run) {
    const target = document.querySelector('#desk-pipeline');
    const proposalBar = document.querySelector('#desk-proposal');
    target.replaceChildren();
    (run.trace || []).forEach((row) => target.append(agentCard(row)));
    const strategyRow = (run.trace || []).find((row) => row.agent === 'strategy') || {};
    const proposal = run.proposal || {};
    proposalBar.hidden = false;
    proposalBar.textContent =
      proposal.side && proposal.side !== 'hold'
        ? `Proposal: ${proposal.side.toUpperCase()} ${proposal.qty} ${run.symbol} (score ${proposal.score}) — then the risk manager had its say.`
        : strategyRow.status === 'stand_down'
          ? 'Proposal: none — not one agent had data, so the desk stands down instead of squeezing a guess out of silence.'
          : 'Proposal: hold — the composite sits inside the middle band, and the desk holds its fire rather than force a trade.';
    const approved = !!(run.verdict && run.verdict.approved && proposal.side && proposal.side !== 'hold');
    document.querySelector('#desk-exec-wrap').hidden = !approved;
    currentRun = approved ? run : null;
  }

  async function runDesk() {
    if (deskBusy) return;
    const symbol = String(document.querySelector('#desk-symbol').value || '').trim().toUpperCase();
    if (!symbol) {
      message('#desk-status', 'Type a symbol first — the desk rides on it.', true);
      return;
    }
    deskBusy = true;
    const runButton = document.querySelector('#desk-run');
    runButton.disabled = true;
    document.querySelector('#desk-exec-wrap').hidden = true;
    currentRun = null;
    message('#desk-status', 'Running the pipeline — news → technicals → fundamentals → proposal → risk…');
    try {
      const run = await request('/api/desk/run', { symbol });
      renderTrace(run);
      const verdict = run.verdict || {};
      message('#desk-status', String(verdict.reason || 'The desk answered; no trade was approved.'));
    } catch (error) {
      message('#desk-status', error.message || 'The desk could not complete this run; nothing was invented in its place.', true);
    } finally {
      deskBusy = false;
      runButton.disabled = false;
    }
  }

  function clearArm() {
    deskArmed = null;
    if (armTimer) {
      window.clearTimeout(armTimer);
      armTimer = null;
    }
  }

  async function executeProposal() {
    if (deskBusy || !currentRun) return;
    const alpaca = window.LokiAlpaca || {};
    if (!alpaca.railReady || !alpaca.railReady()) {
      message('#desk-exec-message', 'Arm the rail first in the Alpaca panel — the desk never holds keys of its own.', true);
      return;
    }
    if (sessionOrders >= DESK_MAX_ORDERS) {
      message('#desk-exec-message', `The desk's session ceiling is ${DESK_MAX_ORDERS} orders — the desk stands down until the page reloads.`, true);
      return;
    }
    const proposal = currentRun.proposal || {};
    const symbol = String(currentRun.symbol || '');
    const qty = Number(proposal.qty || 0);
    const side = proposal.side === 'sell' ? 'sell' : 'buy';
    const summary = `${side.toUpperCase()} ${qty} ${symbol} — market, day`;
    if (deskArmed !== summary) {
      deskArmed = summary;
      message('#desk-exec-message', `Review: ${summary}. A real order on your Alpaca PAPER account. Press again within 15 s to send it.`);
      armTimer = window.setTimeout(() => {
        clearArm();
        message('#desk-exec-message', 'The confirmation window closed — nothing was sent.');
      }, ARM_WINDOW_MS);
      return;
    }
    clearArm();
    deskBusy = true;
    message('#desk-exec-message', 'Sending through the paper rail…');
    let saved = null;
    try {
      saved = JSON.parse(window.localStorage.getItem('loki_alpaca_keys_v1') || 'null');
    } catch (error) {
      saved = null;
    }
    if (!saved || !saved.key_id || !saved.secret_key) {
      deskBusy = false;
      message('#desk-exec-message', 'The stored keys vanished — verify the rail in the Alpaca panel again.', true);
      return;
    }
    try {
      const body = {
        key_id: saved.key_id,
        secret_key: saved.secret_key,
        symbol,
        side,
        quantity: qty,
        order_type: 'market',
      };
      const answer = await (alpaca.sendRailOrder ? alpaca.sendRailOrder(body) : request('/api/broker/alpaca/order', body));
      sessionOrders += 1;
      updateOrderCount();
      const status = String(((answer || {}).order || {}).status || 'unknown').toLowerCase();
      message('#desk-exec-message', `Sent to Alpaca paper: ${summary} — Alpaca's status: ${status}.`);
      logLine(`Executed ${summary} — Alpaca status: ${status}.`);
    } catch (error) {
      message('#desk-exec-message', error.message || 'Alpaca did not answer the order; nothing was confirmed.', true);
      logLine(`Order failed on ${symbol}: ${error.message || 'no answer'}`, true);
    } finally {
      deskBusy = false;
    }
  }

  function init() {
    const form = document.querySelector('#desk-form');
    if (!form) return;
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      runDesk();
    });
    const execButton = document.querySelector('#desk-exec');
    if (execButton) execButton.addEventListener('click', executeProposal);
    updateOrderCount();
    document.querySelector('#desk-note').textContent =
      'Agents read public feeds (Yahoo Finance search & chart, Binance Spot) and compute in code; no language model and no order moves from the server. Abstain means the feed was unusable, never a guess.';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Small debug handle for probes: what happened this session, nothing more.
  window.LokiDesk = {
    state: () => ({ busy: deskBusy, armed: deskArmed, sessionOrders, currentSymbol: currentRun ? currentRun.symbol : null }),
  };
})();
