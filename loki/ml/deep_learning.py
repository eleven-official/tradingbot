"""
Loki Trading Platform - Deep Learning Models
Advanced neural networks for trading: LSTM, Transformer, ensemble models
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, models
    from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint

    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    print("TensorFlow not available. Install with: pip install tensorflow")

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim

    PYTORCH_AVAILABLE = True
except ImportError:
    PYTORCH_AVAILABLE = False
    print("PyTorch not available. Install with: pip install torch")

from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

logger = logging.getLogger(__name__)


@dataclass
class ModelPrediction:
    """Model prediction result"""

    prediction: float
    confidence: float
    model_name: str
    features_used: List[str]
    timestamp: pd.Timestamp


@dataclass
class ModelPerformance:
    """Model performance metrics"""

    accuracy: float
    precision: float
    recall: float
    f1_score: float
    sharpe_ratio: float
    total_return: float
    win_rate: float


class LSTMPricePredictor:
    """
    LSTM-based price prediction model
    Uses historical prices, volume, and technical indicators
    """

    def __init__(self, sequence_length: int = 60, lstm_units: int = 128, dropout_rate: float = 0.2):
        if not TENSORFLOW_AVAILABLE:
            raise ImportError("TensorFlow required for LSTM model")

        self.sequence_length = sequence_length
        self.lstm_units = lstm_units
        self.dropout_rate = dropout_rate
        self.model: Optional[keras.Model] = None
        self.scaler = StandardScaler()

    def build_model(self, n_features: int) -> keras.Model:
        """Build LSTM architecture"""
        model = models.Sequential(
            [
                layers.Input(shape=(self.sequence_length, n_features)),
                # First LSTM layer with return sequences
                layers.LSTM(self.lstm_units, return_sequences=True, activation="tanh"),
                layers.Dropout(self.dropout_rate),
                # Second LSTM layer
                layers.LSTM(self.lstm_units // 2, return_sequences=False, activation="tanh"),
                layers.Dropout(self.dropout_rate),
                # Dense layers
                layers.Dense(64, activation="relu"),
                layers.Dropout(self.dropout_rate / 2),
                layers.Dense(32, activation="relu"),
                # Output layer (3 classes: buy, hold, sell)
                layers.Dense(3, activation="softmax"),
            ]
        )

        model.compile(
            optimizer="adam",
            loss="categorical_crossentropy",
            metrics=["accuracy", "precision", "recall"],
        )

        return model

    def prepare_sequences(
        self, data: pd.DataFrame, target_column: str = "close"
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequences for LSTM training

        Args:
            data: DataFrame with OHLCV data
            target_column: Column to predict

        Returns:
            X, y arrays for training
        """
        # Scale features
        scaled_data = self.scaler.fit_transform(data)

        X, y = [], []

        for i in range(self.sequence_length, len(scaled_data)):
            X.append(scaled_data[i - self.sequence_length : i])

            # Create target: 0=sell, 1=hold, 2=buy
            future_return = (data[target_column].iloc[i] - data[target_column].iloc[i - 1]) / data[
                target_column
            ].iloc[i - 1]
            if future_return > 0.005:  # 0.5% threshold
                y.append([0, 0, 1])  # Buy
            elif future_return < -0.005:
                y.append([1, 0, 0])  # Sell
            else:
                y.append([0, 1, 0])  # Hold

        return np.array(X), np.array(y)

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32,
    ) -> Dict:
        """Train the LSTM model"""
        if self.model is None:
            self.model = self.build_model(X_train.shape[2])

        # Callbacks
        early_stop = EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)

        checkpoint = ModelCheckpoint(
            "loki_lstm_best.h5", monitor="val_accuracy", save_best_only=True
        )

        # Train
        history = self.model.fit(
            X_train,
            y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=[early_stop, checkpoint],
            verbose=1,
        )

        return history.history

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions"""
        if self.model is None:
            raise ValueError("Model not trained yet")
        return self.model.predict(X)


class TransformerModel:
    """
    Transformer-based model for time-series prediction
    State-of-the-art architecture with attention mechanisms
    """

    def __init__(
        self, d_model: int = 128, num_heads: int = 8, num_layers: int = 4, dropout: float = 0.1
    ):
        if not TENSORFLOW_AVAILABLE:
            raise ImportError("TensorFlow required for Transformer model")

        self.d_model = d_model
        self.num_heads = num_heads
        self.num_layers = num_layers
        self.dropout = dropout
        self.model: Optional[keras.Model] = None

    def build_model(self, sequence_length: int, n_features: int) -> keras.Model:
        """Build Transformer architecture"""
        inputs = layers.Input(shape=(sequence_length, n_features))

        # Positional encoding
        x = layers.Dense(self.d_model)(inputs)

        # Transformer blocks
        for _ in range(self.num_layers):
            # Multi-head attention
            attn_output = layers.MultiHeadAttention(
                num_heads=self.num_heads,
                key_dim=self.d_model // self.num_heads,
                dropout=self.dropout,
            )(x, x)

            # Add & Norm
            x = layers.LayerNormalization(epsilon=1e-6)(x + attn_output)

            # Feed-forward network
            ffn = layers.Dense(self.d_model * 4, activation="relu")(x)
            ffn = layers.Dropout(self.dropout)(ffn)
            ffn = layers.Dense(self.d_model)(ffn)

            # Add & Norm
            x = layers.LayerNormalization(epsilon=1e-6)(x + ffn)

        # Global pooling and output
        x = layers.GlobalAveragePooling1D()(x)
        x = layers.Dense(64, activation="relu")(x)
        x = layers.Dropout(self.dropout)(x)
        outputs = layers.Dense(3, activation="softmax")(x)

        model = models.Model(inputs=inputs, outputs=outputs)

        model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])

        return model


class EnsembleModel:
    """
    Ensemble of multiple models for robust predictions
    Combines LSTM, Transformer, and traditional ML models
    """

    def __init__(self):
        self.models: List[Tuple[str, object]] = []
        self.weights: List[float] = []

    def add_model(self, name: str, model: object, weight: float = 1.0):
        """Add a model to the ensemble"""
        self.models.append((name, model))
        self.weights.append(weight)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make ensemble prediction
        Weighted average of all model predictions
        """
        if not self.models:
            raise ValueError("No models in ensemble")

        predictions = []
        total_weight = sum(self.weights)

        for (name, model), weight in zip(self.models, self.weights):
            try:
                pred = model.predict(X)
                predictions.append(pred * (weight / total_weight))
            except Exception as e:
                logger.error(f"Error in model {name}: {e}")
                continue

        if not predictions:
            raise ValueError("All models failed to predict")

        return np.sum(predictions, axis=0)


