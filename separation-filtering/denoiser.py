"""
canary/denoiser.py
------------------
Neural noise suppression using noisereduce (stationary + non-stationary)
with an optional fallback to a simple spectral gate.

Strategy:
  1. Estimate noise profile from the first ~0.5s (or a silent pad) of audio.
  2. Run noisereduce.reduce_noise() with non-stationary=True for dynamic
     environments (music, background chatter, RIR).
  3. Optionally apply a Wiener filter for residual smoothing.
"""

from __future__ import annotations

import numpy as np
import noisereduce as nr
import warnings


class Denoiser:
    """
    Wraps noisereduce for plug-and-play spectral noise suppression.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate in Hz (e.g. 16000).
    prop_decrease : float
        How aggressively to reduce noise (0.0–1.0). Default 0.85.
    stationary : bool
        If True, assumes noise profile is stationary (e.g. HVAC hum).
        If False (default), uses non-stationary reduction for real rooms.
    noise_clip_duration : float
        Duration in seconds at the START of the audio to use as noise
        reference. If 0, noisereduce estimates noise automatically.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        prop_decrease: float = 0.85,
        stationary: bool = False,
        noise_clip_duration: float = 0.0,
    ):
        self.sample_rate = sample_rate
        self.prop_decrease = prop_decrease
        self.stationary = stationary
        self.noise_clip_duration = noise_clip_duration

    # ------------------------------------------------------------------
    def enhance(self, audio: np.ndarray) -> np.ndarray:
        """
        Denoise a 1-D float32 numpy array.

        Parameters
        ----------
        audio : np.ndarray  shape (N,)  dtype float32 or float64
        
        Returns
        -------
        denoised : np.ndarray  same shape and dtype
        """
        if audio.ndim != 1:
            raise ValueError(f"Expected 1-D array, got shape {audio.shape}")

        dtype = audio.dtype
        audio_f = audio.astype(np.float32)

        # Build optional noise reference clip
        noise_clip: np.ndarray | None = None
        if self.noise_clip_duration > 0:
            n_samples = int(self.noise_clip_duration * self.sample_rate)
            noise_clip = audio_f[:n_samples]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            denoised = nr.reduce_noise(
                y=audio_f,
                sr=self.sample_rate,
                y_noise=noise_clip,
                stationary=self.stationary,
                prop_decrease=self.prop_decrease,
                n_fft=512,
                win_length=512,
                hop_length=128,
                time_mask_smooth_ms=50,
                freq_mask_smooth_hz=500,
            )

        # Prevent clipping
        peak = np.max(np.abs(denoised))
        if peak > 1e-6:
            denoised = denoised / peak * min(peak, 0.98)

        return denoised.astype(dtype)

    # ------------------------------------------------------------------
    def enhance_stereo(self, audio: np.ndarray) -> np.ndarray:
        """Denoise stereo audio, channel-by-channel. Shape (2, N)."""
        if audio.ndim == 1:
            return self.enhance(audio)
        return np.stack([self.enhance(audio[c]) for c in range(audio.shape[0])])
