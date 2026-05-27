"""Shared data models for The Canary pipeline.

These dataclasses define the contracts between pipeline stages.
Freezing these early ensures Engineer A and Engineer B can work independently.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import numpy as np
import time


class PipelineMode(str, Enum):
    """Audio routing mode determined by Scene Complexity Score."""
    MODE_A = "A"  # Clean single speaker
    MODE_B = "B"  # Single speaker + noise
    MODE_C = "C"  # Overlapping speakers


class DecisionAction(str, Enum):
    """Actions the arbitration engine can take."""
    EXECUTE = "execute"
    EXECUTE_BOTH = "execute_both"
    CLARIFY = "clarify"
    REJECT = "reject"


class UserRole(str, Enum):
    """RBAC roles for household users."""
    ADMIN = "admin"
    GUEST = "guest"
    UNKNOWN = "unknown"


@dataclass
class AudioStream:
    """A single separated audio stream from the acoustic pipeline."""
    stream_id: int
    audio: np.ndarray          # float32, 16kHz, mono
    sample_rate: int = 16000
    speaker_id: str = "unknown"
    speaker_confidence: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class PipelineOutput:
    """Output from Engineer A's acoustic pipeline (Stages 0-2).
    
    This is the FROZEN INTEGRATION CONTRACT between Engineer A and Engineer B.
    Do not modify without both engineers agreeing.
    """
    mode: PipelineMode
    timestamp: float
    audio_streams: list[AudioStream]
    scene_complexity_score: float = 0.0
    vad_confidence: float = 0.0
    wakeword_confidence: float = 0.0
    overlap_probability: float = 0.0
    noise_floor_db: float = -40.0


@dataclass
class TranscriptionResult:
    """Structured output from ASR + speaker metadata."""
    text: str
    speaker_id: str
    speaker_role: UserRole
    confidence: float              # ASR confidence
    speaker_confidence: float      # Biometric match confidence
    timestamp: float
    language: str = "en"
    emotion: str = "neutral"       # SenseVoice emotion tag


@dataclass
class ArbitrationDecision:
    """Decision from the arbitration engine."""
    action: DecisionAction
    commands: list[dict] = field(default_factory=list)
    reason: str = ""
    priority_speaker: Optional[str] = None
    confidence: float = 0.0
