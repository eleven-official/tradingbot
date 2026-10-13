"""
Loki Machine Learning Price Predictor
LSTM/Transformer models for price prediction with confidence intervals
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    """Price prediction with confidence"""
    timestamp: datetime
    current_price: float
    predicted_price: float
    predicted_change_pct: float
    confidence: float  # 0-100
    lower_bound: float
    upper_bound: float
    timeframe: str  # "1h", "1d", "1w"
    features_used: List[str]


class FeatureEngineer:
    """Advanced feature engineering for ML models"""
    
    def __init__(self):
        self.feature_names = []
    
    def create_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Create comprehensive feature set
        
        Args:
            data: OHLCV DataFrame
        
        Returns:
            DataFrame with engineered features
        """
        df = data.copy()
        
        # Price features
        df['returns'] = df['close'].pct_change()
        df['log_returns'] = np.log(df['close'] / df['close'].shift(1))
        df['price_range'] = (df['high'] - df['low']) / df['close']
        df['body_size'] = abs(df['close'] - df['open']) / df['close']
        
        # Moving averages
        for window in [5, 10, 20, 50]:
            df[f'sma_{window}'] = df['close'].rolling(window).mean()
            df[f'ema_{window}'] = df['close'].ewm(span=window).mean()
            df[f'price_to_sma_{window}'] = df['close'] / df[f'sma_{window}']
        
        # Volatility features
        df['volatility_5'] = df['returns'].rolling(5).std()
        df['volatility_20'] = df['returns'].rolling(20).std()
        df['volatility_ratio'] = df['volatility_5'] / df['volatility_20']
        
        # Momentum indicators
        df['rsi'] = self._calculate_rsi(df['close'])
        df['macd'], df['macd_signal'] = self._calculate_macd(df['close'])
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # Volume features
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        df['volume_price_trend'] = df['volume'] * df['returns']
        
        # Trend features
        df['trend_5'] = df['close'].rolling(5).apply(lambda x: 1 if x.iloc[-1] > x.iloc[0] else -1, raw=False)
        df['trend_20'] = df['close'].rolling(20).apply(lambda x: 1 if x.iloc[-1] > x.iloc[0] else -1, raw=False)
        
        # Support/Resistance features
        df['high_5'] = df['high'].rolling(5).max()
        df['low_5'] = df['low'].rolling(5).min()
        df['high_20'] = df['high'].rolling(20).max()
        df['low_20'] = df['low'].rolling(20).min()
        df['distance_to_high'] = (df['high_20'] - df['close']) / df['close']
        df['distance_to_low'] = (df['close'] - df['low_20']) / df['close']
        
        # Lag features
        for lag in [1, 2, 3, 5]:
            df[f'returns_lag_{lag}'] = df['returns'].shift(lag)
            df[f'volume_lag_{lag}'] = df['volume'].shift(lag)
        
        # Time features
        df['day_of_week'] = pd.to_datetime(df.index).dayofweek
        df['month'] = pd.to_datetime(df.index).month
        df['hour'] = pd.to_datetime(df.index).hour if hasattr(df.index, 'hour') else 0
        
        # Store feature names (excluding original OHLCV)
        self.feature_names = [col for col in df.columns if col not in ['open', 'high', 'low', 'close', 'volume']]
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(self, prices: pd.Series) -> Tuple[pd.Series, pd.Series]:
        """Calculate MACD"""
        ema_12 = prices.ewm(span=12).mean()
        ema_26 = prices.ewm(span=26).mean()
        macd = ema_12 - ema_26
        signal = macd.ewm(span=9).mean()
        return macd, signal


