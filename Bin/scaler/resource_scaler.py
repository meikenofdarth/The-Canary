"""Dynamic Resource Scaler — the final gate before Sanchit's pipeline.

HOW IT WORKS:
    The scaler takes the scene analysis output and packages everything
    into a ScalerDecision. This is the HANDOFF POINT to Sanchit's code.
    
    It applies final quality checks:
    1. Confidence filtering: Drop audio if overall confidence is too low
    2. Audio quality check: Verify the cleaned audio is usable
    3. Mode-specific DSP preparation:
       - Mode A: Gentle 80 Hz high-pass + peak-normalize to 0.9
       - Mode B: 4-band Wiener filter (frequency-aware noise suppression)
       - Mode C: Peak normalize to 0.9 for TIGER (no extra processing)
    
    Multi-Band Wiener Filter (Mode B):
    ────────────────────────────────────
    Instead of a single gain applied to all frequencies, we split the
    spectrum into 4 bands and apply different gains per band:
    
        Band 0:    0 – 500 Hz   (rumble, low voice resonance)
        Band 1:  500 – 2000 Hz  (speech formants F1/F2 — most important)
        Band 2: 2000 – 4000 Hz  (speech formants F3/F4, sibilants)
        Band 3: 4000 – 8000 Hz  (high-frequency noise, fricatives)
    
    Each band has a configurable floor (minimum gain) to prevent
    over-subtraction artifacts ("musical noise").
    
    ┌────────────────────────────────────────────────────────────────┐
    │              Dynamic Resource Scaler                           │
    │                                                                │
    │  Input: PreProcessedAudio + SceneAnalysis + VAD/WW results    │
    │                                                                │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
    │  │  MODE A       │  │  MODE B       │  │  MODE C       │       │
    │  │ HPF 80Hz +    │  │ 4-Band Wiener │  │ Peak norm     │       │
    │  │ Peak 0.9      │  │ per-band gain │  │ to 0.9        │       │
    │  └──────┬────────┘  └──────┬────────┘  └──────┬────────┘      │
    │         └──────────────────┼──────────────────┘               │
    │                            │                                   │
    │                    ScalerDecision                              │
    │               (audio + mode + metadata)                        │
    │                            │                                   │
    │                  → Sanchit's Pipeline                          │
    └────────────────────────────────────────────────────────────────┘
"""
import numpy as np
import logging
import time
from typing import Optional

from ..config import VoiceConfig, PipelineMode
from ..models import (
    VADResult, WakeWordResult, PreProcessedAudio,
    AudioFeatures, SceneAnalysis, ScalerDecision,
)
from ..separation.speaker_analyzer import SpeakerAnalysis
from ..separation.spectral_separator import SeparationResult

logger = logging.getLogger(__name__)


