import pytest

from loki.portfolio import PortfolioInputError, Position, build_portfolio_summary


def test_build_portfolio_summary_calculates_valuation_and_weights() -> None:
    summary = build_portfolio_summary(
        [
            Position("btc", quantity=2, average_cost=100, current_price=125),
            Position("eth", quantity=5, average_cost=20, current_price=10),
        ],
        cash=50,
        currency="aud",
    )

    assert summary["currency"] == "AUD"
    assert summary["total_cost_basis"] == 300
    assert summary["invested_value"] == 300
    assert summary["total_value"] == 350
    assert summary["unrealized_gain_loss"] == 0
    assert summary["cash_weight"] == pytest.approx(50 / 350)
    assert summary["positions"][0]["symbol"] == "BTC"
    assert summary["positions"][0]["portfolio_weight"] == pytest.approx(250 / 350)


def test_build_portfolio_summary_marks_concentrated_portfolios() -> None:
    summary = build_portfolio_summary(
        [Position("BTC", quantity=1, average_cost=100, current_price=150)],
        cash=0,
    )

    assert summary["largest_position_weight"] == 1
    assert summary["effective_positions"] == 1
    assert summary["diversification_score"] == 0
    assert summary["risk_flags"]


def test_build_portfolio_summary_rejects_duplicate_symbols() -> None:
    positions = [
        Position("BTC", quantity=1, average_cost=100, current_price=100),
        Position("btc", quantity=2, average_cost=100, current_price=100),
    ]

    with pytest.raises(PortfolioInputError, match="only once"):
        build_portfolio_summary(positions)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "symbol": "BTC",
                "quantity": -1,
                "average_cost": 100,
                "current_price": 100,
            },
            "quantity",
        ),
        (
            {
                "symbol": "BTC",
                "quantity": 1,
                "average_cost": float("nan"),
                "current_price": 100,
            },
            "average_cost",
        ),
    ],
)
def test_position_rejects_invalid_values(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(PortfolioInputError, match=message):
        Position(**kwargs)
