"""Offline, read-only explanations grounded in a supplied terminal snapshot.

The assistant never receives an account, broker, callback, or credentials. Its
only inputs are a question and plain snapshot data; it cannot submit orders.
This is an intent-based assistant, not a language model or market predictor.

Snapshot keys used by the desktop:
    metrics, positions, current_prices, latest_signal, guard, latest_backtest,
    symbol, strategy, data_mode, trading_mode, is_running, as_of.
The aliases prices/signal/risk/validation/data_source are also accepted.
Metrics use percentage points (win_rate=70, max_drawdown_pct=12); guard limits
and signal confidence use fractions (max_drawdown_pct=.12, confidence=.7).
Missing or invalid measurements are reported as unknown, never as zero.
Stateless API clients can supply ``previous_intent`` from the prior reply; only
known topics are accepted, and fresh snapshot data must still be supplied.
"""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import math
import re
from typing import Any, Optional


@dataclass(frozen=True)
class CopilotReply:
    text: str
    intent: str
    evidence: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.intent,
            "evidence": list(self.evidence),
            "suggestions": list(self.suggestions),
        }


def _mapping(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _label(value: Any, fallback: str = "unknown") -> str:
    """Keep untrusted snapshot labels readable and bounded; never execute them."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return fallback
    return " ".join(str(value).split())[:200] or fallback


def _cash(value: Any, prefix: str = "$") -> str:
    number = _number(value)
    return f"{prefix}{number:,.2f}" if number is not None else "unknown"


def _percent(value: Any, fraction: bool = False) -> str:
    number = _number(value)
    if number is None:
        return "unknown"
    return f"{number * 100 if fraction else number:.2f}%"


def _count(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None and number >= 0 and number.is_integer() else None


class LokiCopilot:
    """A bounded local conversation that explains data, without trading authority.

    Reuse one instance for follow-up questions. Each response uses only the
    context supplied on that turn, so old prices and balances are never reused.
    Conversation history contains question/intent pairs, not financial snapshots.
    """

    def __init__(self, history_limit: int = 20):
        self.history = deque(maxlen=max(1, min(int(history_limit), 100)))
        self.last_intent = "help"

    def reset(self) -> None:
        self.history.clear()
        self.last_intent = "help"

    def respond(self, message: str, context: Optional[Mapping] = None) -> CopilotReply:
        question = " ".join(str(message or "").split())[:2000]
        snapshot = _mapping(context)
        intent = self._intent(question)
        handlers = {
            "portfolio": self._portfolio,
            "risk": self._risk,
            "performance": self._performance,
            "strategy": self._strategy,
            "signal": self._signal,
            "backtest": self._backtest,
            "status": self._status,
            "guarantee": self._guarantee,
            "action": self._action,
            "help": self._help,
        }
        if intent == "followup":
            previous = snapshot.get("previous_intent")
            intent = previous if isinstance(previous, str) and previous in handlers else self.last_intent
        body, evidence, suggestions = handlers[intent](snapshot, question)
        origin = self._origin(snapshot)
        text = f"{origin}\n\n{body}"
        if evidence:
            text += "\n\nEvidence: " + "; ".join(evidence) + "."
        reply = CopilotReply(text, intent, tuple(evidence), tuple(suggestions))
        self.history.append({"question": question, "intent": intent})
        self.last_intent = intent
        return reply

    def _intent(self, question: str) -> str:
        q = question.lower()
        if not q:
            return "help"
        if re.search(r"\b(guarantee\w*|gurrenty|certain profit|risk.free|100%|70\s*%)", q):
            return "guarantee"
        if re.search(
            r"\b(place|submit|execute)\b.*\b(order|trade|buy|sell)\b|"
            r"^(?:please\s+)?(?:buy|sell|purchase)\b|"
            r"\b(?:can|could|will|would) you\s+(?:buy|sell|purchase)\b|"
            r"\b(buy|sell|purchase)\s+(?:all|now|\d)|"
            r"\b(start|enable|activate|resume|stop|pause)\b.*\b(trading|pilot|bot|live)\b|"
            r"\b(turn on|switch to|go)\s+live\b|"
            r"\b(disable|remove|reset|increase|change|set)\b.*\b(stop|halt|guard|risk|limit)\b|"
            r"\b(liquidate|close)\b.*\b(all|position|trade)\b",
            q,
        ):
            return "action"
        if q in {"why", "why?", "more", "tell me more", "explain", "explain more",
                 "what does that mean", "what does that mean?", "what about that"}:
            return "followup"
        if re.search(r"\b(backtest|test\w*|validation|validate|out.of.sample|walk.forward|research)\b", q):
            return "backtest"
        if re.search(r"\b(risk|sizing|position.size|drawdown|halt\w*|stop.loss|exposure|concentration|safe\w*)\b", q):
            return "risk"
        if re.search(r"\b(win.rate|profit\w*|performance|pnl|p&l|expectancy|return\w*|losing|losses)\b", q):
            return "performance"
        if re.search(r"\b(portfolio|position\w*|holding\w*|balance|cash|equity|account)\b", q):
            return "portfolio"
        if re.search(r"\b(signal|buy|sell|hold|conviction|confidence|entry|target|price|quote)\b", q):
            return "signal"
        if re.search(r"\b(strateg\w*|momentum|breakout|ensemble|reversion|josh|regime|improve|better)\b", q):
            return "strategy"
        if re.search(r"\b(status|running|mode|live|paper|simulat\w*|connected|happening|overview)\b", q):
            return "status"
        return "help"

    @staticmethod
    def _origin(context: Mapping) -> str:
        source = _label(context.get("data_mode", context.get("data_source")))
        mode = _label(context.get("trading_mode"))
        stamp = _label(context.get("as_of"), "timestamp not supplied")
        origin = f"Snapshot: {source} data | {mode} trading | {stamp}."
        if context.get("data_fresh") is False:
            origin += " Quotes are reported stale or unavailable; snapshot values may be outdated."
        age = _number(context.get("quote_age_seconds"))
        if age is not None and age >= 0:
            origin += f" Reported quote age: {age:.1f} seconds."
        return origin

    @staticmethod
    def _help(context: Mapping, question: str):
        return (
            "I'm Loki's local, read-only assistant. I explain the terminal snapshot, "
            "portfolio, risk limits, strategy signals and backtest evidence. I keep the "
            "topic for follow-up questions such as 'why?'. Ask about a specific topic "
            "to get figures from this snapshot. I have no access to news or external accounts.",
            [],
            ["Show my portfolio", "Explain my risk", "Why this signal?", "Review the backtest"],
        )

    @staticmethod
    def _action(context: Mapping, question: str):
        return (
            "Chat cannot place orders, start trading, reset a halt or change risk limits. "
            "No action was taken. Use the terminal's explicit controls to review those "
            "actions. I can explain the current signal and risk before you decide.",
            [],
            ["Explain my risk", "Why this signal?"],
        )

    @staticmethod
    def _guarantee(context: Mapping, question: str):
        return (
            "I cannot guarantee a 70% win rate, a 70% return or any future profit. "
            "Win rate is the share of closed trades that won; profitability also depends "
            "on win size, loss size, fees and slippage. A 70% win rate can still lose money. "
            "Treat 70% as a research target: test on unseen data after costs, inspect "
            "drawdown and sample size, then collect paper-trading evidence. A simulated "
            "or historical result does not establish future returns.",
            [],
            ["Show my performance", "Review the backtest", "Explain my risk"],
        )

    @staticmethod
    def _status(context: Mapping, question: str):
        guard = _mapping(context.get("guard", context.get("risk")))
        running = context.get("is_running")
        status = "running" if running is True else "paused" if running is False else "unknown"
        halt = guard.get("halted")
        halt_status = "halted" if halt is True else "not halted" if halt is False else "unknown"
        body = (
            f"Pilot: {status}. Risk guard: {halt_status}. Selected instrument: "
            f"{_label(context.get('symbol'))}. Strategy: {_label(context.get('strategy'))}."
        )
        if halt is True:
            body += f" Halt reason: {_label(guard.get('halt_reason'))}."
        source = _label(context.get("data_mode", context.get("data_source"))).lower()
        if source in {"simulated", "synthetic", "demo"}:
            body += " These prices are simulated and do not establish a market trading edge."
        return body, ["terminal mode and guard snapshot"], ["Show my portfolio", "Explain my risk"]

    @staticmethod
    def _portfolio(context: Mapping, question: str):
        metrics = _mapping(context.get("metrics"))
        positions = _mapping(context.get("positions"))
        prices = _mapping(context.get("current_prices", context.get("prices")))
        lines = [
            f"Equity {_cash(metrics.get('equity'))}; available cash {_cash(metrics.get('cash'))}; "
            f"account P&L {_cash(metrics.get('total_pnl'))} "
            f"({_percent(metrics.get('total_return_pct'))})."
        ]
        evidence = ["account metrics snapshot"] if metrics else []
        if "positions" not in context:
            lines.append("Open positions were not supplied.")
        elif not isinstance(context.get("positions"), Mapping):
            lines.append("The positions snapshot is invalid; open positions are unknown.")
        elif not positions:
            lines.append("No open positions in the supplied snapshot.")
            evidence.append("positions snapshot")
        else:
            lines.append(f"Open positions: {len(positions)}.")
            evidence.append("positions and available price snapshot")
            for symbol, raw in list(positions.items())[:8]:
                position = _mapping(raw)
                quantity = _number(position.get("quantity"))
                quote = _number(prices.get(symbol))
                qty_text = f"{quantity:g}" if quantity is not None else "unknown"
                line = f"- {_label(symbol)}: {qty_text} units; average entry {_cash(position.get('avg_price'))}"
                if quote is not None and quote > 0 and quantity is not None:
                    line += f"; snapshot value {_cash(quantity * quote)}"
                else:
                    line += "; snapshot market value unknown (missing valid quote or quantity)"
                lines.append(line + ".")
            if len(positions) > 8:
                lines.append(f"{len(positions) - 8} more positions are listed in the Positions tab.")
        return "\n".join(lines), evidence, ["Explain my risk", "Show my performance"]

    @staticmethod
    def _risk(context: Mapping, question: str):
        metrics = _mapping(context.get("metrics"))
        guard = _mapping(context.get("guard", context.get("risk")))
        preview = _mapping(context.get("position_preview"))
        if preview.get("mode") == "preview_only":
            guard = preview
        if guard.get("mode") == "preview_only":
            quantity = _number(guard.get("quantity"))
            body = (
                f"Position preview only: quantity {quantity:g}; " if quantity is not None else
                "Position preview only: quantity unknown; "
            )
            body += (
                f"notional {_cash(guard.get('notional'), '')}; cash required {_cash(guard.get('cash_required'), '')}; "
                f"planned loss at the stop {_cash(guard.get('planned_loss_at_stop'), '')} "
                f"against a risk budget of {_cash(guard.get('risk_budget'), '')}. "
                f"The reported binding limit is {_label(guard.get('binding_limit'))}. "
                "Amounts use the input quote currency. "
                "This is a long-only cash sizing estimate with configured entry and exit costs. "
                "It excludes existing portfolio exposure and exchange lot sizes. A gap through "
                "the stop can increase the loss. No order was submitted."
            )
            return body, ["supplied position sizing preview"], ["Review the backtest", "Show my portfolio"]
        positions = _mapping(context.get("positions"))
        prices = _mapping(context.get("current_prices", context.get("prices")))
        lines = [
            f"Observed maximum drawdown: {_percent(metrics.get('max_drawdown_pct'))}. "
            f"Configured daily loss limit: {_percent(guard.get('max_daily_loss_pct'), True)}; "
            f"drawdown limit: {_percent(guard.get('max_drawdown_pct'), True)}."
        ]
        evidence = []
        if metrics:
            evidence.append("account metrics snapshot")
        if guard:
            evidence.append("configured guard snapshot")
        if guard.get("halted") is True:
            lines.append(f"The risk guard is halted: {_label(guard.get('halt_reason'))}.")
        elif guard.get("halted") is False:
            lines.append("The guard reports no active halt; this does not establish that all risks are acceptable.")
        equity = _number(metrics.get("equity"))
        values = []
        missing_quotes = 0
        missing_stops = 0
        for symbol, raw in positions.items():
            position = _mapping(raw)
            qty = _number(position.get("quantity"))
            quote = _number(prices.get(symbol))
            stop = _number(position.get("stop_loss"))
            if qty is None or quote is None or quote <= 0:
                missing_quotes += 1
            else:
                values.append((str(symbol), abs(qty * quote)))
            if stop is None or stop <= 0:
                missing_stops += 1
        if values and equity is not None and equity > 0:
            symbol, largest = max(values, key=lambda item: item[1])
            qualifier = "partial " if missing_quotes else ""
            lines.append(
                f"Quoted {qualifier}gross exposure: {sum(value for _, value in values) / equity:.1%} "
                f"of equity. Largest quoted holding: {_label(symbol)} at {largest / equity:.1%}."
            )
            evidence.append("derived from quantities × supplied prices ÷ equity")
        if missing_quotes:
            lines.append(f"Exposure is incomplete: {missing_quotes} position(s) lack a valid quantity or quote.")
        if missing_stops:
            lines.append(f"{missing_stops} position(s) have no valid stop in the supplied snapshot.")
        lines.append(
            "Drawdown measures decline from an equity peak. Stops and configured limits "
            "can reduce exposure, but gaps, stale prices and execution costs can increase losses."
        )
        return "\n".join(lines), evidence, ["Show my portfolio", "Review the backtest"]

    @staticmethod
    def _performance(context: Mapping, question: str):
        metrics = _mapping(context.get("metrics"))
        research = _mapping(context.get("latest_backtest", context.get("validation")))
        if not metrics and isinstance(research.get("summary"), Mapping):
            body, evidence, suggestions = LokiCopilot._lab_backtest(research)
            return "No account performance was supplied. Research results follow.\n" + body, evidence, suggestions
        wins = _count(metrics.get("winning_trades"))
        losses = _count(metrics.get("losing_trades"))
        closed = _count(metrics.get("closed_trades", metrics.get("closed_trade_count")))
        if closed is None and wins is not None and losses is not None:
            closed = wins + losses
        lines = [
            f"Account P&L {_cash(metrics.get('total_pnl'))}; return "
            f"{_percent(metrics.get('total_return_pct'))}; maximum drawdown "
            f"{_percent(metrics.get('max_drawdown_pct'))}."
        ]
        evidence = ["account metrics snapshot"] if metrics else []
        if closed == 0:
            lines.append("There are no completed trades to estimate a win rate, profit factor or trade expectancy.")
        else:
            count_label = str(closed) if closed is not None else "unknown"
            lines.append(f"Completed trades: {count_label}; observed win rate {_percent(metrics.get('win_rate'))}.")
            win_rate = _number(metrics.get("win_rate"))
            avg_win = _number(metrics.get("avg_win"))
            avg_loss = _number(metrics.get("avg_loss"))
            if (closed and win_rate is not None and 0 <= win_rate <= 100
                    and avg_win is not None and avg_win >= 0
                    and avg_loss is not None and avg_loss >= 0):
                expectancy = win_rate / 100 * avg_win - (1 - win_rate / 100) * avg_loss
                lines.append(f"Reported trade expectancy: {_cash(expectancy)} per completed trade.")
                evidence.append("expectancy = win share × average win − loss share × average loss")
            if losses == 0 and wins:
                lines.append("No observed losing trades: profit factor is not reliably estimable from this sample.")
            else:
                pf = _number(metrics.get("profit_factor"))
                if pf is not None and pf >= 0:
                    lines.append(f"Reported profit factor: {pf:.2f} (gross gains divided by gross losses).")
            if closed is None or closed < 100:
                lines.append("The completed-trade sample is limited; the observed win rate is not a reliable future probability.")
        lines.append(
            "Assess win size and loss size alongside win rate. Verify the cost accounting "
            "and compare with unseen-data and paper-trading results before drawing conclusions."
        )
        return "\n".join(lines), evidence, ["Review the backtest", "Explain my risk", "Can you guarantee 70%?"]

    @staticmethod
    def _strategy(context: Mapping, question: str):
        key = _label(context.get("strategy"))
        if key == "Volatility-sized long-only trend with a trailing close exit":
            result = _mapping(context.get("latest_backtest", context.get("validation")))
            config = _mapping(result.get("config"))
            body = (
                "The Strategy Lab tests a long-only trend strategy. Completed closes "
                "must be above the slow moving average, and the fast average must be "
                "above the slow average. Recent volatility sets the entry allocation, "
                "capped by the configured exposure limit. It uses no leverage. "
                "Parameters are selected from a small fixed set on expanding training "
                "windows; later forward windows provide the reported results. If the "
                "training evidence is unconvincing, the selected strategy can stay in cash. "
                "Trend and trailing-close exit signals fill at the next opening price, "
                "so gaps can exceed the trailing threshold. Fees and slippage apply "
                "on entry and exit."
            )
            if config:
                body += (
                    f" Reported exposure cap: {_percent(config.get('max_exposure'), True)}; "
                    f"trailing-close threshold: {_percent(config.get('trailing_stop_pct'), True)}."
                )
            return body, ["Strategy Lab rule definitions and supplied research settings"], [
                "Review the backtest", "Explain my risk", "Show my performance",
            ]
        descriptions = {
            "momentum": "Momentum compares trend, EMA/MACD momentum and RSI conditions.",
            "mean_reversion": "Mean reversion looks for unusually stretched prices and a possible move back toward an average.",
            "breakout": "Breakout looks for a move beyond prior price extremes with volume confirmation.",
            "ml_ensemble": "The ensemble combines component strategy scores and changes their weights by market regime.",
            "volatility_surface": "The volatility strategy compares current volatility with its recent range.",
            "josh": "Josh's strategy combines several price, volume and trend conditions into a rule-based score.",
        }
        body = f"Selected strategy: {key}. " + descriptions.get(
            key, "No strategy-specific explanation is available in this snapshot."
        )
        body += (
            " A signal's confidence is a rule-agreement score, not a calibrated chance "
            "of winning. To improve a strategy, evaluate fees and slippage, regime stability, "
            "unseen data and drawdown before adjusting parameters. Repeatedly tuning to "
            "the same backtest can overfit it."
        )
        return body, ["selected strategy snapshot"], ["Why this signal?", "Review the backtest"]

    @staticmethod
    def _signal(context: Mapping, question: str):
        prices = _mapping(context.get("current_prices", context.get("prices")))
        positions = _mapping(context.get("positions"))
        selected = _label(context.get("symbol"))
        requested = selected
        candidates = sorted({str(key) for key in prices} | {str(key) for key in positions}, key=len, reverse=True)
        for symbol in candidates:
            if re.search(r"(?<![\w/])" + re.escape(symbol) + r"(?![\w/])", question, re.I):
                requested = symbol
                break
        else:
            pair = re.search(r"\b[A-Za-z]{2,10}/[A-Za-z]{2,6}\b", question)
            ticker = re.search(r"\$([A-Za-z]{1,6})\b", question)
            if pair:
                requested = pair.group().upper()
            elif ticker:
                requested = ticker.group(1).upper()
        signal = _mapping(context.get("latest_signal", context.get("signal")))
        signal_symbol = _label(signal.get("symbol"), selected)
        if signal_symbol.lower() != requested.lower():
            signal = {}
        lines = [f"Instrument: {requested}; supplied quote {_cash(prices.get(requested))}."]
        evidence = ["supplied instrument price"] if _number(prices.get(requested)) is not None else []
        if not signal:
            lines.append("No signal was supplied for this instrument. That is missing evidence, not an instruction to buy or sell.")
        else:
            action = _label(signal.get("action"))
            confidence = _number(signal.get("confidence"))
            score = _percent(confidence, True) if confidence is not None and 0 <= confidence <= 1 else "unknown"
            lines.append(f"Reported action: {action}; rule-agreement score: {score}.")
            lines.append(f"Strategy's stated reason: {_label(signal.get('reason'), 'not supplied')}.")
            evidence.append("latest strategy signal snapshot")
            entry = _number(signal.get("entry_price"))
            stop = _number(signal.get("stop_loss"))
            target = _number(signal.get("take_profit"))
            if entry is not None:
                lines.append(f"Reference entry {_cash(entry)}; stop {_cash(stop)}; target {_cash(target)}.")
                if action.upper() == "BUY" and stop is not None and target is not None and 0 < stop < entry < target:
                    lines.append(f"Planned reward/risk: {(target - entry) / (entry - stop):.2f}:1 before costs and gaps.")
                    evidence.append("derived from supplied entry, stop and target")
            lines.append("The score is not a probability of profit. This explanation does not execute a trade.")
        return "\n".join(lines), evidence, ["Explain my risk", "Explain the strategy", "Review the backtest"]

    @staticmethod
    def _backtest(context: Mapping, question: str):
        result = _mapping(context.get("latest_backtest", context.get("validation")))
        if not result:
            return (
                "No backtest or validation result was supplied. Run a test on unseen chronological "
                "data and inspect return after fees/slippage, maximum drawdown, trade count "
                "and a buy-and-hold benchmark. Synthetic data checks mechanics; it cannot "
                "establish a real-market trading edge.",
                [],
                ["Explain the strategy", "Show my performance"],
            )
        if isinstance(result.get("summary"), Mapping):
            return LokiCopilot._lab_backtest(result)
        lines = [
            f"Reported backtest: return {_percent(result.get('return_pct'))}; "
            f"net profit {_cash(result.get('net_profit'))}; observed win rate "
            f"{_percent(result.get('win_rate'))}; maximum drawdown "
            f"{_percent(result.get('max_drawdown_pct', result.get('max_drawdown')))}.",
            f"Completed trades: {_count(result.get('total_trades')) if _count(result.get('total_trades')) is not None else 'unknown'}.",
        ]
        source = _label(result.get("data_source"), "not supplied")
        lines.append(f"Test data source: {source}.")
        if "out_of_sample" in result:
            flag = result.get("out_of_sample")
            label = "yes" if flag is True else "no" if flag is False else "unknown"
            lines.append(f"Marked out of sample: {label} (as reported by the test).")
        else:
            lines.append("An out-of-sample evaluation was not supplied.")
        lines.append(
            "Historical results are observations, not a future return guarantee. "
            "Check cost assumptions, sample size, drawdown and independent paper results."
        )
        return "\n".join(lines), ["supplied backtest result"], ["Explain my risk", "Can you guarantee 70%?"]

    @staticmethod
    def _lab_backtest(result: Mapping):
        """Explain Strategy Lab's nested report; its rates are fractions."""
        summary = _mapping(result.get("summary"))
        benchmark = _mapping(result.get("benchmark"))
        config = _mapping(result.get("config"))
        drawdown = _number(summary.get("max_drawdown"))
        trades = _count(summary.get("total_trades"))
        lines = [
            f"Reported Strategy Lab result: return {_percent(summary.get('total_return'), True)}; "
            f"maximum drawdown {_percent(abs(drawdown) if drawdown is not None else None, True)}; "
            f"completed trades {trades if trades is not None else 'unknown'}.",
            f"Observed win rate: {_percent(summary.get('win_rate'), True)}; "
            f"reported trade expectancy {_cash(summary.get('expectancy'), '')} in the input quote currency.",
        ]
        interval = summary.get("win_rate_ci95")
        if isinstance(interval, (list, tuple)) and len(interval) == 2:
            lower, upper = _number(interval[0]), _number(interval[1])
            if lower is not None and upper is not None and 0 <= lower <= upper <= 1:
                lines.append(
                    f"Descriptive 95% win-rate interval: {lower:.1%}–{upper:.1%}. "
                    "Serial dependence can make actual uncertainty larger."
                )
        if benchmark:
            lines.append(f"Reported buy-and-hold benchmark return: {_percent(benchmark.get('total_return'), True)}.")
        fee, slippage = _number(config.get("fee_bps")), _number(config.get("slippage_bps"))
        if fee is not None and slippage is not None:
            lines.append(f"Configured costs per side: {fee:g} bps fees plus {slippage:g} bps slippage.")
        lines.append(f"Research status: {_label(result.get('status'))}.")
        reasons = result.get("rejection_reasons")
        if isinstance(reasons, (list, tuple)):
            lines.extend(f"- {_label(reason)}" for reason in reasons[:4])
        lines.append(
            "This report uses the supplied historical research data; its provenance "
            "is not independently verified. A paper candidate is not a future-profit "
            "guarantee or approval to trade live."
        )
        return "\n".join(lines), ["supplied Strategy Lab summary, benchmark and research settings"], [
            "Explain the strategy", "Explain my risk", "Can you guarantee 70%?",
        ]
