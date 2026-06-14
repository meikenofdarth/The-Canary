"""
canary/pipeline.py
-------------------
End-to-end orchestrator for The Canary audio intelligence pipeline.

Flow:
  record() → audio_np
     ↓
  Denoiser.enhance()         ← Spectral noise suppression
     ↓
  SpeakerCountEstimator.estimate()  ← Silero VAD + spectral clustering
     ↓
  SpeakerSeparator.separate()       ← SepFormer blind separation
     ↓
  save_wav() × N speakers           ← outputs/<timestamp>/speaker_N.wav
     ↓
  metrics report                    ← SI-SNR, denoising gain printed
"""

from __future__ import annotations

import os
import time
import datetime
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path
from typing import List, Optional, Tuple

from computation.audio.denoiser import Denoiser
from computation.audio.speaker_counter import SpeakerCountEstimator
from computation.audio.separator import SpeakerSeparator
from computation.audio import metrics as M


# ---------------------------------------------------------------------------
SAMPLE_RATE = 16000   # Everything runs at 16kHz
CHANNELS    = 1       # Mono capture


# ---------------------------------------------------------------------------
def record_audio(
    duration: float,
    sample_rate: int = SAMPLE_RATE,
    device: Optional[int] = None,
    on_progress=None,
) -> np.ndarray:
    """
    Record `duration` seconds from the default microphone.

    Parameters
    ----------
    duration : float        Recording length in seconds.
    sample_rate : int       Hz (default 16000).
    device : int | None     sounddevice device index. None = system default.
    on_progress : callable  Optional callback(elapsed_s, total_s).

    Returns
    -------
    np.ndarray shape (N,) float32 mono
    """
    frames: List[np.ndarray] = []
    start = time.time()

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())
        if on_progress:
            on_progress(time.time() - start, duration)

    with sd.InputStream(
        samplerate=sample_rate,
        channels=CHANNELS,
        dtype="float32",
        device=device,
        callback=callback,
        blocksize=int(sample_rate * 0.1),  # 100ms blocks
    ):
        sd.sleep(int(duration * 1000))

    audio = np.concatenate(frames, axis=0).squeeze()  # (N,)
    return audio.astype(np.float32)


# ---------------------------------------------------------------------------
def load_audio_file(path: str, target_sr: int = SAMPLE_RATE) -> Tuple[np.ndarray, int]:
    """
    Load any audio file (WAV, FLAC, MP3 via soundfile/librosa).

    Returns (mono float32 array, sample_rate)
    """
    audio, sr = sf.read(path, dtype="float32", always_2d=False)

    # Convert stereo → mono
    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    # Resample if needed
    if sr != target_sr:
        import torchaudio
        import torch
        t = torch.from_numpy(audio).unsqueeze(0)
        t = torchaudio.functional.resample(t, sr, target_sr)
        audio = t.squeeze(0).numpy()
        sr = target_sr

    return audio.astype(np.float32), sr


# ---------------------------------------------------------------------------
def save_wav(audio: np.ndarray, path: str, sample_rate: int = SAMPLE_RATE):
    """Save a 1-D float32 array as a 16-bit PCM WAV file."""
    sf.write(path, audio, sample_rate, subtype="PCM_16")


