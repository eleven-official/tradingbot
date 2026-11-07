"""Loki's conversational brain, shared by "Talk to Loki" and the chat room.

No external language model: every answer is assembled from real inputs —
the live AI engine's read for a symbol (the same checklist the paper trader
uses), live public quotes, the shipped 20-year track record, and a plain-
English trading glossary. When the brain has nothing confident to say it
returns None and the caller falls back to its own logic.

Nothing here places orders or gives personal advice.
"""

from __future__ import annotations

import logging
import random
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

FOOTER = "Research, not financial advice — Loki never places orders."

# --- symbol detection ---------------------------------------------------------
NAMES: Dict[str, str] = {
    "bitcoin": "BTC-USD", "btc": "BTC-USD", "ethereum": "ETH-USD", "ether": "ETH-USD", "eth": "ETH-USD",
    "solana": "SOL-USD", "sol": "SOL-USD", "dogecoin": "DOGE-USD", "doge": "DOGE-USD", "ripple": "XRP-USD",
    "xrp": "XRP-USD", "cardano": "ADA-USD", "litecoin": "LTC-USD", "chainlink": "LINK-USD", "bnb": "BNB-USD",
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "amazon": "AMZN", "google": "GOOGL",
    "alphabet": "GOOGL", "meta": "META", "facebook": "META", "tesla": "TSLA", "netflix": "NFLX", "amd": "AMD",
    "jpmorgan": "JPM", "exxon": "XOM", "gold": "GLD", "bonds": "TLT", "treasuries": "TLT",
    "s&p": "SPY", "s&p 500": "SPY", "sp500": "SPY", "the s&p": "SPY", "nasdaq": "QQQ", "dow": "DIA",
    "russell": "IWM", "small caps": "IWM",
}
NOT_TICKERS = {
    "I", "A", "AI", "OK", "US", "USA", "CEO", "IPO", "ETF", "ETFS", "ATR", "RSI", "MACD", "SMA", "EMA", "PNL",
    "THE", "AND", "FOR", "YOU", "ARE", "IS", "IT", "ME", "MY", "DO", "TO", "IN", "ON", "AT", "OF", "OR", "BE",
    "WHAT", "HOW", "WHY", "WHO", "BUY", "SELL", "HOLD", "LOKI", "HI", "HEY", "YES", "NO", "PF", "DD", "VS",
    "FED", "CPI", "GDP", "USD", "EUR", "AUD", "TP", "SL", "FOMO", "YOLO", "LOL", "OMG", "PM", "AM", "UTC", "ET",
}
_PAIR = re.compile(r"\b([A-Za-z]{2,6})\s*[/-]\s*(USDT|USDC|USD)\b", re.I)
_DOLLAR = re.compile(r"\$([A-Za-z]{1,5})\b")
_UPPER = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z])?)\b")