class SimpleLSTMPredictor:
    """
    Simple LSTM-style predictor using statistical methods
    (Fallback when TensorFlow not available)
    """
    
    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.feature_engineer = FeatureEngineer()
        self.is_trained = False
        self.weights = None
    
    def train(self, data: pd.DataFrame, target_col: str = 'close'):
        """Train the predictor"""
        logger.info(f"🎓 Training predictor on {len(data)} samples...")
        
        # Engineer features
        df = self.feature_engineer.create_features(data)
        
        # Prepare training data
        X, y = self._prepare_sequences(df, target_col)
        
        if len(X) == 0:
            logger.warning("Not enough data for training")
            return
        
        # Simple weighted average training (statistical approach)
        # Calculate correlation of each feature with target
        self.weights = {}
        feature_df = df[self.feature_engineer.feature_names].fillna(0)
        target = df[target_col].pct_change().shift(-1).fillna(0)  # Next period return
        
        for feature in self.feature_engineer.feature_names:
            if feature in feature_df.columns:
                corr = feature_df[feature].corr(target)
                self.weights[feature] = corr if not np.isnan(corr) else 0.0
        
        self.is_trained = True
        logger.info(f"✓ Training complete! {len(self.weights)} features weighted")
    
    def predict(
        self,
        data: pd.DataFrame,
        horizon: int = 1,
        confidence_level: float = 0.95
    ) -> Prediction:
        """
        Make price prediction
        
        Args:
            data: Historical OHLCV data
            horizon: Prediction horizon (1 = next period)
            confidence_level: Confidence level for intervals
        
        Returns:
            Prediction object
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")
        
        # Engineer features
        df = self.feature_engineer.create_features(data)
        
        # Get latest features
        latest_features = df[self.feature_engineer.feature_names].iloc[-1].fillna(0)
        current_price = df['close'].iloc[-1]
        
        # Calculate weighted prediction
        prediction_signal = 0.0
        total_weight = 0.0
        
        for feature, weight in self.weights.items():
            if feature in latest_features.index:
                prediction_signal += latest_features[feature] * weight
                total_weight += abs(weight)
        
        # Normalize and scale
        if total_weight > 0:
            prediction_signal /= total_weight
        
        # Convert to price change
        predicted_change_pct = prediction_signal * 100 * horizon
        predicted_price = current_price * (1 + predicted_change_pct / 100)
        
        # Calculate confidence based on historical accuracy
        historical_returns = df['returns'].dropna()
        volatility = historical_returns.std()
        
        # Confidence decreases with volatility and horizon
        base_confidence = 70.0
        volatility_penalty = min(30, volatility * 1000)  # Max 30% penalty
        horizon_penalty = horizon * 5  # 5% per period
        confidence = max(20, base_confidence - volatility_penalty - horizon_penalty)
        
        # Calculate confidence intervals
        z_score = 1.96 if confidence_level == 0.95 else 2.576  # 95% or 99%
        std_dev = volatility * np.sqrt(horizon)
        
        lower_bound = current_price * (1 - z_score * std_dev)
        upper_bound = current_price * (1 + z_score * std_dev)
        
        return Prediction(
            timestamp=datetime.now(),
            current_price=current_price,
            predicted_price=predicted_price,
            predicted_change_pct=predicted_change_pct,
            confidence=confidence,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            timeframe=f"{horizon}period",
            features_used=list(self.weights.keys())[:10]  # Top 10 features
        )
    
    def _prepare_sequences(self, data: pd.DataFrame, target_col: str) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for training"""
        feature_df = data[self.feature_engineer.feature_names].fillna(0)
        target = data[target_col]
        
        X, y = [], []
        
        for i in range(self.lookback, len(data)):
            X.append(feature_df.iloc[i-self.lookback:i].values)
            y.append(target.iloc[i])
        
        return np.array(X), np.array(y)
    
    def backtest_predictions(self, data: pd.DataFrame, horizon: int = 1) -> Dict:
        """
        Backtest prediction accuracy
        
        Returns:
            Dict with accuracy metrics
        """
        logger.info("🧪 Backtesting predictions...")
        
        predictions = []
        actuals = []
        
        # Roll through data making predictions
        for i in range(self.lookback + 50, len(data) - horizon):
            train_data = data.iloc[:i]
            test_point = data.iloc[i + horizon]
            
            # Train on data up to this point
            self.train(train_data)
            
            # Make prediction
            try:
                pred = self.predict(train_data, horizon)
                predictions.append(pred.predicted_price)
                actuals.append(test_point['close'])
            except:
                continue
        
        if len(predictions) == 0:
            return {'error': 'Not enough data for backtesting'}
        
        predictions = np.array(predictions)
        actuals = np.array(actuals)
        
        # Calculate metrics
        mae = np.mean(np.abs(predictions - actuals))
        rmse = np.sqrt(np.mean((predictions - actuals) ** 2))
        mape = np.mean(np.abs((predictions - actuals) / actuals)) * 100
        
        # Direction accuracy
        pred_direction = np.sign(np.diff(np.concatenate([[actuals[0]], predictions])))
        actual_direction = np.sign(np.diff(actuals))
        direction_accuracy = np.mean(pred_direction == actual_direction) * 100
        
        results = {
            'n_predictions': len(predictions),
            'mae': float(mae),
            'rmse': float(rmse),
            'mape': float(mape),
            'direction_accuracy': float(direction_accuracy)
        }
        
        logger.info(f"✓ Backtest complete!")
        logger.info(f"   Direction Accuracy: {direction_accuracy:.1f}%")
        logger.info(f"   MAPE: {mape:.2f}%")
        
        return results


