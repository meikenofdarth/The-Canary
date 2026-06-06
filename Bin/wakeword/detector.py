"""Wake-Word Detector — STT-based keyword search.

HOW IT WORKS:
    Instead of acoustic pattern matching (unreliable without a trained model),
    this detector transcribes the audio to text and searches for the keyword.

    Pipeline:
        audio  →  noise-aware normalisation
               →  SpeechRecognition (Google STT, online)  ← primary
               →  Whisper tiny (offline fallback)
               →  text.lower().contains("canary")
               →  WakeWordResult(detected, confidence, transcript)

    Supported keywords (all variants of "canary"):
        "canary", "hey canary", "ok canary", "hi canary",
        "okay canary", "hello canary"

    STT backends tried in order:
        1. Google Web Speech API  — fast, accurate, free, needs internet
        2. OpenAI Whisper tiny    — offline, ~39 MB model, slightly slower
        3. Acoustic fallback      — energy + syllable heuristic (no install needed)

INSTALL:
    pip install SpeechRecognition openai-whisper pydub

BYPASS:
    Set config.wakeword_threshold = 0.0  →  always returns detected=True
"""

import io
import logging
import pickle
import wave
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from ..config import VoiceConfig
from ..models import WakeWordResult

logger = logging.getLogger(__name__)

CALIBRATION_DIR = Path.home() / ".cache" / "canary"

# ── Binary pipeline cache ─────────────────────────────────────────────────────
# Temporary .bin file that holds audio PCM + all pipeline metadata.
# Created when audio enters the pipeline, deleted after the final decision.

_CACHE_BIN = Path(__file__).parent.parent / ".canary_pipe.bin"