def detect_symbols(text: str) -> List[str]:
    """Engine-format symbols named in a message (most specific first)."""
    found: List[str] = []

    def add(sym: str) -> None:
        if sym and sym not in found:
            found.append(sym)

    for base, _quote in _PAIR.findall(text):
        add(f"{base.upper()}-USD")
    for sym in _DOLLAR.findall(text):
        add(NAMES.get(sym.lower(), sym.upper()))
    low = f" {text.lower()} "
    for name in sorted(NAMES, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", low):
            add(NAMES[name])
    for token in _UPPER.findall(text):
        if token not in NOT_TICKERS and not any(token in f for f in found):
            add(NAMES.get(token.lower(), token))
    return found[:3]


# --- glossary -----------------------------------------------------------------
GLOSSARY: Dict[Tuple[str, ...], str] = {
    ("stop loss", "stop-loss", "stoploss", "stop order"): "A stop loss is a pre-set exit price below your entry (for a long). If price falls there, you sell and cap the loss. Loki's AI sets its stop in ATR units — a multiple of the asset's normal daily range — so a jumpy asset gets a wider stop than a calm one. Stops can slip in fast markets or overnight gaps.",
    ("take profit", "profit target", "target price"): "A take-profit is a pre-set exit above entry that banks a gain. Loki's current stock rules deliberately use no fixed target: winners are held until the trend breaks (price closes below its 200-day average), because cutting winners short was the old model's biggest weakness.",
    ("atr", "average true range"): "ATR (Average True Range) is the typical size of a day's price swing, averaged over ~14 days. It's Loki's ruler: stops, targets and the volatility cap are all measured in ATRs so the same rule fits a sleepy ETF and a wild coin.",
    ("rsi", "relative strength index"): "RSI scores recent up-moves against down-moves on a 0-100 scale. Above ~70 is often called overbought, below ~30 oversold. In Loki it is one small input to the momentum factor — never a trigger on its own.",
    ("macd",): "MACD compares a fast and a slow moving average of price. When the fast one rises above the slow one, momentum is turning up. Loki uses MACD as one vote inside its momentum factor.",
    ("moving average", "200-day", "200 day", "sma", "ema"): "A moving average is the average closing price over the last N days. The 200-day average is the classic long-term trend line: above it, the trend is up. Loki's AI only buys above it, and for stocks it exits when price closes back below it.",
    ("drawdown", "max drawdown"): "Drawdown is how far an account falls from its previous peak before recovering. A −20% drawdown means $10,000 dipped to $8,000 at its worst. Loki optimises to keep drawdowns smaller than simply holding — over 2023-26 its average worst drop was about −21% on stocks versus −27% for buy-and-hold.",
    ("sharpe", "sharpe ratio"): "The Sharpe ratio is return divided by volatility — return per unit of bumpiness. Above 1 is strong for a single strategy. Loki selects its rules on Sharpe (with a drawdown penalty) rather than raw profit, because raw profit rewards luck.",
    ("profit factor",): "Profit factor = total money won ÷ total money lost. Above 1 means the strategy made money; 2 means it won twice what it lost. A high profit factor with few trades is weak evidence, so Loki also reports trade counts.",
    ("win rate", "hit rate"): "Win rate is the share of trades that made money. It's overrated: a strategy winning 35% of the time can be very profitable if winners are big and losers are cut fast — that's how Loki's trend rules work.",
    ("position size", "position sizing", "how much should i buy", "how much to buy"): "Position sizing decides how much to buy. Loki's AI uses volatility targeting: it sizes each position so it swings about 20% a year, capped at 100% of the account — a calm ETF gets a bigger position, a volatile coin a smaller one. That keeps risk steady across assets.",
    ("volatility", "vol target", "volatility targeting"): "Volatility is how much a price jumps around, usually annualised. Volatility targeting sizes positions inversely to it, so every trade carries roughly the same risk. It was the single biggest upgrade over the old AI, which left ~90% of the account idle.",
    ("trend following", "trend-following", "trend"): "Trend following buys what's already rising and steps aside when it stops. It loses small and often in choppy markets but catches big moves and dodges long crashes. Loki's stock AI is a trend follower: strong trend score to enter, 200-day break to exit.",
    ("backtest", "backtesting"): "A backtest replays a strategy on historical prices to see how it would have done. They're easy to fool yourself with, so Loki chooses rules on 2005-2022 only and judges them once on 2023 onward — data the training never touched.",
    ("overfitting", "overfit", "curve fit"): "Overfitting is tuning a strategy so precisely to the past that it fails on new data. Loki fights it by fitting one rulebook across 13 stocks/ETFs (not one per symbol), choosing on the worse of two time windows, and reporting an untouched holdout.",
    ("holdout", "out of sample", "out-of-sample"): "Out-of-sample (holdout) data is history the model never saw while being built. Loki's holdout is 2023 to today; the AI's rules were frozen before looking at it, so its results there are the honest test.",
    ("slippage",): "Slippage is the difference between the price you expected and the price you got. Loki charges 5 basis points (0.05%) of slippage plus 10 bps of fees on every buy and sell in its tests.",
    ("paper trading", "paper trade", "paper money"): "Paper trading means simulated money with real prices — practice with no risk. Loki's AI trading page runs the AI on a paper account in your browser; no real orders are ever sent from it.",
    ("short", "shorting", "short selling"): "Shorting means borrowing and selling an asset to profit if it falls. Loki's paper AI is long-only: in a downtrend it simply sits in cash.",
    ("leverage", "margin"): "Leverage means trading with borrowed money, magnifying both gains and losses. Loki's AI never uses leverage — exposure is capped at 100% of the account.",
    ("diversification", "diversify"): "Diversification is spreading money across assets that don't move together, so one bad bet can't sink the account. Holding several uncorrelated trend positions smooths returns far more than any single one.",
    ("etf",): "An ETF (exchange-traded fund) is a basket of assets that trades like one stock — SPY holds the S&P 500, QQQ the Nasdaq-100, GLD gold. Loki's stock AI was trained on 13 major ETFs and stocks.",
    ("bull market", "bear market", "bull", "bear", "regime"): "A bull market is a sustained uptrend, a bear market a sustained downtrend (often −20% or more). Loki classifies every day into STRONG_BULL, BULL, RANGING, BEAR or CRISIS from its trend and volatility, and blocks new buys in bear regimes.",
    ("crypto", "cryptocurrency"): "Crypto trades 24/7 and is roughly 3-4× as volatile as stocks. Loki trains a separate rulebook for it; over 2023-26 it averaged about +9% a year with a −29% average worst drop, against −71% for just holding coins.",
    ("expectancy",): "Expectancy is the average profit per trade (wins and losses combined). Positive expectancy after costs is the only thing that makes a strategy worth running.",
    ("candle", "candlestick"): "A candlestick shows one period's open, high, low and close. Green means it closed above the open, red below. Loki's AI decides on completed daily candles only — never on today's still-forming one.",
    ("alpaca",): "Alpaca is a US broker with a free paper-trading API. In Loki's AI trading page you can paste your Alpaca paper keys (they stay in your browser) to see your account and send clicked paper orders.",
    ("tradovate",): "Tradovate is a futures broker used by many funded-account firms. Loki can connect read-only to view your balances and positions — sign in with your Tradovate API credentials and only the issued token is kept, encrypted.",
}


def _glossary(text: str) -> Optional[str]:
    low = text.lower()
    best: Tuple[int, Optional[str]] = (0, None)
    for keys, body in GLOSSARY.items():
        for k in keys:
            if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", low) and len(k) > best[0]:
                best = (len(k), body)
    return best[1]


# --- intents ------------------------------------------------------------------
_GREETING = re.compile(r"^\s*(hi|hey|hello|yo|sup|gm|good (morning|afternoon|evening)|howdy|hiya)\b[\s!.,?]*", re.I)
_THANKS = re.compile(r"\b(thanks|thank you|thx|cheers|appreciate it)\b", re.I)
_HELP = re.compile(r"\b(help|what can you do|how do i use|commands|what do you do)\b", re.I)
_IDENTITY = re.compile(r"\b(who are you|what are you|are you (an? )?(ai|bot|human|real))\b", re.I)
_TRACK = re.compile(r"\b(track record|historic\w*|history|backtest(ed|s)?|profitab\w*|how (good|well)|how did|performance|results?|win rate|returns?|proof|make money|making money)\b", re.I)
_HOW_AI = re.compile(r"\b(how (does|do) (the |your )?(ai|you|loki|model) (work|trade|decide|think|learn)|learn(s|ing)? from (its |your )?mistakes|explain (the |your )?(ai|model))\b", re.I)
_ORDER = re.compile(r"^\s*(please\s+)?(buy|sell|short|close|place|submit|execute)\b", re.I)
_MARKET = re.compile(r"\b(market(s)? (today|now|doing|look)|how('s| is) the market|what('s| is) moving|movers|market overview|market update|the tape)\b", re.I)
_ADVICE = re.compile(r"\b(should i|can i|is it (a )?good (time|idea)|worth (buying|it)|buy|sell|invest|entry|enter|think of|thoughts on|opinion|analy[sz]e|read on|outlook|what about|look(s|ing)? (at|good)|forecast|predict)\b", re.I)
_ASK_AI_DEFINE = re.compile(r"\b(what('s| is| are)|explain|define|meaning of|tell me about)\b", re.I)


def _pick(options: List[str]) -> str:
    return random.choice(options)


# --- data access (lazy imports keep startup light; tests patch these) ---------
def _ai_read(symbol: str) -> Optional[Dict[str, Any]]:
    from fastapi import HTTPException

    from loki.api import ai_paper

    try:
        analysis = ai_paper._analyze(symbol)
    except HTTPException:
        return None
    except Exception as exc:  # noqa: BLE001 - chat must never 500 on a data blip
        logger.warning("brain AI read failed for %s: %s", symbol, exc.__class__.__name__)
        return None
    cfg = ai_paper._get_pipeline(symbol)[1]
    return {"analysis": analysis, "cfg": cfg, "source": ai_paper._PROFILE_SOURCE.get(symbol, "default")}


def _quotes(symbols: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    from loki.api.market_feed import quote_or_failure

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(symbols)))) as pool:
        return list(pool.map(lambda s: quote_or_failure(s[0], s[1], 15.0), symbols))


