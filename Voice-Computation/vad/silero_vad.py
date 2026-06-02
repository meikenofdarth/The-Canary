"""Silero VAD — Voice Activity Detection (Pure ONNX Runtime).

HOW IT WORKS:
    Silero VAD is a tiny ONNX model (~0.5M parameters) that classifies
    short audio chunks as speech or non-speech. It runs in <1ms per chunk.

    The model processes 512 samples at 16kHz (~32ms of audio).
    It outputs a speech probability between 0.0 and 1.0.

    ONNX Model Interface (Silero v5):
        Inputs:  input  float32[1, 512]
                 sr     int64[1]          ← shape (1,) NOT scalar!
                 state  float32[2, 1, 128]
        Outputs: output float32[1, 1]
                 stateN float32[2, 1, 128]

FIXES IN THIS VERSION vs ORIGINAL:
    1. sr input shape fixed to (1,) — original used scalar (), causing ONNX failure
    2. Energy pre-gate: skip inference entirely on silent audio
    3. Spike suppression: require N consecutive above-threshold frames
    4. Probability smoothing: rolling 3-frame average
    5. Auto-log model interface on load for debugging
"""

import logging
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np
import onnxruntime as ort

from ..config import VoiceConfig
from ..models import VADResult

logger = logging.getLogger(__name__)

SILERO_ONNX_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/"
    "src/silero_vad/data/silero_vad.onnx"
)
CACHE_DIR = Path.home() / ".cache" / "canary" / "models"


