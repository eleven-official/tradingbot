"""
Multi-Agent Trading System Foundation
Inspired by AutoHedge project
Provides specialized agents for different trading tasks
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np


class AgentType(Enum):
    """Types of trading agents."""
    DIRECTOR = "director"
    QUANT = "quant"
    RISK = "risk"
    EXECUTION = "execution"
    SENTIMENT = "sentiment"


@dataclass
class AgentOutput:
    """Standardized output from agents."""
    agent_type: AgentType
    data: Dict[str, Any]
    confidence: float
    timestamp: str


class BaseAgent:
    """Base class for all trading agents."""
    
    def __init__(self, agent_type: AgentType):
        self.agent_type = agent_type
        self.name = f"{agent_type.value.capitalize()}-Agent"
    
    def process(self, input_data: Dict[str, Any]) -> AgentOutput:
        """Process input data and return agent output."""
        raise NotImplementedError("Subclasses must implement process()")
    
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input data."""
        return True


class DirectorAgent(BaseAgent):
    """
    Director Agent: Orchestrates trading strategy and thesis generation.
    Coordinates other agents and makes high-level decisions.
    """
    
    def __init__(self):
        super().__init__(AgentType.DIRECTOR)
    
    def process(self, input_data: Dict[str, Any]) -> AgentOutput:
        """
        Generate trading thesis and coordinate other agents.
        
        Input: market_data, portfolio_state, risk_parameters
        Output: trading_thesis, market_regime, agent_tasks
        """
        market_data = input_data.get('market_data', {})
        portfolio_state = input_data.get('portfolio_state', {})
        
        # Analyze market regime
        market_regime = self._detect_market_regime(market_data)
        
        # Generate trading thesis
        thesis = self._generate_thesis(market_regime, portfolio_state)
        
        # Coordinate agent tasks
        agent_tasks = self._coordinate_agents(thesis, market_data)
        
        return AgentOutput(
            agent_type=self.agent_type,
            data={
                'market_regime': market_regime,
                'trading_thesis': thesis,
                'agent_tasks': agent_tasks,
                'recommendation': thesis.get('recommendation', 'HOLD')
            },
            confidence=thesis.get('confidence', 0.5),
            timestamp=pd.Timestamp.now().isoformat()
        )
    
    def _detect_market_regime(self, market_data: Dict) -> str:
        """Detect current market regime."""
        if 'returns' in market_data:
            returns = market_data['returns']
            volatility = returns.std()
            trend = returns.mean()
            
            if trend > 0 and volatility < returns.std() * 0.8:
                return "strong_bull"
            elif trend > 0:
                return "moderate_bull"
            elif trend < 0 and volatility < returns.std() * 0.8:
                return "strong_bear"
            elif trend < 0:
                return "moderate_bear"
            elif volatility > returns.std() * 1.5:
                return "high_volatility"
            else:
                return "ranging"
        return "unknown"
    
    def _generate_thesis(self, regime: str, portfolio: Dict) -> Dict:
        """Generate trading thesis based on regime and portfolio."""
        thesis = {
            'regime': regime,
            'recommendation': 'HOLD',
            'confidence': 0.5,
            'rationale': '',
            'risk_level': 'MEDIUM'
        }
        
        if regime in ['strong_bull', 'moderate_bull']:
            thesis['recommendation'] = 'BUY'
            thesis['confidence'] = 0.7 if regime == 'strong_bull' else 0.6
            thesis['rationale'] = f"Bullish market detected ({regime})"
            thesis['risk_level'] = 'LOW' if regime == 'strong_bull' else 'MEDIUM'
        elif regime in ['strong_bear', 'moderate_bear']:
            thesis['recommendation'] = 'SELL'
            thesis['confidence'] = 0.7 if regime == 'strong_bear' else 0.6
            thesis['rationale'] = f"Bearish market detected ({regime})"
            thesis['risk_level'] = 'HIGH'
        elif regime == 'high_volatility':
            thesis['recommendation'] = 'HOLD'
            thesis['confidence'] = 0.4
            thesis['rationale'] = "High volatility - reduce exposure"
            thesis['risk_level'] = 'HIGH'
        
        return thesis
    
    def _coordinate_agents(self, thesis: Dict, market_data: Dict) -> List[str]:
        """Coordinate which agents to run."""
        tasks = []
        
        if thesis['recommendation'] != 'HOLD':
            tasks.append('quant_analysis')
            tasks.append('risk_assessment')
            tasks.append('execution_planning')
        
        tasks.append('sentiment_analysis')
        
        return tasks


