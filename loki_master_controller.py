#!/usr/bin/env python3
"""
LOKI Master Controller
Central command system integrating all advanced trading components.
"""

import asyncio
import logging
import threading
import time
import datetime
from typing import Dict, List, Optional
import json
import sys
import os

# Import all advanced components
try:
    from strategy_factory import get_strategy, get_available_strategies, StrategySignal
    from advanced_backtester import AdvancedBacktester, WalkForwardOptimizer
    from portfolio_manager import AdvancedPortfolioManager
    from realtime_monitor import RealTimeMonitor, email_alert_callback, emergency_stop_callback
    from ml_optimizer import MLStrategyOptimizer, RLStrategyOptimizer
    from execution_engine import SmartOrderRouter, MarketDataFeed, Order, OrderType
except ImportError as e:
    logging.warning(f"Import error: {e}. Some features may not be available.")

class LokiMasterController:
    """Master controller coordinating all trading system components."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.is_running = False
        self.is_live_trading = False
        
        # Initialize components
        self.portfolio_manager = None
        self.strategies = {}
        self.market_data_feed = None
        self.order_router = None
        self.monitor = None
        self.ml_optimizer = None
        
        # Trading state
        self.current_positions = {}
        self.active_signals = {}
        self.performance_metrics = {}
        
        # Setup logging
        self._setup_logging()
        
        # Initialize all components
        self._initialize_components()
    
    def _setup_logging(self):
        """Setup comprehensive logging system."""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # File handler
        file_handler = logging.FileHandler(f'loki_trading_{datetime.date.today()}.log')
        file_handler.setFormatter(logging.Formatter(log_format))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))
        
        # Root logger configuration
        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler, console_handler]
        )
        
        self.logger = logging.getLogger("LokiMaster")
        self.logger.info("🚀 LOKI Master Controller initializing...")
    
    def _initialize_components(self):
        """Initialize all trading system components."""
        
        try:
            # Portfolio Manager
            initial_capital = self.config.get('initial_capital', 100000)
            self.portfolio_manager = AdvancedPortfolioManager(
                initial_capital=initial_capital,
                max_positions=self.config.get('max_positions', 10)
            )
            
            # Market Data Feed
            self.market_data_feed = MarketDataFeed()
            
            # Order Router
            self.order_router = SmartOrderRouter(self.market_data_feed)
            
            # Real-time Monitor
            alert_callbacks = [email_alert_callback, emergency_stop_callback]
            self.monitor = RealTimeMonitor(self.portfolio_manager, alert_callbacks)
            
            # ML Optimizer
            self.ml_optimizer = MLStrategyOptimizer()
            
            # Initialize strategies
            self._initialize_strategies()
            
            self.logger.info("✅ All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Component initialization failed: {e}")
            raise
    
    def _initialize_strategies(self):
        """Initialize trading strategies with allocations."""
        
        strategy_configs = self.config.get('strategies', {})
        
        for strategy_name, strategy_config in strategy_configs.items():
            try:
                # Create strategy instance
                strategy = get_strategy(
                    strategy_name, 
                    None,  # Mock kite object
                    strategy_config,
                    enhanced=True
                )
                
                self.strategies[strategy_name] = strategy
                
                # Add to portfolio manager
                allocation = strategy_config.get('allocation', 0.1)
                max_weight = strategy_config.get('max_weight', 0.3)
                
                self.portfolio_manager.add_strategy(
                    strategy_name, 
                    allocation, 
                    max_weight
                )
                
                self.logger.info(f"✅ Strategy {strategy_name} initialized with {allocation:.1%} allocation")
                
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize strategy {strategy_name}: {e}")
    
    def start_trading_system(self):
        """Start the complete trading system."""
        
        if self.is_running:
            self.logger.warning("Trading system is already running")
            return
        
        self.logger.info("🔥 Starting LOKI Trading System...")
        
        try:
            # Start monitoring system
            self.monitor.start_monitoring()
            
            # Start market data feed (simulation)
            threading.Thread(target=self._market_data_simulator, daemon=True).start()
            
            # Start strategy execution loop
            threading.Thread(target=self._strategy_execution_loop, daemon=True).start()
            
            # Start portfolio rebalancing
            threading.Thread(target=self._portfolio_rebalancing_loop, daemon=True).start()
            
            self.is_running = True
            self.logger.info("🎯 LOKI Trading System is now LIVE!")
            
            # Display system status
            self._display_system_status()
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start trading system: {e}")
            self.stop_trading_system()
    
    def stop_trading_system(self):
        """Stop the trading system safely."""
        
        self.logger.info("🛑 Stopping LOKI Trading System...")
        
        self.is_running = False
        self.is_live_trading = False
        
        # Close all positions
        self._emergency_close_all_positions()
        
        # Stop monitoring
        if self.monitor:
            self.monitor.stop_monitoring()
        
        self.logger.info("✅ Trading system stopped safely")
    
    def _market_data_simulator(self):
        """Simulate real-time market data feed."""
        
        symbols = ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'TCS', 'INFY']
        base_prices = {symbol: 100.0 for symbol in symbols}
        
        while self.is_running:
            for symbol in symbols:
                # Simulate price movement
                change = np.random.normal(0, 0.001)  # 0.1% volatility
                base_prices[symbol] *= (1 + change)
                
                # Generate bid/ask
                spread = base_prices[symbol] * 0.001  # 0.1% spread
                bid = base_prices[symbol] - spread/2
                ask = base_prices[symbol] + spread/2
                volume = np.random.randint(1000, 10000)
                
                # Update market data
                self.market_data_feed.update_market_data(
                    symbol, bid, ask, base_prices[symbol], volume
                )
            
            time.sleep(1)  # Update every second
    
    def _strategy_execution_loop(self):
        """Main strategy execution loop."""
        
        while self.is_running:
            try:
                # Create mock market data for strategies
                mock_data = self._create_mock_market_data()
                
                if len(mock_data) < 50:
                    time.sleep(5)
                    continue
                
                # Execute each strategy
                for strategy_name, strategy in self.strategies.items():
                    try:
                        # Generate signal
                        signal = strategy.generate_signals(
                            mock_data,
                            sentiment='Bullish',  # Would come from sentiment analysis
                            cpr_pivots={'tc': 102, 'bc': 98, 'pivot': 100},
                            vix_conditions=set()
                        )
                        
                        # Process signal if actionable
                        if isinstance(signal, StrategySignal) and signal.action in ['BUY', 'SELL']:
                            if signal.confidence >= 0.7:  # High confidence threshold
                                self._execute_strategy_signal(strategy_name, signal, mock_data.iloc[-1])
                        
                    except Exception as e:
                        self.logger.error(f"Error executing strategy {strategy_name}: {e}")
                
                time.sleep(10)  # Strategy execution interval
                
            except Exception as e:
                self.logger.error(f"Error in strategy execution loop: {e}")
                time.sleep(5)
    
    def _execute_strategy_signal(self, strategy_name: str, signal: StrategySignal, market_data):
        """Execute a strategy signal through the order management system."""
        
        symbol = 'NIFTY'  # Default symbol for demo
        current_price = market_data['close']
        
        # Execute signal through portfolio manager
        success = self.portfolio_manager.execute_signal(
            signal, symbol, current_price, strategy_name
        )
        
        if success:
            self.logger.info(f"🎯 Executed {signal.action} signal from {strategy_name}: "
                           f"Confidence={signal.confidence:.1%}, Price={current_price:.2f}")
            
            # Create order for execution engine
            order = Order(
                order_id=f"{strategy_name}_{datetime.datetime.now().strftime('%H%M%S')}",
                symbol=symbol,
                side=signal.action,
                quantity=100,  # Fixed quantity for demo
                order_type=OrderType.MARKET,
                urgency_level="MEDIUM"
            )
            
            # Submit to order router
            self.order_router.submit_order(order)
            
        else:
            self.logger.warning(f"⚠️ Signal from {strategy_name} rejected by portfolio manager")
    
    def _create_mock_market_data(self) -> pd.DataFrame:
        """Create mock market data for strategy execution."""
        
        # Generate realistic OHLCV data
        dates = pd.date_range(start='2024-01-01 09:15', periods=100, freq='5min')
        
        np.random.seed(int(time.time()) % 1000)  # Semi-random seed
        
        base_price = 20000
        data = []
        
        for i in range(100):
            change = np.random.normal(0.001, 0.01)
            base_price *= (1 + change)
            
            high = base_price * (1 + abs(np.random.normal(0, 0.005)))
            low = base_price * (1 - abs(np.random.normal(0, 0.005)))
            open_price = base_price * (1 + np.random.normal(0, 0.002))
            
            data.append([open_price, high, low, base_price, np.random.randint(1000, 10000)])
        
        df = pd.DataFrame(data, columns=['open', 'high', 'low', 'close', 'volume'], index=dates)
        
        # Add technical indicators
        df['rsi'] = self._calculate_rsi(df['close'])
        df['ema_9'] = df['close'].ewm(span=9).mean()
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_50'] = df['close'].ewm(span=50).mean()
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['atr'] = self._calculate_atr(df)
        df['vwap'] = self._calculate_vwap(df)
        
        return df
    
    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_atr(self, df, period=14):
        """Calculate ATR."""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def _calculate_vwap(self, df):
        """Calculate VWAP."""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        return (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    
    def _portfolio_rebalancing_loop(self):
        """Periodic portfolio rebalancing."""
        
        while self.is_running:
            try:
                # Rebalance every hour
                time.sleep(3600)
                
                if self.is_running:
                    self.portfolio_manager.rebalance_portfolio()
                    self.logger.info("📊 Portfolio rebalanced")
                    
            except Exception as e:
                self.logger.error(f"Error in rebalancing: {e}")
    
    def _emergency_close_all_positions(self):
        """Emergency position closure."""
        
        self.logger.warning("🚨 Emergency closing all positions...")
        
        positions_to_close = list(self.portfolio_manager.positions.keys())
        
        for symbol in positions_to_close:
            try:
                self.portfolio_manager.close_position(symbol, "Emergency close")
                self.logger.info(f"✅ Closed position in {symbol}")
            except Exception as e:
                self.logger.error(f"❌ Failed to close {symbol}: {e}")
    
    def _display_system_status(self):
        """Display real-time system status."""
        
        print("\n" + "="*80)
        print("🔥 LOKI NEURAL TRADING SYSTEM - STATUS DASHBOARD")
        print("="*80)
        
        # System info
        print(f"📊 System Status: {'🟢 LIVE' if self.is_running else '🔴 STOPPED'}")
        print(f"💰 Initial Capital: ${self.portfolio_manager.initial_capital:,.2f}")
        print(f"🎯 Active Strategies: {len(self.strategies)}")
        
        # Strategy status
        print("\n📈 ACTIVE STRATEGIES:")
        for name in self.strategies.keys():
            print(f"   • {name}")
        
        # Portfolio summary
        if self.portfolio_manager:
            summary = self.portfolio_manager.get_portfolio_summary()
            print(f"\n💼 PORTFOLIO OVERVIEW:")
            print(f"   • Total Value: ${summary['total_value']:,.2f}")
            print(f"   • Total P&L: ${summary['total_pnl']:,.2f}")
            print(f"   • Return: {summary['total_return']:.2%}")
            print(f"   • Active Positions: {summary['active_positions']}")
            print(f"   • Cash Balance: ${summary['cash_balance']:,.2f}")
        
        print("\n🔍 MONITORING:")
        print("   • Real-time risk monitoring: ✅ Active")
        print("   • Alert system: ✅ Active")
        print("   • Performance tracking: ✅ Active")
        
        print("="*80)
        print("🎯 System ready for trading. Press Ctrl+C to stop safely.")
        print("="*80)
    
    def run_optimization(self, strategy_name: str):
        """Run ML optimization for a strategy."""
        
        self.logger.info(f"🤖 Starting ML optimization for {strategy_name}...")
        
        try:
            # Create sample data for optimization
            sample_data = self._create_mock_market_data()
            
            # Define parameter ranges (example)
            param_ranges = {
                'min_confidence_threshold': [0.5, 0.9],
                'max_signals_per_hour': [1, 5],
                'ema_cross_lookback': [3, 10]
            }
            
            # Run optimization
            strategy_class = type(self.strategies[strategy_name])
            result = self.ml_optimizer.optimize_strategy(
                strategy_class, sample_data, param_ranges
            )
            
            self.logger.info(f"🎯 Optimization completed! Best performance: {result.performance_score:.4f}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Optimization failed: {e}")
            return None
    
    def get_system_metrics(self) -> Dict:
        """Get comprehensive system performance metrics."""
        
        metrics = {}
        
        # Portfolio metrics
        if self.portfolio_manager:
            metrics['portfolio'] = self.portfolio_manager.get_portfolio_summary()
        
        # Monitor metrics
        if self.monitor:
            metrics['monitoring'] = self.monitor.get_performance_dashboard()
        
        # Execution metrics
        if self.order_router:
            metrics['execution'] = self.order_router.get_execution_report()
        
        # System status
        metrics['system'] = {
            'is_running': self.is_running,
            'uptime_seconds': time.time() - getattr(self, '_start_time', time.time()),
            'active_strategies': len(self.strategies),
            'component_health': {
                'portfolio_manager': self.portfolio_manager is not None,
                'market_data_feed': self.market_data_feed is not None,
                'order_router': self.order_router is not None,
                'monitor': self.monitor is not None and self.monitor.is_monitoring
            }
        }
        
        return metrics


def main():
    """Main entry point for LOKI Trading System."""
    
    # Default configuration
    config = {
        'initial_capital': 100000,
        'max_positions': 8,
        'strategies': {
            'Gemini_Default': {
                'allocation': 0.3,
                'max_weight': 0.4,
                'trading_flags': {
                    'min_confidence_threshold': 0.7,
                    'max_signals_per_hour': 3
                }
            },
            'Quantum_Momentum': {
                'allocation': 0.25,
                'max_weight': 0.3,
                'trading_flags': {
                    'min_confidence_threshold': 0.8,
                    'max_signals_per_hour': 2
                }
            },
            'Neural_Network': {
                'allocation': 0.2,
                'max_weight': 0.25,
                'trading_flags': {
                    'min_confidence_threshold': 0.75,
                    'max_signals_per_hour': 2
                }
            },
            'Adaptive_Arbitrage': {
                'allocation': 0.25,
                'max_weight': 0.3,
                'trading_flags': {
                    'min_confidence_threshold': 0.6,
                    'max_signals_per_hour': 5
                }
            }
        }
    }
    
    # Load configuration from file if exists
    if os.path.exists('loki_config.json'):
        try:
            with open('loki_config.json', 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
            print("✅ Configuration loaded from loki_config.json")
        except Exception as e:
            print(f"⚠️ Error loading config file: {e}. Using defaults.")
    
    # Initialize and start LOKI
    try:
        loki = LokiMasterController(config)
        loki._start_time = time.time()
        
        # Start the trading system
        loki.start_trading_system()
        
        # Keep system running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Shutdown signal received...")
            loki.stop_trading_system()
            
    except Exception as e:
        print(f"💥 LOKI System Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()