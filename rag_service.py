"""
RAG (Retrieval-Augmented Generation) service for the trading bot.

This module is the *retrieval* half of the bot's decision support: it reads the
bot's own historical trade ledger (``output/trade_log.xlsx``, written by
``reporting.log_trade``) and surfaces relevant statistics to the strategy
selector and the loss analyzer. The "generation" half lives in
``langgraph_agent.py`` and ``agents.py``, which embed the retrieved context in
their Gemini prompts.

Deliberately dependency-light and offline: no embeddings, no vector store, no
network. Historical context is retrieved by exact strategy keys plus a
keyword overlap score between past trade rationales and today's detected
market conditions.

Public API (consumed by trading_bot.py, agents.py, langgraph_agent.py):
    RAGService(config)                          -- constructor
    .trade_log_path                             -- pathlib.Path of the ledger
    ._load_data(path)                           -- DataFrame or None
    .retrieve_context_for_strategy_selection(conditions)   -> str
    .retrieve_context_for_loss_analysis(trade_details)     -> str
    .get_trading_mode(vix_value=0.0)            -> 'AGGRESSIVE' | 'MODERATE'
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Repository root (this file lives at the repo root next to trading_bot.py).
PROJECT_ROOT = Path(__file__).resolve().parent

# Modes returned by get_trading_mode(). trading_bot.py treats 'AGGRESSIVE' as
# the override and everything else as the baseline moderate profile.
MODE_AGGRESSIVE = "AGGRESSIVE"
MODE_MODERATE = "MODERATE"

# Fallback capital base (INR) used for the drawdown-ratio check when the bot's
# starting capital cannot be found anywhere in config. Matches the smallest
# risk tier in config.example.yaml so the ratio is meaningful for paper runs.
_DEFAULT_CAPITAL_BASE = 100_000.0

# Stopwords that would otherwise make the rationale/condition overlap score
# meaningless.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the "
    "this to was were will with not no but if then than so such just over under"
    .split()
)


class RAGService:
    """Local retrieval over the bot's own trade history.

    Constructed once by ``TradingBot`` and shared with the position-management
    agent and the LangGraph agent. All reads are best-effort: a missing or
    unreadable ledger degrades to "no context" rather than raising, because the
    bot must keep trading on day one when no history exists yet.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config or {}
        self.rag_config = self.config.get("rag") or {}
        self.mode_config = self.config.get("mode_switching") or {}

        self.recency_window_days: int = int(self.rag_config.get("recency_window_days", 30))
        self.min_trades_per_strategy: int = int(self.rag_config.get("min_trades_per_strategy", 3))

        self.trade_log_path: Path = PROJECT_ROOT / "output" / "trade_log.xlsx"

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _load_data(self, path: Path | str) -> Optional[pd.DataFrame]:
        """Load the trade ledger into a DataFrame, or None if unavailable.

        Accepts .xlsx (the canonical format written by reporting.py) and .csv.
        Also tries the CWD-relative path, so the bot works whether it is
        launched from the repo root or from elsewhere.
        """
        candidates = [Path(path)]
        if not candidates[0].is_absolute():
            candidates.append(PROJECT_ROOT / candidates[0])
        candidates.append(Path.cwd() / Path(path).name)

        for candidate in candidates:
            try:
                if not candidate.exists() or candidate.stat().st_size == 0:
                    continue
                if candidate.suffix.lower() == ".csv":
                    df = pd.read_csv(candidate)
                else:
                    df = pd.read_excel(candidate)
                if df is None or df.empty or "Timestamp" not in df.columns:
                    continue
                df = df.copy()
                df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
                df = df.dropna(subset=["Timestamp"])
                return df
            except Exception as exc:  # noqa: BLE001 - ledger reads are best-effort
                logger.debug("RAG: could not read %s: %s", candidate, exc)
        return None

    def _recent_trades(self) -> pd.DataFrame:
        """Trades within config.rag.recency_window_days, oldest first."""
        df = self._load_data(self.trade_log_path)
        if df is None or df.empty:
            return pd.DataFrame()
        cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=self.recency_window_days)
        recent = df[df["Timestamp"] >= cutoff].copy()
        return recent.sort_values("Timestamp")

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    @staticmethod
    def _tokenize(text: str) -> set:
        return {
            t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(t) > 2 and t not in _STOPWORDS
        }

    @staticmethod
    def _is_closed_trade(row: pd.Series) -> bool:
        """A closed trade has an exit price and a computed P&L value."""
        try:
            if pd.isna(row.get("ExitPrice")):
                return False
            return row.get("ProfitLoss") is not None and not pd.isna(row.get("ProfitLoss"))
        except Exception:  # noqa: BLE001
            return False

    def _strategy_stats(self, trades: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """Per-strategy aggregates over closed trades in the window."""
        stats: Dict[str, Dict[str, float]] = {}
        if trades is None or trades.empty:
            return stats
        closed = trades[trades.apply(self._is_closed_trade, axis=1)]
        for strategy, grp in closed.groupby(closed["Strategy"].fillna("UNKNOWN")):
            pnl = pd.to_numeric(grp["ProfitLoss"], errors="coerce").fillna(0.0)
            wins = int((pnl > 0).sum())
            total = int(len(grp))
            stats[str(strategy)] = {
                "trades": total,
                "wins": wins,
                "win_rate": (wins / total * 100.0) if total else 0.0,
                "net_pnl": float(pnl.sum()),
                "avg_pnl": float(pnl.mean()) if total else 0.0,
                "best": float(pnl.max()) if total else 0.0,
                "worst": float(pnl.min()) if total else 0.0,
            }
        return stats

    def retrieve_context_for_strategy_selection(
        self, todays_conditions: Optional[Iterable] = None
    ) -> str:
        """Compact per-strategy performance digest for today's selector prompt.

        Only strategies with >= config.rag.min_trades_per_strategy trades in the
        recency window are ranked (see config.example.yaml: this stops the LLM
        anchoring on stale or statistically meaningless data). Also reports
        which past trades share keywords with today's detected market
        conditions, giving the selector a cheap relevance signal.
        """
        trades = self._recent_trades()
        if trades.empty:
            return "No historical trades in the recency window; no strategy context available."

        stats = self._strategy_stats(trades)
        qualified = {
            name: s for name, s in stats.items()
            if s["trades"] >= self.min_trades_per_strategy
        }

        lines = [
            f"Trade history: {len(trades)} trades over the last "
            f"{self.recency_window_days} calendar days."
        ]

        if qualified:
            ranked = sorted(
                qualified.items(),
                key=lambda kv: (kv[1]["win_rate"], kv[1]["net_pnl"]),
                reverse=True,
            )
            lines.append(
                f"Strategies with >= {self.min_trades_per_strategy} trades "
                "(best first; win rate, net P&L):"
            )
            for name, s in ranked:
                lines.append(
                    f"  - {name}: {s['trades']} trades, "
                    f"win rate {s['win_rate']:.0f}%, "
                    f"net P&L {s['net_pnl']:+,.0f}, "
                    f"avg {s['avg_pnl']:+,.0f}/trade"
                )
            lines.append(f"Best qualified strategy by win rate: {ranked[0][0]}.")
        else:
            lines.append(
                f"No strategy has reached the {self.min_trades_per_strategy}-trade "
                "minimum in the window; treat all strategy statistics as "
                "low-confidence."
            )

        # Keyword overlap between today's conditions and past rationales.
        conditions = {str(c) for c in (todays_conditions or set())}
        condition_tokens = self._tokenize(" ".join(conditions))
        if condition_tokens:
            matched: Dict[str, int] = {}
            for _, row in trades.iterrows():
                overlap = condition_tokens & self._tokenize(str(row.get("Rationale") or ""))
                if overlap:
                    strategy = str(row.get("Strategy") or "UNKNOWN")
                    matched[strategy] = matched.get(strategy, 0) + 1
            if matched:
                top = sorted(matched.items(), key=lambda kv: kv[1], reverse=True)[:3]
                pretty = ", ".join(f"{s} ({n} trades)" for s, n in top)
                lines.append(
                    f"Historical trades whose rationale overlaps today's "
                    f"conditions ({', '.join(sorted(conditions))}): {pretty}."
                )
            else:
                lines.append(
                    "No past trades share rationale keywords with today's "
                    f"conditions ({', '.join(sorted(conditions))}); today may be "
                    "an untraded regime - weight the regime table more heavily."
                )

        return "\n".join(lines)

    def retrieve_context_for_loss_analysis(self, trade_details: Dict[str, Any]) -> str:
        """Similar past trades (same strategy and/or symbol) for loss review.

        Returns the most comparable recent losing trades with their outcome
        and recorded rationale, so the analyzer can contrast this loss against
        the historical pattern instead of reasoning from a single data point.
        """
        trades = self._recent_trades()
        if trades.empty:
            return "No historical trades available for comparison."

        strategy = str((trade_details or {}).get("Strategy") or "")
        symbol = str((trade_details or {}).get("Symbol") or "")
        closed = trades[trades.apply(self._is_closed_trade, axis=1)]
        pnl = pd.to_numeric(closed.get("ProfitLoss"), errors="coerce").fillna(0.0)

        similar = pd.Series([True] * len(closed), index=closed.index)
        if strategy:
            similar &= closed["Strategy"].fillna("").str.contains(re.escape(strategy), case=False)
        if symbol:
            # Compare on the underlying root (NIFTY24O1724000CE -> NIFTY).
            root = re.match(r"^([A-Za-z]+)", symbol)
            if root:
                similar &= closed["Symbol"].fillna("").str.upper().str.startswith(
                    root.group(1).upper()
                )

        subset = closed[similar]
        if subset.empty:
            return (
                f"No prior trades found for strategy='{strategy}' symbol='{symbol}' "
                f"in the last {self.recency_window_days} days."
            )

        subset = subset.assign(_pnl=pnl[subset.index])
        losers = subset[subset["_pnl"] < 0].tail(5)
        source = losers if not losers.empty else subset.tail(5)

        lines = [
            f"{len(subset)} comparable past trade(s) in the last "
            f"{self.recency_window_days} days "
            f"(net {subset['_pnl'].sum():+,.0f}, win rate "
            f"{(subset['_pnl'] > 0).mean() * 100:.0f}%). Most recent relevant:"
        ]
        for _, row in source.iterrows():
            lines.append(
                f"  - {row.get('Timestamp'):%Y-%m-%d} {row.get('Symbol')} "
                f"{row.get('TradeType')}: P&L {row.get('ProfitLoss'):+,.0f} "
                f"({row.get('ProfitLoss_Pct', 'n/a')}%) | rationale: "
                f"{str(row.get('Rationale') or 'none')[:200]}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------
    def get_trading_mode(self, vix_value: float = 0.0) -> str:
        """Pick AGGRESSIVE vs MODERATE from recent results and market stress.

        Rules (all from config.mode_switching, see config.example.yaml):
          * mode_switching.enable == false        -> always MODERATE
          * VIX >= moderate_vix_threshold         -> MODERATE (blocks AGGRESSIVE)
          * >= moderate_trigger_losses consecutive losses in the lookback
            window                                 -> MODERATE
          * equity drawdown in the lookback window >= moderate_drawdown
            fraction of the capital base           -> MODERATE
          * >= aggressive_trigger_wins wins in the lookback window
            (and no rule above fired)              -> AGGRESSIVE
          * anything else                          -> MODERATE
        """
        if not self.mode_config.get("enable", True):
            return MODE_MODERATE

        vix = float(vix_value or 0.0)
        vix_threshold = float(self.mode_config.get("moderate_vix_threshold", 18.0))
        if vix > 0 and vix >= vix_threshold:
            logger.info("RAG mode: MODERATE (VIX %.2f >= %.2f)", vix, vix_threshold)
            return MODE_MODERATE

        trades = self._recent_trades()
        lookback_n = int(self.mode_config.get("lookback_trades", 5))
        window = trades.tail(lookback_n)
        if window.empty:
            return MODE_MODERATE

        closed = window[window.apply(self._is_closed_trade, axis=1)]
        if closed.empty:
            return MODE_MODERATE

        pnl = pd.to_numeric(closed["ProfitLoss"], errors="coerce").fillna(0.0).tolist()

        # Consecutive losses measured from the most recent trade backwards.
        consecutive_losses = 0
        for value in reversed(pnl):
            if value < 0:
                consecutive_losses += 1
            else:
                break
        moderate_losses = int(self.mode_config.get("moderate_trigger_losses", 2))
        if consecutive_losses >= moderate_losses:
            logger.info(
                "RAG mode: MODERATE (%d consecutive losses >= %d)",
                consecutive_losses, moderate_losses,
            )
            return MODE_MODERATE

        # Max drawdown of the cumulative P&L curve as a fraction of capital.
        capital_base = float(
            self.config.get("starting_capital")
            or (self.config.get("paper_trading") or {}).get("starting_capital")
            or _DEFAULT_CAPITAL_BASE
        )
        curve = pd.Series(pnl).cumsum()
        drawdown = float((curve.cummax() - curve).max())
        drawdown_frac = drawdown / capital_base if capital_base > 0 else 0.0
        moderate_dd = float(self.mode_config.get("moderate_drawdown", 0.08))
        if drawdown_frac >= moderate_dd:
            logger.info(
                "RAG mode: MODERATE (drawdown %.2f%% >= %.2f%%)",
                drawdown_frac * 100, moderate_dd * 100,
            )
            return MODE_MODERATE

        wins = sum(1 for value in pnl if value > 0)
        aggressive_wins = int(self.mode_config.get("aggressive_trigger_wins", 3))
        if wins >= aggressive_wins:
            logger.info(
                "RAG mode: AGGRESSIVE (%d/%d recent wins, VIX %.2f, drawdown %.2f%%)",
                wins, len(pnl), vix, drawdown_frac * 100,
            )
            return MODE_AGGRESSIVE

        return MODE_MODERATE
