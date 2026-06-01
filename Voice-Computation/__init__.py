"""Voice-Computation module for The Canary.

Stage 0 (Passive Idle) + Pre-Processing + Scene Analysis + Dynamic Resource Scaler.
"""
from .config import VoiceConfig, PipelineMode
from .models import ScalerDecision

__all__ = ["VoiceConfig", "PipelineMode", "ScalerDecision"]
