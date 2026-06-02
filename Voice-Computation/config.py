"""Central configuration for the Voice-Computation module."""

from dataclasses import dataclass, field
from enum import Enum


class PipelineMode(str, Enum):
    """Audio routing mode determined by Scene Complexity Score."""

    MODE_A = "A"  # Clean single speaker → lightweight DSP, skip separation
    MODE_B = "B"  # Moderate noise/mild overlap → adaptive DSP + verification
    MODE_C = "C"  # Heavy overlap/noisy → full TIGER separation


@dataclass
class VoiceConfig:
    """Configuration for the entire Voice-Computation pipeline.

    Adjust thresholds based on your hardware and environment.
    """

    # ── Audio Capture ──────────────────────────────────────────────
    sample_rate: int = 16000  # Hz (everything runs at 16kHz)
    channels: int = 1  # Mono
    chunk_duration_ms: int = 30  # Size of each audio chunk in ms
    buffer_duration_s: float = 10.0  # Ring buffer holds this many seconds
    activation_window_s: float = (
        1.5  # Audio window passed to processing after activation
    )

    # ── Silero VAD ─────────────────────────────────────────────────
    vad_threshold: float = 0.5  # Speech probability threshold
    vad_min_speech_ms: int = 250  # Minimum speech duration to trigger
    vad_min_silence_ms: int = 300  # Silence duration before speech end
    vad_window_size_samples: int = 512  # Silero processes 512 samples at 16kHz (32ms)
    vad_energy_threshold: float = (
        0.001  # Min RMS energy — below this = silence, skip ONNX
    )
    vad_consecutive_required: int = (
        2  # Consecutive above-threshold frames to confirm speech
    )

    # ── Wake-Word ──────────────────────────────────────────────────
    wakeword_threshold: float = 0.5  # Activation threshold
    wakeword_keywords: list = field(
        default_factory=lambda: ["canary", "hey canary", "ok canary"]
    )
    wakeword_energy_threshold: float = 0.01  # Min RMS for keyword check
    wakeword_min_duration_ms: int = 250  # Minimum speech duration for a keyword
    wakeword_max_duration_ms: int = 2000  # Maximum speech duration for a keyword
    wakeword_mfcc_threshold: float = (
        10.0  # DTW distance threshold for template matching
    )
    wakeword_models: list = field(
        default_factory=lambda: []
    )  # legacy openwakeword models
    wakeword_consecutive_hits: int = 2  # Require N consecutive detections

    # ── Pre-Processing ─────────────────────────────────────────────
    pre_emphasis_coeff: float = 0.97  # Pre-emphasis filter coefficient
    noise_estimation_frames: int = 10  # Number of frames for noise estimation
    noise_oversubtraction: float = 2.0  # Spectral subtraction oversubtraction factor

    # ── Feature Extraction ─────────────────────────────────────────
    n_mels: int = 40  # Mel filterbank bins (matches microWakeWord)
    n_fft: int = 512  # FFT size
    hop_length: int = 160  # 10ms hop at 16kHz

    # ── Scene Analysis ─────────────────────────────────────────────
    # Scene Complexity Score weights
    scs_weight_overlap: float = 0.4  # Weight for overlap probability
    scs_weight_noise: float = 0.35  # Weight for noise floor
    scs_weight_wakeword: float = 0.25  # Weight for (1 - wakeword_certainty)

    # SCS thresholds for mode routing
    scs_threshold_a: float = 0.20  # Below this → Mode A
    scs_threshold_b: float = 0.45  # Below this → Mode B, above → Mode C

    # ── Dynamic Resource Scaler ────────────────────────────────────
    min_confidence_threshold: float = 0.5  # Drop audio below this confidence

    # ── Paths ──────────────────────────────────────────────────────
    silero_model_path: str = ""  # Empty = auto-download from torch.hub
    test_audio_dir: str = "data/test_audio"

    @property
    def chunk_size_samples(self) -> int:
        """Number of samples per audio chunk."""
        return int(self.sample_rate * self.chunk_duration_ms / 1000)

    @property
    def buffer_size_samples(self) -> int:
        """Total ring buffer size in samples."""
        return int(self.sample_rate * self.buffer_duration_s)

    @property
    def activation_window_samples(self) -> int:
        """Number of samples in the activation window."""
        return int(self.sample_rate * self.activation_window_s)
