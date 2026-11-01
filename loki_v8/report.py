"""LOKI v8 — automated research report generation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import LokiConfig
from .crypto_paper import replay, load_book, profile_for
from .data import get_provider
from .learn import run_learning_cycle
from .portfolio import build_portfolio, PortfolioAllocation, print_allocation
from .stress import run_stress_test, monte_carlo_stress, PREDEFINED_SCENARIOS, print_stress_results
from .importance import compute_factor_importance, attribute_trades, aggregate_importance, print_importance, print_aggregated
from .journal import decision_accuracy, export_journal

logger = logging.getLogger(__name__)

STATE_DIR = Path("state") / "reports"
STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ResearchReport:
    """Complete research report."""
    title: str
    generated_at: str
    symbols: List[str]
    period: str
    timeframe: str
    capital: float

    # Strategy performance
    strategy_performance: Dict[str, Any] = field(default_factory=dict)

    # Portfolio construction
    portfolio: Optional[Dict[str, Any]] = None

    # Stress testing
    stress_results: List[Dict[str, Any]] = field(default_factory=list)
    monte_carlo: Optional[Dict[str, Any]] = None

    # Learning loop
    learning: Optional[Dict[str, Any]] = None

    # Feature importance
    feature_importance: Dict[str, Any] = field(default_factory=dict)
    trade_attributions: List[Dict[str, Any]] = field(default_factory=list)

    # Decision accuracy
    decision_stats: Dict[str, Any] = field(default_factory=dict)

    # Summary
    executive_summary: str = ""
    key_findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def generate_report(
    symbols: Optional[List[str]] = None,
    period: str = "3y",
    timeframe: str = "1d",
    capital: float = 100_000.0,
    include_stress: bool = True,
    include_monte_carlo: bool = True,
    include_learning: bool = True,
    include_importance: bool = True,
    include_journal: bool = True,
    title: Optional[str] = None,
) -> ResearchReport:
    """Generate a complete research report."""
    if symbols is None:
        from .train_crypto import DEFAULT_CRYPTO_UNIVERSE
        symbols = list(DEFAULT_CRYPTO_UNIVERSE)

    report = ResearchReport(
        title=title or f"Loki Research Report — {datetime.now().strftime('%Y-%m-%d')}",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        symbols=symbols,
        period=period,
        timeframe=timeframe,
        capital=capital,
    )

    provider = get_provider()

    # 1. Strategy Performance (paper replay)
    print("Running paper replay...")
    paper_result = replay(symbols, bars=180, capital=capital, period=period, timeframe=timeframe, write_ledger=False)
    report.strategy_performance = {
        "portfolio": paper_result.get("portfolio", {}),
        "symbols": paper_result.get("symbols", []),
        "total_trades": len(paper_result.get("trades", [])),
        "equity_curve": paper_result.get("equity_curve", []),
    }

    # 2. Portfolio Construction
    print("Building portfolio allocation...")
    try:
        allocation = build_portfolio(symbols, period="1y", timeframe=timeframe)
        report.portfolio = {
            "weights": allocation.weights,
            "cluster_exposures": allocation.cluster_exposures,
            "expected_return": allocation.expected_return,
            "expected_volatility": allocation.expected_volatility,
            "sharpe": allocation.sharpe,
            "max_drawdown_estimate": allocation.max_drawdown_estimate,
            "clusters": [
                {"assets": c.assets, "avg_correlation": c.avg_correlation, "representative": c.representative}
                for c in allocation.clusters
            ],
        }
    except Exception as e:
        logger.warning("Portfolio construction failed: %s", e)
        report.portfolio = {"error": str(e)}

    # 3. Stress Testing
    if include_stress and report.portfolio and "error" not in report.portfolio:
        print("Running stress tests...")
        try:
            from .portfolio import fetch_returns
            hist_returns = fetch_returns(symbols, "2y", timeframe)
            from .stress import run_stress_test
            from .portfolio import PortfolioAllocation
            alloc_obj = PortfolioAllocation(
                weights=report.portfolio["weights"],
                cluster_exposures=report.portfolio["cluster_exposures"],
                expected_return=report.portfolio["expected_return"],
                expected_volatility=report.portfolio["expected_volatility"],
                sharpe=report.portfolio["sharpe"],
                max_drawdown_estimate=report.portfolio["max_drawdown_estimate"],
                correlation_matrix=pd.DataFrame(),
                clusters=[],
                timestamp=report.generated_at,
            )
            stress = run_stress_test(alloc_obj, historical_returns=hist_returns)
            report.stress_results = [
                {
                    "scenario": r.scenario,
                    "portfolio_return": r.portfolio_return,
                    "portfolio_drawdown": r.portfolio_drawdown,
                    "worst_asset": r.worst_asset,
                    "worst_asset_return": r.worst_asset_return,
                    "var_95": r.var_95,
                    "var_99": r.var_99,
                    "cvar_95": r.cvar_95,
                    "max_leverage": r.max_leverage,
                    "timestamp": r.timestamp,
                }
                for r in stress
            ]
        except Exception as e:
            logger.warning("Stress testing failed: %s", e)
            report.stress_results = [{"error": str(e)}]

    # 4. Monte Carlo
    if include_monte_carlo and report.portfolio and "error" not in report.portfolio:
        print("Running Monte Carlo simulation...")
        try:
            from .stress import monte_carlo_stress
            from .portfolio import PortfolioAllocation
            alloc_obj = PortfolioAllocation(
                weights=report.portfolio["weights"],
                cluster_exposures=report.portfolio["cluster_exposures"],
                expected_return=report.portfolio["expected_return"],
                expected_volatility=report.portfolio["expected_volatility"],
                sharpe=report.portfolio["sharpe"],
                max_drawdown_estimate=report.portfolio["max_drawdown_estimate"],
                correlation_matrix=pd.DataFrame(),
                clusters=[],
                timestamp=report.generated_at,
            )
            mc = monte_carlo_stress(alloc_obj, n_paths=5000, horizon_days=252)
            report.monte_carlo = mc
        except Exception as e:
            logger.warning("Monte Carlo failed: %s", e)
            report.monte_carlo = {"error": str(e)}

    # 5. Learning Loop
    if include_learning:
        print("Running learning cycle...")
        try:
            learning = run_learning_cycle()
            report.learning = learning
        except Exception as e:
            logger.warning("Learning cycle failed: %s", e)
            report.learning = {"error": str(e)}

    # 6. Feature Importance
    if include_importance:
        print("Computing feature importance...")
        try:
            for sym in symbols[:5]:  # Limit to 5 symbols for speed
                try:
                    history = provider.fetch_history(sym, period, timeframe)
                    if history is not None and not history.empty:
                        cfg = LokiConfig(period=period, timeframe=timeframe)
                        importance = compute_factor_importance(sym, history, cfg)
                        report.feature_importance[sym] = {
                            "factor_importance": importance.factor_importance,
                            "regime_importance": importance.regime_importance,
                            "signal_contributions": importance.signal_contributions,
                        }

                        # Also attribute trades if we have paper trades
                        paper_trades = [t for t in paper_result.get("trades", []) if t["symbol"] == sym]
                        if paper_trades:
                            attributions = attribute_trades(paper_trades, history, cfg)
                            report.trade_attributions.extend([
                                {
                                    "symbol": a.symbol,
                                    "entry_time": a.entry_time,
                                    "exit_time": a.exit_time,
                                    "side": a.side,
                                    "pnl": a.pnl,
                                    "factor_contributions": a.factor_contributions,
                                    "regime": a.regime,
                                    "signal_strength": a.signal_strength,
                                }
                                for a in attributions
                            ])
                except Exception as e:
                    logger.warning("Importance for %s failed: %s", sym, e)
        except Exception as e:
            logger.warning("Feature importance failed: %s", e)

    # 7. Decision Accuracy
    if include_journal:
        print("Checking decision accuracy...")
        try:
            report.decision_stats = decision_accuracy()
        except Exception as e:
            logger.warning("Decision accuracy failed: %s", e)

    # 8. Generate Summary
    report.executive_summary = _generate_executive_summary(report)
    report.key_findings = _generate_key_findings(report)
    report.recommendations = _generate_recommendations(report)

    return report


def _generate_executive_summary(report: ResearchReport) -> str:
    """Generate executive summary text."""
    lines = []
    lines.append(f"Research Report: {report.title}")
    lines.append(f"Generated: {report.generated_at}")
    lines.append(f"Universe: {', '.join(report.symbols)}")
    lines.append(f"Period: {report.period} | Timeframe: {report.timeframe} | Capital: ${report.capital:,.0f}")
    lines.append("")

    # Portfolio performance
    perf = report.strategy_performance.get("portfolio", {})
    if perf:
        lines.append(f"Paper Replay (180 bars):")
        lines.append(f"  Net Return:  {perf.get('return_pct', 0):.2f}%")
        lines.append(f"  Trades:      {perf.get('trades', 0)}")
        lines.append(f"  Win Rate:    {perf.get('win_rate_pct', 0):.1f}%")
        lines.append(f"  Profit Factor: {perf.get('profit_factor', 0):.2f}")
        lines.append(f"  Expectancy:  ${perf.get('expectancy', 0):.2f}/fill")
        lines.append(f"  Max DD:      {perf.get('max_drawdown_pct', 0):.2f}%")

    # Portfolio allocation
    if report.portfolio and "error" not in report.portfolio:
        lines.append(f"\nOptimal Portfolio:")
        lines.append(f"  Expected Return: {report.portfolio['expected_return']*100:.2f}%")
        lines.append(f"  Expected Vol:    {report.portfolio['expected_volatility']*100:.2f}%")
        lines.append(f"  Sharpe:          {report.portfolio['sharpe']:.2f}")
        lines.append(f"  Est. Max DD:     {report.portfolio['max_drawdown_estimate']*100:.2f}%")
        top_weights = sorted(report.portfolio["weights"].items(), key=lambda x: -x[1])[:5]
        lines.append(f"  Top 5: {', '.join(f'{s} ({w*100:.1f}%)' for s, w in top_weights)}")

    # Stress tests
    if report.stress_results and "error" not in report.stress_results[0] if report.stress_results else True:
        lines.append(f"\nStress Test Summary:")
        for r in report.stress_results[:3]:
            lines.append(f"  {r['scenario']}: Return {r['portfolio_return']*100:.1f}%, DD {r['portfolio_drawdown']*100:.1f}%")

    # Learning
    if report.learning and "error" not in report.learning:
        adj = report.learning.get("suggestions", {}).get("adjustments", [])
        if adj:
            lines.append(f"\nLearning Adjustments:")
            for a in adj[:3]:
                lines.append(f"  • {a}")

    # Decision accuracy
    if report.decision_stats:
        acc = report.decision_stats.get("accuracy", 0)
        lines.append(f"\nDecision Accuracy: {acc*100:.1f}% ({report.decision_stats.get('correct', 0)}/{report.decision_stats.get('reviewed', 0)})")

    return "\n".join(lines)


def _generate_key_findings(report: ResearchReport) -> List[str]:
    """Generate key findings list."""
    findings = []

    perf = report.strategy_performance.get("portfolio", {})
    if perf:
        expectancy = perf.get("expectancy", 0)
        if expectancy > 0:
            findings.append(f"Positive expectancy (${expectancy:.2f}/trade) on paper replay")
        else:
            findings.append(f"Negative expectancy (${expectancy:.2f}/trade) — strategy needs improvement")

        win_rate = perf.get("win_rate_pct", 0)
        pf = perf.get("profit_factor", 0)
        if win_rate < 50 and pf > 1.5:
            findings.append("Low win rate but high profit factor — asymmetric payoff profile")
        elif win_rate > 60 and pf < 1.5:
            findings.append("High win rate but low profit factor — small wins, large losses")

    if report.portfolio and "error" not in report.portfolio:
        clusters = report.portfolio.get("clusters", [])
        if len(clusters) < len(report.symbols) * 0.5:
            findings.append("Portfolio has good diversification across correlation clusters")
        else:
            findings.append("Portfolio concentrated in few correlation clusters — consider adding uncorrelated assets")

    if report.stress_results:
        worst_dd = min(r.get("portfolio_drawdown", 0) for r in report.stress_results if "error" not in r)
        if worst_dd < -0.4:
            findings.append(f"Severe tail risk: worst scenario DD {worst_dd*100:.1f}%")
        elif worst_dd < -0.2:
            findings.append(f"Moderate tail risk: worst scenario DD {worst_dd*100:.1f}%")
        else:
            findings.append(f"Controlled tail risk: worst scenario DD {worst_dd*100:.1f}%")

    if report.learning and "error" not in report.learning:
        adj = report.learning.get("suggestions", {}).get("adjustments", [])
        if adj:
            findings.append(f"Learning loop suggests {len(adj)} parameter adjustments")

    if report.decision_stats:
        acc = report.decision_stats.get("accuracy", 0)
        if acc > 0.7:
            findings.append(f"Decision accuracy is strong at {acc*100:.1f}%")
        elif acc > 0.5:
            findings.append(f"Decision accuracy is moderate at {acc*100:.1f}%")
        else:
            findings.append(f"Decision accuracy needs improvement at {acc*100:.1f}%")

    return findings


def _generate_recommendations(report: ResearchReport) -> List[str]:
    """Generate actionable recommendations."""
    recs = []

    # From learning
    if report.learning and "error" not in report.learning:
        adj = report.learning.get("suggestions", {}).get("adjustments", [])
        for a in adj:
            recs.append(f"Retrain with: {a}")

    # From stress
    if report.stress_results:
        for r in report.stress_results:
            if "error" not in r and r.get("portfolio_drawdown", 0) < -0.3:
                recs.append(f"Reduce position sizes for {r['scenario']} scenario (DD {r['portfolio_drawdown']*100:.1f}%)")

    # From portfolio
    if report.portfolio and "error" not in report.portfolio:
        weights = report.portfolio.get("weights", {})
        max_w = max(weights.values()) if weights else 0
        if max_w > 0.25:
            recs.append(f"Reduce max position size (currently {max_w*100:.1f}%) to improve diversification")

        clusters = report.portfolio.get("clusters", [])
        for c in clusters:
            if len(c.assets) > 3:
                recs.append(f"Cluster {c.representative} has {len(c.assets)} correlated assets — consider reducing cluster exposure")

    # From decision accuracy
    if report.decision_stats:
        acc = report.decision_stats.get("accuracy", 0)
        if acc < 0.6:
            recs.append("Decision accuracy below 60% — review decision process and add more rigorous pre-trade checklist")

    # Generic good practices
    if not recs:
        recs.append("Continue monitoring paper performance before live deployment")
        recs.append("Schedule weekly decision reviews to improve accuracy")

    return recs


def save_report(
    report: ResearchReport,
    path: Optional[Path] = None,
) -> Path:
    """Save report to JSON."""
    if path is None:
        path = STATE_DIR / f"report_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "title": report.title,
        "generated_at": report.generated_at,
        "symbols": report.symbols,
        "period": report.period,
        "timeframe": report.timeframe,
        "capital": report.capital,
        "strategy_performance": report.strategy_performance,
        "portfolio": report.portfolio,
        "stress_results": report.stress_results,
        "monte_carlo": report.monte_carlo,
        "learning": report.learning,
        "feature_importance": report.feature_importance,
        "trade_attributions": report.trade_attributions,
        "decision_stats": report.decision_stats,
        "executive_summary": report.executive_summary,
        "key_findings": report.key_findings,
        "recommendations": report.recommendations,
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def load_report(path: Path) -> ResearchReport:
    """Load report from JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return ResearchReport(
        title=data["title"],
        generated_at=data["generated_at"],
        symbols=data["symbols"],
        period=data["period"],
        timeframe=data["timeframe"],
        capital=data["capital"],
        strategy_performance=data.get("strategy_performance", {}),
        portfolio=data.get("portfolio"),
        stress_results=data.get("stress_results", []),
        monte_carlo=data.get("monte_carlo"),
        learning=data.get("learning"),
        feature_importance=data.get("feature_importance", {}),
        trade_attributions=data.get("trade_attributions", []),
        decision_stats=data.get("decision_stats", {}),
        executive_summary=data.get("executive_summary", ""),
        key_findings=data.get("key_findings", []),
        recommendations=data.get("recommendations", []),
    )


