"""Voice-Computation Pipeline — orchestrates all stages.

This is the main entry point. It connects:
    AudioCapture → Silero VAD → Wake-Word → Pre-Processing →
    Scene Analysis → Dynamic Resource Scaler → ScalerDecision

USAGE:
    from voice_computation.pipeline import VoiceComputationPipeline

    pipeline = VoiceComputationPipeline()

    # Option 1: Process a numpy array directly
    decision = pipeline.process(audio_array)

    # Option 2: Run the live loop (captures from mic)
    pipeline.run_live(callback=my_handler)
"""

import logging
import time
from typing import Callable, Optional

import numpy as np

from .config import PipelineMode, VoiceConfig
from .models import (
    AudioFeatures,
    PreProcessedAudio,
    ScalerDecision,
    SceneAnalysis,
    VADResult,
    WakeWordResult,
)
from .preprocessing.features import FeatureExtractor
from .preprocessing.noise_estimator import NoiseEstimator
from .preprocessing.normalizer import AudioNormalizer
from .scaler.resource_scaler import DynamicResourceScaler
from .scene.analyzer import SceneAnalyzer
from .separation.speaker_analyzer import SpeakerAcousticAnalyzer
from .separation.spectral_separator import SpectralSpeakerSeparator
from .vad.silero_vad import SileroVAD
from .wakeword.detector import WakeWordDetector

logger = logging.getLogger(__name__)


