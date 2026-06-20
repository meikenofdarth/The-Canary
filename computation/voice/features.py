
from __future__ import annotations

import os
import logging
import warnings

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub.utils._headers").setLevel(logging.ERROR)
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

import numpy as np

SAMPLE_RATE = 16_000
FRAME_MS    = 30
FRAME_LEN   = int(SAMPLE_RATE * FRAME_MS / 1000)
MFCC_N      = 40


def _resample_mono(audio: np.ndarray, sr: int) -> np.ndarray:
    import librosa
    if audio.ndim > 1:
        audio = audio.mean(axis=-1)
    audio = audio.astype(np.float32)
    if sr != SAMPLE_RATE:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)
    peak = np.max(np.abs(audio))
    if peak > 1e-6:
        audio = audio / peak * 0.95
    return audio.astype(np.float32)


def _vad_mask(audio: np.ndarray) -> np.ndarray:
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
    mask   = _vad_mask(audio)
    voiced = audio[mask]
    if len(voiced) < FRAME_LEN:
        return audio
    return voiced


def _extract_embedding(audio: np.ndarray) -> np.ndarray:
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    model = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="pretrained_models/spkrec-ecapa-voxceleb",
        run_opts={"device": "cpu"},
    )

    tensor = torch.from_numpy(audio).unsqueeze(0)
    with torch.no_grad():
        emb = model.encode_batch(tensor)

    vec = emb.squeeze().cpu().numpy().astype(np.float32)
    norm = np.linalg.norm(vec) + 1e-10
    return (vec / norm).astype(np.float32)


def _extract_pitch(audio: np.ndarray) -> dict:
    import librosa

    f0, voiced_flag, voiced_probs = librosa.pyin(
        audio,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=SAMPLE_RATE,
        hop_length=256,
        frame_length=2048,
    )

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


def _extract_energy(audio: np.ndarray) -> dict:
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


def _extract_speaking_rate(audio: np.ndarray) -> dict:
    from scipy.signal import butter, sosfilt, find_peaks

    sos = butter(4, [300, 3400], btype="bandpass", fs=SAMPLE_RATE, output="sos")
    filtered = sosfilt(sos, audio.astype(np.float64))

    hop = 128
    n_frames = len(filtered) // hop
    envelope = np.array([
        float(np.sqrt(np.mean(filtered[i * hop:(i + 1) * hop] ** 2)))
        for i in range(n_frames)
    ])

    kernel = np.array([0.1, 0.2, 0.4, 0.2, 0.1])
    if len(envelope) > len(kernel):
        envelope = np.convolve(envelope, kernel, mode="same")

    min_dist   = max(1, int(0.08 * SAMPLE_RATE / hop))
    peak_height = float(np.max(envelope)) * 0.20 if np.max(envelope) > 1e-8 else 0.0
    peaks, _   = find_peaks(envelope, distance=min_dist, height=peak_height)

    mask            = _vad_mask(audio)
    voiced_seconds  = float(np.sum(mask)) / SAMPLE_RATE
    if voiced_seconds < 0.5:
        voiced_seconds = max(len(audio) / SAMPLE_RATE, 0.1)

    rate = float(len(peaks)) / voiced_seconds

    return {
        "syllables_per_second": round(rate, 3),
        "voiced_duration":      round(voiced_seconds, 3),
    }


def _extract_spectral(audio: np.ndarray) -> dict:
    import librosa

    voiced = _voiced_audio(audio)

    mfccs = librosa.feature.mfcc(
        y=voiced,
        sr=SAMPLE_RATE,
        n_mfcc=MFCC_N,
        n_fft=1024,
        hop_length=256,
    )

    centroid  = librosa.feature.spectral_centroid(
        y=voiced, sr=SAMPLE_RATE, n_fft=1024, hop_length=256)
    bandwidth = librosa.feature.spectral_bandwidth(
        y=voiced, sr=SAMPLE_RATE, n_fft=1024, hop_length=256)

    return {
        "mfcc_mean":  mfccs.mean(axis=1).astype(np.float32),
        "mfcc_std":   mfccs.std(axis=1).astype(np.float32),
        "centroid":   float(np.mean(centroid)),
        "bandwidth":  float(np.mean(bandwidth)),
    }


def extract(audio: np.ndarray, sr: int) -> dict:
    audio16 = _resample_mono(audio, sr)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        embedding = _extract_embedding(audio16)
        pitch = _extract_pitch(audio16)
        energy = _extract_energy(audio16)
        speaking_rate = _extract_speaking_rate(audio16)
        spectral = _extract_spectral(audio16)

    return {
        "embedding":     embedding,
        "pitch":         pitch,
        "energy":        energy,
        "speaking_rate": speaking_rate,
        "spectral":      spectral,
    }
