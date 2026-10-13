"""
Order Flow Toxicity Filter - VPIN and Order Book Imbalance
Detects predatory institutional spoofing and toxic retail traps
"""
import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import statistics


@dataclass
class ToxicityMetrics:
    """Current toxicity metrics."""
    vpin_score: float
    order_book_imbalance: float
    spread_widening: float
    liquidity_score: float
    spoofing_probability: float
    overall_toxicity: float
    timestamp: datetime = field(default_factory=datetime.now)


class VPINFilter:
    """
    Volume-Synchronized Probability of Liquidation (VPIN) filter.
    Detects toxic flow and predatory trading patterns.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.toxicity_config = config.get('toxicity_filter', {})
        
        # Configuration
        self.enabled = self.toxicity_config.get('enabled', True)
        self.vpin_threshold = self.toxicity_config.get('vpin_threshold', 0.3)
        self.imbalance_threshold = self.toxicity_config.get('imbalance_threshold', 0.6)
        self.freeze_duration_minutes = self.toxicity_config.get('freeze_duration_minutes', 5)
        
        # Data buffers
        self.volume_buckets: deque = deque(maxlen=100)
        self.trade_volume: deque = deque(maxlen=1000)
        self. buys_volume: deque = deque(maxlen=1000)
        self.sells_volume: deque = deque(maxlen=1000)
        
        # Toxicity history
        self.toxicity_history: deque = deque(maxlen=100)
        self.is_frozen = False
        self.freeze_until: Optional[datetime] = None
        
        # Current metrics
        self.current_metrics = ToxicityMetrics(
            vpin_score=0.0,
            order_book_imbalance=0.0,
            spread_widening=0.0,
            liquidity_score=1.0,
            spoofing_probability=0.0,
            overall_toxicity=0.0
        )
        
        logging.info("VPIN Filter initialized")
    
    async def initialize(self):
        """Initialize the VPIN filter."""
        self.logger = logging.getLogger(__name__)
        self.logger.info("VPIN Filter initialized")
    
    async def update_trade_data(self, price: float, volume: float, side: str):
        """Update with new trade data."""
        # Add to volume buffers
        self.trade_volume.append(volume)
        
        if side == 'buy':
            self.buys_volume.append(volume)
        else:
            self.sells_volume.append(volume)
        
        # Check if bucket is complete
        if len(self.trade_volume) >= 100:
            bucket_volume = sum(self.trade_volume)
            bucket_buys = sum(self.buys_volume)
            bucket_sells = sum(self.sells_volume)
            
            self.volume_buckets.append({
                'total': bucket_volume,
                'buys': bucket_buys,
                'sells': bucket_sells,
                'timestamp': datetime.now()
            })
            
            # Clear buffers
            self.trade_volume.clear()
            self.buys_volume.clear()
            self.sells_volume.clear()
            
            # Update VPIN
            await self._update_vpin()
    
    async def _update_vpin(self):
        """Update VPIN calculation."""
        if len(self.volume_buckets) < 2:
            return
        
        # Calculate VPIN
        volumes = [b['total'] for b in self.volume_buckets]
        avg_volume = statistics.mean(volumes)
        
        # Calculate volume volatility
        volume_volatility = statistics.stdev(volumes) if len(volumes) > 1 else 0
        vpin = volume_volatility / avg_volume if avg_volume > 0 else 0
        
        # Update current metrics
        self.current_metrics.vpin_score = vpin
        
        # Calculate order book imbalance
        total_buys = sum(b['buys'] for b in self.volume_buckets)
        total_sells = sum(b['sells'] for b in self.volume_buckets)
        total_volume = total_buys + total_sells
        
        imbalance = abs(total_buys - total_sells) / total_volume if total_volume > 0 else 0
        self.current_metrics.order_book_imbalance = imbalance
        
        # Calculate overall toxicity
        self.current_metrics.overall_toxicity = self._calculate_overall_toxicity()
        
        # Add to history
        self.toxicity_history.append(self.current_metrics.overall_toxicity)
        
        # Check if should freeze
        if self.current_metrics.overall_toxicity > self.vpin_threshold:
            await self._freeze_trading()
    
    def _calculate_overall_toxicity(self) -> float:
        """Calculate overall toxicity score."""
        vpin_weight = 0.4
        imbalance_weight = 0.3
        spread_weight = 0.2
        spoofing_weight = 0.1
        
        vpin_score = min(self.current_metrics.vpin_score / self.vpin_threshold, 1.0)
        imbalance_score = min(self.current_metrics.order_book_imbalance / self.imbalance_threshold, 1.0)
        spread_score = min(self.current_metrics.spread_widening / 0.5, 1.0)  # 50% spread max
        spoofing_score = self.current_metrics.spoofing_probability
        
        overall = (
            vpin_score * vpin_weight +
            imbalance_score * imbalance_weight +
            spread_score * spread_weight +
            spoofing_score * spoofing_weight
        )
        
        return overall
    
    async def _freeze_trading(self):
        """Freeze trading due to high toxicity."""
        self.is_frozen = True
        self.freeze_until = datetime.now() + timedelta(minutes=self.freeze_duration_minutes)
        
        self.logger.warning(
            f"Trading frozen due to high toxicity: {self.current_metrics.overall_toxicity:.2f} "
            f"(threshold: {self.vpin_threshold})"
        )
    
    async def check_trading_allowed(self) -> bool:
        """Check if trading is allowed (not frozen)."""
        if self.is_frozen:
            if datetime.now() > self.freeze_until:
                self.is_frozen = False
                self.freeze_until = None
                self.logger.info("Trading freeze lifted")
                return True
            return False
        
        return True
    
    async def get_toxicity_level(self) -> float:
        """Get current toxicity level."""
        return self.current_metrics.overall_toxicity
    
    async def get_spoofing_probability(self) -> float:
        """Calculate probability of spoofing."""
        # Analyze order book patterns for spoofing
        # Look for large orders that appear and disappear quickly
        
        if len(self.volume_buckets) < 10:
            return 0.0
        
        # Calculate order placement velocity
        recent_volumes = [b['total'] for b in list(self.volume_buckets)[-10:]]
        volume_changes = np.diff(recent_volumes)
        
        # High variance suggests potential spoofing
        if len(volume_changes) > 0:
            spoofing_prob = min(np.std(volume_changes) / np.mean(recent_volumes), 1.0)
        else:
            spoofing_prob = 0.0
        
        self.current_metrics.spoofing_probability = spoofing_prob
        return spoofing_prob
    
    async def update_order_book(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]):
        """Update with order book data."""
        if not bids or not asks:
            return
        
        # Calculate spread
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        
        if best_bid > 0 and best_ask > 0:
            spread = (best_ask - best_bid) / best_bid
            self.current_metrics.spread_widening = spread
        
        # Calculate liquidity score
        total_bid_volume = sum(b[1] for b in bids[:5])  # Top 5 levels
        total_ask_volume = sum(a[1] for a in asks[:5])
        total_liquidity = total_bid_volume + total_ask_volume
        
        if total_liquidity > 0:
            self.current_metrics.liquidity_score = min(total_liquidity / 1000000, 1.0)  # Normalize to 1M
    
    async def should_skip_trade(self) -> Tuple[bool, str]:
        """Check if trade should be skipped due to toxicity."""
        if not await self.check_trading_allowed():
            return True, "Trading frozen due to high toxicity"
        
        if self.current_metrics.overall_toxicity > self.vpin_threshold * 0.8:
            return True, f"High toxicity: {self.current_metrics.overall_toxicity:.2f}"
        
        if self.current_metrics.spoofing_probability > 0.7:
            return True, f"High spoofing probability: {self.current_metrics.spoofing_probability:.2f}"
        
        return False, ""
    
    async def shutdown(self):
        """Shutdown the VPIN filter."""
        self.logger.info("VPIN Filter shutdown complete")