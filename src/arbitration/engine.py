"""Arbitration Engine — Rule-based conflict resolution + RBAC.

Evaluates transcriptions from multiple speakers,
detects conflicts, applies privilege hierarchy,
and determines the appropriate action.

Strategy: Rule-based logic is PRIMARY. SLM is SECONDARY (bonus).
"""
from src.common.models import (
    TranscriptionResult, ArbitrationDecision, 
    DecisionAction, UserRole
)


# Intent keywords for conflict detection
OPPOSING_INTENTS = {
    ("on", "off"), ("off", "on"),
    ("play", "stop"), ("stop", "play"),
    ("open", "close"), ("close", "open"),
    ("increase", "decrease"), ("decrease", "increase"),
    ("up", "down"), ("down", "up"),
    ("start", "stop"), ("stop", "start"),
}

# Target keywords for device/action matching
TARGET_KEYWORDS = [
    "lights", "light", "tv", "television", "music", "ac", 
    "air conditioner", "fan", "thermostat", "alarm", "timer",
    "door", "window", "curtain", "heater"
]


class ArbitrationEngine:
    """Rule-based arbitration engine with RBAC support."""
    
    def __init__(self, state_store=None):
        """Initialize with optional state store for profile lookups."""
        self.state_store = state_store
    
    def arbitrate(self, results: list[TranscriptionResult]) -> ArbitrationDecision:
        """Main arbitration entry point.
        
        Args:
            results: List of transcription results (1 or 2 speakers)
            
        Returns:
            ArbitrationDecision with action, commands, and reason
        """
        if not results:
            return ArbitrationDecision(
                action=DecisionAction.REJECT,
                reason="No transcriptions received"
            )
        
        # Filter out low-confidence results
        valid = [r for r in results if r.confidence >= 0.5]
        if not valid:
            return ArbitrationDecision(
                action=DecisionAction.CLARIFY,
                reason="All transcriptions below confidence threshold"
            )
        
        # Reject unknown speakers
        unknown = [r for r in valid if r.speaker_id == "unknown"]
        if unknown and len(unknown) == len(valid):
            return ArbitrationDecision(
                action=DecisionAction.REJECT,
                reason="No recognized speakers detected"
            )
        
        # Single command path
        if len(valid) == 1:
            return self._handle_single(valid[0])
        
        # Multi-command path
        return self._handle_multiple(valid)
    
    def _handle_single(self, result: TranscriptionResult) -> ArbitrationDecision:
        """Handle a single speaker command."""
        if result.speaker_id == "unknown":
            return ArbitrationDecision(
                action=DecisionAction.CLARIFY,
                reason="Speaker not recognized. Please identify yourself."
            )
        
        return ArbitrationDecision(
            action=DecisionAction.EXECUTE,
            commands=[{"text": result.text, "speaker": result.speaker_id}],
            reason=f"Single command from {result.speaker_id} (confidence: {result.confidence:.2f})",
            priority_speaker=result.speaker_id,
            confidence=result.confidence
        )
    
    def _handle_multiple(self, results: list[TranscriptionResult]) -> ArbitrationDecision:
        """Handle multiple simultaneous commands."""
        r1, r2 = results[0], results[1]
        
        if self.detect_conflict(r1.text, r2.text):
            return self._resolve_conflict(r1, r2)
        
        # Non-conflicting: execute both
        return ArbitrationDecision(
            action=DecisionAction.EXECUTE_BOTH,
            commands=[
                {"text": r1.text, "speaker": r1.speaker_id},
                {"text": r2.text, "speaker": r2.speaker_id}
            ],
            reason="Non-conflicting commands — executing both sequentially",
            confidence=min(r1.confidence, r2.confidence)
        )
    
    def _resolve_conflict(self, r1: TranscriptionResult, r2: TranscriptionResult) -> ArbitrationDecision:
        """Resolve conflicting commands using RBAC hierarchy."""
        # Admin overrides Guest
        if r1.speaker_role == UserRole.ADMIN and r2.speaker_role != UserRole.ADMIN:
            return ArbitrationDecision(
                action=DecisionAction.EXECUTE,
                commands=[{"text": r1.text, "speaker": r1.speaker_id}],
                reason=f"Conflict resolved: {r1.speaker_id} (Admin) overrides {r2.speaker_id} (Guest)",
                priority_speaker=r1.speaker_id,
                confidence=r1.confidence
            )
        
        if r2.speaker_role == UserRole.ADMIN and r1.speaker_role != UserRole.ADMIN:
            return ArbitrationDecision(
                action=DecisionAction.EXECUTE,
                commands=[{"text": r2.text, "speaker": r2.speaker_id}],
                reason=f"Conflict resolved: {r2.speaker_id} (Admin) overrides {r1.speaker_id} (Guest)",
                priority_speaker=r2.speaker_id,
                confidence=r2.confidence
            )
        
        # Same privilege level: ask for clarification
        return ArbitrationDecision(
            action=DecisionAction.CLARIFY,
            reason=f"Conflicting commands from users with equal privilege. Please clarify.",
            commands=[
                {"text": r1.text, "speaker": r1.speaker_id},
                {"text": r2.text, "speaker": r2.speaker_id}
            ]
        )
    
    def detect_conflict(self, cmd_a: str, cmd_b: str) -> bool:
        """Detect if two commands conflict (same target, opposing intents)."""
        a_lower = cmd_a.lower()
        b_lower = cmd_b.lower()
        
        # Find shared target
        shared_target = None
        for target in TARGET_KEYWORDS:
            if target in a_lower and target in b_lower:
                shared_target = target
                break
        
        if not shared_target:
            return False
        
        # Check for opposing intent keywords
        for intent_a, intent_b in OPPOSING_INTENTS:
            if intent_a in a_lower and intent_b in b_lower:
                return True
        
        return False