class QuantAgent(BaseAgent):
    """
    Quant Agent: Performs technical and statistical analysis.
    Provides quantitative scores and technical indicators.
    """
    
    def __init__(self):
        super().__init__(AgentType.QUANT)
    
    def process(self, input_data: Dict[str, Any]) -> AgentOutput:
        """
        Perform quantitative analysis.
        
        Input: symbol, price_data, thesis
        Output: technical_score, volume_score, trend_strength, key_levels
        """
        symbol = input_data.get('symbol', '')
        price_data = input_data.get('price_data', pd.DataFrame())
        
        if price_data.empty:
            return AgentOutput(
                agent_type=self.agent_type,
                data={'error': 'No price data available'},
                confidence=0.0,
                timestamp=pd.Timestamp.now().isoformat()
            )
        
        # Calculate technical indicators
        technical_score = self._calculate_technical_score(price_data)
        volume_score = self._calculate_volume_score(price_data)
        trend_strength = self._calculate_trend_strength(price_data)
        volatility = self._calculate_volatility(price_data)
        key_levels = self._identify_key_levels(price_data)
        
        # Overall probability score
        probability_score = (technical_score + volume_score + trend_strength) / 3
        
        return AgentOutput(
            agent_type=self.agent_type,
            data={
                'symbol': symbol,
                'technical_score': technical_score,
                'volume_score': volume_score,
                'trend_strength': trend_strength,
                'volatility': volatility,
                'probability_score': probability_score,
                'key_levels': key_levels
            },
            confidence=probability_score,
            timestamp=pd.Timestamp.now().isoformat()
        )
    
    def _calculate_technical_score(self, df: pd.DataFrame) -> float:
        """Calculate technical score (0-1)."""
        scores = []
        
        # RSI
        if len(df) > 14:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            last_rsi = rsi.iloc[-1]
            if 30 < last_rsi < 70:
                scores.append(0.8)
            elif last_rsi < 30:
                scores.append(0.9)  # Oversold - buy signal
            else:
                scores.append(0.1)  # Overbought - sell signal
        
        # Moving average alignment
        if len(df) > 50:
            sma_20 = df['close'].rolling(20).mean().iloc[-1]
            sma_50 = df['close'].rolling(50).mean().iloc[-1]
            if df['close'].iloc[-1] > sma_20 > sma_50:
                scores.append(0.9)
            elif df['close'].iloc[-1] < sma_20 < sma_50:
                scores.append(0.1)
            else:
                scores.append(0.5)
        
        return np.mean(scores) if scores else 0.5
    
    def _calculate_volume_score(self, df: pd.DataFrame) -> float:
        """Calculate volume score (0-1)."""
        if 'volume' not in df.columns or len(df) < 20:
            return 0.5
        
        avg_volume = df['volume'].rolling(20).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        
        if current_volume > avg_volume * 1.5:
            return 0.9
        elif current_volume > avg_volume:
            return 0.7
        else:
            return 0.4
    
    def _calculate_trend_strength(self, df: pd.DataFrame) -> float:
        """Calculate trend strength (0-1)."""
        if len(df) < 20:
            return 0.5
        
        returns = df['close'].pct_change().dropna()
        positive_ratio = (returns > 0).sum() / len(returns)
        
        return positive_ratio
    
    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """Calculate volatility."""
        if len(df) < 20:
            return 0.0
        
        returns = df['close'].pct_change().dropna()
        return returns.std() * np.sqrt(252)  # Annualized
    
    def _identify_key_levels(self, df: pd.DataFrame) -> Dict[str, float]:
        """Identify support and resistance levels."""
        if len(df) < 50:
            return {'support': 0, 'resistance': 0, 'pivot': 0}
        
        recent = df.tail(50)
        support = recent['low'].min()
        resistance = recent['high'].max()
        pivot = (support + resistance) / 2
        
        return {
            'support': support,
            'resistance': resistance,
            'pivot': pivot
        }


