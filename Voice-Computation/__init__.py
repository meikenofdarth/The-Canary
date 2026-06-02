"""Voice-Computation module for The Canary.

Stage 0 (Passive Idle) + Pre-Processing + Scene Analysis + Dynamic Resource Scaler.

Public API:
    VoiceComputationPipeline  — main pipeline class
    ScalerDecision            — output dataclass (handoff to Sanchit)
    PipelineMode              — MODE_A / MODE_B / MODE_C
    VoiceConfig               — configuration dataclass

    scaler_to_pipeline_output — bridge: ScalerDecision → PipelineOutput
    pipeline_output_summary   — bridge: human-readable summary string
"""
from .config import VoiceConfig, PipelineMode
from .models import ScalerDecision
from .bridge import scaler_to_pipeline_output, pipeline_output_summary

__all__ = [
    "VoiceConfig",
    "PipelineMode",
    "ScalerDecision",
    "scaler_to_pipeline_output",
    "pipeline_output_summary",
]
