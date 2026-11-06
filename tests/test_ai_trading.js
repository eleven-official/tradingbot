/* Offline regression tests for the actual browser paper runner. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/ai_trading.js'), 'utf8');

function runner(overrides = {}) {
  const saved = new Map([['loki_ai_paper_v1', JSON.stringify({
    cash: 10000, startCash: 10000, symbol: 'SPY', running: true,
    position: null, trades: [], log: [], curve: [], ...overrides,
  })]]);
  let cycle, reply;
  const requests = [];
  vm.runInNewContext(source, {
    document: {readyState: 'complete', getElementById: () => null,
      querySelector: () => null, addEventListener() {}},
    window: {addEventListener() {}}, AbortSignal,
    localStorage: {getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value)},
    setInterval: fn => { cycle = fn; return 1; }, clearInterval() {},
    fetch: async (url, options) => {
      requests.push({url, body: JSON.parse(options.body)});
      return {ok: true, json: async () => reply};
    },
  });
  return {
    async check(price, qty) {
      saved.delete('loki_runner_lease');
      reply = {symbol: overrides.symbol || 'SPY', price, trail: [
        {agent: 'quant', action: 'BUY', stop: 98, target: 104},
        {agent: 'risk', approved: true, qty},
      ]};
      await cycle();
      return JSON.parse(saved.get('loki_ai_paper_v1'));
    }, requests,
  };
}

test('paper entry debits simulated cash and only calls the analysis endpoint', async () => {
  const r = runner();
  const state = await r.check(100, 5);
  assert.ok(Math.abs(state.cash - (10000 - 5 * 100 * 1.0005 * 1.001)) < 1e-8);
  assert.equal(state.position.costModel, '10bps-fee-5bps-slip-v1');
  assert.equal(state.position.qty, 5);
  assert.equal(r.requests.length, 1);
  assert.equal(r.requests[0].url, '/api/fusion/ai/step');
});

test('protective exit credits cash and cannot reopen on the same BUY decision', async () => {
  const r = runner({cash: 9500, position: {symbol: 'SPY', qty: 5, entry: 100, stop: 98, target: 104}});
  const state = await r.check(97, 5);
  const proceeds = 5 * 97 * .9995 * .999;
  assert.ok(Math.abs(state.cash - (9500 + proceeds)) < 1e-8);
  assert.equal(state.position, null);
  assert.equal(state.trades.length, 1);
  assert.ok(Math.abs(state.trades[0].pnl - (proceeds - 500)) < 1e-8);
});

test('invalid approved quantities never allocate fallback cash', async () => {
  for (const qty of [0, -1, null, 'invalid']) {
    const state = await runner().check(100, qty);
    assert.equal(state.cash, 10000);
    assert.equal(state.position, null);
    assert.match(state.log[0].text, /valid quantity/);
  }
});

test('crypto quantities round down to avoid overspending the balance', async () => {
  const state = await runner({symbol: 'BTC-USD', cash: 100}).check(100, 1.0000009);
  assert.ok(state.position.qty < 1);
  assert.ok(state.cash >= 0 && state.cash < .001);
});

test('unchanged quote round trip loses fees and slippage rather than reporting a fake break-even', async () => {
  const r = runner();
  const opened = await r.check(100, 5);
  const closing = runner({cash: opened.cash, position: {...opened.position, target: 100}});
  const closed = await closing.check(100, 5);
  assert.equal(closed.position, null);
  assert.ok(closed.trades[0].pnl < 0);
  assert.ok(Math.abs(closed.cash - 10000 - closed.trades[0].pnl) < 1e-8);
});