def _portfolio() -> Optional[Dict[str, Any]]:
    from fastapi import Response

    from loki.api import ai_paper

    try:
        return ai_paper.ai_portfolio(Response())
    except Exception as exc:  # noqa: BLE001 - chat must never 500 on a data blip
        logger.warning("brain portfolio read failed: %s", exc.__class__.__name__)
        return None


def _universal() -> Dict[str, Any]:
    from loki_v8.train import load_report

    return (load_report() or {}).get("universal") or {}


# --- answer builders ----------------------------------------------------------
def _pct(v: Any) -> str:
    try:
        return f"{float(v):+.1f}%"
    except (TypeError, ValueError):
        return "—"


def _symbol_record(symbol: str) -> Optional[str]:
    uni = _universal()
    for kind in ("equity", "crypto"):
        for row in (uni.get(kind) or {}).get("holdout") or []:
            if row.get("symbol") == symbol and row.get("strategy"):
                s, b = row["strategy"], row.get("buy_hold") or {}
                return (f"On the untouched 2023→now test, the AI's rules made {_pct(s.get('cagr_pct'))} a year on {symbol} "
                        f"over {s.get('trades')} trades (worst drop {_pct(s.get('max_dd_pct'))}), versus {_pct(b.get('cagr_pct'))} "
                        f"a year and {_pct(b.get('max_dd_pct'))} worst drop for simply holding it.")
    return None