class AutoMLOptimizer:
    """
    Automated Machine Learning optimizer
    Automatically tunes hyperparameters and selects best model
    """

    def __init__(self, max_trials: int = 20):
        self.max_trials = max_trials
        self.best_model = None
        self.best_score = -np.inf

    def optimize_hyperparameters(
        self, X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, y_val: np.ndarray
    ) -> Dict:
        """
        Optimize hyperparameters using random search

        Returns:
            Dict with best hyperparameters and model
        """
        best_params = {}

        for trial in range(self.max_trials):
            # Random hyperparameters
            params = {
                "lstm_units": np.random.choice([64, 128, 256]),
                "dropout_rate": np.random.uniform(0.1, 0.4),
                "learning_rate": np.random.choice([0.001, 0.0005, 0.0001]),
                "batch_size": np.random.choice([16, 32, 64]),
            }

            # Build and train model
            try:
                model = LSTMPricePredictor(
                    lstm_units=params["lstm_units"], dropout_rate=params["dropout_rate"]
                )

                model.build_model(X_train.shape[2])

                history = model.train(
                    X_train, y_train, X_val, y_val, epochs=10, batch_size=params["batch_size"]
                )

                # Evaluate
                val_accuracy = max(history.get("val_accuracy", [0]))

                if val_accuracy > self.best_score:
                    self.best_score = val_accuracy
                    self.best_model = model
                    best_params = params

                logger.info(
                    f"Trial {trial + 1}/{self.max_trials}: Val Accuracy = {val_accuracy:.4f}"
                )

            except Exception as e:
                logger.error(f"Trial {trial + 1} failed: {e}")
                continue

        return {
            "best_model": self.best_model,
            "best_params": best_params,
            "best_score": self.best_score,
        }