class VoiceComputationPipeline:
    """Main pipeline orchestrator for the Voice-Computation module.

    Connects all stages into a single process() call.

    Args:
        config: VoiceConfig (uses defaults if None).
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._init_modules()
        self._is_activated = False  # Whether wake-word has been detected

        # Last stage results (read by demo.py to avoid re-running)
        self.last_vad_result: Optional[VADResult] = None
        self.last_wakeword_result: Optional[WakeWordResult] = None

        # Metrics
        self._total_chunks = 0
        self._total_activations = 0
        self._total_drops = 0

    def _init_modules(self) -> None:
        """Initialize all sub-modules."""
        logger.info("Initializing Voice-Computation pipeline...")

        self.vad = SileroVAD(self.config)
        self.wakeword = WakeWordDetector(self.config)
        self.normalizer = AudioNormalizer(self.config)
        self.noise_estimator = NoiseEstimator(self.config)
        self.feature_extractor = FeatureExtractor(self.config)
        self.scene_analyzer = SceneAnalyzer(self.config)
        self.speaker_analyzer = SpeakerAcousticAnalyzer(self.config)
        self.spectral_separator = SpectralSpeakerSeparator(self.config)
        self.resource_scaler = DynamicResourceScaler(self.config)

        logger.info("Voice-Computation pipeline initialized")

    def process(self, audio: np.ndarray) -> Optional[ScalerDecision]:
        """Process an audio segment through the full pipeline.

        This is the main entry point for processing audio.

        Args:
            audio: float32 numpy array @ 16kHz. Can be mono or stereo.

        Returns:
            ScalerDecision if audio should be processed downstream.
            None if audio was dropped (silence, no wake-word, etc.)
        """
        start_time = time.time()
        self._total_chunks += 1

        # Check if the input is stereo, and extract mono for Stage 0 gates
        is_stereo = audio.ndim > 1 and audio.shape[1] == 2
        mono_audio = audio.mean(axis=1) if is_stereo else audio

        # ── Stage 0: VAD Gate ──────────────────────────────────────
        vad_result = self.vad.process_audio(mono_audio)

        # Store VAD results to binary pipeline cache
        from .wakeword.detector import _cache_delete, _cache_read, _cache_write

        cache = _cache_read()
        cache.update(
            {
                "speech_probability": vad_result.speech_probability,
                "vad_confidence": vad_result.speech_probability,
                "noise_floor_db": vad_result.noise_floor_db,
            }
        )
        _cache_write(cache)

        # Hard gate: pure silence with no activation history → skip everything.
        bypass_mode = self.config.wakeword_threshold <= 0
        if not bypass_mode and not vad_result.is_speech and not self._is_activated:
            # Give the wakeword STT a chance to override the VAD silence gate
            wakeword_result = self.wakeword.process_audio(mono_audio)
            self.last_vad_result = vad_result
            self.last_wakeword_result = wakeword_result

            # Require: non-empty transcript + wakeword confidence >= threshold
            # and minimum audio RMS energy to accept the STT override.
            rms = float(np.sqrt(np.mean(mono_audio**2) + 1e-12))
            stt_transcript = (wakeword_result.transcript or "").strip()
            stt_conf_ok = wakeword_result.confidence >= getattr(
                self.config, "wakeword_threshold", 0.5
            )
            energy_ok = rms >= getattr(self.config, "wakeword_energy_threshold", 0.01)

            if not (stt_transcript and stt_conf_ok and energy_ok):
                # Not enough evidence — update noise model and drop
                self.noise_estimator.update_noise_estimate(mono_audio)
                self._total_drops += 1
                logger.debug(
                    "VAD+STT: No speech detected (vad_prob=%.3f, stt='%s', conf=%.3f, rms=%.4f)",
                    vad_result.speech_probability,
                    stt_transcript,
                    wakeword_result.confidence,
                    rms,
                )
                _cache_delete()
                return None

            # STT override accepted — proceed to activation
            goto_activation = True
        else:
            goto_activation = False

        # ── Stage 0: Wake-Word Gate ────────────────────────────────
        if not goto_activation:
            wakeword_result = self.wakeword.process_audio(mono_audio)
            self.last_vad_result = vad_result
            self.last_wakeword_result = wakeword_result

        # ── Activation Logic ───────────────────────────────────────
        gate_passed = False

        if wakeword_result.detected:
            rms = float(np.sqrt(np.mean(mono_audio**2) + 1e-12))
            conf_ok = wakeword_result.confidence >= getattr(
                self.config, "wakeword_threshold", 0.5
            )
            energy_ok = rms >= getattr(self.config, "wakeword_energy_threshold", 0.01)
            vad_ok = (
                vad_result.speech_probability
                >= getattr(self.config, "vad_threshold", 0.5) * 0.5
            )

            if conf_ok and (energy_ok or vad_ok):
                gate_passed = True
                self._is_activated = True
                self._total_activations += 1
                logger.info(
                    "ACTIVATED by wake-word '%s' (conf=%.3f, rms=%.4f)",
                    wakeword_result.keyword,
                    wakeword_result.confidence,
                    rms,
                )
            else:
                # Not confident enough to activate
                logger.debug(
                    "Wake-word ignored (conf=%.3f, rms=%.4f, vad=%.3f)",
                    wakeword_result.confidence,
                    rms,
                    vad_result.speech_probability,
                )

        elif self._is_activated:
            gate_passed = True
            logger.debug("Continuing under existing activation")

        elif (
            self.config.wakeword_fallback_to_vad
            and wakeword_result.stt_backend == "acoustic-fallback"
            and vad_result.speech_probability
            >= self.config.wakeword_fallback_vad_threshold
        ):
            gate_passed = True
            self._is_activated = True
            self._total_activations += 1
            logger.info(
                "ACTIVATED via VAD fallback (no STT backend, vad_prob=%.3f)",
                vad_result.speech_probability,
            )

        if not gate_passed:
            self._total_drops += 1
            logger.debug(
                "Wake-word not detected (conf=%.3f, backend=%s)",
                wakeword_result.confidence,
                getattr(wakeword_result, "stt_backend", "?"),
            )
            _cache_delete()
            return None

        # ── Pre-Processing (Mono) ──────────────────────────────────
        preprocessed_mono = self.normalizer.process(mono_audio)
        preprocessed_mono.noise_floor_db = vad_result.noise_floor_db

        # Apply noise subtraction if we have a noise estimate
        if self.noise_estimator.has_estimate:
            preprocessed_mono.audio = self.noise_estimator.subtract_noise(preprocessed_mono.audio)
            preprocessed_mono.noise_floor_db = self.noise_estimator.get_noise_floor_db()

        # ── Feature Extraction ─────────────────────────────────────
        features = self.feature_extractor.extract(preprocessed_mono.audio)

        # ── Pre-estimate Speaker Count & Overlap ───────────────────
        est_speaker_count = self.scene_analyzer._estimate_speaker_count(features)
        overlap_prob = self.scene_analyzer._estimate_overlap_probability(features, est_speaker_count)

        # ── Separation (Separation-First) ──────────────────────────
        if is_stereo:
            separation = self.spectral_separator.process(audio)
        else:
            separation = self.spectral_separator.process(preprocessed_mono.audio, overlap_probability=overlap_prob)

        # ── Post-Separation Speaker Analysis & Diarization ─────────
        if separation.speaker_streams:
            speaker_analysis = self.speaker_analyzer.analyze_separated(separation.speaker_streams)
        else:
            speaker_analysis = self.speaker_analyzer.analyze_separated([preprocessed_mono.audio])

        # ── Scene Analysis ─────────────────────────────────────────
        scene = self.scene_analyzer.analyze(
            features=features,
            vad_confidence=vad_result.speech_probability,
            wakeword_confidence=wakeword_result.confidence,
            noise_floor_db=preprocessed_mono.noise_floor_db,
            wakeword_available=(wakeword_result.stt_backend != "acoustic-fallback"),
            speaker_analysis=speaker_analysis,
        )

        # ── Dynamic Resource Scaler ────────────────────────────────
        decision = self.resource_scaler.decide(
            preprocessed=preprocessed_mono,
            features=features,
            scene=scene,
            vad_result=vad_result,
            wakeword_result=wakeword_result,
            speaker_analysis=speaker_analysis,
            separation=separation,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        audio_duration_ms = len(audio) / self.config.sample_rate * 1000
        xrt = elapsed_ms / audio_duration_ms if audio_duration_ms > 0 else 0

        logger.info(
            "Pipeline: %.1fms audio processed in %.1fms (xRT=%.3f) → %s",
            audio_duration_ms,
            elapsed_ms,
            xrt,
            decision.mode.value,
        )

        # Final decision produced — delete the temporary binary cache
        _cache_delete()

        return decision

    def process_chunk_streaming(self, chunk: np.ndarray) -> Optional[VADResult]:
        """Process a single 30ms chunk for streaming VAD.

        Use this for continuous monitoring. When it returns a VAD result
        with is_speech=True, accumulate audio and call process() with
        the full buffer once speech ends.

        Args:
            chunk: float32 array of ~480 samples (30ms @ 16kHz).

        Returns:
            VADResult for this chunk.
        """
        return self.vad.process_chunk(chunk)

    def run_live(
        self,
        callback: Callable[[ScalerDecision], None],
        duration_s: float = 0,
    ) -> None:
        """Run the pipeline live from the microphone.

        Captures audio, processes through the pipeline, and calls
        the callback whenever a ScalerDecision is ready.

        Args:
            callback: Function called with each ScalerDecision.
            duration_s: How long to run (0 = forever, Ctrl+C to stop).
        """
        from .audio.capture import AudioCapture

        logger.info("Starting live pipeline...")
        capture = AudioCapture(self.config)
        capture.start()

        try:
            start = time.time()
            check_interval = self.config.activation_window_s  # Check every 1.5s

            while True:
                time.sleep(check_interval)

                # Get the latest audio window
                audio = capture.get_audio(duration_s=self.config.activation_window_s)

                if len(audio) < self.config.chunk_size_samples:
                    continue

                # Process through pipeline
                decision = self.process(audio)

                if decision is not None:
                    callback(decision)
                    # Reset activation after processing
                    self._is_activated = False
                    self.vad.reset()
                    self.wakeword.reset()

                # Check duration
                if duration_s > 0 and (time.time() - start) >= duration_s:
                    logger.info("Live pipeline duration reached")
                    break

        except KeyboardInterrupt:
            logger.info("Live pipeline interrupted by user")
        finally:
            capture.stop()

    def deactivate(self) -> None:
        """Reset activation state (go back to idle)."""
        self._is_activated = False
        self.vad.reset()
        self.wakeword.reset()

    @property
    def stats(self) -> dict:
        """Get pipeline statistics."""
        return {
            "total_chunks": self._total_chunks,
            "total_activations": self._total_activations,
            "total_drops": self._total_drops,
            "drop_rate": self._total_drops / max(self._total_chunks, 1),
            "scaler_stats": self.resource_scaler.stats,
        }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    config = VoiceConfig()
    pipeline = VoiceComputationPipeline(config)

    # Test with synthetic audio
    print("\n=== Testing with synthetic audio ===")

    # Clean speech (sine wave — not real speech, but tests the pipeline)
    t = np.arange(24000) / 16000  # 1.5 seconds
    audio = np.sin(2 * np.pi * 300 * t).astype(np.float32) * 0.5

    result = pipeline.process(audio)
    if result:
        print(f"Result: {result}")
        print(f"Dict: {result.to_dict()}")
    else:
        print("Audio was dropped (expected for synthetic audio without speech)")

    print(f"\nStats: {pipeline.stats}")
    print("\nPipeline test complete!")