GATE_TEXT = {
    "signal": ("the signal is strong enough", "the signal isn't strong enough yet"),
    "volatility_cap": ("volatility is within limits", "volatility is above the cap"),
    "trend_filter": ("price is above its 200-day average (uptrend)", "price is below its 200-day average (no uptrend)"),
    "regime_filter": ("the market regime allows buying", "it's in a bear regime, so new buys are blocked"),
    "learned_filter": ("it doesn't look like the AI's past losing setups", "it looks too much like the AI's past losing trades"),
}


def explain_symbol(symbol: str, name: str = "") -> Optional[str]:
    read = _ai_read(symbol)
    if not read:
        return None  # caller falls back to its own quote/headline answer
    a, cfg = read["analysis"], read["cfg"]
    plan = a.get("plan") or {}
    regime = (a.get("regime") or "unknown").replace("_", " ").lower()
    lines = [f"Here's the AI's live read on {symbol} at {a['price']:,.2f}:"]
    if not plan.get("ready"):
        lines.append(f"It needs about {plan.get('bars_needed', 251)} days of history before it will trade this one, and only has {plan.get('bars', 0)}.")
    else:
        score, thr = plan.get("score"), plan.get("threshold")
        lines.append(f"• Market regime: {regime}. Trend score {score:+.0f} against an entry bar of {thr:.0f}.")
        passed = [GATE_TEXT.get(g["name"], (g["name"], g["name"]))[0] for g in plan.get("gates", []) if g["passed"]]
        failed = [GATE_TEXT.get(g["name"], (g["name"], g["name"]))[1] for g in plan.get("gates", []) if not g["passed"]]
        if plan.get("action") == "SELL":
            failed = ["its trend score is negative" if f == GATE_TEXT["signal"][1] else f for f in failed]
        if plan.get("allowed"):
            vol = plan.get("ann_vol") or 0
            exposure = min(cfg.max_exposure_pct, cfg.target_vol_pct / vol * 100) if vol > 0 else None
            lines.append("• Verdict: BUY setup — every check passes (" + "; ".join(passed) + ").")
            if exposure:
                lines.append(f"• It would put about {exposure:.0f}% of a paper account in, with a protective stop "
                             f"{cfg.stop_loss_atr:g} ATR below entry" + (", holding until price breaks its 200-day average." if cfg.exit_mode == "trend" else "."))
        else:
            verdict = "WAIT — it would not buy right now"
            if plan.get("action") == "SELL":
                verdict = "STAND ASIDE — momentum is pointing down"
            lines.append(f"• Verdict: {verdict}, because " + "; and ".join(failed) + ".")
            if passed:
                lines.append("• On the plus side: " + "; ".join(passed) + ".")
        wp = plan.get("win_probability")
        if wp is not None:
            lines.append(f"• Its learned-from-mistakes filter says setups like today's won about {wp * 100:.0f}% of the time historically.")
    record = _symbol_record(symbol)
    if record:
        lines.append(record)
    if read["source"] == "universal_long_history":
        lines.append("These rules were trained on up to 20 years of history and checked on data they never saw.")
    lines.append(FOOTER)
    return "\n".join(lines)


