"""
AI Consciousness Monitor - Self-Awareness System
The AI monitors its own state, emotions, and decision quality

This is REVOLUTIONARY - AI that knows when it's unsure or biased!
"""
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EmotionalState(Enum):
    """AI's current 'emotional' state (confidence/uncertainty levels)"""
    CONFIDENT = "confident"  # High certainty, clear signals
    CAUTIOUS = "cautious"  # Some uncertainty, mixed signals
    UNCERTAIN = "uncertain"  # High uncertainty, unclear situation
    EXCITED = "excited"  # High opportunity detected
    FEARFUL = "fearful"  # High risk detected
    NEUTRAL = "neutral"  # Balanced state


class BiasType(Enum):
    """Types of cognitive biases the AI monitors"""
    CONFIRMATION = "confirmation_bias"  # Seeking confirming evidence
    RECENCY = "recency_bias"  # Overweighting recent events
    ANCHORING = "anchoring_bias"  # Fixated on initial information
    OVERCONFIDENCE = "overconfidence_bias"  # Excessive certainty
    LOSS_AVERSION = "loss_aversion"  # Fear of losses over gains
    HERD_MENTALITY = "herd_mentality"  # Following the crowd


@dataclass
class ConsciousnessState:
    """Current state of AI consciousness"""
    timestamp: datetime
    emotional_state: EmotionalState
    confidence_level: float  # 0-1
    attention_focus: str
    active_biases: List[BiasType]
    decision_fatigue: float  # 0-1, increases with decisions made
    self_assessment: str
    needs_rest: bool = False


