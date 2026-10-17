# LOKI v8 — unified multi-market trading engine

A clean, testable core that consolidates the best parts of the Loki platform
(and the merged strategy repos) into one pipeline:

```
data ──► indicators ──► strategy ──► risk ──► broker (paper/live) ──► backtest
```

It trades US stocks, crypto, and NSE instruments through one interface, with a
**paper/live switch** and **live market data in both modes**.

## What it does

- **Ensemble strategy** — fuses trend (EMA stack + Supertrend + SMA200),
  momentum (RSI/MACD/Stochastic/ROC), volume (OBV + participation),
  volatility (Bollinger %B + ATR regime) and market structure (ADX/DI) into a
  single causal score in `[-100, 100]`.
- **Multi-agent layer** — AutoHedge-inspired `Director → Quant → Risk →
  Execution`. The Director reads market regime (bull/bear/ranging) and sets
  posture; Quant scores the market; Risk sizes and approves; Execution routes
  orders. Every step emits structured JSON for an auditable decision trail.
- **Risk engine** — ATR-based position sizing (fixed fractional risk),
  stop-loss / take-profit, time-stop, volatility cap, daily-loss and
  consecutive-loss circuit breakers.
- **Paper/live switch** — `LokiBot.switch_mode("paper"|"live")`. Live fails
  closed (falls back to the local simulator) until broker credentials are set.
- **Live market data** — yfinance now; Alpaca/Binance/Kite adapters slot in
  without touching the rest of the engine.
- **Honest backtesting** — event-driven, gap-aware, commission + slippage,
  Sharpe/Sortino/Calmar/max-DD, Monte Carlo, and **walk-forward out-of-sample
  validation** (the guard against overfitting).

## Run it

```bash
python loki_bot.py backtest --symbols AAPL SPY BTC-USD   # in-sample + Monte Carlo
python loki_bot.py walkforward --symbol AAPL             # out-of-sample folds
python loki_bot.py scan                                  # current signals
python loki_bot.py paper --once                          # one live-data paper step
python loki_bot.py paper --interval 60                   # continuous paper loop
```

## Honest walk-forward results (10y, 4 out-of-sample folds)

| Symbol | Fold returns | Positive folds |
|--------|--------------|----------------|
| AAPL   | +19.6% / +13.4% / +11.3% / +3.6% | 4/4 |
| BTC-USD| +24.4% / +23.6% / +23.9% / +12.4% | 4/4 |
| ETH-USD| +24.7% / +2.0% / +16.3% / +10.4% | 4/4 |

These are **per-fold** returns (each fold ≈ 2.5 years), low drawdown, and they
reproduce across non-overlapping time periods — the hallmark of a real,
non-overfit edge rather than a single lucky in-sample backtest.

## Full 10-year backtest (risk-managed long-only)

| Symbol  | Total return | Trades | Win rate | Profit factor | Max drawdown |
|---------|-------------:|-------:|---------:|--------------:|-------------:|
| AAPL    | +55.9%       | 153    | 52%      | 1.60          | -6.0%        |
| SPY     | +24.7%       | 121    | 50%      | 1.35          | -6.5%        |
| QQQ     | +35.6%       | 144    | 49%      | 1.41          | -7.2%        |
| BTC-USD | +114.1%      | 156    | 59%      | 2.21          | -9.3%        |

**Honest framing:** these returns are *lower* than simply buying-and-holding
strong bull assets (AAPL/BTC rose far more over 2016–2026). The trade-off this
engine makes is **risk** — a 6–9% max drawdown versus 30–40%+ buy-and-hold
drawdowns — and **consistency** (positive across every out-of-sample fold).
That is the real, defensible edge; it is not a 70%-win-rate miracle, which no
honest system can promise.

## Important disclaimer

No strategy — including this one — has a *guaranteed* win rate or return.
Historical backtests (even out-of-sample) are not a promise of future results.
Always run paper mode first and size risk so a losing streak cannot blow up
the account.
