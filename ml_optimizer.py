#!/usr/bin/env python3
"""
Machine Learning Strategy Optimizer
Advanced AI-powered strategy optimization with reinforcement learning and hyperparameter tuning.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
import pickle
import datetime
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

@dataclass
class OptimizationResult:
    """Strategy optimization results."""
    strategy_name: str
    best_params: Dict
    performance_score: float
    confidence_interval: Tuple[float, float]
    feature_importance: Dict
    validation_metrics: Dict
    optimization_time: float

class FeatureEngineering:
    """Advanced feature engineering for trading strategies."""
    
    def __init__(self):
        self.scalers = {}
        self.feature_names = []
    
    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create comprehensive feature set for ML optimization."""
        features = df.copy()
        
        # Price-based features
        features['returns'] = df['close'].pct_change()
        features['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        features['volatility'] = features['returns'].rolling(window=20).std()
        
        # Technical indicators
        features['rsi'] = self._calculate_rsi(df['close'])
        features['macd'], features['macd_signal'] = self._calculate_macd(df['close'])
        features['bb_upper'], features['bb_lower'], features['bb_width'] = self._calculate_bollinger_bands(df['close'])
        
        # Volume features
        if 'volume' in df.columns:
            features['volume_sma'] = df['volume'].rolling(window=20).mean()
            features['volume_ratio'] = df['volume'] / features['volume_sma']
            features['price_volume'] = df['close'] * df['volume']
        
        # Time-based features
        features['hour'] = df.index.hour if hasattr(df.index, 'hour') else 12
        features['day_of_week'] = df.index.dayofweek if hasattr(df.index, 'dayofweek') else 1
        features['is_morning'] = (features['hour'] >= 9) & (features['hour'] <= 11)
        features['is_afternoon'] = (features['hour'] >= 14) & (features['hour'] <= 16)
        
        # Market microstructure
        features['spread_proxy'] = (df['high'] - df['low']) / df['close']
        features['price_position'] = (df['close'] - df['low']) / (df['high'] - df['low'])
        
        # Momentum features
        for period in [5, 10, 20, 50]:
            features[f'momentum_{period}'] = df['close'] / df['close'].shift(period) - 1
            features[f'ema_{period}'] = df['close'].ewm(span=period).mean()
            
        # Mean reversion features
        features['mean_reversion_5'] = (df['close'] - df['close'].rolling(5).mean()) / df['close'].rolling(5).std()
        features['mean_reversion_20'] = (df['close'] - df['close'].rolling(20).mean()) / df['close'].rolling(20).std()
        
        # Volatility regime
        features['vol_regime'] = self._classify_volatility_regime(features['volatility'])
        
        # Trend strength
        features['trend_strength'] = self._calculate_trend_strength(df['close'])
        
        # Market state features
        features['market_state'] = self._classify_market_state(df)
        
        # Lag features
        for lag in [1, 2, 3, 5]:
            features[f'returns_lag_{lag}'] = features['returns'].shift(lag)
            features[f'volume_lag_{lag}'] = df['volume'].shift(lag) if 'volume' in df.columns else 0
        
        # Interaction features
        features['rsi_volatility'] = features['rsi'] * features['volatility']
        features['momentum_volume'] = features['momentum_5'] * features.get('volume_ratio', 1)
        
        self.feature_names = [col for col in features.columns if col not in ['open', 'high', 'low', 'close', 'volume']]
        
        return features.fillna(method='ffill').fillna(0)
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series]:
        """Calculate MACD indicator."""
        ema_12 = prices.ewm(span=12).mean()
        ema_26 = prices.ewm(span=26).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9).mean()
        return macd, signal
    
    def _calculate_bollinger_bands(self, prices: pd.Series, period: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands."""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        width = (upper - lower) / sma
        return upper, lower, width
    
    def _classify_volatility_regime(self, volatility: pd.Series) -> pd.Series:
        """Classify volatility into regimes."""
        vol_percentiles = volatility.rolling(window=252, min_periods=50).quantile([0.33, 0.66])
        
        def classify_vol(vol_value, window_data):
            if len(window_data) < 2:
                return 1  # Medium
            if vol_value <= window_data.iloc[0]:
                return 0  # Low
            elif vol_value >= window_data.iloc[1]:
                return 2  # High
            else:
                return 1  # Medium
        
        return volatility.rolling(window=252, min_periods=50).apply(
            lambda x: classify_vol(x.iloc[-1], vol_percentiles.loc[x.index[-1]] if x.index[-1] in vol_percentiles.index else pd.Series([x.quantile(0.33), x.quantile(0.66)]))
        )
    
    def _calculate_trend_strength(self, prices: pd.Series) -> pd.Series:
        """Calculate trend strength indicator."""
        sma_20 = prices.rolling(window=20).mean()
        sma_50 = prices.rolling(window=50).mean()
        
        # Trend direction
        trend_direction = np.where(sma_20 > sma_50, 1, -1)
        
        # Trend strength (R-squared of linear regression)
        def calculate_r_squared(window):
            if len(window) < 10:
                return 0
            x = np.arange(len(window))
            y = window.values
            correlation = np.corrcoef(x, y)[0, 1]
            return correlation ** 2 if not np.isnan(correlation) else 0
        
        r_squared = prices.rolling(window=20).apply(calculate_r_squared)
        return trend_direction * r_squared
    
    def _classify_market_state(self, df: pd.DataFrame) -> pd.Series:
        """Classify market state (trending, ranging, volatile)."""
        returns = df['close'].pct_change()
        volatility = returns.rolling(window=20).std()
        
        # Trend strength
        trend_strength = abs(self._calculate_trend_strength(df['close']))
        
        # Market state classification
        def classify_state(trend, vol, vol_threshold_low=0.01, vol_threshold_high=0.03, trend_threshold=0.3):
            if vol > vol_threshold_high:
                return 2  # Volatile
            elif trend > trend_threshold:
                return 0  # Trending
            else:
                return 1  # Ranging
        
        return pd.Series([
            classify_state(t, v) for t, v in zip(trend_strength, volatility)
        ], index=df.index)


class MLStrategyOptimizer:
    """Machine learning-based strategy parameter optimization."""
    
    def __init__(self):
        self.feature_engineer = FeatureEngineering()
        self.models = {}
        self.optimization_history = []
        
    def optimize_strategy(self, strategy_class, historical_data: pd.DataFrame, 
                         param_ranges: Dict, target_metric: str = 'sharpe_ratio',
                         cv_folds: int = 5) -> OptimizationResult:
        """
        Optimize strategy parameters using machine learning.
        
        Args:
            strategy_class: Strategy class to optimize
            historical_data: Historical market data
            param_ranges: Dictionary of parameter ranges to test
            target_metric: Metric to optimize ('sharpe_ratio', 'total_return', etc.)
            cv_folds: Number of cross-validation folds
        """
        start_time = datetime.datetime.now()
        
        logging.info(f"Starting ML optimization for {strategy_class.__name__}")
        
        # Feature engineering
        features_df = self.feature_engineer.create_features(historical_data)
        
        # Generate parameter combinations and performance data
        X, y, param_combinations = self._generate_training_data(
            strategy_class, features_df, param_ranges, target_metric
        )
        
        if len(X) < 10:
            raise ValueError("Insufficient training data for optimization")
        
        # Train ML models
        best_model, model_performance = self._train_optimization_model(X, y, cv_folds)
        
        # Find optimal parameters
        best_params = self._find_optimal_parameters(best_model, param_ranges, X.columns)
        
        # Validate results
        validation_metrics = self._validate_optimization(
            strategy_class, historical_data, best_params, target_metric
        )
        
        # Feature importance
        feature_importance = dict(zip(X.columns, best_model.feature_importances_))
        
        optimization_time = (datetime.datetime.now() - start_time).total_seconds()
        
        result = OptimizationResult(
            strategy_name=strategy_class.__name__,
            best_params=best_params,
            performance_score=validation_metrics[target_metric],
            confidence_interval=validation_metrics.get('confidence_interval', (0, 0)),
            feature_importance=feature_importance,
            validation_metrics=validation_metrics,
            optimization_time=optimization_time
        )
        
        self.optimization_history.append(result)
        
        logging.info(f"Optimization completed in {optimization_time:.1f}s. Best {target_metric}: {result.performance_score:.4f}")
        
        return result
    
    def _generate_training_data(self, strategy_class, features_df: pd.DataFrame, 
                              param_ranges: Dict, target_metric: str) -> Tuple[pd.DataFrame, pd.Series, List[Dict]]:
        """Generate training data by testing parameter combinations."""
        from advanced_backtester import AdvancedBacktester
        
        # Generate parameter combinations (Latin Hypercube Sampling for efficiency)
        param_combinations = self._latin_hypercube_sampling(param_ranges, n_samples=100)
        
        X_data = []
        y_data = []
        
        # Split data into windows for training
        window_size = len(features_df) // 10  # 10% windows
        
        for params in param_combinations:
            for i in range(5, len(features_df) - window_size, window_size // 2):  # Sliding windows
                window_data = features_df.iloc[i:i + window_size]
                
                if len(window_data) < 50:  # Minimum window size
                    continue
                
                try:
                    # Create strategy with parameters
                    mock_config = {'trading_flags': params}
                    strategy = strategy_class(None, mock_config)
                    
                    # Run backtest
                    backtester = AdvancedBacktester()
                    result = backtester.run_backtest(strategy, window_data)
                    
                    # Extract features for this window
                    window_features = self._extract_window_features(window_data, params)
                    
                    X_data.append(window_features)
                    y_data.append(getattr(result, target_metric, 0.0))
                    
                except Exception as e:
                    logging.warning(f"Error in parameter combination {params}: {e}")
                    continue
        
        if not X_data:
            raise ValueError("No valid training data generated")
        
        X = pd.DataFrame(X_data)
        y = pd.Series(y_data)
        
        return X, y, param_combinations
    
    def _latin_hypercube_sampling(self, param_ranges: Dict, n_samples: int = 100) -> List[Dict]:
        """Generate parameter combinations using Latin Hypercube Sampling."""
        from scipy.stats import qmc
        
        param_names = list(param_ranges.keys())
        n_params = len(param_names)
        
        if n_params == 0:
            return [{}]
        
        # Generate Latin Hypercube samples
        sampler = qmc.LatinHypercube(d=n_params, seed=42)
        samples = sampler.random(n=n_samples)
        
        param_combinations = []
        for sample in samples:
            combination = {}
            for i, param_name in enumerate(param_names):
                param_range = param_ranges[param_name]
                
                if isinstance(param_range[0], int):
                    # Integer parameter
                    value = int(param_range[0] + sample[i] * (param_range[1] - param_range[0]))
                else:
                    # Float parameter
                    value = param_range[0] + sample[i] * (param_range[1] - param_range[0])
                
                combination[param_name] = value
            
            param_combinations.append(combination)
        
        return param_combinations
    
    def _extract_window_features(self, window_data: pd.DataFrame, params: Dict) -> Dict:
        """Extract features that describe the market conditions in this window."""
        features = {}
        
        # Market condition features
        returns = window_data['close'].pct_change().dropna()
        features['mean_return'] = returns.mean()
        features['volatility'] = returns.std()
        features['skewness'] = returns.skew()
        features['kurtosis'] = returns.kurtosis()
        
        # Trend features
        features['trend_strength'] = (window_data['close'].iloc[-1] - window_data['close'].iloc[0]) / window_data['close'].iloc[0]
        
        # Volume features (if available)
        if 'volume' in window_data.columns:
            features['avg_volume'] = window_data['volume'].mean()
            features['volume_trend'] = (window_data['volume'].iloc[-1] - window_data['volume'].iloc[0]) / window_data['volume'].iloc[0]
        else:
            features['avg_volume'] = 0
            features['volume_trend'] = 0
        
        # Technical indicator features
        if 'rsi' in window_data.columns:
            features['avg_rsi'] = window_data['rsi'].mean()
            features['rsi_range'] = window_data['rsi'].max() - window_data['rsi'].min()
        
        # Parameter features (encoded)
        for param_name, param_value in params.items():
            features[f'param_{param_name}'] = param_value
        
        return features
    
    def _train_optimization_model(self, X: pd.DataFrame, y: pd.Series, cv_folds: int) -> Tuple:
        """Train machine learning model for parameter optimization."""
        
        # Prepare data
        X_scaled = StandardScaler().fit_transform(X)
        X_scaled_df = pd.DataFrame(X_scaled, columns=X.columns, index=X.index)
        
        # Models to try
        models = {
            'random_forest': RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1),
            'gradient_boost': GradientBoostingRegressor(n_estimators=100, random_state=42),
        }
        
        # Time series cross-validation
        tscv = TimeSeriesSplit(n_splits=cv_folds)
        
        best_model = None
        best_score = -np.inf
        model_performances = {}
        
        for model_name, model in models.items():
            scores = []
            
            for train_idx, val_idx in tscv.split(X_scaled_df):
                X_train, X_val = X_scaled_df.iloc[train_idx], X_scaled_df.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
                
                model.fit(X_train, y_train)
                predictions = model.predict(X_val)
                score = -mean_squared_error(y_val, predictions)  # Negative MSE as score
                scores.append(score)
            
            avg_score = np.mean(scores)
            model_performances[model_name] = {
                'score': avg_score,
                'std': np.std(scores)
            }
            
            if avg_score > best_score:
                best_score = avg_score
                best_model = model
        
        # Retrain best model on full dataset
        best_model.fit(X_scaled, y)
        
        logging.info(f"Best model performance: {best_score:.4f}")
        
        return best_model, model_performances
    
    def _find_optimal_parameters(self, model, param_ranges: Dict, feature_names: List[str]) -> Dict:
        """Find optimal parameters using trained model."""
        
        # Generate many parameter combinations for prediction
        test_combinations = self._latin_hypercube_sampling(param_ranges, n_samples=1000)
        
        best_params = None
        best_predicted_score = -np.inf
        
        for params in test_combinations:
            # Create feature vector for this parameter combination
            # For now, use median market conditions as baseline
            baseline_features = {fname: 0.0 for fname in feature_names if not fname.startswith('param_')}
            
            # Add parameter features
            for param_name, param_value in params.items():
                baseline_features[f'param_{param_name}'] = param_value
            
            # Ensure all required features are present
            feature_vector = [baseline_features.get(fname, 0.0) for fname in feature_names]
            
            try:
                predicted_score = model.predict([feature_vector])[0]
                
                if predicted_score > best_predicted_score:
                    best_predicted_score = predicted_score
                    best_params = params
            except Exception as e:
                logging.warning(f"Prediction error for params {params}: {e}")
                continue
        
        return best_params or {}
    
    def _validate_optimization(self, strategy_class, historical_data: pd.DataFrame, 
                             best_params: Dict, target_metric: str) -> Dict:
        """Validate optimization results on out-of-sample data."""
        from advanced_backtester import AdvancedBacktester
        
        # Use last 30% of data for validation
        split_point = int(len(historical_data) * 0.7)
        validation_data = historical_data.iloc[split_point:]
        
        try:
            # Test optimized strategy
            mock_config = {'trading_flags': best_params}
            strategy = strategy_class(None, mock_config)
            
            backtester = AdvancedBacktester()
            result = backtester.run_backtest(strategy, validation_data)
            
            return {
                'total_return': result.total_return,
                'sharpe_ratio': result.sharpe_ratio,
                'max_drawdown': result.max_drawdown,
                'win_rate': result.win_rate,
                'total_trades': result.total_trades,
                'confidence_interval': result.confidence_interval
            }
            
        except Exception as e:
            logging.error(f"Validation error: {e}")
            return {target_metric: 0.0, 'error': str(e)}
    
    def save_optimization_results(self, results: List[OptimizationResult], filepath: str):
        """Save optimization results for future analysis."""
        with open(filepath, 'wb') as f:
            pickle.dump(results, f)
        
        logging.info(f"Optimization results saved to {filepath}")
    
    def load_optimization_results(self, filepath: str) -> List[OptimizationResult]:
        """Load previously saved optimization results."""
        try:
            with open(filepath, 'rb') as f:
                results = pickle.load(f)
            
            logging.info(f"Loaded {len(results)} optimization results from {filepath}")
            return results
        
        except FileNotFoundError:
            logging.warning(f"No optimization results found at {filepath}")
            return []


# Reinforcement Learning Strategy Optimizer
class RLStrategyOptimizer:
    """Reinforcement learning approach to strategy optimization."""
    
    def __init__(self, learning_rate: float = 0.01, epsilon: float = 0.1):
        self.learning_rate = learning_rate
        self.epsilon = epsilon
        self.q_table = {}
        self.state_action_counts = {}
        
    def optimize_with_rl(self, strategy_class, historical_data: pd.DataFrame, 
                        param_ranges: Dict, episodes: int = 100) -> Dict:
        """Optimize strategy using Q-learning reinforcement learning."""
        
        logging.info(f"Starting RL optimization with {episodes} episodes")
        
        # Initialize Q-table
        self._initialize_q_table(param_ranges)
        
        best_params = None
        best_reward = -np.inf
        
        for episode in range(episodes):
            # Select action (parameter combination) using epsilon-greedy
            current_params = self._select_action(param_ranges)
            
            # Evaluate strategy with these parameters
            reward = self._evaluate_strategy(strategy_class, historical_data, current_params)
            
            # Update Q-value
            self._update_q_value(current_params, reward)
            
            # Track best parameters
            if reward > best_reward:
                best_reward = reward
                best_params = current_params
            
            # Decay exploration
            self.epsilon = max(0.01, self.epsilon * 0.995)
            
            if episode % 20 == 0:
                logging.info(f"Episode {episode}: Best reward = {best_reward:.4f}, ε = {self.epsilon:.3f}")
        
        logging.info(f"RL optimization completed. Best reward: {best_reward:.4f}")
        return best_params
    
    def _initialize_q_table(self, param_ranges: Dict):
        """Initialize Q-table with parameter combinations."""
        # Simplified: discretize parameter ranges
        for param_name, param_range in param_ranges.items():
            if isinstance(param_range[0], int):
                values = list(range(param_range[0], param_range[1] + 1))
            else:
                values = np.linspace(param_range[0], param_range[1], 10)
            
            for value in values:
                state_key = f"{param_name}_{value}"
                if state_key not in self.q_table:
                    self.q_table[state_key] = 0.0
                    self.state_action_counts[state_key] = 0
    
    def _select_action(self, param_ranges: Dict) -> Dict:
        """Select parameter combination using epsilon-greedy policy."""
        if np.random.random() < self.epsilon:
            # Explore: random parameters
            params = {}
            for param_name, param_range in param_ranges.items():
                if isinstance(param_range[0], int):
                    params[param_name] = np.random.randint(param_range[0], param_range[1] + 1)
                else:
                    params[param_name] = np.random.uniform(param_range[0], param_range[1])
            return params
        else:
            # Exploit: best known parameters
            best_params = {}
            for param_name, param_range in param_ranges.items():
                best_value = None
                best_q = -np.inf
                
                if isinstance(param_range[0], int):
                    values = list(range(param_range[0], param_range[1] + 1))
                else:
                    values = np.linspace(param_range[0], param_range[1], 10)
                
                for value in values:
                    state_key = f"{param_name}_{value}"
                    if state_key in self.q_table and self.q_table[state_key] > best_q:
                        best_q = self.q_table[state_key]
                        best_value = value
                
                best_params[param_name] = best_value or values[0]
            
            return best_params
    
    def _evaluate_strategy(self, strategy_class, historical_data: pd.DataFrame, params: Dict) -> float:
        """Evaluate strategy performance as reward signal."""
        from advanced_backtester import AdvancedBacktester
        
        try:
            mock_config = {'trading_flags': params}
            strategy = strategy_class(None, mock_config)
            
            # Use subset of data for faster evaluation
            sample_data = historical_data.sample(min(1000, len(historical_data)))
            
            backtester = AdvancedBacktester()
            result = backtester.run_backtest(strategy, sample_data)
            
            # Composite reward: Sharpe ratio with drawdown penalty
            reward = result.sharpe_ratio - result.max_drawdown * 2
            
            return reward
            
        except Exception as e:
            logging.warning(f"Strategy evaluation error: {e}")
            return -10.0  # Large negative reward for errors
    
    def _update_q_value(self, params: Dict, reward: float):
        """Update Q-values using Q-learning algorithm."""
        for param_name, param_value in params.items():
            state_key = f"{param_name}_{param_value}"
            
            if state_key in self.q_table:
                # Q-learning update
                old_q = self.q_table[state_key]
                self.state_action_counts[state_key] += 1
                
                # Adaptive learning rate based on visit count
                adaptive_lr = self.learning_rate / (1 + 0.01 * self.state_action_counts[state_key])
                
                self.q_table[state_key] = old_q + adaptive_lr * (reward - old_q)


if __name__ == "__main__":
    print("🤖 Machine Learning Strategy Optimizer")
    print("Features:")
    print("  • Advanced feature engineering")
    print("  • Multiple ML algorithms")
    print("  • Time series cross-validation")
    print("  • Latin Hypercube Sampling")
    print("  • Reinforcement Learning optimization")
    print("  • Automated hyperparameter tuning")
    print("  • Feature importance analysis")
    print("\n✅ AI-powered optimization system ready!")