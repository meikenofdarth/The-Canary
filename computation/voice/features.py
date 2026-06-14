"""
voice_computation/features.py
==============================
Feature Group Extractor for Voice Identity Engine.

Extracts 5 independent feature groups from any audio buffer:

  Group A  —  ECAPA-TDNN speaker embedding  (192-dim d-vector)  weight: 60%
  Group B  —  Pitch profile                 (mean/std/min/max)  weight: 15%
  Group C  —  Energy (RMS) profile          (mean/std)          weight: 10%
  Group D  —  Speaking rate                 (syllables/second)  weight: 10%
  Group E  —  Spectral profile              (MFCC40 + centroid) weight:  5%

All audio is normalised to 16 kHz mono before any computation.
VAD strips silence from all feature calculations so we measure
actual speech, not pauses.

Public API
----------
  extract(audio: np.ndarray, sr: int) -> dict
"""

from __future__ import annotations

import os
import logging
import warnings

# Suppress HuggingFace Hub unauthenticated-request warning.
# ECAPA-TDNN is cached locally; the Hub is never contacted at runtime.
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub.utils._headers").setLevel(logging.ERROR)
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

import numpy as np

SAMPLE_RATE = 16_000          # canonical internal sample rate
FRAME_MS    = 30              # VAD frame length in ms
FRAME_LEN   = int(SAMPLE_RATE * FRAME_MS / 1000)   # samples per frame
MFCC_N      = 40              # number of MFCC coefficients


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resample_mono(audio: np.ndarray, sr: int) -> np.ndarray:
    """Resample to 16 kHz mono float32."""
    import librosa
    if audio.ndim > 1:
        audio = audio.mean(axis=-1)
    audio = audio.astype(np.float32)
    if sr != SAMPLE_RATE:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)
    # Peak-normalise so level differences don't skew energy features
    peak = np.max(np.abs(audio))
    if peak > 1e-6:
        audio = audio / peak * 0.95
    return audio.astype(np.float32)


def _vad_mask(audio: np.ndarray) -> np.ndarray:
    """
    Energy-based VAD.  Returns a boolean mask (same length as audio) that is
    True for samples belonging to voiced frames.

    A frame is voiced if its RMS exceeds 3× the noise floor (10th percentile
    of all frame RMS values).  This is robust, fast, and dependency-free.
    """
    n_frames = len(audio) // FRAME_LEN
    if n_frames == 0:
        return np.ones(len(audio), dtype=bool)

    rms_frames = np.array([
        np.sqrt(np.mean(audio[i * FRAME_LEN:(i + 1) * FRAME_LEN] ** 2))
        for i in range(n_frames)
    ])
    noise_floor = float(np.percentile(rms_frames, 10)) + 1e-10
    voiced_frames = rms_frames > noise_floor * 3.0

    mask = np.zeros(len(audio), dtype=bool)
    for i, v in enumerate(voiced_frames):
        if v:
            mask[i * FRAME_LEN:(i + 1) * FRAME_LEN] = True
    return mask


def _voiced_audio(audio: np.ndarray) -> np.ndarray:
    """Return only the voiced (non-silent) samples."""
    mask   = _vad_mask(audio)
    voiced = audio[mask]
    if len(voiced) < FRAME_LEN:        # fallback: return everything
        return audio
    return voiced


# ─────────────────────────────────────────────────────────────────────────────
#  Group A — ECAPA-TDNN speaker embedding
# ─────────────────────────────────────────────────────────────────────────────

