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
    # Silero's recommended starting point is 0.5. Tune against real recordings.
    vad_threshold: float = 0.5  # Speech probability threshold
    vad_min_speech_ms: int = 250  # Minimum speech duration to trigger
    vad_min_silence_ms: int = 300  # Silence duration before speech end
    vad_window_size_samples: int = 512  # Silero processes 512 samples at 16kHz (32ms)
    vad_energy_threshold: float = (
        0.003  # Min RMS energy — below this = silence, skip ONNX
    )
    vad_consecutive_required: int = (
        2  # Consecutive above-threshold frames to confirm speech
    )

    # ── Wake-Word ──────────────────────────────────────────────────
    # Make wake-word stricter: require higher STT confidence and energy
    wakeword_threshold: float = (
        0.85  # Activation threshold (higher = fewer false triggers)
    )
    wakeword_keywords: list = field(
        default_factory=lambda: ["canary", "hey canary", "ok canary"]
    )
    wakeword_energy_threshold: float = 0.02  # Min RMS for keyword check
    wakeword_min_duration_ms: int = 250  # Minimum speech duration for a keyword
    wakeword_max_duration_ms: int = 2000  # Maximum speech duration for a keyword
    wakeword_mfcc_threshold: float = (
        15.0  # DTW distance threshold for template matching (more strict)
    )
    wakeword_models: list = field(
        default_factory=lambda: []
    )  # legacy openwakeword models
    wakeword_consecutive_hits: int = 2  # Require N consecutive detections

    # ── Wake-Word Fallback ─────────────────────────────────────────
    # When True: if no STT backend is available (no internet, no Whisper),
    # use VAD confidence as a soft gate instead of always dropping.
    # This allows offline testing and demos without "Hey Canary" detection.
    wakeword_fallback_to_vad: bool = True
    wakeword_fallback_vad_threshold: float = 0.6  # Min VAD prob to pass as soft wake

    # ── Pre-Processing ─────────────────────────────────────────────
    pre_emphasis_coeff: float = 0.97  # Pre-emphasis filter coefficient
    noise_estimation_frames: int = 10  # Number of frames for noise estimation
    noise_oversubtraction: float = 1.5  # Spectral subtraction oversubtraction factor
    # (lowered from 2.0 to reduce musical noise)
    dither_amplitude: float = 1e-6  # Dithering amplitude added before DSP

    # ── Multi-Band Wiener Filter (Mode B DSP) ─────────────────────
    # Band edges in Hz: [0-500, 500-2000, 2000-4000, 4000-8000]
    # Gain floor per band — higher = more noise allowed through (0.0-1.0)
    wiener_band_edges_hz: list = field(default_factory=lambda: [500, 2000, 4000])
    wiener_band_floors: list = field(
        default_factory=lambda: [0.15, 0.08, 0.05, 0.12]
        # Low-freq: higher floor (preserve resonance), mid: aggressive, high: moderate
    )

    # ── Feature Extraction ─────────────────────────────────────────
    n_mels: int = 40  # Mel filterbank bins (matches microWakeWord)
    n_fft: int = 512  # FFT size
    hop_length: int = 160  # 10ms hop at 16kHz

    # ── Scene Analysis ─────────────────────────────────────────────
    # Scene Complexity Score weights. Emphasize speaker overlap over noise.
    # Noise should route to Mode B (denoising), not Mode C (separation).
    scs_weight_overlap: float = 0.70  # Weight for overlap probability
    scs_weight_noise: float = 0.20  # Weight for noise floor
    scs_weight_wakeword: float = 0.10  # Weight for (1 - wakeword certainty)

    # SCS thresholds for mode routing
    scs_threshold_a: float = 0.22  # Below this → Mode A
    scs_threshold_b: float = 0.40  # Below this → Mode B, above → Mode C

    # ── Local Speaker Analysis + Separation Fallback ──────────────
    # Mono spectral separation is a practical fallback until the trained
    # TIGER stage is connected. These thresholds are deliberately sensitive
    # enough for normal conversational volume.
    speaker_frame_rms_threshold: float = 0.004
    speaker_min_profile_frames: int = 8
    speaker_pitch_min_hz: float = 75.0
    speaker_pitch_max_hz: float = 420.0
    speaker_pitch_cluster_min_gap_hz: float = 42.0
    speaker_multi_pitch_ratio_threshold: float = 0.55
    separation_max_speakers: int = 2
    separation_mask_floor: float = 0.02

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
