
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf

VOICES_ROOT = Path(__file__).parent.parent.parent / "database" / "Voices"

W_EMBEDDING = 0.95
W_PITCH     = 0.01
W_ENERGY    = 0.01
W_RATE      = 0.01
W_MFCC      = 0.02

SIGMA_PITCH  = 25.0
SIGMA_ENERGY = 0.08
SIGMA_RATE   = 1.2


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    denom = (np.linalg.norm(a) + 1e-10) * (np.linalg.norm(b) + 1e-10)
    return float(np.clip(np.dot(a, b) / denom, 0.0, 1.0))


def _gaussian_sim(x: float, mu: float, sigma: float) -> float:
    return float(np.exp(-0.5 * ((x - mu) / (sigma + 1e-10)) ** 2))


def _extract_windowed_embeddings(audio: np.ndarray,
                                 window_s: float = 1.5, hop_s: float = 0.5) -> list:
    from computation.voice.features import _extract_embedding

    sr = 16_000
    win_len = int(window_s * sr)
    hop_len = int(hop_s * sr)

    embeddings = []
    pos = 0
    while pos + win_len <= len(audio):
        window = audio[pos: pos + win_len]
        if float(np.sqrt(np.mean(window ** 2))) >= 0.005:
            embeddings.append(_extract_embedding(window))
        pos += hop_len

    if not embeddings:
        embeddings.append(_extract_embedding(audio))

    return embeddings


def _best_sim_windowed(embeddings: list, profile: dict) -> float:
    best = 0.0
    refs = [profile["_embedding_centroid_np"]]
    extra = profile.get("_embeddings_np")
    if extra is not None:
        refs.extend(extra)

    for emb in embeddings:
        for ref in refs:
            s = _cosine_sim(emb, ref)
            if s > best:
                best = s
    return best


def _load_profiles() -> dict:
    from database.canary_db import get_all_users
    profiles = {}
    for u in get_all_users():
        name = u.get("name")
        emb  = u.get("embedding_centroid")
        if not name or not emb:
            continue
        emb_np  = np.array(emb, dtype=np.float32)
        mfcc_np = np.array(u.get("mfcc_mean") or [0.0]*40, dtype=np.float32)
        profiles[name] = {
            "name": name,
            "_embedding_centroid_np": emb_np,
            "_embeddings_np":         emb_np[None, :],
            "_mfcc_centroid_np":      mfcc_np,
            "pitch":       {"mean": float(u.get("pitch_mean")  or 0.0)},
            "energy":      {"mean": float(u.get("energy_mean") or 0.0)},
            "speech_rate": float(u.get("speech_rate") or 0.0),
        }
    return profiles


def _score_against_profile(runtime_feats: dict, profile: dict,
                           is_multi: bool = False) -> dict:
    windowed_embs = runtime_feats.get("_windowed_embeddings")
    if windowed_embs:
        emb_sim = _best_sim_windowed(windowed_embs, profile)
    else:
        emb_rt  = runtime_feats["embedding"]
        emb_sim = _cosine_sim(emb_rt, profile["_embedding_centroid_np"])
        refs = profile.get("_embeddings_np")
        if refs is not None:
            for ref in refs:
                s = _cosine_sim(emb_rt, ref)
                if s > emb_sim:
                    emb_sim = s

    emb_sim = min(float(emb_sim) + 0.10, 1.0)

    pitch_rt  = runtime_feats["pitch"]["mean_pitch"]
    pitch_ref = profile["pitch"]["mean"]
    pitch_sim = _gaussian_sim(pitch_rt, pitch_ref, SIGMA_PITCH)

    energy_rt  = runtime_feats["energy"]["mean_rms"]
    energy_ref = profile["energy"]["mean"]
    energy_sim = _gaussian_sim(energy_rt, energy_ref, SIGMA_ENERGY)

    rate_rt  = runtime_feats["speaking_rate"]["syllables_per_second"]
    rate_ref = profile["speech_rate"]
    rate_sim = _gaussian_sim(rate_rt, rate_ref, SIGMA_RATE)

    mfcc_rt  = runtime_feats["spectral"]["mfcc_mean"]
    mfcc_ref = profile["_mfcc_centroid_np"]
    mfcc_sim = _cosine_sim(mfcc_rt, mfcc_ref)

    final = (
        W_EMBEDDING * emb_sim +
        W_PITCH     * pitch_sim +
        W_ENERGY    * energy_sim +
        W_RATE      * rate_sim +
        W_MFCC      * mfcc_sim
    )

    return {
        "final_score":  round(float(final),      4),
        "embedding":    round(float(emb_sim),    4),
        "pitch":        round(float(pitch_sim),  4),
        "energy":       round(float(energy_sim), 4),
        "speech_rate":  round(float(rate_sim),   4),
        "mfcc":         round(float(mfcc_sim),   4),

        "_pitch_rt":   round(float(pitch_rt),    2),
        "_pitch_ref":  round(float(pitch_ref),   2),
        "_rate_rt":    round(float(rate_rt),     3),
        "_rate_ref":   round(float(rate_ref),    3),
    }


def score_against_all(audio: np.ndarray, sr: int,
                      profiles: dict | None = None,
                      is_multi: bool = False,
                      exclude: set | None = None) -> dict:
    from computation.voice.features import extract

    if profiles is None:
        profiles = _load_profiles()

    if not profiles:
        return {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        runtime_feats = extract(audio, sr)

    from computation.voice.features import _resample_mono
    audio16 = _resample_mono(audio, sr)
    runtime_feats["_windowed_embeddings"] = _extract_windowed_embeddings(audio16)

    results = {}
    for name, profile in profiles.items():
        if exclude and name in exclude:
            continue
        results[name] = _score_against_profile(runtime_feats, profile,
                                               is_multi=is_multi)

    return results


def score_file(wav_path: str | Path,
               profiles: dict | None = None) -> dict:
    audio, sr = sf.read(str(wav_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=-1)
    return score_against_all(audio, sr, profiles=profiles)
