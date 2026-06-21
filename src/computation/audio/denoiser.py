
from __future__ import annotations

import numpy as np
import noisereduce as nr
import warnings


class Denoiser:

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

    def enhance(self, audio: np.ndarray) -> np.ndarray:
        if audio.ndim != 1:
            raise ValueError(f"Expected 1-D array, got shape {audio.shape}")

        dtype = audio.dtype
        audio_f = audio.astype(np.float32)

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

        peak = np.max(np.abs(denoised))
        if peak > 1e-6:
            denoised = denoised / peak * min(peak, 0.98)

        return denoised.astype(dtype)

    def enhance_stereo(self, audio: np.ndarray) -> np.ndarray:
        if audio.ndim == 1:
            return self.enhance(audio)
        return np.stack([self.enhance(audio[c]) for c in range(audio.shape[0])])