def _extract_embedding(audio: np.ndarray) -> np.ndarray:
    """
    ECAPA-TDNN d-vector via SpeechBrain.
    Model: speechbrain/spkrec-ecapa-voxceleb
    Output: 192-dimensional L2-normalised embedding.
    """
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    model = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="pretrained_models/spkrec-ecapa-voxceleb",
        run_opts={"device": "cpu"},
    )

    tensor = torch.from_numpy(audio).unsqueeze(0)   # (1, T)
    with torch.no_grad():
        emb = model.encode_batch(tensor)             # (1, 1, 192)

    vec = emb.squeeze().cpu().numpy().astype(np.float32)
    # L2 normalise so cosine sim == dot product
    norm = np.linalg.norm(vec) + 1e-10
    return (vec / norm).astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  Group B — Pitch profile
# ─────────────────────────────────────────────────────────────────────────────

def _extract_pitch(audio: np.ndarray) -> dict:
    """
    F0 tracking via librosa.pyin (probabilistic YIN).
    Only voiced frames (confidence > 0.5) are included in statistics.

    Returns:
        mean_pitch  — average F0 across voiced frames (Hz)
        std_pitch   — standard deviation of F0
        min_pitch   — minimum F0
        max_pitch   — maximum F0
    """
    import librosa

    f0, voiced_flag, voiced_probs = librosa.pyin(
        audio,
        fmin=librosa.note_to_hz("C2"),   # ~65 Hz  — lowest human voice
        fmax=librosa.note_to_hz("C7"),   # ~2093 Hz — highest falsetto
        sr=SAMPLE_RATE,
        hop_length=256,
        frame_length=2048,
    )

    # Keep only high-confidence voiced frames
    confident = voiced_probs > 0.5
    voiced_f0 = f0[confident & ~np.isnan(f0)]

    if len(voiced_f0) == 0:
        return {"mean_pitch": 0.0, "std_pitch": 0.0,
                "min_pitch":  0.0, "max_pitch":  0.0}

    return {
        "mean_pitch": float(np.mean(voiced_f0)),
        "std_pitch":  float(np.std(voiced_f0)),
        "min_pitch":  float(np.min(voiced_f0)),
        "max_pitch":  float(np.max(voiced_f0)),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Group C — Energy (RMS) profile
# ─────────────────────────────────────────────────────────────────────────────

def _extract_energy(audio: np.ndarray) -> dict:
    """
    Compute per-frame RMS energy statistics over voiced frames only.

    Returns:
        mean_rms — average RMS of voiced frames
        std_rms  — standard deviation of RMS
    """
    voiced = _voiced_audio(audio)
    n_frames = len(voiced) // FRAME_LEN
    if n_frames == 0:
        return {"mean_rms": 0.0, "std_rms": 0.0}

    rms_vals = np.array([
        float(np.sqrt(np.mean(voiced[i * FRAME_LEN:(i + 1) * FRAME_LEN] ** 2)))
        for i in range(n_frames)
    ])

    return {
        "mean_rms": float(np.mean(rms_vals)),
        "std_rms":  float(np.std(rms_vals)),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Group D — Speaking rate
# ─────────────────────────────────────────────────────────────────────────────

def _extract_speaking_rate(audio: np.ndarray) -> dict:
    """
    Estimate speaking rate as syllables per second.

    Method: count energy envelope peaks in the 300–3400 Hz speech band.
    Each energy peak roughly corresponds to one syllable nucleus.
    This is the classic Villing et al. (2006) approach — no ASR needed.

    Returns:
        syllables_per_second — estimated speaking rate
        voiced_duration      — total voiced duration in seconds (for QA)
    """
    from scipy.signal import butter, sosfilt, find_peaks

    # Band-pass to speech fundamental range
    sos = butter(4, [300, 3400], btype="bandpass", fs=SAMPLE_RATE, output="sos")
    filtered = sosfilt(sos, audio.astype(np.float64))

    # Smooth RMS envelope
    hop = 128
    n_frames = len(filtered) // hop
    envelope = np.array([
        float(np.sqrt(np.mean(filtered[i * hop:(i + 1) * hop] ** 2)))
        for i in range(n_frames)
    ])

    # Smooth with a small Gaussian-like window
    kernel = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
    if len(envelope) > len(kernel):
        envelope = np.convolve(envelope, kernel, mode="same")

    # Peak detection: min distance ~80 ms (shortest syllable), height = 20% of max
    min_dist   = max(1, int(0.08 * SAMPLE_RATE / hop))
    peak_height = float(np.max(envelope)) * 0.20 if np.max(envelope) > 1e-8 else 0.0
    peaks, _   = find_peaks(envelope, distance=min_dist, height=peak_height)

    # Voiced duration via VAD
    mask            = _vad_mask(audio)
    voiced_seconds  = float(np.sum(mask)) / SAMPLE_RATE
    if voiced_seconds < 0.5:
        voiced_seconds = max(len(audio) / SAMPLE_RATE, 0.1)

    rate = float(len(peaks)) / voiced_seconds

    return {
        "syllables_per_second": round(rate, 3),
        "voiced_duration":      round(voiced_seconds, 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Group E — Spectral profile (MFCC + centroid + bandwidth)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_spectral(audio: np.ndarray) -> dict:
    """
    Extract MFCC statistics and spectral shape descriptors.

    MFCCs (40 coefficients) — skip the zeroth coefficient (energy).
    Mean and std across all frames give a compact voice fingerprint.

    Returns:
        mfcc_mean   — np.ndarray (40,)   float32
        mfcc_std    — np.ndarray (40,)   float32
        centroid    — mean spectral centroid (Hz)
        bandwidth   — mean spectral bandwidth (Hz)
    """
    import librosa

    voiced = _voiced_audio(audio)

    mfccs = librosa.feature.mfcc(
        y=voiced,
        sr=SAMPLE_RATE,
        n_mfcc=MFCC_N,
        n_fft=1024,
        hop_length=256,
    )  # shape: (MFCC_N, T)

    centroid  = librosa.feature.spectral_centroid(
        y=voiced, sr=SAMPLE_RATE, n_fft=1024, hop_length=256)
    bandwidth = librosa.feature.spectral_bandwidth(
        y=voiced, sr=SAMPLE_RATE, n_fft=1024, hop_length=256)

    return {
        "mfcc_mean":  mfccs.mean(axis=1).astype(np.float32),   # (40,)
        "mfcc_std":   mfccs.std(axis=1).astype(np.float32),    # (40,)
        "centroid":   float(np.mean(centroid)),
        "bandwidth":  float(np.mean(bandwidth)),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract(audio: np.ndarray, sr: int) -> dict:
    """
    Extract all 5 feature groups from a raw audio buffer.

    Parameters
    ----------
    audio : np.ndarray
        Raw audio samples (any shape, any sample rate).
    sr : int
        Sample rate of `audio`.

    Returns
    -------
    dict with keys:
        embedding       — np.ndarray (192,)   L2-normalised ECAPA-TDNN d-vector
        pitch           — dict  {mean_pitch, std_pitch, min_pitch, max_pitch}
        energy          — dict  {mean_rms, std_rms}
        speaking_rate   — dict  {syllables_per_second, voiced_duration}
        spectral        — dict  {mfcc_mean (40,), mfcc_std (40,), centroid, bandwidth}
    """
    audio16 = _resample_mono(audio, sr)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        print("    [features] extracting embedding ...", flush=True)
        embedding = _extract_embedding(audio16)

        print("    [features] extracting pitch     ...", flush=True)
        pitch = _extract_pitch(audio16)

        print("    [features] extracting energy    ...", flush=True)
        energy = _extract_energy(audio16)

        print("    [features] extracting rate      ...", flush=True)
        speaking_rate = _extract_speaking_rate(audio16)

        print("    [features] extracting spectral  ...", flush=True)
        spectral = _extract_spectral(audio16)

    return {
        "embedding":     embedding,
        "pitch":         pitch,
        "energy":        energy,
        "speaking_rate": speaking_rate,
        "spectral":      spectral,
    }
