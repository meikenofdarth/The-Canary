"""Noise Floor Estimator — tracks ambient noise in real-time.

HOW IT WORKS:
    The noise estimator maintains a running estimate of the background
    noise spectrum using the "minimum statistics" approach:
    
    1. Compute the STFT (Short-Time Fourier Transform) of each audio frame
    2. During non-speech segments, update the noise spectrum estimate
    3. Use the noise spectrum to perform spectral subtraction
    
    Spectral subtraction formula:
        |clean_spectrum|² = |noisy_spectrum|² - α * |noise_spectrum|²
    
    Where α (oversubtraction factor) controls how aggressive the noise
    removal is. Higher α = more noise removed, but risks "musical noise"
    artifacts.
    
    ┌─────────────────────────────────────────────────────────────────┐
    │  Noisy spectrum:    ████████████████████████████████████████     │
    │  Noise estimate:    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                      │
    │  After subtraction: ░░░░░░░░████████████████████                │
    │                              ↑ Speech energy preserved          │
    └─────────────────────────────────────────────────────────────────┘
"""
import numpy as np
import logging
from typing import Optional

from ..config import VoiceConfig

logger = logging.getLogger(__name__)


class NoiseEstimator:
    """Estimates and subtracts background noise from audio.
    
    Uses spectral subtraction with running noise floor estimation.
    Only updates the noise estimate during non-speech segments
    (determined by the VAD upstream).
    
    Args:
        config: VoiceConfig with FFT and noise parameters.
    """
    
    def __init__(self, config: VoiceConfig):
        self.config = config
        self._n_fft = config.n_fft
        self._hop_length = config.hop_length
        
        # Running noise spectrum estimate (magnitude²)
        self._noise_spectrum: Optional[np.ndarray] = None
        self._frames_accumulated = 0
        self._alpha = 0.1  # EMA coefficient for noise update
    
    def update_noise_estimate(self, audio: np.ndarray) -> None:
        """Update the noise floor estimate using a non-speech segment.
        
        Call this with audio that the VAD classified as non-speech.
        The noise spectrum is updated using exponential moving average.
        
        Args:
            audio: float32 audio classified as non-speech.
        """
        # Compute STFT magnitude²
        spectrum = self._compute_power_spectrum(audio)
        
        if spectrum is None:
            return
        
        # Average across time frames to get a single noise profile
        noise_profile = np.mean(spectrum, axis=1)
        
        if self._noise_spectrum is None:
            self._noise_spectrum = noise_profile
        else:
            # Exponential moving average
            self._noise_spectrum = (
                self._alpha * noise_profile + 
                (1 - self._alpha) * self._noise_spectrum
            )
        
        self._frames_accumulated += 1
    
    def subtract_noise(self, audio: np.ndarray) -> np.ndarray:
        """Apply spectral subtraction to remove estimated noise.
        
        Args:
            audio: float32 audio to denoise.
            
        Returns:
            Denoised float32 audio (same length as input).
        """
        if self._noise_spectrum is None:
            # No noise estimate yet — return audio unchanged
            logger.debug("No noise estimate available, skipping subtraction")
            return audio
        
        # Compute STFT
        n_fft = self._n_fft
        hop = self._hop_length
        window = np.hanning(n_fft).astype(np.float32)
        
        # Pad audio to fit FFT
        pad_length = n_fft - (len(audio) % hop)
        audio_padded = np.pad(audio, (0, pad_length))
        
        # STFT
        n_frames = (len(audio_padded) - n_fft) // hop + 1
        stft = np.zeros((n_fft // 2 + 1, n_frames), dtype=np.complex128)
        
        for i in range(n_frames):
            start = i * hop
            frame = audio_padded[start:start + n_fft] * window
            spectrum = np.fft.rfft(frame)
            stft[:, i] = spectrum
        
        # Spectral subtraction
        magnitude = np.abs(stft)
        phase = np.angle(stft)
        power = magnitude ** 2
        
        # Subtract noise power (with oversubtraction factor)
        alpha = self.config.noise_oversubtraction
        noise_power = self._noise_spectrum[:, np.newaxis]  # Broadcast across frames
        
        # Ensure noise spectrum matches STFT size
        if noise_power.shape[0] != power.shape[0]:
            noise_power = np.interp(
                np.linspace(0, 1, power.shape[0]),
                np.linspace(0, 1, noise_power.shape[0]),
                noise_power.flatten()
            )[:, np.newaxis]
        
        clean_power = np.maximum(power - alpha * noise_power, 0.0)
        
        # Spectral flooring: don't let it go below a minimum
        # This prevents "musical noise" artifacts
        floor = 0.01 * noise_power
        clean_power = np.maximum(clean_power, floor)
        
        # Reconstruct
        clean_magnitude = np.sqrt(clean_power)
        clean_stft = clean_magnitude * np.exp(1j * phase)
        
        # Inverse STFT (overlap-add)
        output = np.zeros(len(audio_padded), dtype=np.float32)
        window_sum = np.zeros(len(audio_padded), dtype=np.float32)
        
        for i in range(n_frames):
            start = i * hop
            frame = np.fft.irfft(clean_stft[:, i]).real.astype(np.float32)
            output[start:start + n_fft] += frame * window
            window_sum[start:start + n_fft] += window ** 2
        
        # Normalize by window sum (avoid division by zero)
        mask = window_sum > 1e-8
        output[mask] /= window_sum[mask]
        
        # Trim to original length
        return output[:len(audio)]
    
    def get_noise_floor_db(self) -> float:
        """Get the current noise floor estimate in dB.
        
        Returns:
            Noise floor in dB. -60 if no estimate available.
        """
        if self._noise_spectrum is None:
            return -60.0
        
        mean_power = np.mean(self._noise_spectrum)
        if mean_power < 1e-10:
            return -60.0
        
        return float(10 * np.log10(mean_power))
    
    def _compute_power_spectrum(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """Compute power spectrum (magnitude²) via STFT.
        
        Returns:
            2D array of shape (n_fft//2+1, n_frames) or None if audio too short.
        """
        n_fft = self._n_fft
        hop = self._hop_length
        
        if len(audio) < n_fft:
            return None
        
        window = np.hanning(n_fft).astype(np.float32)
        n_frames = (len(audio) - n_fft) // hop + 1
        
        spectrum = np.zeros((n_fft // 2 + 1, n_frames))
        
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + n_fft] * window
            fft = np.fft.rfft(frame)
            spectrum[:, i] = np.abs(fft) ** 2
        
        return spectrum
    
    @property
    def has_estimate(self) -> bool:
        """Whether a noise estimate has been computed."""
        return self._noise_spectrum is not None
    
    def reset(self) -> None:
        """Reset noise estimate."""
        self._noise_spectrum = None
        self._frames_accumulated = 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = VoiceConfig()
    estimator = NoiseEstimator(config)
    
    # Simulate: first give it some noise-only audio
    noise = np.random.randn(16000).astype(np.float32) * 0.02
    estimator.update_noise_estimate(noise)
    print(f"Noise floor after calibration: {estimator.get_noise_floor_db():.1f} dB")
    
    # Now denoise speech + noise
    t = np.arange(16000) / 16000
    speech = np.sin(2 * np.pi * 300 * t) * 0.3
    noisy_speech = (speech + noise).astype(np.float32)
    
    clean = estimator.subtract_noise(noisy_speech)
    
    original_snr = 10 * np.log10(np.sum(speech**2) / np.sum(noise**2))
    print(f"Original SNR: {original_snr:.1f} dB")
    print(f"Output shape: {clean.shape}")
    print("NoiseEstimator test passed!")