# ---------------------------------------------------------------------------
class CanaryPipeline:
    """
    Main pipeline class. Wires all components together.

    Usage
    -----
    pipeline = CanaryPipeline()

    # From mic:
    results = pipeline.run_from_mic(duration=10.0)

    # From file:
    results = pipeline.run_from_file("meeting.wav")

    Results dict keys:
      output_dir      : str   path to this run's output folder
      n_speakers      : int   estimated speaker count
      speaker_files   : list  paths to speaker_1.wav, speaker_2.wav, …
      denoised_file   : str   path to denoised mixture
      metrics         : dict  SI-SNR, denoising stats
    """

    def __init__(
        self,
        output_root: str = "outputs",
        denoise_prop: float = 0.85,
        max_speakers: int = 3,
        device: str | None = None,
        model_cache: str = "pretrained_models",
    ):
        self.output_root = Path(output_root)
        self.output_root.mkdir(exist_ok=True)

        # Lazily initialised components
        self._denoiser: Optional[Denoiser] = None
        self._counter: Optional[SpeakerCountEstimator] = None
        self._separator: Optional[SpeakerSeparator] = None

        self.denoise_prop = denoise_prop
        self.max_speakers = max_speakers
        self.device = device
        self.model_cache = model_cache

    # ------------------------------------------------------------------
    def _ensure_denoiser(self):
        if self._denoiser is None:
            self._denoiser = Denoiser(
                sample_rate=SAMPLE_RATE,
                prop_decrease=self.denoise_prop,
                stationary=False,
            )

    def _ensure_counter(self):
        if self._counter is None:
            self._counter = SpeakerCountEstimator(
                sample_rate=SAMPLE_RATE,
                max_speakers=self.max_speakers,
            )

    def _ensure_separator(self):
        if self._separator is None:
            self._separator = SpeakerSeparator(
                device=self.device,
                cache_dir=self.model_cache,
            )

    # ------------------------------------------------------------------
    def _make_output_dir(self) -> Path:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.output_root / ts
        out.mkdir(parents=True, exist_ok=True)
        return out

    # ------------------------------------------------------------------
    def process(
        self,
        audio: np.ndarray,
        sr: int = SAMPLE_RATE,
        progress_cb=None,
    ) -> dict:
        """
        Core processing: denoise → count speakers → separate → save.

        Parameters
        ----------
        audio : np.ndarray  float32 1-D, 16kHz mono
        sr    : int         sample rate (should be 16000)
        progress_cb : callable(stage: str)  optional progress hook

        Returns
        -------
        dict with results
        """

        def _cb(stage):
            if progress_cb:
                progress_cb(stage)

        out_dir = self._make_output_dir()

        # ── Stage 0: Save raw input ──────────────────────────────────
        raw_path = str(out_dir / "raw_input.wav")
        save_wav(audio, raw_path, sr)

        # ── Stage 1: Denoise ─────────────────────────────────────────
        _cb("denoising")
        self._ensure_denoiser()
        denoised = self._denoiser.enhance(audio)
        denoised_path = str(out_dir / "denoised_mix.wav")
        save_wav(denoised, denoised_path, sr)
        dnoise_metrics = M.denoising_gain(audio, denoised)

        # ── Stage 2: Estimate speaker count ─────────────────────────
        _cb("counting_speakers")
        self._ensure_counter()
        n_speakers = self._counter.estimate(denoised)

        # ── Stage 3: Separate ────────────────────────────────────────
        _cb("separating")
        self._ensure_separator()
        streams = self._separator.separate(denoised, sr, n_speakers)

        # ── Stage 4: Save per-speaker WAVs ───────────────────────────
        _cb("saving")
        speaker_files = []
        for i, stream in enumerate(streams, start=1):
            spk_path = str(out_dir / f"speaker_{i}.wav")
            save_wav(stream, spk_path, sr)
            speaker_files.append(spk_path)

        # ── Stage 5: Compute self-SI-SNR ────────────────────────────
        _cb("metrics")
        self_snr_scores = M.self_si_snr(streams)
        spk_rms = [round(M.rms_db(s), 2) for s in streams]

        return {
            "output_dir": str(out_dir),
            "n_speakers": n_speakers,
            "speaker_files": speaker_files,
            "denoised_file": denoised_path,
            "raw_file": raw_path,
            "metrics": {
                "denoising": dnoise_metrics,
                "self_si_snr_per_speaker": [round(v, 2) for v in self_snr_scores],
                "rms_per_speaker_db": spk_rms,
            },
        }

    # ------------------------------------------------------------------
    def run_from_mic(
        self,
        duration: float = 10.0,
        device: Optional[int] = None,
        progress_cb=None,
    ) -> dict:
        """Record from microphone then process."""
        audio = record_audio(duration, sample_rate=SAMPLE_RATE, device=device)
        return self.process(audio, SAMPLE_RATE, progress_cb)

    # ------------------------------------------------------------------
    def run_from_file(self, path: str, progress_cb=None) -> dict:
        """Load an audio file then process."""
        audio, sr = load_audio_file(path, target_sr=SAMPLE_RATE)
        return self.process(audio, SAMPLE_RATE, progress_cb)