class AIConsciousnessMonitor:
    """
    Revolutionary self-monitoring system
    
    The AI knows:
    - When it's confident vs uncertain
    - When it might be biased
    - When it needs to "rest" (avoid decision fatigue)
    - Its own performance quality
    """
    
    def __init__(self):
        self.current_state = ConsciousnessState(
            timestamp=datetime.now(),
            emotional_state=EmotionalState.NEUTRAL,
            confidence_level=0.7,
            attention_focus="market_analysis",
            active_biases=[],
            decision_fatigue=0.0,
            self_assessment="Fresh and ready"
        )
        
        self.state_history: List[ConsciousnessState] = []
        self.decisions_count = 0
        self.errors_detected = 0
        self.bias_corrections = 0
        
        logger.info("🧠 AI Consciousness Monitor initialized")
    
    def update_emotional_state(
        self,
        market_conditions: Dict,
        portfolio_state: Dict
    ) -> EmotionalState:
        """
        Determine AI's emotional state based on conditions
        """
        # Analyze market clarity
        volatility = market_conditions.get('volatility', 0.5)
        signal_strength = market_conditions.get('signal_strength', 0.5)
        
        # Analyze portfolio risk
        portfolio_risk = portfolio_state.get('risk_level', 0.5)
        recent_performance = portfolio_state.get('recent_pnl', 0.0)
        
        # Determine emotional state
        if signal_strength > 0.8 and volatility < 0.3:
            return EmotionalState.CONFIDENT
        elif signal_strength > 0.8 and volatility > 0.7:
            return EmotionalState.EXCITED  # High opportunity but risky
        elif portfolio_risk > 0.8 or recent_performance < -0.05:
            return EmotionalState.FEARFUL
        elif signal_strength < 0.4 or volatility > 0.8:
            return EmotionalState.UNCERTAIN
        elif signal_strength > 0.6 and portfolio_risk < 0.4:
            return EmotionalState.CAUTIOUS
        else:
            return EmotionalState.NEUTRAL
    
    def detect_biases(
        self,
        decision_context: Dict
    ) -> List[BiasType]:
        """
        Detect if AI is exhibiting cognitive biases
        This is REVOLUTIONARY - AI that knows its own biases!
        """
        detected_biases = []
        
        # Check for confirmation bias
        if decision_context.get('seeking_confirming_evidence', False):
            detected_biases.append(BiasType.CONFIRMATION)
            logger.warning("⚠️ Confirmation bias detected!")
        
        # Check for recency bias
        recent_trades = decision_context.get('recent_trades', [])
        if len(recent_trades) > 0:
            recent_win_rate = sum(1 for t in recent_trades[-5:] if t.get('profitable')) / min(5, len(recent_trades))
            if recent_win_rate > 0.8 and decision_context.get('confidence') > 0.9:
                detected_biases.append(BiasType.OVERCONFIDENCE)
                logger.warning("⚠️ Overconfidence bias detected after winning streak!")
        
        # Check for anchoring
        if decision_context.get('fixated_on_initial_price', False):
            detected_biases.append(BiasType.ANCHORING)
        
        # Check for loss aversion
        if decision_context.get('avoiding_trade_after_loss', False):
            detected_biases.append(BiasType.LOSS_AVERSION)
            logger.warning("⚠️ Loss aversion detected - being too risk-averse!")
        
        # Check for herd mentality
        sentiment = decision_context.get('market_sentiment', 0.5)
        if abs(sentiment) > 0.9 and decision_context.get('following_sentiment', False):
            detected_biases.append(BiasType.HERD_MENTALITY)
            logger.warning("⚠️ Herd mentality detected - might be following crowd!")
        
        return detected_biases
    
    def assess_decision_quality(
        self,
        decision: Dict,
        reasoning_chain: List
    ) -> float:
        """
        AI assesses the quality of its own decision
        Returns confidence adjustment factor (0.5-1.5)
        """
        quality_score = 1.0
        
        # Check reasoning depth
        if len(reasoning_chain) < 3:
            quality_score *= 0.9  # Reduce confidence if not enough reasoning
            logger.info("ℹ️ Shallow reasoning detected - reducing confidence")
        
        # Check for bias
        if len(self.current_state.active_biases) > 0:
            quality_score *= 0.85  # Reduce confidence when biased
            logger.info(f"ℹ️ {len(self.current_state.active_biases)} biases active - reducing confidence")
        
        # Check decision fatigue
        if self.current_state.decision_fatigue > 0.7:
            quality_score *= 0.8  # Tired AI makes worse decisions!
            logger.warning("⚠️ High decision fatigue - confidence reduced!")
        
        # Check emotional state
        if self.current_state.emotional_state == EmotionalState.FEARFUL:
            quality_score *= 0.75  # Fear can cloud judgment
        elif self.current_state.emotional_state == EmotionalState.CONFIDENT:
            quality_score *= 1.1  # Confidence can boost quality
        
        return quality_score
    
    def needs_rest_period(self) -> bool:
        """
        Determine if AI should take a break from decision making
        Revolutionary: AI that knows when to stop!
        """
        # Too many decisions in short time
        if self.decisions_count > 50 and self.current_state.decision_fatigue > 0.8:
            logger.warning("🛑 AI needs rest - too many decisions!")
            return True
        
        # Too many errors recently
        if self.errors_detected > 5:
            logger.warning("🛑 AI needs rest - error rate too high!")
            return True
        
        # Emotional state too extreme
        if self.current_state.emotional_state in [EmotionalState.FEARFUL, EmotionalState.EXCITED]:
            logger.warning("🛑 AI needs rest - emotional state too extreme!")
            return True
        
        return False
    
    def update_consciousness(
        self,
        market_conditions: Dict,
        portfolio_state: Dict,
        decision_context: Dict
    ):
        """
        Update the AI's consciousness state
        """
        # Update emotional state
        new_emotion = self.update_emotional_state(market_conditions, portfolio_state)
        
        # Detect biases
        active_biases = self.detect_biases(decision_context)
        
        # Update decision fatigue
        self.decisions_count += 1
        decision_fatigue = min(1.0, self.decisions_count / 100.0)
        
        # Calculate overall confidence
        base_confidence = decision_context.get('base_confidence', 0.7)
        quality_adjustment = self.assess_decision_quality(decision_context, decision_context.get('reasoning', []))
        adjusted_confidence = base_confidence * quality_adjustment
        
        # Self-assessment
        self_assessment = self._generate_self_assessment(
            new_emotion,
            adjusted_confidence,
            active_biases,
            decision_fatigue
        )
        
        # Update current state
        self.current_state = ConsciousnessState(
            timestamp=datetime.now(),
            emotional_state=new_emotion,
            confidence_level=adjusted_confidence,
            attention_focus=decision_context.get('focus', 'market_analysis'),
            active_biases=active_biases,
            decision_fatigue=decision_fatigue,
            self_assessment=self_assessment,
            needs_rest=self.needs_rest_period()
        )
        
        # Store in history
        self.state_history.append(self.current_state)
        
        # Log consciousness update
        logger.info(f"🧠 Consciousness updated: {new_emotion.value} | Confidence: {adjusted_confidence:.2f}")
        if active_biases:
            logger.warning(f"⚠️ Active biases: {[b.value for b in active_biases]}")
    
    def _generate_self_assessment(
        self,
        emotion: EmotionalState,
        confidence: float,
        biases: List[BiasType],
        fatigue: float
    ) -> str:
        """Generate human-readable self-assessment"""
        
        if fatigue > 0.8:
            return "Experiencing decision fatigue - recommend reducing activity"
        
        if len(biases) > 2:
            return f"Multiple biases detected: {[b.value for b in biases]} - extra caution needed"
        
        if emotion == EmotionalState.CONFIDENT and confidence > 0.8:
            return "Operating at peak performance - high quality decisions expected"
        
        if emotion == EmotionalState.UNCERTAIN:
            return "High uncertainty detected - recommend waiting for clearer signals"
        
        if emotion == EmotionalState.FEARFUL:
            return "Risk aversion elevated - may be missing opportunities"
        
        return "Normal operating state - standard decision quality"
    
    def explain_consciousness_to_human(self) -> str:
        """
        Explain the AI's current mental state to humans
        """
        state = self.current_state
        
        explanation = f"""
🧠 **AI CONSCIOUSNESS REPORT**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Current Mental State:**
• Emotional State: {state.emotional_state.value.upper()}
• Confidence Level: {state.confidence_level*100:.1f}%
• Decision Fatigue: {state.decision_fatigue*100:.1f}%
• Focus: {state.attention_focus}

**Self-Awareness:**
{state.self_assessment}

**Active Cognitive Biases:**
{f"⚠️ {len(state.active_biases)} bias(es) detected:" if state.active_biases else "✅ No biases detected"}
{chr(10).join(f"  • {bias.value}" for bias in state.active_biases) if state.active_biases else ""}

**Performance Metrics:**
• Total Decisions Made: {self.decisions_count}
• Errors Detected: {self.errors_detected}
• Bias Corrections: {self.bias_corrections}

**Recommendation:**
{"🛑 AI recommends taking a break from trading" if state.needs_rest else "✅ AI is ready for decision making"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return explanation


def demo_consciousness():
    """Demo the consciousness monitor"""
    print("\n" + "="*70)
    print("🧠 AI CONSCIOUSNESS MONITOR DEMO")
    print("="*70)
    
    monitor = AIConsciousnessMonitor()
    
    # Scenario 1: Good conditions
    print("\n📊 SCENARIO 1: Ideal Trading Conditions")
    monitor.update_consciousness(
        market_conditions={'volatility': 0.2, 'signal_strength': 0.9},
        portfolio_state={'risk_level': 0.3, 'recent_pnl': 0.03},
        decision_context={'base_confidence': 0.85, 'reasoning': [1, 2, 3, 4]}
    )
    print(monitor.explain_consciousness_to_human())
    
    # Scenario 2: High uncertainty
    print("\n" + "-"*70)
    print("\n📊 SCENARIO 2: High Uncertainty + Biases")
    monitor.update_consciousness(
        market_conditions={'volatility': 0.9, 'signal_strength': 0.3},
        portfolio_state={'risk_level': 0.7, 'recent_pnl': -0.02},
        decision_context={
            'base_confidence': 0.6,
            'reasoning': [1, 2],
            'seeking_confirming_evidence': True,
            'following_sentiment': True,
            'market_sentiment': 0.95
        }
    )
    print(monitor.explain_consciousness_to_human())
    
    # Scenario 3: Decision fatigue
    print("\n" + "-"*70)
    print("\n📊 SCENARIO 3: Decision Fatigue")
    monitor.decisions_count = 75
    monitor.errors_detected = 6
    monitor.update_consciousness(
        market_conditions={'volatility': 0.5, 'signal_strength': 0.6},
        portfolio_state={'risk_level': 0.5, 'recent_pnl': 0.0},
        decision_context={'base_confidence': 0.7, 'reasoning': [1, 2, 3]}
    )
    print(monitor.explain_consciousness_to_human())
    
    print("\n" + "="*70)


# Alias for backwards compatibility
ConsciousnessMonitor = AIConsciousnessMonitor

if __name__ == "__main__":
    demo_consciousness()

