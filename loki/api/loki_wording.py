"""Loki's plain-language wording, canonical so pages never drift apart.

Phase 1 of the external audit (v2.38.0) asked for the revenue model to be
marked *proposed* until legally finalized, precise profit/loss/reporting/
dispute definitions, and a fixed paper/live separation statement. Templates
render these constants; the tests pin them, so editing wording here = editing
wording everywhere, one file.
"""

from __future__ import annotations

REVENUE_STATUS = "proposed"
"""The 30% model is a proposal until the operator finalizes it legally.
Also mirrored as an env override so a deployment can promote it the day
the agreement is signed: LOKI_REVENUE_STATUS."""

REVENUE_BANNER = (
    "Proposed, not yet final. The 30% profit-share model below is how the "
    "house intends to charge once a formal agreement is signed. No invoice "
    "can be issued and no payment is collected through Loki today; the "
    "details here become binding only when the operator publishes a signed "
    "agreement."
)

PROFIT_DEFINITION = (
    "Net realised profit means realised gains minus realised losses and "
    "recorded expenses for the subject, in a reporting period — closed, "
    "cash-settled trades only. Unrealised (open-position) gains and paper "
    "or simulated results are never counted."
)

LOSS_TREATMENT = (
    "Losses reduce profit. A loss period is recorded as a negative event and "
    "pulls the books down dollar for dollar; a later correction is recorded "
    "the same way, with its provenance, and never silently edits the past."
)

REPORTING_PERIOD = (
    "Reporting periods are calendar months (UTC). The fee is computed from "
    "the events recorded in that month's book and invoiced monthly once "
    "invoicing exists."
)

DISPUTE_PROCESS = (
    "Disputes: raise one against a specific recorded event within 30 days of "
    "its recording, in writing to the operator contact on /transparency. The "
    "event stays visible with a dispute note while it is reviewed in "
    "calendar order; both parties may insert their evidence on the event. A "
    "disputed fee is withheld until the dispute is closed, and no disputed "
    "amount is treated as owed until then."
)

ROUNDING_RULE = (
    "Money math is exact decimal, rounded only once, half-up, to the cent, "
    "at the point the fee is computed."
)

PAPER_LIVE_SEPARATION = (
    "Paper trading and live trading are separate by design: paper balances "
    "are simulated money while live trading runs only through the Alpaca "
    "runner under your own account, and a broker order or position can "
    "outlive the running page. Stopping automation never closes existing "
    "broker positions — cancel them with your broker."
)

PRIVACY_SUMMARY = (
    "Your email is handled by the account service. Journals and game "
    "progress stay in your browser until you explicitly save them to your "
    "cloud account; cloud copies are private to your account. Broker keys "
    "and cookies are excluded from cloud saves. Revenue books are private "
    "operator records."
)

RETENTION_SUMMARY = (
    "Browser records last until you clear them; cloud records last until "
    "you delete the account or ask for deletion in writing. Nothing is sold "
    "to anyone and nothing is posted publicly except the game leaderboard "
    "fields named in the terms."
)


def revenue_status() -> str:
    import os

    return (os.environ.get("LOKI_REVENUE_STATUS") or REVENUE_STATUS).strip().lower()