def render_markdown(report: ResearchReport) -> str:
    """Render report as Markdown."""
    md = []
    md.append(f"# {report.title}")
    md.append(f"**Generated:** {report.generated_at}  ")
    md.append(f"**Universe:** {', '.join(report.symbols)}  ")
    md.append(f"**Period:** {report.period} | **Timeframe:** {report.timeframe} | **Capital:** ${report.capital:,.0f}")
    md.append("")

    md.append("## Executive Summary")
    md.append(report.executive_summary)
    md.append("")

    md.append("## Strategy Performance (Paper Replay)")
    perf = report.strategy_performance.get("portfolio", {})
    if perf:
        md.append("| Metric | Value |")
        md.append("|--------|-------|")
        md.append(f"| Net Return | {perf.get('return_pct', 0):.2f}% |")
        md.append(f"| Trades | {perf.get('trades', 0)} |")
        md.append(f"| Win Rate | {perf.get('win_rate_pct', 0):.1f}% |")
        md.append(f"| Profit Factor | {perf.get('profit_factor', 0):.2f} |")
        md.append(f"| Expectancy | ${perf.get('expectancy', 0):.2f}/fill |")
        md.append(f"| Max Drawdown | {perf.get('max_drawdown_pct', 0):.2f}% |")
        md.append("")

    md.append("## Portfolio Allocation")
    if report.portfolio and "error" not in report.portfolio:
        p = report.portfolio
        md.append("| Metric | Value |")
        md.append("|--------|-------|")
        md.append(f"| Expected Return | {p['expected_return']*100:.2f}% |")
        md.append(f"| Expected Volatility | {p['expected_volatility']*100:.2f}% |")
        md.append(f"| Sharpe | {p['sharpe']:.2f} |")
        md.append(f"| Est. Max Drawdown | {p['max_drawdown_estimate']*100:.2f}% |")
        md.append("")
        md.append("### Weights")
        md.append("| Symbol | Weight |")
        md.append("|--------|--------|")
        for s, w in sorted(p["weights"].items(), key=lambda x: -x[1]):
            md.append(f"| {s} | {w*100:.2f}% |")
        md.append("")
        md.append("### Clusters")
        md.append("| Representative | Assets | Avg Correlation | Exposure |")
        md.append("|----------------|--------|-----------------|----------|")
        for c in p.get("clusters", []):
            exp = p["cluster_exposures"].get(c["representative"], 0)
            md.append(f"| {c['representative']} | {len(c['assets'])} | {c['avg_correlation']:.2f} | {exp*100:.2f}% |")
        md.append("")

    md.append("## Stress Testing")
    if report.stress_results:
        md.append("| Scenario | Return | Max DD | VaR 95% | CVaR 95% | Worst Asset |")
        md.append("|----------|--------|--------|---------|----------|-------------|")
        for r in report.stress_results:
            if "error" not in r:
                md.append(f"| {r['scenario']} | {r['portfolio_return']*100:.2f}% | {r['portfolio_drawdown']*100:.2f}% | "
                         f"{r['var_95']*100:.2f}% | {r['cvar_95']*100:.2f}% | {r['worst_asset']} |")
        md.append("")

    if report.monte_carlo and "error" not in report.monte_carlo:
        md.append("## Monte Carlo Simulation")
        mc = report.monte_carlo
        md.append("| Metric | Value |")
        md.append("|--------|-------|")
        md.append(f"| Paths | {mc.get('n_paths', 0):,} |")
        md.append(f"| Horizon | {mc.get('horizon_days', 0)} days |")
        md.append(f"| Mean Return | {mc.get('mean_return', 0)*100:.2f}% |")
        md.append(f"| Median Return | {mc.get('median_return', 0)*100:.2f}% |")
        md.append(f"| Prob(Loss) | {mc.get('prob_loss', 0)*100:.1f}% |")
        md.append(f"| Prob(>50% Loss) | {mc.get('prob_50pct_loss', 0)*100:.2f}% |")
        md.append(f"| VaR 95% | {mc.get('var_95', 0)*100:.2f}% |")
        md.append(f"| CVaR 95% | {mc.get('cvar_95', 0)*100:.2f}% |")
        md.append(f"| MaxDD Mean | {mc.get('max_drawdown_mean', 0)*100:.2f}% |")
        md.append(f"| MaxDD 99% | {mc.get('max_drawdown_99', 0)*100:.2f}% |")
        md.append("")

    if report.learning and "error" not in report.learning:
        md.append("## Learning Loop")
        learn = report.learning
        md.append(f"**Session:** {learn.get('session_id', 'N/A')}")
        md.append(f"**Profile:** {learn.get('profile_source', 'N/A')} ({learn.get('preset', 'N/A')})")
        md.append("")
        adj = learn.get("suggestions", {}).get("adjustments", [])
        if adj:
            md.append("### Suggested Adjustments")
            for a in adj:
                md.append(f"- {a}")
            md.append("")
        grid = learn.get("focused_grid", {})
        if grid:
            md.append("### Focused Retraining Grid")
            for k, v in grid.items():
                md.append(f"- **{k}**: {v}")
            md.append("")

    if report.feature_importance:
        md.append("## Feature Importance")
        for sym, imp in report.feature_importance.items():
            md.append(f"### {sym}")
            md.append("| Factor | Importance |")
            md.append("|--------|------------|")
            for f, v in sorted(imp.get("factor_importance", {}).items(), key=lambda x: -x[1]):
                md.append(f"| {f} | {v*100:.2f}% |")
            md.append("")

    if report.decision_stats:
        md.append("## Decision Accuracy")
        ds = report.decision_stats
        md.append("| Metric | Value |")
        md.append("|--------|-------|")
        md.append(f"| Total Decisions | {ds.get('total', 0)} |")
        md.append(f"| Reviewed | {ds.get('reviewed', 0)} |")
        md.append(f"| Correct | {ds.get('correct', 0)} |")
        md.append(f"| Incorrect | {ds.get('incorrect', 0)} |")
        md.append(f"| Accuracy | {ds.get('accuracy', 0)*100:.1f}% |")
        md.append("")

    if report.key_findings:
        md.append("## Key Findings")
        for f in report.key_findings:
            md.append(f"- {f}")
        md.append("")

    if report.recommendations:
        md.append("## Recommendations")
        for r in report.recommendations:
            md.append(f"- {r}")
        md.append("")

    md.append("---")
    md.append(f"*Report generated by Loki v8 at {report.generated_at}*")
    return "\n".join(md)