class FeatureEngineering:
    """
    Automated feature engineering for ML models
    Creates technical indicators, statistical features, and more
    """

    @staticmethod
    def create_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Create comprehensive feature set

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with engineered features
        """
        features = df.copy()

        # Price-based features
        features["returns"] = features["close"].pct_change()
        features["log_returns"] = np.log(features["close"] / features["close"].shift(1))

        # Moving averages
        for period in [5, 10, 20, 50, 200]:
            features[f"sma_{period}"] = features["close"].rolling(period).mean()
            features[f"ema_{period}"] = features["close"].ewm(span=period).mean()

        # Volatility
        features["volatility_20"] = features["returns"].rolling(20).std()
        features["volatility_60"] = features["returns"].rolling(60).std()

        # Momentum indicators
        features["rsi_14"] = FeatureEngineering._calculate_rsi(features["close"], 14)
        features["rsi_28"] = FeatureEngineering._calculate_rsi(features["close"], 28)

        # MACD
        exp1 = features["close"].ewm(span=12).mean()
        exp2 = features["close"].ewm(span=26).mean()
        features["macd"] = exp1 - exp2
        features["macd_signal"] = features["macd"].ewm(span=9).mean()
        features["macd_diff"] = features["macd"] - features["macd_signal"]

        # Bollinger Bands
        sma_20 = features["close"].rolling(20).mean()
        std_20 = features["close"].rolling(20).std()
        features["bb_upper"] = sma_20 + (std_20 * 2)
        features["bb_lower"] = sma_20 - (std_20 * 2)
        features["bb_width"] = features["bb_upper"] - features["bb_lower"]
        features["bb_position"] = (features["close"] - features["bb_lower"]) / features["bb_width"]

        # Volume indicators
        features["volume_sma_20"] = features["volume"].rolling(20).mean()
        features["volume_ratio"] = features["volume"] / features["volume_sma_20"]

        # Price position relative to moving averages
        for period in [20, 50, 200]:
            features[f"price_to_sma_{period}"] = features["close"] / features[f"sma_{period}"]

        # Statistical features
        features["skewness_20"] = features["returns"].rolling(20).skew()
        features["kurtosis_20"] = features["returns"].rolling(20).kurt()

        # Drop NaN values
        features = features.dropna()

        return features

    @staticmethod
    def _calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi


def demo_deep_learning():
    """Demo of deep learning capabilities"""
    print("=" * 60)
    print("LOKI DEEP LEARNING TRADING MODELS")
    print("=" * 60)

    if not TENSORFLOW_AVAILABLE:
        print("TensorFlow not installed. Install with: pip install tensorflow")
        return

    # Generate sample data
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=500, freq="D")
    price = 100 * np.exp(np.cumsum(np.random.normal(0.001, 0.02, 500)))

    df = pd.DataFrame(
        {
            "close": price,
            "open": price * 0.99,
            "high": price * 1.01,
            "low": price * 0.98,
            "volume": np.random.randint(1000000, 10000000, 500),
        },
        index=dates,
    )

    # Feature engineering
    print("\n1. Creating features...")
    features = FeatureEngineering.create_features(df)
    print(f"   Created {len(features.columns)} features")

    # LSTM model
    print("\n2. Building LSTM model...")
    lstm = LSTMPricePredictor(sequence_length=30, lstm_units=64)
    print(f"   LSTM with {lstm.lstm_units} units, sequence length {lstm.sequence_length}")

    # Transformer model
    print("\n3. Building Transformer model...")
    transformer = TransformerModel(d_model=128, num_heads=4)
    print(
        f"   Transformer with {transformer.num_layers} layers, {transformer.num_heads} attention heads"
    )

    # Ensemble
    print("\n4. Creating ensemble model...")
    ensemble = EnsembleModel()
    print("   Ready for multi-model predictions")

    print("\n" + "=" * 60)
    print("Deep Learning System Ready!")
    print("=" * 60)


if __name__ == "__main__":
    demo_deep_learning()
