"""
canary/separator.py
--------------------
Speaker separation using SpeechBrain's pretrained SepFormer models.

Models used (auto-downloaded on first run, cached in ~/.cache/huggingface):
  - speechbrain/sepformer-libri2mix  → 2-speaker separation
  - speechbrain/sepformer-libri3mix  → 3-speaker separation

SepFormer achieves >22 dB SI-SNRi on LibriMix — best-in-class open model.
It operates at 8000 Hz internally (upsampled to 16000 Hz for output).

Architecture quick note:
  Input (16kHz mono) → resample to 8kHz → SepFormer (transformer encoder-decoder
  with dual-path) → N separated streams → resample back to 16kHz → output
"""

from __future__ import annotations

import numpy as np
import torch
import torchaudio
from typing import List
import warnings
import logging

# Silence chatty SpeechBrain logs
logging.getLogger("speechbrain").setLevel(logging.ERROR)


class SpeakerSeparator:
    """
    Wraps SpeechBrain SepFormer for blind source separation.

    Parameters
    ----------
    device : str
        'cpu' or 'cuda'. Defaults to 'cuda' if available.
    cache_dir : str
        Where to save downloaded model weights.
    """

    # SepFormer internal sample rate
    _MODEL_SR = 8000
    # HuggingFace model IDs
    _MODEL_IDS = {
        1: "speechbrain/sepformer-libri2mix",   # reuse 2-spk for 1-spk clean
        2: "speechbrain/sepformer-libri2mix",
        3: "speechbrain/sepformer-libri3mix",
    }

    def __init__(
        self,
        device: str | None = None,
        cache_dir: str = "pretrained_models",
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.cache_dir = cache_dir
        self._models: dict = {}

    # ------------------------------------------------------------------
    def _load_model(self, n_speakers: int):
        """Lazily load the model for a given speaker count."""
        key = min(n_speakers, 3)
        if key not in self._models:
            model_id = self._MODEL_IDS[key]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from speechbrain.inference.separation import SepformerSeparation
                model = SepformerSeparation.from_hparams(
                    source=model_id,
                    savedir=f"{self.cache_dir}/{model_id.split('/')[-1]}",
                    run_opts={"device": self.device},
                )
            self._models[key] = model
        return self._models[key]

    # ------------------------------------------------------------------
    def _resample(
        self, audio: np.ndarray, orig_sr: int, target_sr: int
    ) -> np.ndarray:
        """Resample a 1-D float32 array."""
        if orig_sr == target_sr:
            return audio
        tensor = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        resampled = torchaudio.functional.resample(tensor, orig_sr, target_sr)
        return resampled.squeeze(0).numpy()

    # ------------------------------------------------------------------
    def separate(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        n_speakers: int = 2,
    ) -> List[np.ndarray]:
        """
        Separate mixed audio into per-speaker streams.

        Parameters
        ----------
        audio : np.ndarray  shape (N,)  float32 mono
        sample_rate : int   input sample rate
        n_speakers : int    estimated number of speakers (1–3)

        Returns
        -------
        List of np.ndarray, one per speaker, same length as input,
        at the same sample_rate.
        """
        if audio.ndim != 1:
            raise ValueError(f"Expected 1-D mono audio, got {audio.shape}")

        n_speakers = max(1, min(n_speakers, 3))

        # Short-circuit: if only 1 speaker, return as-is
        if n_speakers == 1:
            return [audio.copy()]

        # --- Resample to 8kHz for SepFormer ---
        audio_8k = self._resample(audio, sample_rate, self._MODEL_SR)

        # SepFormer expects a torch tensor of shape (1, T)
        mix_tensor = torch.from_numpy(audio_8k.astype(np.float32)).unsqueeze(0)

        model = self._load_model(n_speakers)

        with torch.no_grad():
            # est_sources shape: (T, n_spk)
            est_sources = model.separate_batch(mix_tensor)

        separated: List[np.ndarray] = []
        for spk_idx in range(min(n_speakers, est_sources.shape[-1])):
            spk_8k = est_sources[0, :, spk_idx].cpu().numpy()  # (T,)
            # Resample back to original sample rate
            spk_sr = self._resample(spk_8k, self._MODEL_SR, sample_rate)
            # Match length to input
            target_len = len(audio)
            if len(spk_sr) > target_len:
                spk_sr = spk_sr[:target_len]
            elif len(spk_sr) < target_len:
                spk_sr = np.pad(spk_sr, (0, target_len - len(spk_sr)))
            # Normalise
            peak = np.max(np.abs(spk_sr))
            if peak > 1e-6:
                spk_sr = spk_sr / peak * 0.9
            separated.append(spk_sr.astype(np.float32))

        return separated
