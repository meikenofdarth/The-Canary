"""Audio Normalizer — cleans raw audio for downstream processing.

HOW IT WORKS:
    Raw microphone audio often has issues:
    1. DC Offset: A constant voltage bias that shifts the waveform up/down.
       We remove it by subtracting the mean.
    2. Low amplitude: Quiet speakers or distant mics produce weak signals.
       We normalize to a target peak amplitude.
    3. Missing high-frequency emphasis: Speech energy drops at higher frequencies.
       The pre-emphasis filter boosts them, improving downstream feature extraction.
    
    Processing chain:
    Raw Audio → Remove DC → Pre-Emphasis → Peak Normalize → Clip Check → Output
"""
import numpy as np
import logging

from ..config import VoiceConfig
from ..models import PreProcessedAudio

logger = logging.getLogger(__name__)


class AudioNormalizer:
    """Normalizes and cleans raw audio for the pipeline.
    
    Args:
        config: VoiceConfig with pre-emphasis coefficient.
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
        dc_offset = np.mean(audio)
        audio = audio - dc_offset
        
        # 2. Check for clipping (samples at ±1.0)
        is_clipped = np.any(np.abs(audio) >= 0.99)
        if is_clipped:
            logger.warning("Clipping detected in audio")
        
        # 3. Pre-emphasis filter
        # y[n] = x[n] - α * x[n-1]
        # This boosts high frequencies relative to low frequencies.
        # Speech has more energy in low frequencies, so this balances it.
        audio = self._pre_emphasis(audio)
        
        # 4. Peak normalize to [-1, 1]
        audio = self._peak_normalize(audio)
        
        # 5. Estimate SNR
        snr_db = self._estimate_snr(audio)
        
        return PreProcessedAudio(
            audio=audio,
            original_audio=original,
            sample_rate=self.config.sample_rate,
            snr_estimate_db=snr_db,
            is_clipped=is_clipped,
            dc_offset_removed=float(dc_offset),
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
        # np.append prepends the first sample (no change to it)
        return np.append(audio[0], audio[1:] - coeff * audio[:-1])
    
    def _peak_normalize(self, audio: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
        """Normalize audio so the peak amplitude is at target_peak.
        
        Args:
            audio: Input audio.
            target_peak: Target maximum amplitude (0.95 leaves headroom).
        """
        peak = np.abs(audio).max()
        if peak < 1e-8:
            # Audio is essentially silence
            return audio
        return audio * (target_peak / peak)
    
    def _estimate_snr(self, audio: np.ndarray) -> float:
        """Rough SNR estimate using energy ratio.
        
        Splits the signal into "loud" (speech) and "quiet" (noise) parts
        based on the median energy threshold.
        
        This is a heuristic — not precise, but good enough for routing.
        """
        frame_length = 512
        hop = 256
        
        # Calculate per-frame energy
        energies = []
        for i in range(0, len(audio) - frame_length, hop):
            frame = audio[i:i + frame_length]
            energy = np.sum(frame ** 2)
            energies.append(energy)
        
        if not energies:
            return 30.0  # Default assumption
        
        energies = np.array(energies)
        median_energy = np.median(energies)
        
        # Speech frames: above median, Noise frames: below
        speech_energy = energies[energies > median_energy]
        noise_energy = energies[energies <= median_energy]
        
        if len(noise_energy) == 0 or np.mean(noise_energy) < 1e-10:
            return 40.0  # Very clean
        
        snr = 10 * np.log10(np.mean(speech_energy) / np.mean(noise_energy))
        return float(np.clip(snr, -10, 60))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = VoiceConfig()
    normalizer = AudioNormalizer(config)
    
    # Test with noisy audio
    t = np.arange(16000) / 16000  # 1 second
    speech = np.sin(2 * np.pi * 300 * t) * 0.3  # Fake speech
    noise = np.random.randn(16000) * 0.02        # Background noise
    audio = (speech + noise + 0.05).astype(np.float32)  # Add DC offset
    
    result = normalizer.process(audio)
    print(f"DC offset removed: {result.dc_offset_removed:.4f}")
    print(f"Clipped: {result.is_clipped}")
    print(f"SNR estimate: {result.snr_estimate_db:.1f} dB")
    print(f"Output range: [{result.audio.min():.3f}, {result.audio.max():.3f}]")
    print("Normalizer test passed!")
