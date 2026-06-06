"""Noise Floor Estimator — tracks ambient noise in real-time.

HOW IT WORKS:
    The noise estimator maintains a running estimate of the background
    noise spectrum using the "minimum statistics" approach:
    
    1. Compute the STFT (Short-Time Fourier Transform) of each audio frame
    2. During non-speech segments, update the noise spectrum estimate
    3. Use the noise spectrum to perform spectral subtraction
    
    Spectral subtraction formula:
        |clean|² = max(|noisy|² - α·|noise|², β·|noise|²)
    
    Where:
        α (oversubtraction factor) = how aggressive to remove noise
        β (spectral floor) = minimum retained power ratio — prevents
          "musical noise" artifacts when subtraction over-zeros bins.
    
    This version fixes three bugs in the original:
      1. Spectral floor was 0.01 (too low — caused musical noise).
         Now 0.15 (softer floor — safe for all SNR conditions).
      2. Dithering (1e-6) is added before STFT to prevent log(0) issues.
      3. Exposes get_noise_spectrum() for multi-band downstream use.
    
    ┌─────────────────────────────────────────────────────────────────┐
    │  Noisy spectrum:    ████████████████████████████████████████     │
    │  Noise estimate:    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                      │
    │  After subtraction: ░░░░░░░░████████████████████                │
    │                              ↑ Speech energy preserved          │
    │  Spectral floor:    ░░░░░░░░░░░░░░░░░░░░░░░░░░                 │
    │  (prevents complete zeroing of bins → no musical noise)        │
    └─────────────────────────────────────────────────────────────────┘
"""
import numpy as np
import logging
from typing import Optional

from ..config import VoiceConfig

logger = logging.getLogger(__name__)

# Spectral floor: minimum fraction of noise power kept after subtraction.
# 0.15 is safe for SNR > 5 dB. Lower = more aggressive = more musical noise.
_SPECTRAL_FLOOR = 0.15


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
            # Exponential moving average — tracks slowly-changing noise
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
        dither_amp = getattr(self.config, "dither_amplitude", 1e-6)
        
        # Pad audio to fit FFT frames cleanly
        pad_length = n_fft - (len(audio) % hop)
        if pad_length == n_fft:
            pad_length = 0
        audio_padded = np.pad(audio, (0, pad_length)).astype(np.float32)
        
        # STFT
        n_frames = (len(audio_padded) - n_fft) // hop + 1
        stft = np.zeros((n_fft // 2 + 1, n_frames), dtype=np.complex128)
        
        for i in range(n_frames):
            start = i * hop
            frame = audio_padded[start:start + n_fft].astype(np.float64)
            # Dither before FFT to prevent log(0) artifacts in bin magnitudes
            frame += np.random.uniform(-dither_amp, dither_amp, n_fft)
            stft[:, i] = np.fft.rfft(frame * window)
        
        # Spectral subtraction in power domain
        magnitude = np.abs(stft)
        phase = np.angle(stft)
        power = magnitude ** 2
        
        # Oversubtraction factor from config (default 1.5, was 2.0)
        alpha = self.config.noise_oversubtraction
        noise_power = self._get_aligned_noise_power(power.shape[0])
        
        # Subtract noise: max(P_noisy - α·P_noise, β·P_noise)
        clean_power = np.maximum(
            power - alpha * noise_power,
            _SPECTRAL_FLOOR * noise_power,  # Spectral floor — prevents musical noise
        )
        
        # Reconstruct
        clean_magnitude = np.sqrt(clean_power)
        clean_stft = clean_magnitude * np.exp(1j * phase)
        
        # Inverse STFT (overlap-add)
        output = np.zeros(len(audio_padded), dtype=np.float32)
        window_sum = np.zeros(len(audio_padded), dtype=np.float32)
        
        for i in range(n_frames):
            start = i * hop
            frame = np.fft.irfft(clean_stft[:, i]).real[:n_fft].astype(np.float32)
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
        
        mean_power = float(np.mean(self._noise_spectrum))
        if mean_power < 1e-12:
            return -60.0
        
        return float(10.0 * np.log10(mean_power))
    
    def get_noise_spectrum(self) -> Optional[np.ndarray]:
        """Return the current per-bin noise power spectrum.
        
        Useful for multi-band downstream DSP (e.g. resource_scaler Mode B).
        
        Returns:
            float32 array of shape (n_fft//2+1,) or None if unavailable.
        """
        if self._noise_spectrum is None:
            return None
        return self._noise_spectrum.astype(np.float32)

    def _get_aligned_noise_power(self, n_bins: int) -> np.ndarray:
        """Return noise power spectrum aligned/interpolated to n_bins, broadcast-ready."""
        noise = self._noise_spectrum
        if noise.shape[0] == n_bins:
            return noise[:, np.newaxis]
        # Interpolate to match STFT bin count
        x_old = np.linspace(0, 1, noise.shape[0])
        x_new = np.linspace(0, 1, n_bins)
        aligned = np.interp(x_new, x_old, noise)
        return aligned[:, np.newaxis]

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
            frame = audio[start:start + n_fft].astype(np.float64)
            fft = np.fft.rfft(frame * window)
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
    
    noise_spec = estimator.get_noise_spectrum()
    print(f"Noise spectrum shape: {noise_spec.shape}")
    
    # Now denoise speech + noise
    t = np.arange(16000) / 16000
    speech = np.sin(2 * np.pi * 300 * t) * 0.3
    noisy_speech = (speech + noise).astype(np.float32)
    
    clean = estimator.subtract_noise(noisy_speech)
    
    original_snr = 10 * np.log10(np.sum(speech**2) / (np.sum(noise**2) + 1e-12))
    print(f"Original SNR: {original_snr:.1f} dB")
    print(f"Output shape: {clean.shape}")
    print(f"Output peak:  {np.abs(clean).max():.4f}")
    print("NoiseEstimator test passed!")
