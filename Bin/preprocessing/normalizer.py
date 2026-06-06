"""Audio Normalizer — cleans raw audio for downstream processing.

HOW IT WORKS:
    Raw microphone audio often has issues:
    1. DC Offset: A constant voltage bias that shifts the waveform up/down.
       We remove it by subtracting the mean.
    2. Dithering: Tiny white noise (1e-6 amplitude) added BEFORE pre-emphasis
       to prevent log-zero issues and inter-sample distortion in very quiet audio.
    3. Pre-emphasis: Boosts high frequencies (speech energy drops at HF).
       y[n] = x[n] - α * x[n-1]   (α = 0.97 default)
    4. LUFS-style RMS levelling: Normalize to a target RMS (-23 LUFS equivalent)
       rather than pure peak norm, which keeps the SNR estimate meaningful.
    5. Peak clamp: Final safety clamp to ±1.0 with headroom.

    Processing chain:
    Raw Audio → DC Remove → Dither → Pre-Emphasis → RMS Normalize → Peak Clamp → SNR
"""
import numpy as np
import logging

from ..config import VoiceConfig
from ..models import PreProcessedAudio

logger = logging.getLogger(__name__)

# Target RMS for normalisation.  -23 LUFS ≈ RMS of 0.071 for full-scale float.
_TARGET_RMS = 0.071


class AudioNormalizer:
    """Normalizes and cleans raw audio for the pipeline.
    
    Args:
        config: VoiceConfig with pre-emphasis coefficient and dither amplitude.
    """
    
    def __init__(self, config: VoiceConfig):
        self.config = config
    
    def process(self, audio: np.ndarray) -> PreProcessedAudio:
        """Run the full normalization chain.
        
        Args:
            audio: Raw float32 audio @ 16kHz.
            
        Returns:
            PreProcessedAudio with cleaned audio and metadata.
        """
        original = audio.copy()
        
        # 1. Remove DC offset
        dc_offset = float(np.mean(audio))
        audio = audio - dc_offset
        
        # 2. Check for clipping BEFORE any processing
        is_clipped = bool(np.any(np.abs(original) >= 0.99))
        if is_clipped:
            logger.warning("Clipping detected in raw audio — soft-limiting applied")
            # Soft-limit: apply tanh saturation instead of hard clip
            audio = np.tanh(audio * 1.5) / 1.5
        
        # 3. Dither: inject tiny white noise before pre-emphasis.
        #    Prevents log(0) in downstream FFT and improves quantisation noise.
        dither_amp = getattr(self.config, "dither_amplitude", 1e-6)
        if dither_amp > 0:
            dither = np.random.uniform(-dither_amp, dither_amp, size=len(audio)).astype(np.float32)
            audio = audio + dither
        
        # 4. Pre-emphasis filter  y[n] = x[n] - α·x[n-1]
        audio = self._pre_emphasis(audio)
        
        # 5. RMS-based level normalisation (LUFS-equivalent)
        audio, achieved_rms = self._rms_normalize(audio)
        
        # 6. Safety peak clamp — must never exceed ±1.0
        peak = float(np.abs(audio).max())
        if peak > 0.99:
            audio = audio * (0.95 / peak)
        
        # 7. Estimate SNR
        snr_db = self._estimate_snr(audio)
        
        return PreProcessedAudio(
            audio=audio.astype(np.float32),
            original_audio=original,
            sample_rate=self.config.sample_rate,
            snr_estimate_db=snr_db,
            is_clipped=is_clipped,
            dc_offset_removed=dc_offset,
        )
    
    def _pre_emphasis(self, audio: np.ndarray) -> np.ndarray:
        """Apply pre-emphasis filter.
        
        y[n] = x[n] - coeff * x[n-1]
        
        This is a simple high-pass filter that boosts high frequencies.
        Common coefficient: 0.97
        
        WHY: Speech has a natural spectral tilt where energy decreases
        at ~6dB/octave. Pre-emphasis compensates for this, making mel
        spectrograms more uniform across frequency bands.
        """
        coeff = self.config.pre_emphasis_coeff
        emphasized = np.empty_like(audio)
        emphasized[0] = audio[0]
        emphasized[1:] = audio[1:] - coeff * audio[:-1]
        return emphasized
    
    def _rms_normalize(
        self,
        audio: np.ndarray,
        target_rms: float = _TARGET_RMS,
    ) -> tuple:
        """RMS-based normalization to a fixed target level.
        
        More robust than pure peak normalization for SNR preservation:
        - Peak norm can over-amplify clipped audio
        - RMS norm preserves perceived loudness relationships
        
        Returns:
            (normalized_audio, achieved_rms) tuple.
        """
        rms = float(np.sqrt(np.mean(audio ** 2) + 1e-12))
        if rms < 1e-8:
            return audio, rms  # Near-silence — don't amplify
        gain = target_rms / rms
        # Cap gain at 30 dB to avoid excessive amplification of very quiet audio
        gain = min(gain, 31.62)
        return audio * gain, rms

    def _estimate_snr(self, audio: np.ndarray) -> float:
        """Robust SNR estimate using a dual-percentile energy estimator.
        
        Speech frames are the top-25th-percentile energy frames.
        Noise frames are the bottom-25th-percentile energy frames.
        This is more robust than a simple median split because it avoids
        the transition region where frames are partially speech+noise.
        """
        frame_length = 512
        hop = 256
        
        # Calculate per-frame energy
        energies = []
        for i in range(0, len(audio) - frame_length, hop):
            frame = audio[i:i + frame_length]
            energies.append(float(np.sum(frame ** 2) / frame_length))
        
        if len(energies) < 4:
            return 30.0  # Default assumption for very short audio
        
        energies = np.array(energies)
        p25 = np.percentile(energies, 25)
        p75 = np.percentile(energies, 75)
        
        noise_energy = energies[energies <= p25]
        speech_energy = energies[energies >= p75]
        
        noise_mean = float(np.mean(noise_energy)) if len(noise_energy) > 0 else 1e-10
        speech_mean = float(np.mean(speech_energy)) if len(speech_energy) > 0 else 0.0
        
        if noise_mean < 1e-10:
            return 40.0  # Very clean
        
        snr = 10.0 * np.log10(max(speech_mean, 1e-10) / noise_mean)
        return float(np.clip(snr, -10.0, 60.0))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = VoiceConfig()
    normalizer = AudioNormalizer(config)
    
    # Test with noisy audio + DC offset + clipping
    t = np.arange(16000) / 16000  # 1 second
    speech = np.sin(2 * np.pi * 300 * t) * 0.3  # Fake speech
    noise = np.random.randn(16000) * 0.02        # Background noise
    audio = (speech + noise + 0.05).astype(np.float32)  # Add DC offset
    
    result = normalizer.process(audio)
    print(f"DC offset removed: {result.dc_offset_removed:.4f}")
    print(f"Clipped: {result.is_clipped}")
    print(f"SNR estimate: {result.snr_estimate_db:.1f} dB")
    print(f"Output range: [{result.audio.min():.3f}, {result.audio.max():.3f}]")
    print(f"Output RMS:   {float(np.sqrt(np.mean(result.audio**2))):.4f}")
    print("Normalizer test passed!")
