"""Data models (contracts) for the Voice-Computation pipeline.

These dataclasses define what flows between each stage.
This is the interface contract with Sanchit's downstream modules.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .config import PipelineMode


@dataclass
class VADResult:
    """Output from the Silero VAD stage."""

    is_speech: bool
    speech_probability: float  # [0.0 - 1.0]
    speech_start_sample: int = 0  # Where speech begins in the buffer
    speech_end_sample: int = 0  # Where speech ends in the buffer
    noise_floor_db: float = -60.0  # Estimated ambient noise level


@dataclass
class WakeWordResult:
    """Output from the wake-word detection stage."""

    detected: bool
    confidence: float  # [0.0 - 1.0]
    keyword: str = ""  # Which wake-word was detected
    consecutive_hits: int = 0  # How many consecutive frames detected it
    transcript: str = ""        # STT transcript that triggered detection
    stt_backend: str = "unknown"  # Backend that ran: google / whisper / acoustic-fallback


@dataclass
class PreProcessedAudio:
    """Output from the pre-processing stage."""

    audio: np.ndarray  # Cleaned float32 audio at 16kHz
    original_audio: np.ndarray  # Original audio before processing
    sample_rate: int = 16000
    noise_floor_db: float = -60.0
    snr_estimate_db: float = 30.0  # Estimated signal-to-noise ratio
    is_clipped: bool = False  # Whether clipping was detected
    dc_offset_removed: float = 0.0  # DC offset that was removed


@dataclass
class AudioFeatures:
    """Extracted features from the pre-processed audio."""

    mel_spectrogram: np.ndarray  # (n_mels, time_frames)
    energy: np.ndarray  # Per-frame energy
    zero_crossing_rate: np.ndarray  # Per-frame ZCR
    spectral_centroid: np.ndarray  # Per-frame spectral centroid
    rms_energy: float = 0.0  # Overall RMS
    duration_s: float = 0.0

    # New fields for FFT/MFCC/Pitch
    mfcc: Optional[np.ndarray] = None  # (n_mfcc, time_frames) MFCC matrix
    fft_magnitude: Optional[np.ndarray] = None  # (n_fft//2+1,) averaged FFT magnitude
    fft_freqs: Optional[np.ndarray] = None  # Frequency axis for fft_magnitude (Hz)
    pitch_hz: Optional[np.ndarray] = (
        None  # Per-frame fundamental frequency (0=unvoiced)
    )
    spectral_flatness: Optional[np.ndarray] = (
        None  # Per-frame spectral flatness (tonality)
    )
    spectral_rolloff: Optional[np.ndarray] = (
        None  # Per-frame spectral rolloff freq (Hz)
    )


@dataclass
class SceneAnalysis:
    """Output from the Scene Analyzer."""

    scene_complexity_score: float  # SCS [0.0 - 1.0]
    estimated_speaker_count: int  # 1, 2, or 3
    overlap_probability: float  # [0.0 - 1.0]
    noise_level_normalized: float  # [0.0 - 1.0]
    is_directed_speech: bool  # Device-directed vs ambient
    mode: PipelineMode  # Routing decision


@dataclass
class ScalerDecision:
    """Final output from the Dynamic Resource Scaler.

    THIS IS THE HANDOFF CONTRACT TO SANCHIT'S CODE.

    Sanchit receives this and routes to:
    - Mode A: Direct to ASR (skip TIGER)
    - Mode B: Adaptive DSP + speaker verification + ASR
    - Mode C: Full TIGER separation + CAM++ + ASR
    """

    mode: PipelineMode
    audio: np.ndarray  # Cleaned, ready-to-process audio (float32, 16kHz)
    timestamp: float = field(default_factory=time.time)

    # Metadata from upstream stages
    vad_confidence: float = 0.0
    wakeword_confidence: float = 0.0
    scene_complexity_score: float = 0.0
    estimated_speaker_count: int = 1
    overlap_probability: float = 0.0
    noise_floor_db: float = -60.0
    snr_estimate_db: float = 30.0
    is_directed_speech: bool = True

    # Features (optional, for downstream use)
    mel_spectrogram: Optional[np.ndarray] = None
    energy_profile: Optional[np.ndarray] = None
    separated_audio: list[np.ndarray] = field(default_factory=list)
    separation_method: str = "none"
    speaker_profiles: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict for logging / JSON output."""
        return {
            "mode": self.mode.value,
            "timestamp": self.timestamp,
            "vad_confidence": round(self.vad_confidence, 4),
            "wakeword_confidence": round(self.wakeword_confidence, 4),
            "scene_complexity_score": round(self.scene_complexity_score, 4),
            "estimated_speaker_count": self.estimated_speaker_count,
            "overlap_probability": round(self.overlap_probability, 4),
            "noise_floor_db": round(self.noise_floor_db, 2),
            "snr_estimate_db": round(self.snr_estimate_db, 2),
            "is_directed_speech": self.is_directed_speech,
            "audio_duration_s": round(len(self.audio) / 16000, 3),
            "separation_method": self.separation_method,
            "separated_stream_count": len(self.separated_audio),
            "speaker_profiles": self.speaker_profiles,
        }

    def __repr__(self) -> str:
        return (
            f"ScalerDecision(mode={self.mode.value}, "
            f"speakers={self.estimated_speaker_count}, "
            f"SCS={self.scene_complexity_score:.3f}, "
            f"SNR={self.snr_estimate_db:.1f}dB, "
            f"duration={len(self.audio) / 16000:.2f}s)"
        )