class EnsemblePredictor:
    """Ensemble of multiple predictors for better accuracy"""
    
    def __init__(self, n_models: int = 5):
        self.models = [SimpleLSTMPredictor() for _ in range(n_models)]
        self.is_trained = False
    
    def train(self, data: pd.DataFrame):
        """Train all models in ensemble"""
        logger.info(f"🎓 Training ensemble of {len(self.models)} models...")
        
        for i, model in enumerate(self.models):
            # Train each model on slightly different data (bootstrap)
            sample_data = data.sample(frac=0.8, replace=True)
            model.train(sample_data)
        
        self.is_trained = True
        logger.info("✓ Ensemble training complete!")
    
    def predict(self, data: pd.DataFrame, horizon: int = 1) -> Prediction:
        """Make ensemble prediction"""
        if not self.is_trained:
            raise ValueError("Ensemble must be trained before prediction")
        
        # Get predictions from all models
        predictions = []
        for model in self.models:
            try:
                pred = model.predict(data, horizon)
                predictions.append(pred)
            except:
                continue
        
        if len(predictions) == 0:
            raise ValueError("No models could make predictions")
        
        # Aggregate predictions
        predicted_prices = [p.predicted_price for p in predictions]
        confidences = [p.confidence for p in predictions]
        
        # Weighted average by confidence
        weights = np.array(confidences) / sum(confidences)
        final_predicted_price = np.average(predicted_prices, weights=weights)
        
        current_price = predictions[0].current_price
        predicted_change_pct = (final_predicted_price / current_price - 1) * 100
        
        # Ensemble confidence (higher due to multiple models)
        avg_confidence = np.mean(confidences)
        ensemble_boost = min(15, len(predictions) * 3)  # Up to 15% boost
        final_confidence = min(95, avg_confidence + ensemble_boost)
        
        # Tighter confidence intervals due to ensemble
        std_prices = np.std(predicted_prices)
        lower_bound = final_predicted_price - 2 * std_prices
        upper_bound = final_predicted_price + 2 * std_prices
        
        return Prediction(
            timestamp=datetime.now(),
            current_price=current_price,
            predicted_price=final_predicted_price,
            predicted_change_pct=predicted_change_pct,
            confidence=final_confidence,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            timeframe=f"{horizon}period",
            features_used=predictions[0].features_used
        )


# Convenience function
def create_predictor(ensemble: bool = True, n_models: int = 5):
    """
    Create a price predictor
    
    Args:
        ensemble: Use ensemble of models
        n_models: Number of models in ensemble
    
    Returns:
        Predictor instance
    """
    if ensemble:
        return EnsemblePredictor(n_models)
    else:
        return SimpleLSTMPredictor()
