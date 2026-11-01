"""Conservative entry eligibility; historical profit is not future profit."""
import math

from core.fusion import paper_models, paper_rules


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def assess(report):
    reasons = []
    artifact = report.get("artifact", {})
    cash_only = artifact.get("threshold") is None
    if artifact.get("version") not in {paper_models.MODEL_VERSION, paper_rules.VERSION}:
        reasons.append("Unsupported model version; retrain or compare the instrument.")
    if not cash_only and artifact.get("version") == paper_rules.VERSION:
        from core.fusion.paper_research import validate_execution_report
        try:
            validate_execution_report(report)
        except (ValueError, TypeError, KeyError):
            reasons.append("The saved rule failed its frozen validation gates.")
    test = report.get("test", {})
    if not cash_only:
        count = test.get("closed_trades")
        if not isinstance(count, int) or isinstance(count, bool) or count < 3:
            reasons.append("At least three completed later-period trades are required for paper entry review.")
        for key in ("net_return", "expectancy_usd"):
            value = test.get(key)
            if not _finite(value) or value <= 0:
                reasons.append("Later-period " + key + " must be positive after modeled costs.")
        drawdown = test.get("max_drawdown")
        if not _finite(drawdown) or not 0 <= drawdown <= 0.03:
            reasons.append("Later-period account drawdown must be measured and at most 3%.")
        stress = report.get("cost_stress", {})
        if stress.get("multiple") != 2 or not _finite(stress.get("net_return")) or stress["net_return"] <= 0:
            reasons.append("A positive later-period replay at doubled costs is required; run the strategy comparison.")
    return {
        "entry_allowed": not cash_only and not reasons,
        "cash_only": cash_only,
        "can_start": not reasons,
        "reasons": reasons,
        "status": "blocked" if reasons else "cash_only" if cash_only else "experimental_paper_candidate",
        "future_profitability_proven": False,
        "note": "Previously inspected history is development evidence. Passing these gates permits only experimental paper entries, not a profitability claim.",
    }