class RiskAgent(BaseAgent):
    """
    Risk Agent: Assesses position sizing and risk exposure.
    Provides risk metrics and position size recommendations.
    """
    
    def __init__(self):
        super().__init__(AgentType.RISK)
    
    def process(self, input_data: Dict[str, Any]) -> AgentOutput:
        """
        Perform risk assessment.
        
        Input: symbol, thesis, quant_analysis, portfolio_state
        Output: position_size, max_drawdown_risk, market_risk_exposure, risk_score
        """
        symbol = input_data.get('symbol', '')
        thesis = input_data.get('thesis', {})
        quant_analysis = input_data.get('quant_analysis', {})
        portfolio_state = input_data.get('portfolio_state', {})
        
        # Calculate position size based on risk
        position_size = self._calculate_position_size(quant_analysis, portfolio_state)
        
        # Assess drawdown risk
        max_drawdown_risk = self._assess_drawdown_risk(quant_analysis)
        
        # Assess market risk exposure
        market_risk_exposure = self._assess_market_risk(portfolio_state)
        
        # Overall risk score
        risk_score = self._calculate_risk_score(
            position_size, max_drawdown_risk, market_risk_exposure
        )
        
        return AgentOutput(
            agent_type=self.agent_type,
            data={
                'symbol': symbol,
                'position_size': position_size,
                'max_drawdown_risk': max_drawdown_risk,
                'market_risk_exposure': market_risk_exposure,
                'risk_score': risk_score,
                'recommendation': self._get_risk_recommendation(risk_score)
            },
            confidence=1.0 - risk_score,  # Higher confidence for lower risk
            timestamp=pd.Timestamp.now().isoformat()
        )
    
    def _calculate_position_size(self, quant: Dict, portfolio: Dict) -> float:
        """Calculate recommended position size (percentage of portfolio)."""
        probability = quant.get('probability_score', 0.5)
        volatility = quant.get('volatility', 0.2)
        
        # Kelly criterion simplified
        base_size = probability * 0.5  # Max 50% position
        vol_adjusted = base_size / (1 + volatility * 5)
        
        return min(vol_adjusted, 0.25)  # Cap at 25% per position
    
    def _assess_drawdown_risk(self, quant: Dict) -> float:
        """Assess maximum drawdown risk (0-1)."""
        volatility = quant.get('volatility', 0.2)
        return min(volatility * 2, 1.0)
    
    def _assess_market_risk(self, portfolio: Dict) -> float:
        """Assess market risk exposure (0-1)."""
        total_exposure = portfolio.get('total_exposure', 0.5)
        return min(total_exposure, 1.0)
    
    def _calculate_risk_score(self, pos_size: float, dd_risk: float, market_risk: float) -> float:
        """Calculate overall risk score (0-1, higher = riskier)."""
        return (pos_size * 0.4 + dd_risk * 0.3 + market_risk * 0.3)
    
    def _get_risk_recommendation(self, risk_score: float) -> str:
        """Get risk recommendation based on score."""
        if risk_score < 0.3:
            return "LOW_RISK"
        elif risk_score < 0.6:
            return "MODERATE_RISK"
        else:
            return "HIGH_RISK"


class ExecutionAgent(BaseAgent):
    """
    Execution Agent: Generates trade orders.
    Provides order details including entry, stop loss, take profit.
    """
    
    def __init__(self):
        super().__init__(AgentType.EXECUTION)
    
    def process(self, input_data: Dict[str, Any]) -> AgentOutput:
        """
        Generate execution plan.
        
        Input: symbol, thesis, risk_assessment, quant_analysis
        Output: order_type, quantity, entry_price, stop_loss, take_profit
        """
        symbol = input_data.get('symbol', '')
        thesis = input_data.get('thesis', {})
        risk_assessment = input_data.get('risk_assessment', {})
        quant_analysis = input_data.get('quant_analysis', {})
        current_price = input_data.get('current_price', 0)
        
        position_size = risk_assessment.get('position_size', 0.1)
        portfolio_value = input_data.get('portfolio_value', 25000)
        
        # Calculate order details
        order_type = "MARKET"
        quantity = int((portfolio_value * position_size) / current_price)
        
        # Stop loss and take profit based on ATR
        key_levels = quant_analysis.get('key_levels', {})
        volatility = quant_analysis.get('volatility', 0.2)
        
        if thesis.get('recommendation') == 'BUY':
            stop_loss = current_price * (1 - volatility * 2)
            take_profit = current_price * (1 + volatility * 3)
        elif thesis.get('recommendation') == 'SELL':
            stop_loss = current_price * (1 + volatility * 2)
            take_profit = current_price * (1 - volatility * 3)
        else:
            stop_loss = 0
            take_profit = 0
        
        return AgentOutput(
            agent_type=self.agent_type,
            data={
                'symbol': symbol,
                'order_type': order_type,
                'quantity': quantity,
                'entry_price': current_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'time_in_force': 'GTC'
            },
            confidence=risk_assessment.get('confidence', 0.5),
            timestamp=pd.Timestamp.now().isoformat()
        )


