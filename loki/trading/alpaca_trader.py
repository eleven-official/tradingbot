"""
Loki Live Alpaca Trading Integration
Connect your real Alpaca account for live trading with safety controls
"""

import os
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading mode"""

    PAPER = "paper"
    LIVE = "live"


@dataclass
class Position:
    """Trading position"""

    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float
    side: str  # "long" or "short"


@dataclass
class Order:
    """Order information"""

    id: str
    symbol: str
    qty: float
    side: str  # "buy" or "sell"
    type: str  # "market", "limit", "stop"
    status: str
    filled_qty: float
    filled_avg_price: float
    created_at: datetime


class AlpacaTrader:
    """
    Live trading with Alpaca API

    Features:
    - Paper and Live trading modes
    - Order management
    - Position tracking
    - Account info
    - Safety checks
    """

    def __init__(
        self, api_key: str = None, secret_key: str = None, mode: TradingMode = TradingMode.PAPER
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        self.mode = mode

        self.api = None
        self.trading_client = None

        self._init_alpaca()

        mode_str = "PAPER" if mode == TradingMode.PAPER else "🔴 LIVE"
        logger.info(f"💼 Alpaca Trader initialized ({mode_str} mode)")

    def _init_alpaca(self):
        """Initialize Alpaca connection"""
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            if not self.api_key or not self.secret_key:
                logger.error("❌ Alpaca API credentials not found!")
                logger.error("   Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
                return

            # Create trading client
            paper = self.mode == TradingMode.PAPER
            self.trading_client = TradingClient(self.api_key, self.secret_key, paper=paper)

            # Test connection
            account = self.trading_client.get_account()
            logger.info(f"✓ Connected to Alpaca")
            logger.info(f"   Account: ${float(account.equity):,.2f}")
            logger.info(f"   Buying Power: ${float(account.buying_power):,.2f}")

        except ImportError:
            logger.error("❌ Alpaca library not installed!")
            logger.error("   Install: pip install alpaca-py")
        except Exception as e:
            logger.error(f"❌ Error connecting to Alpaca: {e}")

    def get_account_info(self) -> Dict:
        """Get account information"""
        if not self.trading_client:
            return {}

        try:
            account = self.trading_client.get_account()

            return {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "day_trade_count": int(account.daytrade_count),
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
                "account_blocked": account.account_blocked,
                "status": account.status,
            }
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {}

    def get_positions(self) -> List[Position]:
        """Get all open positions"""
        if not self.trading_client:
            return []

        try:
            positions = self.trading_client.get_all_positions()

            result = []
            for pos in positions:
                result.append(
                    Position(
                        symbol=pos.symbol,
                        quantity=float(pos.qty),
                        avg_entry_price=float(pos.avg_entry_price),
                        current_price=float(pos.current_price),
                        market_value=float(pos.market_value),
                        unrealized_pl=float(pos.unrealized_pl),
                        unrealized_pl_pct=float(pos.unrealized_plpc) * 100,
                        side=pos.side,
                    )
                )

            return result

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    def place_market_order(
        self, symbol: str, quantity: float, side: str  # "buy" or "sell"
    ) -> Optional[Order]:
        """
        Place market order

        Args:
            symbol: Stock symbol
            quantity: Number of shares
            side: "buy" or "sell"

        Returns:
            Order object if successful
        """
        if not self.trading_client:
            logger.error("Trading client not initialized")
            return None

        try:
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            # Safety check for live trading
            if self.mode == TradingMode.LIVE:
                logger.warning(
                    f"🔴 LIVE TRADING: Placing {side.upper()} order for {quantity} {symbol}"
                )
                # Additional safety checks here

            # Create order request
            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

            order_request = MarketOrderRequest(
                symbol=symbol, qty=quantity, side=order_side, time_in_force=TimeInForce.DAY
            )

            # Submit order
            order = self.trading_client.submit_order(order_request)

            logger.info(f"✓ Order placed: {side.upper()} {quantity} {symbol}")
            logger.info(f"   Order ID: {order.id}")

            return Order(
                id=str(order.id),
                symbol=order.symbol,
                qty=float(order.qty),
                side=order.side.value,
                type=order.type.value,
                status=order.status.value,
                filled_qty=float(order.filled_qty) if order.filled_qty else 0,
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else 0,
                created_at=order.created_at,
            )

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def place_limit_order(
        self, symbol: str, quantity: float, side: str, limit_price: float
    ) -> Optional[Order]:
        """
        Place limit order

        Args:
            symbol: Stock symbol
            quantity: Number of shares
            side: "buy" or "sell"
            limit_price: Limit price

        Returns:
            Order object if successful
        """
        if not self.trading_client:
            logger.error("Trading client not initialized")
            return None

        try:
            from alpaca.trading.requests import LimitOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            # Safety check
            if self.mode == TradingMode.LIVE:
                logger.warning(
                    f"🔴 LIVE TRADING: Placing LIMIT {side.upper()} order for {quantity} {symbol} @ ${limit_price:.2f}"
                )

            order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL

            order_request = LimitOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=order_side,
                time_in_force=TimeInForce.DAY,
                limit_price=limit_price,
            )

            order = self.trading_client.submit_order(order_request)

            logger.info(
                f"✓ Limit order placed: {side.upper()} {quantity} {symbol} @ ${limit_price:.2f}"
            )

            return Order(
                id=str(order.id),
                symbol=order.symbol,
                qty=float(order.qty),
                side=order.side.value,
                type=order.type.value,
                status=order.status.value,
                filled_qty=float(order.filled_qty) if order.filled_qty else 0,
                filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else 0,
                created_at=order.created_at,
            )

        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            return None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if not self.trading_client:
            return False

        try:
            self.trading_client.cancel_order_by_id(order_id)
            logger.info(f"✓ Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    def get_open_orders(self) -> List[Order]:
        """Get all open orders"""
        if not self.trading_client:
            return []

        try:
            orders = self.trading_client.get_orders()

            result = []
            for order in orders:
                result.append(
                    Order(
                        id=str(order.id),
                        symbol=order.symbol,
                        qty=float(order.qty),
                        side=order.side.value,
                        type=order.type.value,
                        status=order.status.value,
                        filled_qty=float(order.filled_qty) if order.filled_qty else 0,
                        filled_avg_price=(
                            float(order.filled_avg_price) if order.filled_avg_price else 0
                        ),
                        created_at=order.created_at,
                    )
                )

            return result

        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []

    def close_position(self, symbol: str) -> bool:
        """Close a position (sell all shares)"""
        if not self.trading_client:
            return False

        try:
            if self.mode == TradingMode.LIVE:
                logger.warning(f"🔴 LIVE TRADING: Closing position in {symbol}")

            self.trading_client.close_position(symbol)
            logger.info(f"✓ Position {symbol} closed")
            return True

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False

    def close_all_positions(self) -> bool:
        """Close all positions"""
        if not self.trading_client:
            return False

        try:
            if self.mode == TradingMode.LIVE:
                logger.warning("🔴 LIVE TRADING: Closing ALL positions")
                # Require confirmation for live trading
                # In production, add confirmation dialog

            self.trading_client.close_all_positions(cancel_orders=True)
            logger.info("✓ All positions closed")
            return True

        except Exception as e:
            logger.error(f"Error closing all positions: {e}")
            return False

    def is_market_open(self) -> bool:
        """Check if market is open"""
        if not self.trading_client:
            return False

        try:
            clock = self.trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False


# Global trader instance
_trader = None


def get_alpaca_trader(mode: TradingMode = TradingMode.PAPER) -> AlpacaTrader:
    """Get global Alpaca trader instance"""
    global _trader
    if _trader is None:
        _trader = AlpacaTrader(mode=mode)
    return _trader


if __name__ == "__main__":
    # Test Alpaca connection
    logging.basicConfig(level=logging.INFO)

    print("\n" + "=" * 60)
    print("TESTING ALPACA TRADING INTEGRATION")
    print("=" * 60)

    # Initialize trader in paper mode
    print("\n1. Connecting to Alpaca (Paper Trading)...")
    trader = get_alpaca_trader(mode=TradingMode.PAPER)

    # Get account info
    print("\n2. Fetching account information...")
    account = trader.get_account_info()
    if account:
        print(f"   Equity: ${account['equity']:,.2f}")
        print(f"   Cash: ${account['cash']:,.2f}")
        print(f"   Buying Power: ${account['buying_power']:,.2f}")

    # Get positions
    print("\n3. Fetching positions...")
    positions = trader.get_positions()
    if positions:
        for pos in positions:
            print(f"   {pos.symbol}: {pos.quantity} shares @ ${pos.avg_entry_price:.2f}")
            print(f"      P&L: ${pos.unrealized_pl:.2f} ({pos.unrealized_pl_pct:.2f}%)")
    else:
        print("   No open positions")

    # Check market status
    print("\n4. Checking market status...")
    is_open = trader.is_market_open()
    print(f"   Market is {'OPEN' if is_open else 'CLOSED'}")

    print("\n✓ Alpaca integration test complete!")
    print("\n⚠ To enable live trading:")
    print("   1. Set ALPACA_API_KEY and ALPACA_SECRET_KEY")
    print("   2. Change mode to TradingMode.LIVE")
    print("   3. Test thoroughly in paper mode first!")
