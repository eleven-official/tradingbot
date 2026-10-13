"""
Paper Trading Launcher - Free Setup
Easy startup script for paper trading with testnet
"""
# --- UTF-8 stdio guard (auto-inserted) ---
import sys as _sys_io
if hasattr(_sys_io.stdout, "reconfigure"):
    _sys_io.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys_io.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import logging
from datetime import datetime
import pandas as pd
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('paper_trading.log'),
        logging.StreamHandler()
    ],
    encoding='utf-8'
)

logger = logging.getLogger(__name__)


class PaperTradingLauncher:
    """
    Simple paper trading launcher with simulated data (no API keys needed).
    """
    
    def __init__(self):
        self.config = {
            'initial_balance': 100000.0,  # $100,000 AUD
            'maker_fee_bps': 0.02,
            'taker_fee_bps': 0.04,
            'base_slippage_bps': 1.0,
            'symbols': ['BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'ADAUSDT', 'SOLUSDT'],
            'strategy': 'momentum'
        }
        
        self.engine = None
        self.is_running = False
    
    async def initialize(self):
        """Initialize the paper trading engine."""
        logger.info("Initializing Paper Trading System...")
        
        from core_engine.paper_trading_engine import PaperTradingEngine
        
        self.engine = PaperTradingEngine(self.config)
        await self.engine.initialize()
        
        logger.info(f"Paper Trading Engine initialized with ${self.config['initial_balance']:,.2f}")
        logger.info(f"Active Symbols: {', '.join(self.config['symbols'])}")
        logger.info(f"Strategy: {self.config['strategy']}")
    
    async def generate_simulated_data(self, symbol: str, num_bars: int = 100):
        """Generate simulated market data for paper trading."""
        # Generate realistic price data
        np.random.seed(42)
        
        dates = pd.date_range(start=datetime.now() - pd.Timedelta(days=num_bars), 
                             periods=num_bars, freq='h')
        
        # Random walk with drift
        base_price = 50000 if 'BTC' in symbol else 3000 if 'ETH' in symbol else 1
        returns = np.random.normal(0.0001, 0.01, num_bars)
        prices = base_price * (1 + returns).cumprod()
        
        data = pd.DataFrame({
            'open': prices * (1 + np.random.uniform(-0.005, 0.005, num_bars)),
            'high': prices * (1 + np.random.uniform(0, 0.01, num_bars)),
            'low': prices * (1 + np.random.uniform(-0.01, 0, num_bars)),
            'close': prices,
            'volume': np.random.randint(1000, 10000, num_bars)
        }, index=dates)
        
        return data
    
    async def run_paper_trading(self):
        """Run the paper trading session."""
        logger.info("Starting Paper Trading Session...")
        self.is_running = True
        
        strategy_count = 0
        
        while self.is_running:
            try:
                # Trade each symbol
                for symbol in self.config['symbols']:
                    # Generate or fetch market data
                    data = await self.generate_simulated_data(symbol)
                    
                    # Update market data
                    latest_data = data.iloc[-1]
                    market_data = {
                        'timestamp': latest_data.name,
                        'open': latest_data['open'],
                        'high': latest_data['high'],
                        'low': latest_data['low'],
                        'close': latest_data['close'],
                        'volume': latest_data['volume'],
                        'volatility': data['close'].pct_change().std() * np.sqrt(252)
                    }
                    
                    await self.engine.update_market_data(symbol, market_data)
                    
                    # Run strategy every 10 iterations
                    if strategy_count % 10 == 0:
                        from core_engine.academic_strategies import StrategyLibrary
                        
                        # Get strategy library once
                        if not hasattr(self, 'strategy_library'):
                            self.strategy_library = StrategyLibrary()
                        
                        strategy = self.strategy_library.get_strategy(self.config['strategy'])
                        
                        if strategy:
                            signals = strategy.generate_signals(data)
                            
                            for signal in signals:
                                await self.engine.process_signal(signal)
                    
                    # Update equity curve
                    await self.engine.update_equity_curve()
                
                strategy_count += 1
                
                # Print status every 25 iterations
                if strategy_count % 25 == 0:
                    account = self.engine.get_account_summary()
                    logger.info(f"Iteration {strategy_count} | Balance: ${account.current_balance:,.2f} | "
                              f"Positions: {len(self.engine.positions)} | "
                              f"Trades: {account.total_trades}")
                
                # Sleep to simulate real-time
                await asyncio.sleep(1)
                
                # Stop after 200 iterations for demo
                if strategy_count >= 200:
                    logger.info("Paper trading session complete (200 iterations)")
                    break
            
            except Exception as e:
                logger.error(f"❌ Error in paper trading loop: {e}")
                await asyncio.sleep(5)
    
    async def stop(self):
        """Stop the paper trading session."""
        logger.info("Stopping Paper Trading Session...")
        self.is_running = False
        
        if self.engine:
            await self.engine.shutdown()
        
        # Print final results
        if self.engine:
            account = self.engine.get_account_summary()
            metrics = self.engine.get_performance_metrics()
            
            logger.info("\n" + "="*60)
            logger.info("FINAL PAPER TRADING RESULTS")
            logger.info("="*60)
            logger.info(f"Initial Balance: ${account.initial_balance:,.2f}")
            logger.info(f"Final Balance: ${account.current_balance:,.2f}")
            logger.info(f"Total Return: {((account.current_balance - account.initial_balance) / account.initial_balance):.2%}")
            logger.info(f"Total Trades: {account.total_trades}")
            logger.info(f"Win Rate: {account.win_rate:.2%}")
            logger.info(f"Max Drawdown: {account.max_drawdown:.2%}")
            logger.info(f"Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}")
            logger.info("="*60)
        
        logger.info("Paper Trading Session stopped")


async def main():
    """Main entry point."""
    launcher = PaperTradingLauncher()
    
    try:
        await launcher.initialize()
        await launcher.run_paper_trading()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await launcher.stop()


if __name__ == '__main__':
    print("""
============================================================
                                                             
          FREE PAPER TRADING SYSTEM
                                                             
    No API Keys Required - Simulated Market Data
    Risk-Free Learning Environment
                                                             
============================================================
    """)
    
    asyncio.run(main())