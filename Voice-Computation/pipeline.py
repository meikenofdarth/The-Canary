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
        self.resource_scaler = DynamicResourceScaler(self.config)

        logger.info("Voice-Computation pipeline initialized")

    def process(self, audio: np.ndarray) -> Optional[ScalerDecision]:
        """Process an audio segment through the full pipeline.

        This is the main entry point for processing audio.

        Args:
            audio: float32 numpy array @ 16kHz. Can be any length,
                   but 1-2 seconds is ideal.

        Returns:
            ScalerDecision if audio should be processed downstream.
            None if audio was dropped (silence, no wake-word, etc.)
        """
        start_time = time.time()
        self._total_chunks += 1

        # ── Stage 0: VAD Gate ──────────────────────────────────────
        vad_result = self.vad.process_audio(audio)

        # Store VAD results to hidden text file first
        from .wakeword.detector import load_hidden_data, save_hidden_data
        existing_data = load_hidden_data()
        existing_data.update({
            "speech_probability": vad_result.speech_probability,
            "vad_confidence": vad_result.speech_probability,
            "noise_floor_db": vad_result.noise_floor_db,
        })
        save_hidden_data(existing_data)

        # ── Stage 0: Wake-Word Gate ────────────────────────────────
        wakeword_result = self.wakeword.process_audio(audio)

        # Wake-word detection bypasses the VAD gate. If wake word is not detected,
        # and VAD says no speech, drop it.
        if not wakeword_result.detected and not self._is_activated:
            if not vad_result.is_speech:
                # No speech and no wake-word → update noise estimate and stay idle
                self.noise_estimator.update_noise_estimate(audio)
                self._total_drops += 1
                logger.debug(
                    "VAD: No speech detected (prob=%.3f)", vad_result.speech_probability
                )
                return None

            # Speech but no wake-word → ambient conversation
            self._total_drops += 1
            logger.debug(
                "Wake-word not detected (conf=%.3f)", wakeword_result.confidence
            )
            return None

        if wakeword_result.detected:
            self._is_activated = True
            self._total_activations += 1
            logger.info(
                "ACTIVATED by wake-word '%s' (conf=%.3f)",
                wakeword_result.keyword,
                wakeword_result.confidence,
            )

        # ── Pre-Processing ─────────────────────────────────────────
        # Normalize audio
        preprocessed = self.normalizer.process(audio)

        # Apply noise subtraction if we have a noise estimate
        if self.noise_estimator.has_estimate:
            preprocessed.audio = self.noise_estimator.subtract_noise(preprocessed.audio)
            preprocessed.noise_floor_db = self.noise_estimator.get_noise_floor_db()

        # ── Feature Extraction ─────────────────────────────────────
        features = self.feature_extractor.extract(preprocessed.audio)

        # ── Scene Analysis ─────────────────────────────────────────
        scene = self.scene_analyzer.analyze(
            features=features,
            vad_confidence=vad_result.speech_probability,
            wakeword_confidence=wakeword_result.confidence,
            noise_floor_db=preprocessed.noise_floor_db,
        )

        # ── Dynamic Resource Scaler ────────────────────────────────
        decision = self.resource_scaler.decide(
            preprocessed=preprocessed,
            features=features,
            scene=scene,
            vad_result=vad_result,
            wakeword_result=wakeword_result,
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
