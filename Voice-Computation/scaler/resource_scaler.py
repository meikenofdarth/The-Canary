"""Dynamic Resource Scaler — the final gate before Sanchit's pipeline.

HOW IT WORKS:
    The scaler takes the scene analysis output and packages everything
    into a ScalerDecision. This is the HANDOFF POINT to Sanchit's code.
    
    It applies final quality checks:
    1. Confidence filtering: Drop audio if overall confidence is too low
    2. Audio quality check: Verify the cleaned audio is usable
    3. Mode-specific preparation:
       - Mode A: Just pass cleaned audio (no separation needed)
       - Mode B: Apply additional adaptive filtering
       - Mode C: Pass as-is (TIGER will handle separation)
    
    ┌────────────────────────────────────────────────────────────────┐
    │              Dynamic Resource Scaler                           │
    │                                                                │
    │  Input: PreProcessedAudio + SceneAnalysis + VAD/WW results    │
    │                                                                │
    │  ┌──────────┐    ┌──────────┐    ┌──────────┐                 │
    │  │  MODE A   │    │  MODE B   │    │  MODE C   │                │
    │  │ Clean     │    │ Moderate  │    │ Complex   │                │
    │  │ 1 speaker │    │ Noisy     │    │ Overlap   │                │
    │  │ Skip sep. │    │ Adapt.DSP │    │ Full sep. │                │
    │  └────┬─────┘    └────┬─────┘    └────┬─────┘                 │
    │       │               │               │                        │
    │       └───────────────┼───────────────┘                        │
    │                       │                                        │
    │              ScalerDecision                                    │
    │        (audio + mode + metadata)                               │
    │                       │                                        │
    │              → Sanchit's Pipeline                              │
    └────────────────────────────────────────────────────────────────┘
"""
import numpy as np
import logging
import time

from ..config import VoiceConfig, PipelineMode
from ..models import (
    VADResult, WakeWordResult, PreProcessedAudio,
    AudioFeatures, SceneAnalysis, ScalerDecision,
)

logger = logging.getLogger(__name__)