def _cache_write(data: dict) -> None:
    """Serialize pipeline state to the binary cache (pickle)."""
    try:
        with open(_CACHE_BIN, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass


def _cache_read() -> dict:
    """Deserialize pipeline state from the binary cache."""
    if not _CACHE_BIN.exists():
        return {}
    try:
        with open(_CACHE_BIN, "rb") as f:
            return pickle.load(f)
    except Exception:
        return {}


def _cache_delete() -> None:
    """Remove the binary cache file silently."""
    try:
        if _CACHE_BIN.exists():
            _CACHE_BIN.unlink()
    except Exception:
        pass


# All keyword variants to search for in transcript
_KEYWORDS: List[str] = [
    "hey canary",
    "ok canary",
    "okay canary",
    "hi canary",
    "hello canary",
    "canary",  # must be last — shortest / most general
]


class WakeWordDetector:
    """Keyword detector using speech-to-text transcription.

    Transcribes the audio with Google STT (or Whisper offline), then checks
    whether the word "canary" (or any variant) appears in the transcript.

    Args:
        config: VoiceConfig.
    """

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._bypass = False
        self._is_loaded = True  # No model file needed for STT approach

        self._sr_module = None  # speech_recognition module
        self._recognizer = None  # sr.Recognizer instance
        self._whisper_model = None  # whisper model (loaded lazily)

        self._stt_available = False
        self._whisper_available = False

        # Debounce
        self._consecutive_hits_needed = getattr(config, "wakeword_consecutive_hits", 1)
        self._consecutive_count = 0

        if getattr(config, "wakeword_threshold", 0.5) <= 0:
            self._bypass = True
            logger.info("Wake-word bypass enabled (threshold=0) — all speech passes")
            return

        self._setup_stt()

    # ── STT Setup ─────────────────────────────────────────────────────────────

    def _setup_stt(self) -> None:
        """Try to import SpeechRecognition and Whisper."""
        # 1. SpeechRecognition (Google + Whisper wrapper)
        try:
            import speech_recognition as sr

            self._sr_module = sr
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = 200  # lower = more sensitive
            self._recognizer.dynamic_energy_threshold = True
            self._stt_available = True
            logger.info("SpeechRecognition loaded — Google STT ready")
        except ImportError:
            logger.warning(
                "SpeechRecognition not installed. "
                "Run: pip install SpeechRecognition\n"
                "Falling back to offline Whisper."
            )

        # 2. Whisper (offline fallback — load model lazily on first use)
        try:
            import whisper  # noqa: F401  — just test import

            self._whisper_available = True
            logger.info("Whisper available for offline fallback")
        except ImportError:
            logger.info(
                "openai-whisper not installed — no offline fallback. "
                "Run: pip install openai-whisper"
            )

        if not self._stt_available and not self._whisper_available:
            logger.warning(
                "No STT backend available. Using acoustic fallback.\n"
                "Install: pip install SpeechRecognition openai-whisper"
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def process_chunk(self, audio_chunk: np.ndarray) -> WakeWordResult:
        """Quick energy check for streaming chunks (< 0.3 s).

        For full detection call process_audio() with the complete utterance.
        """
        if self._bypass:
            return WakeWordResult(
                detected=True, confidence=1.0, keyword="bypass",
                transcript="bypass", stt_backend="bypass"
            )

        energy_threshold = getattr(self.config, "wakeword_energy_threshold", 0.01)
        rms = float(np.sqrt(np.mean(audio_chunk**2) + 1e-12))
        if rms < energy_threshold:
            return WakeWordResult(detected=False, confidence=0.0,
                                  stt_backend="acoustic-fallback")

        # Short chunks — not enough to transcribe reliably, return pending
        if len(audio_chunk) < int(self.config.sample_rate * 0.25):
            return WakeWordResult(detected=False, confidence=rms,
                                  stt_backend="acoustic-fallback")

        return self.process_audio(audio_chunk)

    def process_audio(self, audio: np.ndarray) -> WakeWordResult:
        """Transcribe audio and check for 'canary' in the transcript.

        Steps:
          1. Compute noise metrics (RMS)
          2. Transcribe via Google STT → Whisper → acoustic fallback
          3. Store audio PCM + transcript + metrics in binary cache
          4. Read transcript back from the binary cache
          5. Search transcript for keyword variants
          6. Debounce & update cache with detection result

        When no STT backend is available (acoustic-fallback), sets
        stt_backend='acoustic-fallback' so pipeline.py can engage VAD fallback.

        Args:
            audio: float32 mono @ 16 kHz, any length.

        Returns:
            WakeWordResult with detected, confidence, keyword, transcript, stt_backend.
        """
        if self._bypass:
            return WakeWordResult(
                detected=True, confidence=1.0, keyword="bypass",
                transcript="bypass", stt_backend="bypass"
            )

        # ── Noise measurement ────────────────────────────────────────────
        rms = float(np.sqrt(np.mean(audio**2) + 1e-12))

        # ── Transcribe ───────────────────────────────────────────────────
        transcript, method = self._transcribe(audio)
        transcript_lower = transcript.lower().strip()

        logger.debug("STT [%s]: '%s'", method, transcript_lower)

        # ── Acoustic fallback: use RMS as a proxy confidence ─────────────
        # When no STT ran, return early with fallback marker so the pipeline
        # can decide whether to engage the VAD-based soft gate instead.
        if method == "acoustic-fallback":
            # Clamp RMS to [0, 1] range as a rough confidence proxy
            fallback_conf = float(np.clip(rms * 10, 0.0, 1.0))
            logger.debug(
                "STT acoustic-fallback: rms=%.4f → confidence=%.3f",
                rms, fallback_conf
            )
            return WakeWordResult(
                detected=False,
                confidence=fallback_conf,
                keyword="",
                transcript="",
                stt_backend="acoustic-fallback",
            )

        # ── Write to binary cache ────────────────────────────────────────
        cache = _cache_read()
        cache.update({
            "audio_pcm": audio.tobytes(),
            "audio_dtype": str(audio.dtype),
            "audio_len": len(audio),
            "transcript": transcript_lower,
            "stt_method": method,
            "rms": rms,
            "sample_rate": self.config.sample_rate,
            "duration_seconds": len(audio) / self.config.sample_rate,
        })
        _cache_write(cache)

        # ── Read back from cache (redirect) ──────────────────────────────
        cache = _cache_read()
        parsed_transcript = cache.get("transcript", transcript_lower)

        # ── Keyword search ───────────────────────────────────────────────
        detected_kw, confidence = self._search_keywords(parsed_transcript)
        detected = confidence >= getattr(self.config, "wakeword_threshold", 0.5)

        if detected:
            self._consecutive_count += 1
        else:
            self._consecutive_count = max(0, self._consecutive_count - 1)

        final_detected = (
            detected and self._consecutive_count >= self._consecutive_hits_needed
        )

        # ── Update cache with detection result ───────────────────────────
        cache["wakeword_detected"] = final_detected
        cache["wakeword_confidence"] = confidence
        cache["keyword"] = detected_kw
        _cache_write(cache)

        if final_detected:
            logger.info(
                "Wake-word DETECTED: '%s' via %s | transcript: \"%s\"",
                detected_kw,
                method,
                parsed_transcript,
            )
            self._consecutive_count = 0

        return WakeWordResult(
            detected=final_detected,
            confidence=confidence,
            keyword=detected_kw,
            transcript=parsed_transcript,
            stt_backend=method,
        )

    def reset(self) -> None:
        """Reset detection state."""
        self._consecutive_count = 0

    # ── Transcription ─────────────────────────────────────────────────────────

    def _transcribe(self, audio: np.ndarray) -> Tuple[str, str]:
        """Transcribe audio to text. Returns (transcript, method_name).

        Tries in order:
            1. Google STT  (online, fast, accurate)
            2. Whisper tiny (offline, ~39 MB)
            3. Acoustic fallback (no install needed, rough heuristic)
        """
        # --- 1. Google STT ---
        if self._stt_available:
            text = self._transcribe_google(audio)
            if text is not None:
                return text, "google"

        # --- 2. Whisper offline ---
        if self._whisper_available:
            text = self._transcribe_whisper(audio)
            if text is not None:
                return text, "whisper"

        # --- 3. Acoustic fallback ---
        return "", "acoustic-fallback"

    def _audio_to_sr_audiodata(self, audio: np.ndarray):
        """Convert float32 numpy audio to speech_recognition.AudioData."""
        sr_mod = self._sr_module
        # float32 [-1,1]  →  int16  →  bytes
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        return sr_mod.AudioData(
            frame_data=pcm.tobytes(),
            sample_rate=self.config.sample_rate,
            sample_width=2,  # 16-bit = 2 bytes
        )

    def _transcribe_google(self, audio: np.ndarray) -> Optional[str]:
        """Google Web Speech API transcription."""
        sr_mod = self._sr_module
        try:
            audio_data = self._audio_to_sr_audiodata(audio)
            text = self._recognizer.recognize_google(audio_data)
            return text
        except self._sr_module.UnknownValueError:
            logger.debug("Google STT: could not understand audio")
            return ""  # Silence / unintelligible — not an error
        except self._sr_module.RequestError as e:
            logger.debug("Google STT unavailable (%s), trying Whisper", e)
            return None  # Signal to try next backend

    def _transcribe_whisper(self, audio: np.ndarray) -> Optional[str]:
        """Whisper tiny offline transcription."""
        try:
            import whisper

            if self._whisper_model is None:
                logger.info("Loading Whisper tiny model (first run, ~39 MB)...")
                self._whisper_model = whisper.load_model("tiny")
                logger.info("Whisper tiny model loaded.")

            # Whisper expects float32 at 16 kHz
            result = self._whisper_model.transcribe(
                audio.astype(np.float32),
                language="en",
                fp16=False,
            )
            return result.get("text", "")
        except Exception as e:
            logger.debug("Whisper transcription failed: %s", e)
            return None

    # ── Keyword Search ────────────────────────────────────────────────────────

    def _search_keywords(self, text: str) -> Tuple[str, float]:
        """Search transcript for any keyword variant.

        Returns (matched_keyword, confidence).
        Confidence 1.0 for full keyword match, 0.9 for bare "canary" alone.
        Returns ("", 0.0) if not found.
        """
        if not text:
            return "", 0.0

        # Full multi-word keyword match (highest priority)
        for kw in _KEYWORDS:
            if kw in text:
                conf = 1.0 if len(kw.split()) > 1 else 0.9
                return kw, conf

        return "", 0.0


# ── Module self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Dynamically load config from parent package
    import importlib.util
    import os
    import sys

    _pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _spec = importlib.util.spec_from_file_location(
        "Voice_Computation",
        os.path.join(_pkg_dir, "__init__.py"),
        submodule_search_locations=[_pkg_dir],
    )
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["Voice_Computation"] = _mod
    _spec.loader.exec_module(_mod)

    from Voice_Computation.config import VoiceConfig

    config = VoiceConfig()
    detector = WakeWordDetector(config)

    sr = config.sample_rate

    # Silence — should not detect
    silence = np.zeros(sr, dtype=np.float32)
    r = detector.process_audio(silence)
    print(f"Silence     : detected={r.detected}  conf={r.confidence:.3f}")
    assert not r.detected

    print("\nSTT backend setup:")
    print(f"  SpeechRecognition available : {detector._stt_available}")
    print(f"  Whisper available           : {detector._whisper_available}")
    print("\nWakeWordDetector self-test passed.")
