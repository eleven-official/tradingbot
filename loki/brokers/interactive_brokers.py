"""
Interactive Brokers Adapter
Placeholder for IB integration
"""

from loki.brokers.alpaca_broker import AlpacaBrokerAdapter
from loki.brokers.base import BrokerCapabilities


class InteractiveBrokersAdapter(AlpacaBrokerAdapter):
    """
    Interactive Brokers implementation
    TODO: Implement with ib_insync or ibapi
    """

    @property
    def capabilities(self) -> BrokerCapabilities:
        return BrokerCapabilities(
            supports_stocks=True,
            supports_options=True,
            supports_futures=True,
            supports_forex=True,
            supports_extended_hours=True,
            supports_margin=True,
            supports_short_selling=True,
            min_order_value=0,
            commission_per_trade=1.0,
        )

    # TODO: Implement IB-specific methods