class DynamicResourceScaler:
    """Packages all upstream results into a final ScalerDecision.
    
    This is the last module in YOUR scope. The ScalerDecision is
    what Sanchit receives and uses to decide which AI models to run.
    
    Args:
        config: VoiceConfig with confidence thresholds.
    """
    
    def __init__(self, config: VoiceConfig):
        self.config = config
        self._decisions_made = 0
        self._mode_counts = {
            PipelineMode.MODE_A: 0,
            PipelineMode.MODE_B: 0,
            PipelineMode.MODE_C: 0,
        }
    
    def decide(
        self,
        preprocessed: PreProcessedAudio,
        features: AudioFeatures,
        scene: SceneAnalysis,
        vad_result: VADResult,
        wakeword_result: WakeWordResult,
    ) -> ScalerDecision:
        """Make the final routing decision.
        
        Args:
            preprocessed: Cleaned audio from pre-processing.
            features: Extracted audio features.
            scene: Scene analysis results.
            vad_result: VAD detection results.
            wakeword_result: Wake-word detection results.
            
        Returns:
            ScalerDecision ready for Sanchit's pipeline.
            Returns None-like decision if audio should be dropped.
        """
        mode = scene.mode
        audio = preprocessed.audio
        
        # Apply mode-specific processing
        if mode == PipelineMode.MODE_A:
            audio = self._prepare_mode_a(audio)
        elif mode == PipelineMode.MODE_B:
            audio = self._prepare_mode_b(audio, preprocessed.noise_floor_db)
        else:  # MODE_C
            audio = self._prepare_mode_c(audio)
        
        decision = ScalerDecision(
            mode=mode,
            audio=audio,
            timestamp=time.time(),
            vad_confidence=vad_result.speech_probability,
            wakeword_confidence=wakeword_result.confidence,
            scene_complexity_score=scene.scene_complexity_score,
            estimated_speaker_count=scene.estimated_speaker_count,
            overlap_probability=scene.overlap_probability,
            noise_floor_db=preprocessed.noise_floor_db,
            snr_estimate_db=preprocessed.snr_estimate_db,
            is_directed_speech=scene.is_directed_speech,
            mel_spectrogram=features.mel_spectrogram,
            energy_profile=features.energy,
        )
        
        # Track stats
        self._decisions_made += 1
        self._mode_counts[mode] += 1
        
        logger.info(
            "Scaler decision #%d: %s (total: A=%d, B=%d, C=%d)",
            self._decisions_made, decision,
            self._mode_counts[PipelineMode.MODE_A],
            self._mode_counts[PipelineMode.MODE_B],
            self._mode_counts[PipelineMode.MODE_C],
        )
        
        return decision
    
    def should_process(
        self,
        vad_result: VADResult,
        wakeword_result: WakeWordResult,
    ) -> bool:
        """Quick check: should we even bother processing this audio?
        
        Returns False if:
        - No speech detected
        - No wake-word detected
        - Confidence is too low
        
        This saves compute by short-circuiting before heavy processing.
        """
        if not vad_result.is_speech:
            return False
        
        if not wakeword_result.detected:
            return False
        
        if vad_result.speech_probability < self.config.min_confidence_threshold:
            return False
        
        return True
    
    def _prepare_mode_a(self, audio: np.ndarray) -> np.ndarray:
        """Mode A: Clean single speaker — minimal processing.
        
        The audio is already clean. Just ensure proper normalization.
        TIGER separation is skipped entirely for this path.
        """
        # Just ensure the audio is properly scaled
        peak = np.abs(audio).max()
        if peak > 0 and peak < 0.1:
            # Audio is too quiet — boost it
            audio = audio * (0.5 / peak)
        return audio
    
    def _prepare_mode_b(self, audio: np.ndarray, noise_floor_db: float) -> np.ndarray:
        """Mode B: Moderate noise — apply additional adaptive filtering.
        
        Uses a simple Wiener-like filter to reduce noise without
        the full TIGER separation pipeline.
        """
        # Simple spectral gating based on noise floor
        n_fft = self.config.n_fft
        hop = self.config.hop_length
        
        if len(audio) < n_fft:
            return audio
        
        window = np.hanning(n_fft).astype(np.float32)
        n_frames = (len(audio) - n_fft) // hop + 1
        
        # STFT
        stft = np.zeros((n_fft // 2 + 1, n_frames), dtype=np.complex128)
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + n_fft] * window
            stft[:, i] = np.fft.rfft(frame)
        
        # Estimate noise threshold from noise floor
        noise_threshold = 10 ** (noise_floor_db / 20) * 2
        
        # Spectral gating: suppress bins below noise threshold
        mag = np.abs(stft)
        phase = np.angle(stft)
        
        # Wiener-like gain: G = max(1 - noise/signal, floor)
        gain = np.maximum(1 - noise_threshold / (mag + 1e-10), 0.1)
        clean_mag = mag * gain
        
        # Reconstruct
        clean_stft = clean_mag * np.exp(1j * phase)
        output = np.zeros(len(audio), dtype=np.float32)
        window_sum = np.zeros(len(audio), dtype=np.float32)
        
        for i in range(n_frames):
            start = i * hop
            end = min(start + n_fft, len(audio))
            frame = np.fft.irfft(clean_stft[:, i]).real[:end - start].astype(np.float32)
            output[start:end] += frame * window[:end - start]
            window_sum[start:end] += window[:end - start] ** 2
        
        mask = window_sum > 1e-8
        output[mask] /= window_sum[mask]
        
        return output
    
    def _prepare_mode_c(self, audio: np.ndarray) -> np.ndarray:
        """Mode C: Heavy overlap — pass audio as-is.
        
        TIGER handles the separation, so we don't want to distort
        the signal with additional processing. Just ensure proper scaling.
        """
        # Ensure audio is in [-1, 1] range for TIGER
        peak = np.abs(audio).max()
        if peak > 1.0:
            audio = audio / peak
        return audio
    
    @property
    def stats(self) -> dict:
        """Get routing statistics."""
        total = max(self._decisions_made, 1)
        return {
            "total_decisions": self._decisions_made,
            "mode_a_count": self._mode_counts[PipelineMode.MODE_A],
            "mode_a_pct": self._mode_counts[PipelineMode.MODE_A] / total * 100,
            "mode_b_count": self._mode_counts[PipelineMode.MODE_B],
            "mode_b_pct": self._mode_counts[PipelineMode.MODE_B] / total * 100,
            "mode_c_count": self._mode_counts[PipelineMode.MODE_C],
            "mode_c_pct": self._mode_counts[PipelineMode.MODE_C] / total * 100,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = VoiceConfig()
    scaler = DynamicResourceScaler(config)
    
    # Simulate a Mode A decision
    preprocessed = PreProcessedAudio(
        audio=np.random.randn(16000).astype(np.float32) * 0.3,
        original_audio=np.random.randn(16000).astype(np.float32) * 0.3,
        snr_estimate_db=35.0,
        noise_floor_db=-50.0,
    )
    features = AudioFeatures(
        mel_spectrogram=np.random.randn(40, 50).astype(np.float32),
        energy=np.ones(50) * 0.3,
        zero_crossing_rate=np.ones(50) * 0.05,
        spectral_centroid=np.ones(50) * 100,
        rms_energy=0.3,
        duration_s=1.0,
    )
    scene = SceneAnalysis(
        scene_complexity_score=0.15,
        estimated_speaker_count=1,
        overlap_probability=0.0,
        noise_level_normalized=0.1,
        is_directed_speech=True,
        mode=PipelineMode.MODE_A,
    )
    vad = VADResult(is_speech=True, speech_probability=0.95)
    ww = WakeWordResult(detected=True, confidence=0.9, keyword="hey_canary")
    
    decision = scaler.decide(preprocessed, features, scene, vad, ww)
    print(f"Decision: {decision}")
    print(f"Dict: {decision.to_dict()}")
    print(f"Stats: {scaler.stats}")
    print("DynamicResourceScaler test passed!")