class SileroVAD:
    """Silero VAD wrapper with energy gating and spike suppression.

    Key fixes vs the original:
    - sr is np.array([sr], dtype=int64) shape (1,) — ONNX model requires this
    - Energy pre-gate prevents ONNX inference on near-silent audio
    - Spike suppression requires vad_consecutive_required frames above threshold
    - Rolling probability buffer smooths single-frame noise spikes

    Args:
        config: VoiceConfig with VAD thresholds and sample rate.
    """

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._session = None
        self._is_loaded = False

        # Silero v5 ONNX state: combined h+c, shape (2, 1, 128)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        # FIX: sr MUST be shape (1,) not scalar ()
        self._sr = np.array([config.sample_rate], dtype=np.int64)

        # Spike suppression: rolling buffer of raw probs
        self._prob_buffer: deque = deque(maxlen=3)
        self._above_threshold_count: int = 0
        self._required_consecutive: int = getattr(config, "vad_consecutive_required", 2)

        # Speech boundary tracking
        self._speech_active = False
        self._speech_start_sample = 0
        self._speech_samples = 0
        self._silence_samples = 0
        self._total_samples_processed = 0

        # Noise floor
        self._noise_floor_db = -60.0
        self._noise_alpha = 0.05

        self._load_model()

    # ── Model Loading ──────────────────────────────────────────────────────

    def _get_model_path(self) -> Path:
        model_path = CACHE_DIR / "silero_vad.onnx"
        if model_path.exists():
            logger.info("Using cached Silero VAD model: %s", model_path)
            return model_path
        logger.info("Downloading Silero VAD ONNX model from GitHub...")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SILERO_ONNX_URL, str(model_path))
        logger.info("Downloaded Silero VAD model → %s", model_path)
        return model_path

    def _load_model(self) -> None:
        logger.info("Loading Silero VAD (ONNX Runtime)...")
        model_path = self._get_model_path()

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 3  # Suppress ONNX warnings

        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )

        # Log actual model interface — useful for debugging
        inputs = {inp.name: inp.shape for inp in self._session.get_inputs()}
        outputs = {out.name: out.shape for out in self._session.get_outputs()}
        logger.info("Silero VAD inputs:  %s", inputs)
        logger.info("Silero VAD outputs: %s", outputs)

        self._is_loaded = True
        logger.info(
            "Silero VAD loaded ✓ (ONNX Runtime, sr=%d Hz)", self.config.sample_rate
        )

    # ── Inference ─────────────────────────────────────────────────────────

    def _run_inference(self, audio_chunk: np.ndarray) -> float:
        """Run a single 512-sample inference. Returns speech prob [0, 1]."""
        x = audio_chunk.reshape(1, -1).astype(np.float32)

        ort_inputs = {
            "input": x,
            "sr": self._sr,  # shape (1,) — FIXED
            "state": self._state,  # shape (2, 1, 128)
        }

        outputs = self._session.run(None, ort_inputs)
        speech_prob = float(outputs[0].squeeze())  # (1,1) → scalar
        self._state = outputs[1]  # Updated LSTM state (2,1,128)

        return float(np.clip(speech_prob, 0.0, 1.0))

    # ── Public API ────────────────────────────────────────────────────────

    def process_chunk(self, audio_chunk: np.ndarray) -> VADResult:
        """Process one audio chunk (ideally 512 samples @ 16kHz).

        Pipeline:
          1. Energy pre-gate: return is_speech=False immediately if audio is silent
          2. ONNX inference (one or more 512-sample windows)
          3. Rolling average smoothing over last 3 frames
          4. Consecutive-frame spike suppression
          5. Speech boundary state machine

        Args:
            audio_chunk: float32 array, ideally 512 samples.

        Returns:
            VADResult with is_speech and smoothed speech_probability.
        """
        if not self._is_loaded:
            raise RuntimeError("Silero VAD model not loaded")

        window_size = self.config.vad_window_size_samples  # 512

        # ── 1. Energy Pre-Gate ────────────────────────────────────
        energy_threshold = getattr(self.config, "vad_energy_threshold", 0.001)
        rms = float(np.sqrt(np.mean(audio_chunk**2) + 1e-12))

        if rms < energy_threshold:
            self._prob_buffer.append(0.0)
            self._above_threshold_count = max(0, self._above_threshold_count - 1)
            self._update_noise_floor(audio_chunk, is_speech=False)
            self._update_speech_state(is_speech=False, chunk_length=len(audio_chunk))
            return VADResult(
                is_speech=False,
                speech_probability=0.0,
                speech_start_sample=self._speech_start_sample,
                speech_end_sample=self._total_samples_processed,
                noise_floor_db=self._noise_floor_db,
            )

        # ── 2. ONNX Inference ─────────────────────────────────────
        if len(audio_chunk) <= window_size:
            if len(audio_chunk) < window_size:
                padded = np.zeros(window_size, dtype=np.float32)
                padded[: len(audio_chunk)] = audio_chunk
                audio_chunk = padded
            raw_prob = self._run_inference(audio_chunk)
        else:
            probs = []
            for i in range(0, len(audio_chunk) - window_size + 1, window_size):
                probs.append(self._run_inference(audio_chunk[i : i + window_size]))
            raw_prob = float(np.mean(probs)) if probs else 0.0

        # ── 3. Smooth + Spike Suppression ─────────────────────────
        self._prob_buffer.append(raw_prob)
        smoothed_prob = float(np.mean(self._prob_buffer))

        if smoothed_prob >= self.config.vad_threshold:
            self._above_threshold_count = min(
                self._above_threshold_count + 1, self._required_consecutive + 2
            )
        else:
            self._above_threshold_count = max(0, self._above_threshold_count - 1)

        is_speech = self._above_threshold_count >= self._required_consecutive

        self._update_noise_floor(audio_chunk, is_speech)
        self._update_speech_state(is_speech, len(audio_chunk))

        return VADResult(
            is_speech=is_speech,
            speech_probability=smoothed_prob,
            speech_start_sample=self._speech_start_sample,
            speech_end_sample=self._total_samples_processed,
            noise_floor_db=self._noise_floor_db,
        )

    def process_audio(self, audio: np.ndarray) -> VADResult:
        """Process a longer audio segment. Returns aggregated VAD result.

        Runs frame-by-frame analysis without updating the main state,
        then makes a holistic speech/non-speech decision.
        """
        window_size = self.config.vad_window_size_samples
        energy_threshold = getattr(self.config, "vad_energy_threshold", 0.001)

        if len(audio) < window_size:
            return self.process_chunk(audio)

        # Save state — frame scan is non-destructive
        state_backup = self._state.copy()

        probs = []
        for i in range(0, len(audio) - window_size + 1, window_size):
            chunk = audio[i : i + window_size]
            rms = float(np.sqrt(np.mean(chunk**2) + 1e-12))
            if rms < energy_threshold:
                probs.append(0.0)
                self._update_noise_floor(chunk, is_speech=False)
            else:
                prob = self._run_inference(chunk)
                probs.append(prob)
                self._update_noise_floor(chunk, is_speech=(prob >= self.config.vad_threshold))

        self._state = state_backup

        if not probs:
            return VADResult(
                is_speech=False,
                speech_probability=0.0,
                noise_floor_db=self._noise_floor_db,
            )

        max_prob = float(max(probs))
        speech_frames = sum(1 for p in probs if p >= self.config.vad_threshold)
        speech_fraction = speech_frames / len(probs)

        # Require at least 20% of frames to be speech AND max probability above threshold
        is_speech = (speech_fraction >= 0.2) and (max_prob >= self.config.vad_threshold)

        self._update_speech_state(is_speech, len(audio))

        return VADResult(
            is_speech=is_speech,
            speech_probability=max_prob,
            speech_start_sample=self._speech_start_sample,
            speech_end_sample=self._total_samples_processed,
            noise_floor_db=self._noise_floor_db,
        )

    def get_frame_probabilities(self, audio: np.ndarray) -> list:
        """Get per-frame speech probabilities for visualization (non-destructive).

        Returns one probability per 512-sample window.
        """
        window_size = self.config.vad_window_size_samples
        energy_threshold = getattr(self.config, "vad_energy_threshold", 0.001)
        state_backup = self._state.copy()
        probs = []

        for i in range(0, len(audio) - window_size + 1, window_size):
            chunk = audio[i : i + window_size]
            rms = float(np.sqrt(np.mean(chunk**2) + 1e-12))
            if rms < energy_threshold:
                probs.append(0.0)
            else:
                probs.append(self._run_inference(chunk))

        self._state = state_backup
        return probs

    # ── Internal State Machines ───────────────────────────────────────────

    def _update_noise_floor(self, audio: np.ndarray, is_speech: bool) -> None:
        if not is_speech and len(audio) > 0:
            rms = float(np.sqrt(np.mean(audio**2) + 1e-12))
            if rms > 1e-10:
                db = 20 * np.log10(rms)
                self._noise_floor_db = (
                    self._noise_alpha * db
                    + (1 - self._noise_alpha) * self._noise_floor_db
                )

    def _update_speech_state(self, is_speech: bool, chunk_length: int) -> None:
        sr = self.config.sample_rate
        min_speech = int(self.config.vad_min_speech_ms * sr / 1000)
        min_silence = int(self.config.vad_min_silence_ms * sr / 1000)

        if is_speech:
            if not self._speech_active:
                self._speech_samples += chunk_length
                if self._speech_samples >= min_speech:
                    self._speech_active = True
                    self._speech_start_sample = (
                        self._total_samples_processed - self._speech_samples
                    )
                    self._silence_samples = 0
            else:
                self._silence_samples = 0
        else:
            if self._speech_active:
                self._silence_samples += chunk_length
                if self._silence_samples >= min_silence:
                    self._speech_active = False
                    self._speech_samples = 0
                    self._silence_samples = 0
            else:
                self._speech_samples = 0

        self._total_samples_processed += chunk_length

    def reset(self) -> None:
        """Reset all state (call between utterances)."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._prob_buffer.clear()
        self._above_threshold_count = 0
        self._speech_active = False
        self._speech_start_sample = 0
        self._speech_samples = 0
        self._silence_samples = 0

    @property
    def is_speech_active(self) -> bool:
        return self._speech_active

    @property
    def noise_floor_db(self) -> float:
        return self._noise_floor_db


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = VoiceConfig()
    print("Testing Silero VAD (ONNX, fixed sr shape)...")
    vad = SileroVAD(config)

    silence = np.zeros(512, dtype=np.float32)
    r = vad.process_chunk(silence)
    print(f"Silence:   speech={r.is_speech}, prob={r.speech_probability:.4f}")

    noise = np.random.randn(512).astype(np.float32) * 0.005
    r = vad.process_chunk(noise)
    print(f"Low noise: speech={r.is_speech}, prob={r.speech_probability:.4f}")

    speech_sim = np.random.randn(16000).astype(np.float32) * 0.3
    r = vad.process_audio(speech_sim)
    print(f"Louder:    speech={r.is_speech}, prob={r.speech_probability:.4f}")
    print(f"Noise floor: {vad.noise_floor_db:.1f} dB")
    print("Silero VAD test passed!")