def market_overview() -> str:
    basket = [("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("BTC/USDT", "Bitcoin"), ("ETH/USDT", "Ethereum"),
              ("GC=F", "Gold"), ("^VIX", "VIX (fear gauge)"), ("CL=F", "Oil")]
    rows = [r for r in _quotes(basket) if r.get("ok")]
    if not rows:
        return "The market feeds aren't answering right now — give it a minute and ask again."
    parts = [f"{r['label']} {r['price']:,.2f} ({_pct(r.get('change_pct'))})" for r in rows]
    movers = sorted([r for r in rows if isinstance(r.get("change_pct"), (int, float))], key=lambda r: abs(r["change_pct"]), reverse=True)
    lead = ""
    if movers:
        m = movers[0]
        lead = f" Biggest mover in this basket: {m['label']} at {_pct(m['change_pct'])}."
    vix = next((r for r in rows if r["symbol"] == "^VIX"), None)
    mood = ""
    if vix:
        mood = (" Fear is elevated (VIX above 25)." if vix["price"] > 25 else
                " Markets are calm (VIX under 15)." if vix["price"] < 15 else " Fear is moderate.")
    return ("Quick market check: " + " · ".join(parts) + "." + lead + mood +
            " Open Live markets for the full board, or name any ticker and I'll run the AI on it.\n" + FOOTER)


def track_record() -> str:
    uni = _universal()
    eq, cr = (uni.get("equity") or {}), (uni.get("crypto") or {})
    if not eq and not cr:
        return "The 20-year track record isn't loaded on this server yet."
    out = ["Honest numbers. The AI's rules were chosen using 2005-2022 only, then tested once on 2023→now — data they never saw — after fees and slippage:"]
    for label, b in (("Stocks/ETFs", eq), ("Crypto", cr)):
        p = b.get("holdout_pooled") or {}
        if p:
            out.append(f"• {label}: {_pct(p.get('mean_cagr_pct'))} a year on average, profitable on {p.get('profitable_symbols')} of "
                       f"{p.get('symbols')} symbols, average worst drop {_pct(p.get('mean_max_dd_pct'))}. Simply holding the same "
                       f"assets: {_pct(p.get('buy_hold_mean_cagr_pct'))} a year with {_pct(p.get('buy_hold_mean_max_dd_pct'))} worst drop.")
    out.append("So: it makes money on unseen data and crashes far less, but it trailed buy-and-hold in the very strong 2023-26 bull run. Past results never guarantee the next trade.")
    return "\n".join(out)


def how_ai_works() -> str:
    uni = _universal()
    meta = ((uni.get("equity") or {}).get("learning_from_mistakes") or {})
    learn = ("It also learns from its mistakes: I replayed its 20 years of trades, recorded the conditions at every entry, and trained a "
             f"model on which setups turned into losses. It now skips setups that historically won less than {round(meta.get('threshold', 0.3) * 100)}% "
             f"of the time — learned from {meta.get('lessons_final', 'hundreds of')} past trades, and kept only because it also held up on unseen data."
             if meta.get("kept") else
             "It has a learn-from-mistakes filter trained on its own past losing trades; it's only switched on where it improved unseen results.")
    return ("How the AI trades, step by step:\n"
            "1. Every day it scores each market on trend, momentum, money flow, squeeze and volatility, using only finished candles.\n"
            "2. It only buys when the score clears a high bar AND price is above its 200-day average AND the regime isn't bearish AND volatility isn't extreme.\n"
            "3. It sizes the position so it swings about 20% a year (never more than 100% of the account), and sets a wide protective stop.\n"
            "4. Stocks: it holds until price closes below the 200-day average. Crypto: it exits when the signal turns to SELL.\n"
            f"5. {learn}\n"
            "Ask 'how did the AI do?' for its track record, or name any ticker for a live read.\n" + FOOTER)


def portfolio_answer() -> str:
    uni = _universal().get("portfolio") or {}
    h, b = uni.get("holdout") or {}, uni.get("holdout_buy_hold") or {}
    lines = ["The Portfolio AI runs the verified strategy on 21 markets at once — 13 stocks/ETFs (including gold and bonds) "
             "and 8 coins — shares capital equally, scales the whole book to a steady risk level, and never holds more than 100% of the account."]
    if h:
        lines.append(f"On unseen 2023→now data it made {_pct(h.get('cagr_pct'))} a year with a Sharpe of {h.get('sharpe')} and a worst drop of "
                     f"{_pct(h.get('max_dd_pct'))}; holding all 21 equally made {_pct(b.get('cagr_pct'))} a year but fell {_pct(b.get('max_dd_pct'))} at worst.")
    plan = _portfolio()
    if plan and plan.get("positions"):
        held = [p for p in plan["positions"] if p.get("weight", 0) > 0]
        if held:
            lines.append(f"Right now (as of {plan.get('as_of')}) it holds " +
                         ", ".join(f"{p['symbol']} {p['weight'] * 100:.1f}%" for p in held[:8]) +
                         f", with {plan.get('cash', 0) * 100:.0f}% in cash.")
        else:
            lines.append("Right now every market is out of its uptrend, so it's fully in cash.")
    lines.append("Start it with paper money on the AI trading page.\n" + FOOTER)
    return "\n".join(lines)


_PORTFOLIO_Q = re.compile(r"\b(portfolio ai|portfolio|diversif\w*|all (the )?markets|what (is|are) (the ai|you|it) (holding|buying|in)|holdings|allocation)\b", re.I)


HELP_TEXT = ("Here's what I can do:\n"
             "• Name any ticker or coin — 'what about NVDA?', 'should I buy bitcoin?' — and I'll run the live AI on it and explain its decision.\n"
             "• 'How's the market?' for a quick live check across stocks, crypto, gold and the fear gauge.\n"
             "• 'How did the AI do?' for its honest 20-year track record, or 'how does the AI work?'.\n"
             "• 'What is the Portfolio AI holding?' — the 21-market book and its unseen-data record.\n"
             "• Ask what any trading term means — stop loss, ATR, drawdown, Sharpe, position sizing, trend following…\n"
             "I don't place orders or give personal financial advice — I explain what the data and the AI are saying.")


def answer(text: str, name: str = "", *, allow_data: bool = True, skip: Tuple[str, ...] = ()) -> Optional[Dict[str, Any]]:
    """Best answer for a message, or None to let the caller fall back.

    ``skip`` names intents the caller answers better itself (e.g. the chat
    room keeps its own greeting). Order commands always fall through so the
    caller's order-refusal path answers them.
    """
    msg = (text or "").strip()
    if not msg or _ORDER.match(msg):
        return None
    result = _answer(msg, name, allow_data)
    if result and result["intent"] in skip:
        return None
    return result


def _answer(msg: str, name: str, allow_data: bool) -> Optional[Dict[str, Any]]:
    who = f", {name}" if name else ""
    symbols = detect_symbols(msg)
    low = msg.lower()

    if _GREETING.match(msg) and len(msg.split()) <= 4 and not symbols:
        return {"intent": "greeting", "text": _pick([
            f"Hey{who}! I'm Loki. Name a ticker and I'll run the AI on it, ask how the market's doing, or ask me to explain any trading term.",
            f"Hi{who} — good to see you. Want a live market check, the AI's read on a stock or coin, or its track record?",
            f"Hello{who}! Ask me about any ticker (try 'what about NVDA?'), the market today, or how the AI works.",
        ])}
    if _THANKS.search(msg) and len(msg.split()) <= 6:
        return {"intent": "thanks", "text": _pick([f"Any time{who}!", f"Happy to help{who}. Anything else you want me to look at?",
                                                   f"You're welcome{who} — name another ticker whenever you like."])}
    if _IDENTITY.search(msg):
        return {"intent": "identity", "text": ("I'm Loki — the assistant for this trading workspace. I'm not a person and I'm not a general chatbot: "
                                               "I explain what the live market data and Loki's trading AI are saying, in plain English. " + HELP_TEXT.split('\n', 1)[1])}
    if _HELP.search(msg) and not symbols:
        return {"intent": "help", "text": HELP_TEXT}
    if allow_data and _PORTFOLIO_Q.search(msg) and not symbols and not re.search(r"\bmy\b", low):
        return {"intent": "portfolio", "text": portfolio_answer()}
    if _HOW_AI.search(msg):
        return {"intent": "how_ai", "text": how_ai_works()}
    if _TRACK.search(msg) and not symbols and re.search(r"\b(ai|loki|you|model|bot|strategy|it)\b", low):
        return {"intent": "track_record", "text": track_record() + "\n" + FOOTER}
    if allow_data and symbols and (_ADVICE.search(msg) or len(msg.split()) <= 4 or "?" in msg):
        replies = [r for r in (explain_symbol(s, name) for s in symbols[:2]) if r]
        if not replies:
            return None
        body = "\n\n".join(replies)
        if re.search(r"\bshould i\b", low):
            body = "I can't tell you what to do with your money, but here's exactly what the AI sees:\n" + body
        return {"intent": "symbol", "symbols": symbols[:2], "text": body}
    if allow_data and _MARKET.search(msg):
        return {"intent": "market", "text": market_overview()}
    term = _glossary(msg)
    if term and (_ASK_AI_DEFINE.search(msg) or len(msg.split()) <= 5 or "?" in msg):
        return {"intent": "glossary", "text": term + "\n" + _pick(["Want me to show how the AI uses it on a real ticker?",
                                                                   "Name a ticker and I'll show it in action.",
                                                                   "Anything else you'd like explained?"])}
    return None
