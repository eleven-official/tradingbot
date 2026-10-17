"""Offline, read-only explanations grounded in a supplied terminal snapshot.

The assistant never receives an account, broker, callback, or credentials. Its
only inputs are a question and plain snapshot data; it cannot submit orders.
This is a local conversation planner, not a language model or market predictor.

Snapshot keys used by the desktop:
    metrics, positions, current_prices, latest_signal, guard, latest_backtest,
    symbol, strategy, data_mode, trading_mode, is_running, as_of.
The aliases prices/signal/risk/validation/data_source are also accepted.
Metrics use percentage points (win_rate=70, max_drawdown_pct=12); guard limits
and signal confidence use fractions (max_drawdown_pct=.12, confidence=.7).
Missing or invalid measurements are reported as unknown, never as zero.
Stateless API clients can supply ``conversation`` from the prior reply (or the
legacy ``previous_intent``). That state contains topics and an instrument only;
fresh snapshot data must still be supplied. Optional ``recent_trades`` and
``strategy_comparison`` explain actual exits and exploratory strategy results.
``previous_snapshot`` enables explicit comparisons; snapshots are never retained
in conversation state or silently compared across different account/data modes.
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
    topics: tuple[str, ...] = ()
    symbol: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.intent,
            "evidence": list(self.evidence),
            "suggestions": list(self.suggestions),
            "topics": list(self.topics or (self.intent,)),
            "conversation": {"topics": list(self.topics or (self.intent,)), "symbol": self.symbol},
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
    scaled = number * 100 if fraction else number
    return f"{scaled:.2f}%" if math.isfinite(scaled) else "unknown"


def _count(value: Any) -> Optional[int]:
    number = _number(value)
    return int(number) if number is not None and number >= 0 and number.is_integer() else None


def _closed_count(metrics: Mapping) -> Optional[int]:
    closed = _count(metrics.get("closed_trades", metrics.get("closed_trade_count")))
    wins, losses = _count(metrics.get("winning_trades")), _count(metrics.get("losing_trades"))
    return wins + losses if closed is None and wins is not None and losses is not None else closed


def _expectancy(metrics: Mapping) -> Optional[float]:
    rate, win, loss = (_number(metrics.get(key)) for key in ("win_rate", "avg_win", "avg_loss"))
    if (
        _closed_count(metrics)
        and rate is not None
        and 0 <= rate <= 100
        and win is not None
        and win >= 0
        and loss is not None
        and loss >= 0
    ):
        return rate / 100 * win - (1 - rate / 100) * loss
    return None


def _symbol(value: Any) -> Optional[str]:
    """Only retain instrument identifiers, never arbitrary instructions or prices."""
    if isinstance(value, str) and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9.^_-]{0,19}(?:/[A-Za-z0-9]{1,12})?", value
    ):
        return value.upper()
    return None


def _normal_question(question: str) -> str:
    q = question.casefold().replace("’", "'")
    corrections = {
        "porfolio": "portfolio",
        "portflio": "portfolio",
        "preformance": "performance",
        "perfomance": "performance",
        "stragie": "strategy",
        "stratgey": "strategy",
        "stratergy": "strategy",
        "strategys": "strategies",
        "profitablee": "profitable",
        "guarentee": "guarantee",
        "gurrenty": "guarantee",
        "loi": "loki",
        "loosing": "losing",
        "backtset": "backtest",
        "drawdwon": "drawdown",
    }
    return re.sub(r"\b\w+\b", lambda match: corrections.get(match.group(), match.group()), q)


def _fusion_snapshot(context: Mapping) -> dict:
    """Normalize supplied paper snapshots without fetching or inventing quotes."""
    snapshot = dict(context)
    portfolio = _mapping(snapshot.get("portfolio"))
    state = _mapping(portfolio.get("state"))
    metrics = dict(_mapping(portfolio.get("metrics")))
    for key in ("equity", "cash", "total_pnl", "total_return_pct", "closed_trades", "win_rate"):
        if key in portfolio:
            metrics.setdefault(key, portfolio[key])
    metrics.update(_mapping(snapshot.get("metrics")))
    if metrics:
        snapshot["metrics"] = metrics
    raw = snapshot.get("positions", state.get("positions", portfolio.get("positions")))
    if isinstance(raw, (list, tuple)):
        raw = {
            row["symbol"]: row
            for row in raw[:100]
            if isinstance(row, Mapping) and _symbol(row.get("symbol"))
        }
    if isinstance(raw, Mapping):
        positions, prices = {}, dict(
            _mapping(snapshot.get("current_prices", snapshot.get("prices")))
        )
        for symbol, value in list(raw.items())[:100]:
            row = dict(_mapping(value))
            if "average_price" in row:
                row.setdefault("avg_price", row["average_price"])
            if "mark_price" in row:
                prices.setdefault(symbol, row["mark_price"])
            positions[symbol] = row
        snapshot["positions"], snapshot["current_prices"] = positions, prices
    currency = portfolio.get("currency", state.get("quote_currency", snapshot.get("currency")))
    if isinstance(currency, str) and re.fullmatch(r"[A-Za-z]{2,12}", currency):
        snapshot["currency"] = currency.upper()
    return snapshot


class LokiCopilot:
    """A bounded local conversation that explains data, without trading authority.

    Reuse one instance for follow-up questions. Each response uses only the
    context supplied on that turn, so old prices and balances are never reused.
    Conversation history contains question/intent pairs, not financial snapshots.
    """

    def __init__(self, history_limit: int = 20):
        self.history = deque(maxlen=max(1, min(int(history_limit), 100)))
        self.last_intent = "help"
        self.last_topics = ("help",)
        self.last_symbol = None

    def reset(self) -> None:
        self.history.clear()
        self.last_intent = "help"
        self.last_topics = ("help",)
        self.last_symbol = None

    def respond(self, message: str, context: Optional[Mapping] = None) -> CopilotReply:
        question = " ".join(str(message or "").split())[:2000]
        snapshot = _fusion_snapshot(_mapping(context))
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
            "overview": self._overview,
            "diagnosis": self._diagnosis,
            "next_steps": self._next_steps,
            "changes": self._changes,
            "comparison": self._comparison,
            "council": self._council,
            "factors": self._factors,
            "scenario": self._scenario,
            "pullback": self._pullback,
            "learning": self._learning,
        }
        topics = self._topics(question)
        if topics == ["followup"]:
            memory = _mapping(snapshot.get("conversation"))
            previous_topics = memory.get("topics")
            previous = snapshot.get("previous_intent")
            if isinstance(previous_topics, (tuple, list)):
                topics = [
                    topic
                    for topic in previous_topics
                    if isinstance(topic, str) and topic in handlers
                ][:4]
                topics = list(dict.fromkeys(topics)) or ["help"]
            elif isinstance(previous, str) and previous in handlers:
                topics = [previous]
            else:
                topics = list(self.last_topics)
        symbols = self._requested_symbols(question, snapshot)
        if symbols:
            snapshot["requested_symbols"] = symbols
        sections, evidence, suggestions = [], [], []
        titles = {
            "portfolio": "Portfolio",
            "risk": "Risk",
            "performance": "Performance",
            "strategy": "Strategy",
            "signal": "Signal",
            "backtest": "Research",
            "status": "Session",
            "guarantee": "Profit target",
            "action": "Action request",
            "overview": "Your snapshot",
            "diagnosis": "Loss review",
            "next_steps": "Next steps",
            "changes": "Changes",
            "comparison": "Comparison",
            "help": "Talking to Loki",
            "council": "Council review",
            "factors": "Factor evidence",
            "scenario": "Portfolio stress",
            "pullback": "Pullback research",
            "learning": "Historical model training",
        }
        for topic in topics:
            body, sources, prompts = handlers[topic](snapshot, question)
            sections.append(f"{titles[topic]}\n{body}" if len(topics) > 1 else body)
            evidence.extend(sources)
            suggestions.extend(prompts)
        body = "\n\n".join(sections)
        evidence = list(dict.fromkeys(evidence))
        suggestions = list(dict.fromkeys(suggestions))[:5]
        intent = topics[0]
        origin = self._origin(snapshot)
        text = f"{origin}\n\n{body}"
        if evidence:
            text += "\n\nEvidence: " + "; ".join(evidence) + "."
        if snapshot.get("currency") and snapshot["currency"] != "USD":
            text = re.sub(r"\$(?=[-\d])", snapshot["currency"] + " ", text)
        retained_symbol = symbols[-1] if symbols else None
        reply = CopilotReply(
            text, intent, tuple(evidence), tuple(suggestions), tuple(topics), retained_symbol
        )
        self.history.append({"question": question, "intent": intent})
        self.last_intent = intent
        self.last_topics = tuple(topics)
        self.last_symbol = retained_symbol
        return reply

    def _intent(self, question: str) -> str:
        """Legacy single-topic helper; conversation planning uses every topic."""
        return self._topics(question)[0]

    def _topics(self, question: str) -> list[str]:
        q = _normal_question(question)
        # Instrument labels such as TEST/USDT must not become "test" intents.
        q = re.sub(r"(?<![\w/])[a-z0-9]{2,20}/[a-z0-9]{2,12}(?![\w/])|\$[a-z]{1,6}\b", " ", q)
        if not q:
            return ["help"]
        topics = []
        if re.search(
            r"\b(guarantee\w*|certain profit|risk.free)\b|100\s*%|"
            r"\b(?:make|ensure|promise|want|target|achieve)\b.*70\s*%",
            q,
        ):
            topics.append("guarantee")
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
            topics.insert(0, "action")
        special = None
        if re.search(
            r"\b(?:how (?:am i|are we|is (?:my account|loki|it)) doing|catch me up|"
            r"give me (?:an? )?(?:summary|update)|summari[sz]e|overview)\b",
            q,
        ):
            special = "overview"
        elif re.search(
            r"\b(?:why\b.*\b(?:los[est]|losing|loss|losses|down|negative)|"
            r"what (?:went wrong|caused.*loss)|explain.*loss|diagnos\w*)\b",
            q,
        ):
            special = "diagnosis"
        elif re.search(
            r"\b(?:what (?:should (?:i|we) do|do (?:i|we) do|to do|do) next|"
            r"what(?:'s| is) next|next steps?|help me improve)\b",
            q,
        ):
            special = "next_steps"
        elif re.search(
            r"\b(?:what(?:'s| has)? changed|what is different|since (?:last|before)|changes)\b", q
        ):
            special = "changes"
        elif re.search(r"\b(?:compare|comparison|versus|vs\.?|which.*(?:best|better))\b", q):
            special = "comparison"
        if special:
            topics.append(special)
        patterns = [
            ("learning", r"\b(train(?:ed|ing)?|machine.learning|market.model|historical.model|prediction.accuracy)\b"),
            ("pullback", r"\b(pullback|mean.reversion)\b"),
            (
                "council",
                r"\b(council|director|analysts?|autohedge|role.pipeline|blocked proposal)\b",
            ),
            ("factors", r"\b(factors?|indicators?|rsi|vibe|condition.score)\b"),
            ("scenario", r"\b(scenarios?|stress|shock|what.if)\b"),
            (
                "backtest",
                r"\b(backtest|test\w*|validation|validate|out.of.sample|walk.forward|research)\b",
            ),
            (
                "risk",
                r"\b(risk|sizing|position.size|drawdown|halt\w*|stop.loss|exposure|concentration|safe\w*)\b",
            ),
            (
                "performance",
                r"\b(win.rate|profit\w*|performance|pnl|p&l|expectancy|returns?|losing|losses)\b",
            ),
            ("portfolio", r"\b(portfolio|positions?|holding\w*|balance|cash|equity|account)\b"),
            (
                "signal",
                r"\b(signal|buy|sell|hold|conviction|confidence|entry|target|price|quote)\b",
            ),
            (
                "strategy",
                r"\b(strateg\w*|momentum|breakout|ensemble|reversion|josh|regime|improve|better)\b",
            ),
            ("status", r"\b(status|running|mode|live|paper|simulat\w*|connected|happening)\b"),
        ]
        if not special:
            for topic, pattern in patterns:
                if not re.search(pattern, q):
                    continue
                if "action" in topics and topic in {"signal", "status"}:
                    continue
                if "guarantee" in topics and topic in {"performance", "signal"}:
                    continue
                if topic == "portfolio" and re.search(r"\bposition siz", q):
                    continue
                if topic == "strategy" and "pullback" in topics:
                    continue
                topics.append(topic)
        elif re.search(r"\b(?:and|also|plus)\b.*\b(?:risk|drawdown|exposure)\b", q):
            topics.append("risk")
        if topics:
            return list(dict.fromkeys(topics))[:4]
        if re.search(
            r"^(?:and\s+)?(?:why|more|tell me more|explain(?: more)?|"
            r"what does that mean|what about\b.*|and (?:it|its|that|this))\??$",
            q,
        ):
            return ["followup"]
        if re.fullmatch(r"(?:and\s+)?(?:[a-z]{2,10}/[a-z]{2,6}|\$[a-z]{1,6})\??", q):
            return ["followup"]
        return ["help"]

    def _requested_symbols(self, question: str, context: Mapping) -> list[str]:
        prices = _mapping(context.get("current_prices", context.get("prices")))
        positions = _mapping(context.get("positions"))
        selected = _symbol(context.get("symbol"))
        candidates = {
            value for key in (*prices, *positions, context.get("symbol")) if (value := _symbol(key))
        }
        found = []
        for match in re.finditer(
            r"(?<![\w/])(?:[A-Za-z0-9]{2,10}/[A-Za-z0-9]{2,6}|\$[A-Za-z]{1,6})(?![\w/])", question
        ):
            value = match.group().lstrip("$").upper()
            # A shorthand base ticker resolves only when the supplied data is unambiguous.
            aliases = [candidate for candidate in candidates if candidate.split("/")[0] == value]
            found.append(aliases[0] if len(aliases) == 1 else value)
        if not found:
            for candidate in sorted(candidates, key=len, reverse=True):
                aliases = [candidate, candidate.split("/")[0]]
                for alias in aliases:
                    if re.search(r"(?<![\w/])" + re.escape(alias) + r"(?![\w/])", question, re.I):
                        same_base = [value for value in candidates if value.split("/")[0] == alias]
                        if alias == candidate or len(same_base) == 1:
                            found.append(candidate)
                            break
        if found:
            return list(dict.fromkeys(found))[:4]
        q = _normal_question(question)
        if re.search(r"\b(it|its|that|this|more|why)\b|^what about", q):
            memory = _mapping(context.get("conversation"))
            remembered = _symbol(memory.get("symbol")) or self.last_symbol
            if remembered:
                return [remembered]
        return [selected] if selected else []

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
            "portfolio, risk limits, strategy signals and backtest evidence. You can ask "
            "several things together, name an instrument, then follow up with 'why?' "
            "or 'what about ETH/USD?'. I remember topics and instruments, and read "
            "fresh supplied data for every answer. Try 'How am I doing?', 'Why did "
            "we lose?', 'What should I do next?' or 'Compare strategies'. To explain "
            "what changed, I need an earlier snapshot as well as the current one. "
            "In Fusion, ask 'Why did the council wait?', 'Explain the factors' or "
            "'Explain the stress scenario' after running those tools. "
            "I have no access to news or external accounts.",
            [],
            ["How am I doing?", "What should I do next?", "Why did we lose?", "Compare strategies"],
        )

    @staticmethod
    def _overview(context: Mapping, question: str):
        metrics = _mapping(context.get("metrics"))
        result = _mapping(context.get("latest_backtest", context.get("validation")))
        if not metrics:
            if result:
                body, evidence, suggestions = LokiCopilot._backtest(context, question)
                return (
                    "There is no account snapshot here. Your latest research says:\n" + body,
                    evidence,
                    suggestions,
                )
            return (
                "I don't have account performance or a research report in this snapshot yet. "
                "Open a paper session or run Strategy Lab on your historical bars, then ask "
                "again. I can explain the strategy and risk settings in the meantime.",
                [],
                ["Explain the strategy", "Review the backtest", "Explain my risk"],
            )
        pnl = _number(metrics.get("total_pnl"))
        direction = (
            "ahead"
            if pnl is not None and pnl > 0
            else (
                "behind"
                if pnl is not None and pnl < 0
                else "flat" if pnl == 0 else "at an unknown P&L"
            )
        )
        lines = [
            f"The supplied account is {direction}: P&L {_cash(pnl)} "
            f"({_percent(metrics.get('total_return_pct'))}), equity {_cash(metrics.get('equity'))}, "
            f"cash {_cash(metrics.get('cash'))}."
        ]
        count = _closed_count(metrics)
        if count is None:
            lines.append(
                "The number of completed trades was not supplied; a fill count cannot replace it."
            )
        elif count == 0:
            lines.append(
                "No trades have completed, so there is no closed-trade performance evidence yet."
            )
        else:
            lines.append(
                f"There are {count} completed trades, with an observed "
                f"win rate of {_percent(metrics.get('win_rate'))} and maximum "
                f"drawdown of {_percent(metrics.get('max_drawdown_pct'))}."
            )
        expectancy = _expectancy(metrics)
        if expectancy is not None and expectancy < 0:
            lines.append(
                f"The reported average win/loss mix implies {_cash(expectancy)} per "
                "completed trade; the high win rate alone is not an edge."
            )
        guard = _mapping(context.get("guard", context.get("risk")))
        if guard.get("halted") is True:
            lines.append(f"The risk guard is halted: {_label(guard.get('halt_reason'))}.")
        if context.get("data_fresh") is False:
            lines.append(
                "Prices are flagged stale; refresh the data before relying on marked account values."
            )
        lines.append(
            "This is a description of the supplied sample, not a prediction of future profit."
        )
        return (
            "\n".join(lines),
            ["account metrics and current guard snapshot"],
            [
                "Why did we lose?",
                "What should I do next?",
                "Explain my risk",
            ],
        )

    @staticmethod
    def _diagnosis(context: Mapping, question: str):
        result = _mapping(context.get("latest_backtest", context.get("validation")))
        metrics = _mapping(context.get("metrics"))
        research = bool(result) and (
            not metrics
            or bool(re.search(r"\b(backtest|research|test)\b", _normal_question(question)))
        )
        lines, evidence = [], []
        if research:
            summary = _mapping(result.get("summary"))
            ret = _number(summary.get("total_return"))
            if summary:
                lines.append(
                    f"The research report's after-cost return is {_percent(ret, True)}; "
                    f"reported completed-trade expectancy is {_cash(summary.get('expectancy'), '')} "
                    "in its input quote currency."
                )
                evidence.append("supplied research summary")
            else:
                lines.append(
                    f"The exploratory backtest reports return {_percent(result.get('return_pct'))}."
                )
                evidence.append("supplied exploratory backtest")
            raw_trades = result.get("trades")
            reasons = result.get("rejection_reasons")
            if isinstance(reasons, (tuple, list)) and reasons:
                lines.append(
                    "The report's measured limitations: "
                    + "; ".join(_label(reason) for reason in reasons[:4])
                    + "."
                )
            stress = result.get("cost_stress")
            if isinstance(stress, (tuple, list)):
                valid = [
                    _mapping(row)
                    for row in stress
                    if _number(_mapping(row).get("multiplier")) is not None
                    and _number(_mapping(row).get("total_return")) is not None
                ]
                if valid:
                    stressed = max(valid, key=lambda row: float(row["multiplier"]))
                    lines.append(
                        f"At {float(stressed['multiplier']):g}× configured fees and slippage, "
                        f"the reported return is {_percent(stressed['total_return'], True)}. "
                        "This is a cost sensitivity test with parameters held fixed."
                    )
                    evidence.append("supplied cost stress scenarios")
        else:
            raw_trades = context.get("recent_trades")
            pnl = _number(metrics.get("total_pnl"))
            if metrics:
                lines.append(
                    f"Account P&L is {_cash(pnl)}; observed win rate is "
                    f"{_percent(metrics.get('win_rate'))}."
                )
                expectancy = _expectancy(metrics)
                if expectancy is not None:
                    lines.append(
                        f"The reported mix of average wins {_cash(metrics.get('avg_win'))} "
                        f"and average losses {_cash(metrics.get('avg_loss'))} implies "
                        f"{_cash(expectancy)} per completed trade. "
                        + (
                            "Larger losses outweigh the wins in this sample."
                            if expectancy < 0
                            else "That average is positive in this sample; it does not prove a future edge."
                        )
                    )
                if pnl is not None and pnl >= 0:
                    lines.append(
                        "The total account P&L supplied is not negative; individual losing trades can still occur."
                    )
                evidence.append("account metrics snapshot")
        trades = []
        if isinstance(raw_trades, (tuple, list)):
            for row in raw_trades[-500:]:
                trade = _mapping(row)
                action = _label(trade.get("action", trade.get("side", "SELL"))).upper()
                pnl = _number(trade.get("pnl"))
                if pnl is not None and action in {"SELL", "CLOSE", "EXIT"}:
                    trades.append(trade)
        requested = context.get("requested_symbols", [])
        if isinstance(requested, (tuple, list)) and requested and not research:
            # Rows without a symbol remain usable only for an unscoped account question.
            explicit = any(
                re.search(r"(?<![\w/])" + re.escape(str(symbol)) + r"(?![\w/])", question, re.I)
                for symbol in requested
            )
            if explicit or re.search(r"\b(it|its|that)\b", _normal_question(question)):
                trades = [trade for trade in trades if _symbol(trade.get("symbol")) in requested]
        losing = [trade for trade in trades if _number(trade.get("pnl")) < 0]
        if losing:
            currency = "" if research else "$"
            lines.append(
                f"In the supplied closed-trade rows, {len(losing)} losing exits sum to "
                f"{_cash(sum(float(trade['pnl']) for trade in losing), currency)}. "
                "These rows may be only a recent subset of the full history."
            )
            for trade in losing[-3:]:
                name = _label(trade.get("symbol"), "research instrument")
                reason = _label(
                    trade.get("exit_reason", trade.get("reason")), "exit reason not supplied"
                )
                lines.append(
                    f"- {name}: P&L {_cash(trade.get('pnl'), currency)}; recorded exit: {reason}."
                )
            evidence.append("supplied closed-trade exit records")
            lines.append(
                "The exit records explain how those trades closed; they do not establish why the market moved."
            )
        elif trades:
            lines.append("No losing exit appears in the supplied closed-trade subset.")
        else:
            lines.append(
                "No matching closed-trade records were supplied, so I cannot attribute a particular loss "
                "to a signal, exit, fee or market event. Include the trade history to inspect the recorded exits."
            )
        if not lines[:-1]:
            lines.insert(
                0, "There is no account or research performance evidence in this snapshot."
            )
        return (
            "\n".join(lines),
            evidence,
            ["What should I do next?", "Review the backtest", "Explain my risk"],
        )

    @staticmethod
    def _next_steps(context: Mapping, question: str):
        metrics = _mapping(context.get("metrics"))
        result = _mapping(context.get("latest_backtest", context.get("validation")))
        summary = _mapping(result.get("summary"))
        guard = _mapping(context.get("guard", context.get("risk")))
        steps, evidence = [], []
        if context.get("data_fresh") is False:
            steps.append(
                "Refresh the flagged stale or missing quotes, then recheck marked equity and exposure."
            )
            evidence.append("current quote freshness flag")
        if guard.get("halted") is True:
            steps.append(
                f"Review the halt ({_label(guard.get('halt_reason'))}) and its loss history before "
                "using the explicit terminal controls to consider resuming."
            )
            evidence.append("current risk halt")
        expectancy = _expectancy(metrics)
        if expectancy is not None and expectancy < 0:
            steps.append(
                f"Investigate the negative reported expectancy ({_cash(expectancy)} per completed trade). "
                "Compare actual loss size and exit records before changing entries or increasing size."
            )
            evidence.append("derived account trade expectancy")
        count = _closed_count(metrics)
        if count is not None and count < 100:
            steps.append(
                f"Keep evaluating in paper mode: {count} completed account trades are limited evidence. "
                "Track costs, expectancy and drawdown, rather than targeting win rate alone."
            )
            evidence.append("account completed-trade count")
        reasons = result.get("rejection_reasons")
        if isinstance(reasons, (tuple, list)) and reasons:
            steps.append(
                "Address the report's measured gaps: "
                + "; ".join(_label(reason) for reason in reasons[:3])
                + ". Keep a new chronological holdout separate from parameter selection."
            )
            evidence.append("research rejection reasons")
        if result and not reasons:
            steps.append(
                f"Review the report marked {_label(result.get('status'))}: inspect forward windows, "
                "cost stress and the buy-and-hold comparison, then gather independent paper results."
            )
            evidence.append("supplied research status")
        if summary:
            rate, benchmark = _number(summary.get("total_return")), _number(
                _mapping(result.get("benchmark")).get("total_return")
            )
            if rate is not None and benchmark is not None and rate <= benchmark:
                steps.append(
                    "The reported strategy has not beaten its buy-and-hold benchmark after costs. "
                    "Compare drawdown and exposure as well as return before calling it an improvement."
                )
                evidence.append("reported strategy versus benchmark returns")
        if not result:
            steps.append(
                "Run Strategy Lab on ordered historical bars with realistic fees and slippage; "
                "inspect the unseen windows, benchmark, sample size and cost stress."
            )
        if not steps:
            steps.append(
                "Gather an account snapshot or research report first; there is no evidence here "
                "to justify a strategy or sizing change."
            )
        lines = ["Based on this snapshot, the useful next checks are:"]
        lines.extend(f"{index}. {step}" for index, step in enumerate(steps[:5], 1))
        lines.append("These are review steps. No order, setting or trading mode was changed.")
        return (
            "\n".join(lines),
            evidence,
            ["Why did we lose?", "Compare strategies", "Explain my risk"],
        )

    @staticmethod
    def _changes(context: Mapping, question: str):
        previous = _mapping(context.get("previous_snapshot"))
        if not previous:
            return (
                "I have only the current snapshot, so I cannot say what changed since last time. "
                "Conversation memory stores topics and instruments, not old balances or prices. "
                "Supply an earlier timestamped snapshot to compare; 'How am I doing?' explains the current state.",
                [],
                ["How am I doing?", "What should I do next?"],
            )
        keys = [("data_mode", "data_source"), ("trading_mode", "trading_mode")]
        for key, alias in keys:
            before = _label(previous.get(key, previous.get(alias)))
            after = _label(context.get(key, context.get(alias)))
            if before == "unknown" or after == "unknown" or before.casefold() != after.casefold():
                return (
                    "The snapshots have different or unknown data/trading modes, so their account "
                    "and price changes are not comparable. Compare snapshots from the same source and session mode.",
                    ["supplied snapshot modes"],
                    ["How am I doing?"],
                )
        old_stamp, new_stamp = previous.get("as_of"), context.get("as_of")
        if not old_stamp or not new_stamp:
            return (
                "Both snapshots need timestamps to explain a change over time. No time ordering was supplied.",
                [],
                ["How am I doing?"],
            )
        lines = [f"Supplied snapshot comparison: {_label(old_stamp)} → {_label(new_stamp)}."]
        old, new = _mapping(previous.get("metrics")), _mapping(context.get("metrics"))
        for key, name in (("equity", "Equity"), ("cash", "Cash"), ("total_pnl", "Account P&L")):
            before, after = _number(old.get(key)), _number(new.get(key))
            if before is not None and after is not None:
                lines.append(
                    f"{name}: {_cash(before)} → {_cash(after)} (change {_cash(after - before)})."
                )
        old_prices = _mapping(previous.get("current_prices", previous.get("prices")))
        new_prices = _mapping(context.get("current_prices", context.get("prices")))
        for symbol in context.get("requested_symbols", [])[:4]:
            before, after = _number(old_prices.get(symbol)), _number(new_prices.get(symbol))
            if before is not None and before > 0 and after is not None and after > 0:
                lines.append(
                    f"{symbol} supplied quote: {_cash(before)} → {_cash(after)} "
                    f"({(after / before - 1):+.2%})."
                )
        if len(lines) == 1:
            lines.append(
                "No matching valid equity, cash, P&L or instrument prices were supplied in both snapshots."
            )
        lines.append(
            "This comparison reports differences only; deposits, withdrawals and trades can affect balances. "
            "It does not establish the cause of a change."
        )
        return (
            "\n".join(lines),
            ["explicit current and previous snapshot values"],
            ["How am I doing?", "Why did we lose?"],
        )

    @staticmethod
    def _comparison(context: Mapping, question: str):
        raw = context.get("strategy_comparison")
        rows = []
        if isinstance(raw, (tuple, list)):
            for item in raw[:20]:
                row = _mapping(item)
                if _number(row.get("return_pct")) is not None:
                    rows.append(row)
        if rows:
            rows.sort(key=lambda row: float(row["return_pct"]), reverse=True)
            lines = ["Supplied exploratory strategy comparison:"]
            for row in rows[:8]:
                count = _count(row.get("total_trades"))
                lines.append(
                    f"- {_label(row.get('name', row.get('strategy')))}: return "
                    f"{_percent(row.get('return_pct'))}; drawdown "
                    f"{_percent(row.get('max_drawdown_pct', row.get('max_drawdown')))}; "
                    f"completed trades {count if count is not None else 'unknown'}."
                )
            lines.append(
                f"{_label(rows[0].get('name', rows[0].get('strategy')))} has the highest "
                "reported return among these rows. This ranking describes the supplied sample; "
                "it does not show which strategy will perform best next. Verify that date range, "
                "costs and starting capital match, and assess a separate chronological holdout."
            )
            return (
                "\n".join(lines),
                ["supplied exploratory strategy comparison rows"],
                [
                    "Review the backtest",
                    "What should I do next?",
                    "Explain the strategy",
                ],
            )
        result = _mapping(context.get("latest_backtest", context.get("validation")))
        summary, benchmark = _mapping(result.get("summary")), _mapping(result.get("benchmark"))
        strategy_return, baseline_return = _number(summary.get("total_return")), _number(
            benchmark.get("total_return")
        )
        if strategy_return is not None and baseline_return is not None:
            delta = (strategy_return - baseline_return) * 100
            body = (
                f"The supplied Strategy Lab report compares its selected trend strategy "
                f"({_percent(strategy_return, True)} return) with buy-and-hold "
                f"({_percent(baseline_return, True)}). The strategy's return difference is "
                f"{delta:+.2f} percentage points. Strategy drawdown is "
                f"{_percent(abs(value) if (value := _number(summary.get('max_drawdown'))) is not None else None, True)}; "
                f"benchmark drawdown is {_percent(abs(value) if (value := _number(benchmark.get('max_drawdown'))) is not None else None, True)}. "
                "This is one research strategy versus a passive baseline, not evidence that all other "
                "strategies were tested or that future returns will match. The baseline may use more exposure."
            )
            return (
                body,
                ["supplied research summary and buy-and-hold benchmark"],
                [
                    "Review the backtest",
                    "What should I do next?",
                ],
            )
        return (
            "No strategy comparison with measured outcomes was supplied. I cannot name a winning strategy "
            "from its label or rule-agreement score. Use Compare strategies in the desktop terminal, "
            "or run a chronological research report with a buy-and-hold benchmark, then compare "
            "after-cost return, drawdown, closed-trade count and cost sensitivity on matching data.",
            [],
            ["Explain the strategy", "Review the backtest", "What should I do next?"],
        )

    @staticmethod
    def _council(context: Mapping, question: str):
        result = _mapping(context.get("council"))
        if not result:
            return (
                "No council review was supplied. Import history, then convene the council. "
                "Its quant, sentiment, risk, execution and director roles form an inspectable "
                "local rules pipeline; they are not independent language-model agents.",
                [],
                ["Explain the factors", "Review the backtest"],
            )
        director = _mapping(result.get("director"))
        lines = [
            f"The supplied council decision is {_label(director.get('decision'))}: "
            f"{_label(director.get('summary'))}"
        ]
        blocked = director.get("blocked_by")
        if isinstance(blocked, (list, tuple)) and blocked:
            lines.append(
                "Checks blocking the proposal: "
                + "; ".join(_label(item) for item in blocked[:8])
                + "."
            )
        target = _mapping(result.get("performance_target"))
        if target:
            lines.append(
                f"The supplied research has {_count(target.get('closed_trades')) if _count(target.get('closed_trades')) is not None else 'unknown'} "
                f"completed trades; observed wins {_percent(target.get('observed_win_rate'), True)}; "
                f"95% lower bound {_percent(target.get('lower_confidence_bound'), True)}. "
                + (
                    "The report marks its target evidence gate as supported. "
                    if target.get("supported") is True
                    else "The report does not support the target evidence gate. "
                )
            )
            if target.get("same_strategy") is False:
                lines.append(
                    "That research tests a different strategy. It cannot validate this Fusion factor rule."
                )
        proposal = _mapping(result.get("proposal"))
        if proposal:
            lines.append(
                f"The sizing draft for {_label(proposal.get('symbol'))} has quantity "
                f"{_number(proposal.get('quantity')) if _number(proposal.get('quantity')) is not None else 'unknown'}, "
                f"cash required {_cash(proposal.get('cash_required'), '')}, and planned stop loss "
                f"{_cash(proposal.get('planned_loss_at_stop'), '')} in its quote currency. "
                "A blocked draft has not passed the checks; copying it to a form does not approve it."
            )
        lines.append(
            "This is a deterministic role pipeline on caller-supplied evidence. "
            "No AutoHedge LLM was invoked and no order was submitted. A research gate cannot guarantee future wins."
        )
        return (
            "\n".join(lines),
            ["supplied council decision, risk checks and target evidence"],
            ["Explain the factors", "Review the backtest", "Explain my risk"],
        )

    @staticmethod
    def _factors(context: Mapping, question: str):
        result = _mapping(context.get("factor_analysis"))
        if not result:
            return (
                "No factor analysis was supplied. Load completed OHLCV candles and run the Quant lab diagnostics. "
                "Momentum, RSI, trend, volume and volatility describe that history; a condition score is not a win probability.",
                [],
                ["Review the backtest", "Explain the council"],
            )
        signal = _mapping(result.get("signal"))
        lines = [
            f"For {_label(result.get('symbol'))}, the supplied factor stance is {_label(signal.get('stance'))}. "
            f"Rule-agreement score: {_percent(signal.get('score'), True)}. This score counts fixed conditions; "
            "it is not a probability of a profitable trade."
        ]
        conditions = signal.get("conditions")
        if isinstance(conditions, (list, tuple)):
            for raw in conditions[:8]:
                row = _mapping(raw)
                status = (
                    "met"
                    if row.get("passed") is True
                    else "not met" if row.get("passed") is False else "unknown"
                )
                lines.append(f"- {_label(row.get('name'))}: {status}.")
        factors = result.get("factors")
        if isinstance(factors, (list, tuple)):
            for raw in factors[:8]:
                row = _mapping(raw)
                value = _number(row.get("value"))
                rendered = (
                    _percent(value, True)
                    if row.get("unit") == "fraction"
                    else f"{value:.4g}" if value is not None else "unknown"
                )
                lines.append(f"{_label(row.get('label', row.get('id')))}: {rendered}.")
        lines.append(
            "These Vibe-derived indicators use supplied completed bars. Any replay is historical, "
            "with next-open fills and estimated costs; independent forward evidence is still required."
        )
        return (
            "\n".join(lines),
            ["supplied factor values and explicit entry conditions"],
            ["Why did the council wait?", "Review the backtest"],
        )

    @staticmethod
    def _scenario(context: Mapping, question: str):
        result = _mapping(context.get("scenario"))
        if not result or result.get("mode") != "hypothetical_stress":
            return (
                "No hypothetical portfolio stress result was supplied. Record paper positions and run a shock in Scenario lab. "
                "The calculation changes supplied marks and keeps cash fixed; it does not predict market behavior or run MiroFish.",
                [],
                ["Show my portfolio", "Explain my risk"],
            )
        currency = result.get("quote_currency", context.get("currency"))
        prefix = (
            currency.upper() + " "
            if isinstance(currency, str) and re.fullmatch(r"[A-Za-z0-9]{2,12}", currency)
            else ""
        )
        lines = [
            f"The supplied hypothetical shock is {_percent(result.get('effective_shock_pct'))}. "
            f"Equity changes from {_cash(result.get('baseline_equity'), prefix)} to {_cash(result.get('stressed_equity'), prefix)}; "
            f"stress P&L {_cash(result.get('pnl'), prefix)} ({_percent(result.get('return_pct'))})."
        ]
        if not prefix:
            lines.append(
                "The scenario's quote currency was not supplied; no currency conversion is implied."
            )
        positions = result.get("positions")
        if isinstance(positions, (list, tuple)) and not positions:
            lines.append(
                "No positions were open in this scenario, so the price shock leaves cash unchanged."
            )
        assumptions = result.get("assumptions")
        if isinstance(assumptions, (list, tuple)):
            lines.extend(_label(item) for item in assumptions[:4])
        lines.append(
            "This is a sensitivity calculation on manual paper marks, not a forecast, "
            "a probability estimate, a stop fill or a MiroFish agent simulation. The journal was not changed."
        )
        return (
            "\n".join(lines),
            ["supplied hypothetical stress result and assumptions"],
            ["Show my portfolio", "Explain my risk", "What should I do next?"],
        )

    @staticmethod
    def _learning(context: Mapping, question: str):
        report = _mapping(context.get("market_learning"))
        intro = ("Loki's historical learner fits a small regularized logistic model to past daily returns. "
                 "Features use only earlier observations, and scaling and weights use training dates only. "
                 "Validation and test dates do not fit or tune the model. The public source is the "
                 "CC BY 4.0 Open Crypto Pricing factor series; it needs no account or API key. ")
        if not report:
            return (intro + "No training report was supplied. Use Fetch history & train in Quant lab, "
                    "or the offline trainer for a larger licensed return CSV. This does not fine-tune "
                    "the conversational assistant or establish a trading edge.", [], ["What evidence do I need for a 70% win rate?"])
        train, test = _mapping(report.get("training")), _mapping(report.get("test"))
        text = (intro + f"The supplied report covers {_label(report.get('observations'))} dated observations, "
                f"with {_label(train.get('examples'))} training examples through {_label(train.get('end'))}. "
                f"Later test direction accuracy is {_percent(test.get('direction_accuracy'), True)} "
                f"across {_label(test.get('examples'))} predictions; the training-majority baseline scores "
                f"{_percent(test.get('training_majority_baseline_accuracy'), True)}. "
                "Direction accuracy is not a completed-trade win rate. This report proves neither "
                "profitability nor 70% winning trades. Retrospective data revisions and factor design "
                "can bias these exploratory results. The model cannot place orders.")
        return text, ["supplied historical-learning report; provenance and availability are not independently authenticated by chat"], ["Explain the trading strategy", "What should I test next?"]

    @staticmethod
    def _pullback(context: Mapping, question: str):
        report = _mapping(context.get("pullback_research"))
        introduction = ("The pullback hypothesis looks for an oversold close below its 20-bar band "
                        "while remaining above its 100-close average. Three fixed RSI/band/ATR recipes "
                        "compete on earlier training prices. Positive net expectancy, enough trades and "
                        "positive doubled-cost training return are required; otherwise it selects cash. "
                        "The selected recipe is held fixed on later test prices. Entries fill at the "
                        "next open, and ambiguous stop/target bars take the stop first.")
        if not report:
            return (introduction + " No pullback test result was supplied. Run the candidate test on "
                    "at least 260 ordered bars. No 70% winning-trade rate or market edge is established.",
                    [], ["Explain my risk", "Review the backtest"])
        body, evidence, _ = LokiCopilot._lab_backtest(report)
        body = body.replace("Reported Strategy Lab result:", "Reported pullback train/test result:")
        return (introduction + "\n\n" + body + "\nFresh holdout provenance has not been verified. "
                "Repeatedly changing recipes after inspecting test results can overfit.",
                evidence, ["Explain my risk", "Can you guarantee 70%?"])

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
            requested = context.get("requested_symbols", [])
            q = _normal_question(question)
            focus = bool(requested) and (
                bool(re.search(r"\b(it|its|that|what about)\b", q))
                or any(
                    re.search(r"(?<![\w/])" + re.escape(str(symbol)) + r"(?![\w/])", question, re.I)
                    for symbol in requested
                )
            )
            shown = {
                symbol: raw
                for symbol, raw in positions.items()
                if not focus or _symbol(symbol) in requested
            }
            lines.append(
                f"Open positions: {len(positions)}."
                + (" Showing the requested instrument(s)." if focus else "")
            )
            evidence.append("positions and available price snapshot")
            if focus and not shown:
                lines.append("No open position was supplied for " + ", ".join(requested) + ".")
            for symbol, raw in list(shown.items())[:8]:
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
            if len(shown) > 8:
                lines.append(f"{len(shown) - 8} more positions are listed in the Positions tab.")
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
                f"Position preview only: quantity {quantity:g}; "
                if quantity is not None
                else "Position preview only: quantity unknown; "
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
            return (
                body,
                ["supplied position sizing preview"],
                ["Review the backtest", "Show my portfolio"],
            )
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
            lines.append(
                "The guard reports no active halt; this does not establish that all risks are acceptable."
            )
        equity = _number(metrics.get("equity"))
        values = []
        missing_quotes = 0
        missing_stops = 0
        for symbol, raw in positions.items():
            position = _mapping(raw)
            qty = _number(position.get("quantity"))
            quote = _number(prices.get(symbol))
            stop = _number(position.get("stop_loss"))
            exposure = (
                _number(abs(qty * quote))
                if qty is not None and quote is not None and quote > 0
                else None
            )
            if exposure is None:
                missing_quotes += 1
            else:
                values.append((str(symbol), exposure))
            if stop is None or stop <= 0:
                missing_stops += 1
        if values and equity is not None and equity > 0:
            symbol, largest = max(values, key=lambda item: item[1])
            qualifier = "partial " if missing_quotes else ""
            total_pct = _number(sum(value for _, value in values) / equity * 100)
            largest_pct = _number(largest / equity * 100)
            if total_pct is not None and largest_pct is not None:
                lines.append(
                    f"Quoted {qualifier}gross exposure: {total_pct:.1f}% "
                    f"of equity. Largest quoted holding: {_label(symbol)} at {largest_pct:.1f}%."
                )
                evidence.append("derived from quantities × supplied prices ÷ equity")
            else:
                lines.append(
                    "Exposure is unknown because the supplied values exceed the supported numeric range."
                )
        if missing_quotes:
            lines.append(
                f"Exposure is incomplete: {missing_quotes} position(s) lack a valid quantity or quote."
            )
        if missing_stops:
            lines.append(
                f"{missing_stops} position(s) have no valid stop in the supplied snapshot."
            )
        requested = context.get("requested_symbols", [])
        if requested:
            for requested_symbol in requested[:4]:
                position = _mapping(positions.get(requested_symbol))
                if not position:
                    continue
                qty = _number(position.get("quantity"))
                stop = _number(position.get("stop_loss"))
                quote = _number(prices.get(requested_symbol))
                if (
                    qty is not None
                    and qty > 0
                    and quote is not None
                    and quote > 0
                    and stop is not None
                    and 0 < stop < quote
                ):
                    lines.append(
                        f"{requested_symbol}: supplied-price distance to its recorded stop is "
                        f"{(quote - stop) / quote:.1%}; the marked decline to that stop is "
                        f"{_cash(qty * (quote - stop))} before execution costs and gaps. "
                        "This is not the original entry risk or a guaranteed maximum loss."
                    )
                    evidence.append("requested position quantity, quote and recorded stop")
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
            return (
                "No account performance was supplied. Research results follow.\n" + body,
                evidence,
                suggestions,
            )
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
            lines.append(
                "There are no completed trades to estimate a win rate, profit factor or trade expectancy."
            )
        else:
            count_label = str(closed) if closed is not None else "unknown"
            lines.append(
                f"Completed trades: {count_label}; observed win rate {_percent(metrics.get('win_rate'))}."
            )
            win_rate = _number(metrics.get("win_rate"))
            avg_win = _number(metrics.get("avg_win"))
            avg_loss = _number(metrics.get("avg_loss"))
            if (
                closed
                and win_rate is not None
                and 0 <= win_rate <= 100
                and avg_win is not None
                and avg_win >= 0
                and avg_loss is not None
                and avg_loss >= 0
            ):
                expectancy = win_rate / 100 * avg_win - (1 - win_rate / 100) * avg_loss
                lines.append(f"Reported trade expectancy: {_cash(expectancy)} per completed trade.")
                evidence.append("expectancy = win share × average win − loss share × average loss")
            if losses == 0 and wins:
                lines.append(
                    "No observed losing trades: profit factor is not reliably estimable from this sample."
                )
            else:
                pf = _number(metrics.get("profit_factor"))
                if pf is not None and pf >= 0:
                    lines.append(
                        f"Reported profit factor: {pf:.2f} (gross gains divided by gross losses)."
                    )
            if closed is None or closed < 100:
                lines.append(
                    "The completed-trade sample is limited; the observed win rate is not a reliable future probability."
                )
        lines.append(
            "Assess win size and loss size alongside win rate. Verify the cost accounting "
            "and compare with unseen-data and paper-trading results before drawing conclusions."
        )
        return (
            "\n".join(lines),
            evidence,
            ["Review the backtest", "Explain my risk", "Can you guarantee 70%?"],
        )

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
            return (
                body,
                ["Strategy Lab rule definitions and supplied research settings"],
                [
                    "Review the backtest",
                    "Explain my risk",
                    "Show my performance",
                ],
            )
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
        requested = context.get("requested_symbols", [])
        if isinstance(requested, (tuple, list)) and len(requested) > 1:
            bodies, evidence = [], []
            for symbol in requested[:4]:
                single = dict(context, requested_symbols=[symbol])
                body, sources, _ = LokiCopilot._signal(single, "")
                bodies.append(body)
                evidence.extend(sources)
            return (
                "\n\n".join(bodies),
                list(dict.fromkeys(evidence)),
                ["Explain my risk", "Compare strategies"],
            )
        prices = _mapping(context.get("current_prices", context.get("prices")))
        positions = _mapping(context.get("positions"))
        selected = _label(context.get("symbol"))
        supplied_symbols = context.get("requested_symbols", [])
        requested = supplied_symbols[0] if supplied_symbols else selected
        candidates = sorted(
            {str(key) for key in prices} | {str(key) for key in positions}, key=len, reverse=True
        )
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
        evidence = (
            ["supplied instrument price"] if _number(prices.get(requested)) is not None else []
        )
        if not signal:
            lines.append(
                "No signal was supplied for this instrument. That is missing evidence, not an instruction to buy or sell."
            )
        else:
            action = _label(signal.get("action"))
            confidence = _number(signal.get("confidence"))
            score = (
                _percent(confidence, True)
                if confidence is not None and 0 <= confidence <= 1
                else "unknown"
            )
            lines.append(f"Reported action: {action}; rule-agreement score: {score}.")
            lines.append(
                f"Strategy's stated reason: {_label(signal.get('reason'), 'not supplied')}."
            )
            evidence.append("latest strategy signal snapshot")
            entry = _number(signal.get("entry_price"))
            stop = _number(signal.get("stop_loss"))
            target = _number(signal.get("take_profit"))
            if entry is not None:
                lines.append(
                    f"Reference entry {_cash(entry)}; stop {_cash(stop)}; target {_cash(target)}."
                )
                if (
                    action.upper() == "BUY"
                    and stop is not None
                    and target is not None
                    and 0 < stop < entry < target
                ):
                    lines.append(
                        f"Planned reward/risk: {(target - entry) / (entry - stop):.2f}:1 before costs and gaps."
                    )
                    evidence.append("derived from supplied entry, stop and target")
            lines.append(
                "The score is not a probability of profit. This explanation does not execute a trade."
            )
        return (
            "\n".join(lines),
            evidence,
            ["Explain my risk", "Explain the strategy", "Review the backtest"],
        )

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
        return (
            "\n".join(lines),
            ["supplied backtest result"],
            ["Explain my risk", "Can you guarantee 70%?"],
        )

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
            lines.append(
                f"Reported buy-and-hold benchmark return: {_percent(benchmark.get('total_return'), True)}."
            )
        fee, slippage = _number(config.get("fee_bps")), _number(config.get("slippage_bps"))
        if fee is not None and slippage is not None:
            lines.append(
                f"Configured costs per side: {fee:g} bps fees plus {slippage:g} bps slippage."
            )
        lines.append(f"Research status: {_label(result.get('status'))}.")
        reasons = result.get("rejection_reasons")
        if isinstance(reasons, (list, tuple)):
            lines.extend(f"- {_label(reason)}" for reason in reasons[:4])
        lines.append(
            "This report uses the supplied historical research data; its provenance "
            "is not independently verified. A paper candidate is not a future-profit "
            "guarantee or approval to trade live."
        )
        return (
            "\n".join(lines),
            ["supplied Strategy Lab summary, benchmark and research settings"],
            [
                "Explain the strategy",
                "Explain my risk",
                "Can you guarantee 70%?",
            ],
        )
