from dataclasses import dataclass, field
from enum import Enum
import numpy as np


class PipelineMode(str, Enum):
    MODE_A = "A"
    MODE_B = "B"
    MODE_C = "C"


@dataclass
class AudioStream:
    stream_id: int
    audio: np.ndarray
    sample_rate: int = 16000
    speaker_id: str = "unknown"
    speaker_confidence: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class PipelineOutput:
    mode: PipelineMode
    timestamp: float
    audio_streams: list[AudioStream]
    scene_complexity_score: float = 0.0
    vad_confidence: float = 0.0
    wakeword_confidence: float = 0.0
    overlap_probability: float = 0.0
    noise_floor_db: float = -40.0
    speaker_count_estimate: int = 1
