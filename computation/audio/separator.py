
from __future__ import annotations

import numpy as np
import torch
import torchaudio
from typing import List

_MODEL_SR = 16_000
_MODEL_IDS = {
    "clean": "JorisCos/ConvTasNet_Libri2Mix_sepclean_16k",
    "noisy": "JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k",
}
_model_cache: dict = {}

_CHUNK_S = 4.0
_OVERLAP = 0.75
_MAX_WHOLE_S = 20.0

_TARGET_RMS = 0.035


def _get_model(variant: str = "noisy", device: str = "cpu"):
    key = variant if variant in _MODEL_IDS else "noisy"
    if key not in _model_cache:
        from asteroid.models import ConvTasNet
        model = ConvTasNet.from_pretrained(_MODEL_IDS[key])
        model.eval().to(device)
        _model_cache[key] = model
    return _model_cache[key]


def _lufs_normalize(audio: np.ndarray, target_rms: float = _TARGET_RMS) -> tuple:
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) + 1e-10
    gain = target_rms / rms
    return (audio * gain).astype(np.float32), gain


def _gram_schmidt_debleed(streams: list) -> list:
    if len(streams) < 2:
        return streams
    clean = [s.astype(np.float64) for s in streams]
    for i in range(len(clean)):
        for j in range(len(clean)):
            if i == j:
                continue
            alpha = np.dot(clean[i], clean[j]) / (np.dot(clean[j], clean[j]) + 1e-10)
            clean[i] -= alpha * clean[j]
    result = []
    for orig, c in zip(streams, clean):
        peak_o = float(np.max(np.abs(orig))) + 1e-10
        peak_c = float(np.max(np.abs(c)))    + 1e-10
        result.append((c * (peak_o / peak_c)).astype(np.float32))
    return result


def voice_activity_overlap(s1: np.ndarray, s2: np.ndarray, sr: int = 16_000,
                           frame_ms: int = 30) -> float:
    frame_len = max(1, int(sr * frame_ms / 1000))
    n = min(len(s1), len(s2)) // frame_len
    if n < 2:
        return 1.0
    rms1 = np.array([np.sqrt(np.mean(s1[i*frame_len:(i+1)*frame_len]**2)) for i in range(n)])
    rms2 = np.array([np.sqrt(np.mean(s2[i*frame_len:(i+1)*frame_len]**2)) for i in range(n)])
    nf1  = float(np.percentile(rms1, 10)) + 1e-10
    nf2  = float(np.percentile(rms2, 10)) + 1e-10
    v1 = rms1 > nf1 * 3.0
    v2 = rms2 > nf2 * 3.0
    if v1.sum() == 0 or v2.sum() == 0:
        return 0.0
    return float(np.sum(v1 & v2) / max(np.sum(v1 | v2), 1))


def is_ghost_split(streams: list, sr: int = 16_000) -> bool:
    if len(streams) < 2:
        return False
    overlap = voice_activity_overlap(streams[0], streams[1], sr)

    from scipy.signal import butter, sosfilt
    sos = butter(4, [300, 3400], btype="bandpass", fs=sr, output="sos")
    def sb(x): return float(np.sqrt(np.mean(sosfilt(sos, x.astype(np.float64))**2)))
    sb1, sb2 = sb(streams[0]), sb(streams[1])
    ratio = min(sb1, sb2) / (max(sb1, sb2) + 1e-10)

    return overlap < 0.10 and ratio < 0.35


def _separate_chunk(model, chunk: np.ndarray, device: str = "cpu") -> np.ndarray:
    x = chunk.astype(np.float32)
    mu, sigma = float(x.mean()), float(x.std()) + 1e-8
    xn = (x - mu) / sigma

    t = torch.from_numpy(xn).unsqueeze(0).to(device)
    with torch.no_grad():
        est = model(t)
    est = est.squeeze(0).cpu().numpy()

    in_abs  = np.abs(xn).sum()
    out_abs = np.abs(est).sum() + 1e-8
    est = est * (in_abs / out_abs)
    est = est * sigma
    return est.astype(np.float32)