class SentimentAgent(BaseAgent):
    """
    Sentiment Agent: Analyzes market sentiment.
    Provides sentiment analysis and news indicators.
    """
    
    def __init__(self):
        super().__init__(AgentType.SENTIMENT)
    
    def process(self, input_data: Dict[str, Any]) -> AgentOutput:
        """
        Analyze market sentiment.
        
        Input: symbol, news_data, social_data
        Output: sentiment_score, news_sentiment, social_sentiment
        """
        symbol = input_data.get('symbol', '')
        
        # Simplified sentiment analysis (in production, would use NLP/news APIs)
        sentiment_score = 0.5  # Neutral
        news_sentiment = 0.5
        social_sentiment = 0.5
        
        return AgentOutput(
            agent_type=self.agent_type,
            data={
                'symbol': symbol,
                'sentiment_score': sentiment_score,
                'news_sentiment': news_sentiment,
                'social_sentiment': social_sentiment,
                'recommendation': 'NEUTRAL'
            },
            confidence=0.5,
            timestamp=pd.Timestamp.now().isoformat()
        )


class MultiAgentOrchestrator:
    """
    Orchestrates multiple agents for comprehensive trading analysis.
    """
    
    def __init__(self):
        self.director = DirectorAgent()
        self.quant = QuantAgent()
        self.risk = RiskAgent()
        self.execution = ExecutionAgent()
        self.sentiment = SentimentAgent()
    
    def run_analysis(
        self,
        symbol: str,
        price_data: pd.DataFrame,
        portfolio_state: Dict,
        current_price: float
    ) -> Dict[str, Any]:
        """
        Run full multi-agent analysis.
        
        Returns comprehensive analysis from all agents.
        """
        # Step 1: Director generates thesis
        director_input = {
            'market_data': {'returns': price_data['close'].pct_change().dropna()},
            'portfolio_state': portfolio_state
        }
        director_output = self.director.process(director_input)
        
        if director_output.data['recommendation'] == 'HOLD':
            return {
                'recommendation': 'HOLD',
                'confidence': director_output.confidence,
                'rationale': director_output.data['trading_thesis']['rationale'],
                'agent_outputs': {'director': director_output.data}
            }
        
        # Step 2: Quant analysis
        quant_input = {
            'symbol': symbol,
            'price_data': price_data,
            'thesis': director_output.data['trading_thesis']
        }
        quant_output = self.quant.process(quant_input)
        
        # Step 3: Risk assessment
        risk_input = {
            'symbol': symbol,
            'thesis': director_output.data['trading_thesis'],
            'quant_analysis': quant_output.data,
            'portfolio_state': portfolio_state
        }
        risk_output = self.risk.process(risk_input)
        
        # Step 4: Execution planning
        execution_input = {
            'symbol': symbol,
            'thesis': director_output.data['trading_thesis'],
            'risk_assessment': risk_output.data,
            'quant_analysis': quant_output.data,
            'current_price': current_price,
            'portfolio_value': portfolio_state.get('total_value', 25000)
        }
        execution_output = self.execution.process(execution_input)
        
        # Step 5: Sentiment analysis
        sentiment_input = {'symbol': symbol}
        sentiment_output = self.sentiment.process(sentiment_input)
        
        # Combine all outputs
        return {
            'recommendation': director_output.data['recommendation'],
            'confidence': np.mean([
                director_output.confidence,
                quant_output.confidence,
                risk_output.confidence,
                execution_output.confidence
            ]),
            'rationale': director_output.data['trading_thesis']['rationale'],
            'agent_outputs': {
                'director': director_output.data,
                'quant': quant_output.data,
                'risk': risk_output.data,
                'execution': execution_output.data,
                'sentiment': sentiment_output.data
            }
        }