def print_report(report: ResearchReport) -> None:
    """Print report to console."""
    print(f"\n{'='*70}")
    print(f"{report.title}")
    print(f"{'='*70}")
    print(report.executive_summary)
    print(f"\n{'='*70}")
    print("KEY FINDINGS")
    print(f"{'='*70}")
    for i, f in enumerate(report.key_findings, 1):
        print(f"  {i}. {f}")
    print(f"\n{'='*70}")
    print("RECOMMENDATIONS")
    print(f"{'='*70}")
    for i, r in enumerate(report.recommendations, 1):
        print(f"  {i}. {r}")
    print(f"\n{'='*70}")


def main() -> None:
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Generate Loki research report")
    parser.add_argument("--symbols", nargs="+", help="Symbols to include")
    parser.add_argument("--period", default="3y", help="History period")
    parser.add_argument("--timeframe", default="1d", help="Timeframe")
    parser.add_argument("--capital", type=float, default=100000.0, help="Capital")
    parser.add_argument("--no-stress", action="store_true", help="Skip stress tests")
    parser.add_argument("--no-mc", action="store_true", help="Skip Monte Carlo")
    parser.add_argument("--no-learning", action="store_true", help="Skip learning loop")
    parser.add_argument("--no-importance", action="store_true", help="Skip feature importance")
    parser.add_argument("--no-journal", action="store_true", help="Skip journal analytics")
    parser.add_argument("--markdown", action="store_true", help="Output as Markdown")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    report = generate_report(
        symbols=args.symbols,
        period=args.period,
        timeframe=args.timeframe,
        capital=args.capital,
        include_stress=not args.no_stress,
        include_monte_carlo=not args.no_mc,
        include_learning=not args.no_learning,
        include_importance=not args.no_importance,
        include_journal=not args.no_journal,
    )

    if args.json:
        print(json.dumps({
            "title": report.title,
            "generated_at": report.generated_at,
            "symbols": report.symbols,
            "executive_summary": report.executive_summary,
            "key_findings": report.key_findings,
            "recommendations": report.recommendations,
            "strategy_performance": report.strategy_performance,
            "portfolio": report.portfolio,
            "stress_results": report.stress_results,
            "monte_carlo": report.monte_carlo,
            "learning": report.learning,
            "feature_importance": report.feature_importance,
            "decision_stats": report.decision_stats,
        }, indent=2, default=str))
    elif args.markdown:
        print(render_markdown(report))
    else:
        print_report(report)

    # Always save
    path = save_report(report)
    print(f"\nReport saved: {path}")


if __name__ == "__main__":
    main()