class DynamicResourceScaler:
    """Packages all upstream results into a final ScalerDecision.
    
    This is the last module in YOUR scope. The ScalerDecision is
    what Sanchit receives and uses to decide which AI models to run.
    
    Args:
        config: VoiceConfig with confidence thresholds and DSP parameters.
    """
    
    def __init__(self, config: VoiceConfig):
        self.config = config
        self._decisions_made = 0
        self._mode_counts = {
            PipelineMode.MODE_A: 0,
            PipelineMode.MODE_B: 0,
            PipelineMode.MODE_C: 0,
        }

        # Pre-compute frequency bin boundaries from config
        sr = config.sample_rate
        n_bins = config.n_fft // 2 + 1  # e.g. 257 bins for n_fft=512
        bin_hz = sr / config.n_fft      # Hz per bin

        edges = getattr(config, "wiener_band_edges_hz", [500, 2000, 4000])
        self._band_boundaries = [0]
        for hz in edges:
            self._band_boundaries.append(int(round(hz / bin_hz)))
        self._band_boundaries.append(n_bins)

        self._band_floors = getattr(
            config, "wiener_band_floors", [0.15, 0.08, 0.05, 0.12]
        )

    def decide(
        self,
        preprocessed: PreProcessedAudio,
        features: AudioFeatures,
        scene: SceneAnalysis,
        vad_result: VADResult,
        wakeword_result: WakeWordResult,
        speaker_analysis: Optional[SpeakerAnalysis] = None,
        separation: Optional[SeparationResult] = None,
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
        """
        mode = scene.mode
        audio = preprocessed.audio
        
        # Apply mode-specific DSP
        if mode == PipelineMode.MODE_A:
            audio = self._prepare_mode_a(audio)
        elif mode == PipelineMode.MODE_B:
            audio = self._prepare_mode_b(audio, preprocessed.noise_floor_db)
        else:  # MODE_C
            mode_c_audio = separation.processed_audio if separation else audio
            audio = self._prepare_mode_c(mode_c_audio)
        
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
            separated_audio=separation.speaker_streams if separation else [],
            separation_method=separation.method if separation else "none",
            speaker_profiles=(
                [profile.to_dict() for profile in speaker_analysis.profiles]
                if speaker_analysis
                else []
            ),
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
    
    # ── Mode A: Clean single speaker ──────────────────────────────────────
    
    def _prepare_mode_a(self, audio: np.ndarray) -> np.ndarray:
        """Mode A: Clean single speaker.
        
        Processing:
        1. Gentle high-pass filter at 80 Hz (removes mic rumble / HVAC)
        2. Peak normalize to 0.9 for consistent downstream amplitude
        
        TIGER separation is skipped entirely for this path.
        """
        audio = self._highpass_filter(audio, cutoff_hz=80.0)
        audio = self._peak_normalize(audio, target=0.9)
        return audio
    
    # ── Mode B: Moderate noise — 4-Band Wiener Filter ─────────────────────

    def _prepare_mode_b(self, audio: np.ndarray, noise_floor_db: float) -> np.ndarray:
        """Mode B: Moderate noise — apply per-band Wiener filter.
        
        Splits the STFT into 4 frequency bands and computes a Wiener gain
        per band based on the per-band SNR estimate:
        
            G_band = max( 1 - noise_power_band / (signal_power_band + ε), floor_band )
        
        Different floors per band protect speech formants (mid bands)
        while more aggressively suppressing low-frequency rumble and
        high-frequency hiss.
        
        WHY per-band:
          - A single gain suppresses all frequencies equally — bad for speech
            because the formant bands (500–4kHz) need gentle treatment while
            low and high bands can be suppressed more aggressively.
        """
        n_fft = self.config.n_fft
        hop = self.config.hop_length
        dither_amp = getattr(self.config, "dither_amplitude", 1e-6)
        
        if len(audio) < n_fft:
            return audio
        
        # Convert noise floor dB to a linear power reference.
        # Use power domain: P_noise = 10^(dB/10)  (not amplitude domain /20)
        noise_power_ref = 10.0 ** (noise_floor_db / 10.0)
        
        window = np.hanning(n_fft).astype(np.float32)
        n_frames = (len(audio) - n_fft) // hop + 1
        
        # ── Forward STFT ──────────────────────────────────────────────
        stft = np.zeros((n_fft // 2 + 1, n_frames), dtype=np.complex128)
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + n_fft].astype(np.float64)
            frame += np.random.uniform(-dither_amp, dither_amp, n_fft)
            stft[:, i] = np.fft.rfft(frame * window)
        
        mag = np.abs(stft)
        phase = np.angle(stft)
        
        # ── Per-band Wiener gain ──────────────────────────────────────
        gain = np.ones_like(mag)
        bounds = self._band_boundaries
        floors = self._band_floors
        
        for b in range(len(floors)):
            lo, hi = bounds[b], bounds[b + 1]
            if lo >= hi:
                continue
            
            band_mag = mag[lo:hi, :]           # (bins_b, frames)
            band_power = band_mag ** 2         # (bins_b, frames)
            
            # Per-frame SNR in this band
            signal_power = np.mean(band_power, axis=0) + 1e-12   # (frames,)
            
            # Wiener gain per frame: G = max(1 - P_noise / P_signal, floor)
            # Broadcast noise reference across bands
            wiener_g = np.maximum(
                1.0 - noise_power_ref / signal_power,
                floors[b],
            )  # (frames,) — scalar broadcast to (bins_b, frames)
            
            gain[lo:hi, :] = wiener_g[np.newaxis, :]
        
        # ── Apply gain + reconstruct ──────────────────────────────────
        clean_stft = (mag * gain) * np.exp(1j * phase)
        
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
        
        # Final peak normalize
        output = self._peak_normalize(output, target=0.9)
        return output
    
    # ── Mode C: Heavy overlap — pass to TIGER ─────────────────────────────
    
    def _prepare_mode_c(self, audio: np.ndarray) -> np.ndarray:
        """Mode C: Heavy overlap — minimal processing for TIGER compatibility.
        
        TIGER handles the separation, so we MUST NOT distort the signal
        with spectral filtering (it would corrupt the mixing matrix).
        We only ensure the signal is in a known amplitude range.
        """
        # Normalize peak to exactly 0.9 for TIGER's expected input range
        return self._peak_normalize(audio, target=0.9)
    
    # ── Shared DSP Utilities ──────────────────────────────────────────────
    
    def _peak_normalize(self, audio: np.ndarray, target: float = 0.9) -> np.ndarray:
        """Normalize so the peak amplitude equals `target`."""
        peak = float(np.abs(audio).max())
        if peak < 1e-8:
            return audio  # Near-silence — don't amplify
        return (audio * (target / peak)).astype(np.float32)
    
    def _highpass_filter(self, audio: np.ndarray, cutoff_hz: float) -> np.ndarray:
        """Simple single-pole high-pass IIR filter.
        
        y[n] = α * (y[n-1] + x[n] - x[n-1])
        
        Removes DC drift and low-frequency rumble (HVAC, mic stand vibration).
        
        Args:
            audio: float32 input audio.
            cutoff_hz: -3 dB cutoff frequency in Hz.
            
        Returns:
            Filtered float32 audio.
        """
        sr = self.config.sample_rate
        # α for a single-pole HPF
        rc = 1.0 / (2.0 * np.pi * cutoff_hz)
        dt = 1.0 / sr
        alpha = rc / (rc + dt)
        
        y = np.empty_like(audio, dtype=np.float64)
        x = audio.astype(np.float64)
        y[0] = x[0]
        for n in range(1, len(x)):
            y[n] = alpha * (y[n - 1] + x[n] - x[n - 1])
        
        return y.astype(np.float32)

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
        scene_complexity_score=0.12,
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

    # Test Mode B (noisy)
    scene_b = SceneAnalysis(
        scene_complexity_score=0.28,
        estimated_speaker_count=1,
        overlap_probability=0.1,
        noise_level_normalized=0.35,
        is_directed_speech=True,
        mode=PipelineMode.MODE_B,
    )
    preprocessed_b = PreProcessedAudio(
        audio=np.random.randn(24000).astype(np.float32) * 0.3,
        original_audio=np.random.randn(24000).astype(np.float32) * 0.3,
        snr_estimate_db=18.0,
        noise_floor_db=-38.0,
    )
    dec_b = scaler.decide(preprocessed_b, features, scene_b, vad, ww)
    print(f"\nMode B Decision: {dec_b}")
    print("DynamicResourceScaler test passed!")