def _align_permutation(prev_tail: np.ndarray, cur_head: np.ndarray) -> bool:
    def corr(a, b):
        a = a - a.mean(); b = b - b.mean()
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-8
        return float(np.dot(a, b) / denom)

    straight = corr(prev_tail[0], cur_head[0]) + corr(prev_tail[1], cur_head[1])
    swapped  = corr(prev_tail[0], cur_head[1]) + corr(prev_tail[1], cur_head[0])
    return swapped > straight


def separate_waveform(
    audio: np.ndarray,
    variant: str = "noisy",
    device: str = "cpu",
) -> List[np.ndarray]:
    model = _get_model(variant, device)

    audio_norm, gain = _lufs_normalize(audio)

    n = len(audio_norm)
    chunk_len = int(_CHUNK_S * _MODEL_SR)
    hop       = int(chunk_len * (1.0 - _OVERLAP))
    overlap   = chunk_len - hop

    # Whole-clip inference for normal-length utterances: a single forward pass
    # is markedly higher quality than windowed overlap-add (which rescales each
    # chunk independently and creates seam artifacts). Only very long audio is
    # chunked.
    if n <= int(_MAX_WHOLE_S * _MODEL_SR):
        est = _separate_chunk(model, audio_norm, device)
        streams = [est[0][:n] / gain, est[1][:n] / gain]
        return [s.astype(np.float32) for s in _gram_schmidt_debleed(streams)]

    out  = np.zeros((2, n), dtype=np.float64)
    wsum = np.zeros(n,      dtype=np.float64)
    window = np.hanning(chunk_len).astype(np.float64)

    pos   = 0
    first = True
    while pos < n:
        end = min(pos + chunk_len, n)
        seg = audio_norm[pos:end]
        if len(seg) < chunk_len:
            seg = np.pad(seg, (0, chunk_len - len(seg)))

        est = _separate_chunk(model, seg, device)

        if not first and overlap > 0:
            ov = min(overlap, n - pos)
            if ov > 1:
                wnorm     = np.maximum(wsum[pos:pos + ov], 1e-8)
                prev_tail = out[:, pos:pos + ov] / wnorm
                if _align_permutation(prev_tail, est[:, :ov]):
                    est = est[::-1].copy()

        seg_w = window[: end - pos]
        out[0, pos:end] += est[0, : end - pos] * seg_w
        out[1, pos:end] += est[1, : end - pos] * seg_w
        wsum[pos:end]   += seg_w

        first = False
        pos  += hop

    wsum = np.maximum(wsum, 1e-8)
    streams = [out[0] / wsum / gain, out[1] / wsum / gain]

    streams = _gram_schmidt_debleed(streams)
    return [s.astype(np.float32) for s in streams]


class SpeakerSeparator:

    def __init__(self, device: str | None = None, cache_dir: str = "pretrained_models",
                 variant: str = "clean"):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.variant = variant

    def separate(self, audio: np.ndarray, sample_rate: int = 16_000,
                 n_speakers: int = 2) -> List[np.ndarray]:
        if audio.ndim != 1:
            raise ValueError(f"Expected 1-D mono audio, got shape {audio.shape}")

        n_speakers = max(1, min(n_speakers, 2))
        if n_speakers == 1:
            return [audio.copy()]

        if sample_rate != _MODEL_SR:
            t = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
            audio = torchaudio.functional.resample(t, sample_rate, _MODEL_SR).squeeze(0).numpy()

        streams = separate_waveform(audio, variant=self.variant, device=self.device)

        out = []
        for s in streams:
            peak = np.max(np.abs(s))
            if peak > 1e-6:
                s = s / peak * 0.9
            out.append(s.astype(np.float32))
        return out
