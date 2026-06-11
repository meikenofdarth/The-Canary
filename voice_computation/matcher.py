"""
voice_computation/matcher.py
=============================
Runtime Feature Matcher for Voice Identity Engine.

Given a runtime audio buffer, extracts the same 5 feature groups used during
enrollment and computes a weighted similarity score against every enrolled
speaker profile.

Similarity methods per group:

  Group A  Embedding   — cosine similarity          (range [−1, 1] → clamped [0, 1])
  Group B  Pitch       — Gaussian-kernel similarity  (penalises large mean-pitch diff)
  Group C  Energy      — Gaussian-kernel similarity  (on mean RMS)
  Group D  Speech rate — Gaussian-kernel similarity  (on syllables/sec)
  Group E  MFCC        — cosine similarity on centroid vector

Final weighted score:
    score = 0.60 * emb_sim
          + 0.15 * pitch_sim
          + 0.10 * energy_sim
          + 0.10 * rate_sim
          + 0.05 * mfcc_sim

Public API
----------
  score_against_all(audio, sr) -> dict[str, dict]
      Returns per-speaker scores + component breakdown.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf

VOICES_ROOT = Path(__file__).parent.parent / "Voices"

# Fusion weights
W_EMBEDDING = 0.60
W_PITCH     = 0.15
W_ENERGY    = 0.10
W_RATE      = 0.10
W_MFCC      = 0.05

# Gaussian kernel widths (σ) — tuned to typical inter-speaker ranges
SIGMA_PITCH  = 25.0    # Hz   — ~2 semitones for typical inter-speaker pitch diff
SIGMA_ENERGY = 0.08    # RMS  — empirically ~0.05–0.10 between speakers
SIGMA_RATE   = 1.2     # syl/sec — typical ±1 syl/sec between speakers


# ─────────────────────────────────────────────────────────────────────────────
#  Similarity primitives
# ─────────────────────────────────────────────────────────────────────────────

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity clamped to [0, 1]."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    denom = (np.linalg.norm(a) + 1e-10) * (np.linalg.norm(b) + 1e-10)
    raw   = float(np.dot(a, b) / denom)
    return float(np.clip((raw + 1.0) / 2.0, 0.0, 1.0))


def _gaussian_sim(x: float, mu: float, sigma: float) -> float:
    """
    Gaussian-kernel similarity: 1.0 when x == mu, falls off symmetrically.
    Never goes below 0.
    """
    return float(np.exp(-0.5 * ((x - mu) / (sigma + 1e-10)) ** 2))


# ─────────────────────────────────────────────────────────────────────────────
#  Profile loader with numpy array re-hydration
# ─────────────────────────────────────────────────────────────────────────────

def _load_profiles() -> dict:
    """
    Load all enrolled speaker profiles.

    Returns dict: {name: profile_dict}
    Embedding centroid is loaded from features/ as np.ndarray for speed.
    """
    profiles = {}
    if not VOICES_ROOT.exists():
        return profiles

    for spk_dir in sorted(VOICES_ROOT.iterdir()):
        if not spk_dir.is_dir():
            continue
        pfile = spk_dir / "profile.json"
        if not pfile.exists():
            continue
        with open(pfile) as fh:
            p = json.load(fh)

        # Prefer loading centroid embedding from .npy for numerical precision
        npy_centroid = spk_dir / "features" / "embedding_centroid.npy"
        if npy_centroid.exists():
            p["_embedding_centroid_np"] = np.load(str(npy_centroid))
        else:
            p["_embedding_centroid_np"] = np.array(
                p["embedding_centroid"], dtype=np.float32)

        # Also load MFCC centroid from npy if available
        npy_mfcc = spk_dir / "features" / "mfcc_mean.npy"
        if npy_mfcc.exists():
            p["_mfcc_centroid_np"] = np.load(str(npy_mfcc)).mean(axis=0)
        else:
            p["_mfcc_centroid_np"] = np.array(
                p.get("mfcc_mean", [0.0] * 40), dtype=np.float32)

        profiles[p["name"]] = p

    return profiles


# ─────────────────────────────────────────────────────────────────────────────
#  Per-speaker scoring
# ─────────────────────────────────────────────────────────────────────────────

def _score_against_profile(runtime_feats: dict, profile: dict) -> dict:
    """
    Compute weighted similarity between runtime features and one profile.

    Returns a component breakdown dict + final_score.
    """
    # A — Embedding
    emb_rt  = runtime_feats["embedding"]
    emb_ref = profile["_embedding_centroid_np"]
    emb_sim = _cosine_sim(emb_rt, emb_ref)

    # B — Pitch (compare mean pitch only)
    pitch_rt  = runtime_feats["pitch"]["mean_pitch"]
    pitch_ref = profile["pitch"]["mean"]
    pitch_sim = _gaussian_sim(pitch_rt, pitch_ref, SIGMA_PITCH)

    # C — Energy
    energy_rt  = runtime_feats["energy"]["mean_rms"]
    energy_ref = profile["energy"]["mean"]
    energy_sim = _gaussian_sim(energy_rt, energy_ref, SIGMA_ENERGY)

    # D — Speaking rate
    rate_rt  = runtime_feats["speaking_rate"]["syllables_per_second"]
    rate_ref = profile["speech_rate"]
    rate_sim = _gaussian_sim(rate_rt, rate_ref, SIGMA_RATE)

    # E — MFCC centroid cosine
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

        # Raw values for diagnostics
        "_pitch_rt":   round(float(pitch_rt),    2),
        "_pitch_ref":  round(float(pitch_ref),   2),
        "_rate_rt":    round(float(rate_rt),     3),
        "_rate_ref":   round(float(rate_ref),    3),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def score_against_all(audio: np.ndarray, sr: int,
                      profiles: dict | None = None) -> dict:
    """
    Extract features from runtime audio and score against every enrolled
    speaker profile.

    Parameters
    ----------
    audio    : np.ndarray   raw audio samples
    sr       : int          sample rate of audio
    profiles : dict | None  pre-loaded profiles (pass to avoid re-loading in loops)

    Returns
    -------
    dict[str, dict]
        Keyed by speaker name. Each value contains:
            final_score  — weighted similarity score [0, 1]
            embedding    — component score [0, 1]
            pitch        — component score [0, 1]
            energy       — component score [0, 1]
            speech_rate  — component score [0, 1]
            mfcc         — component score [0, 1]
            _pitch_rt    — runtime pitch (Hz)  [diagnostic]
            _pitch_ref   — profile pitch (Hz)  [diagnostic]
            _rate_rt     — runtime speaking rate [diagnostic]
            _rate_ref    — profile speaking rate [diagnostic]
    """
    from voice_computation.features import extract

    if profiles is None:
        profiles = _load_profiles()

    if not profiles:
        return {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        runtime_feats = extract(audio, sr)

    results = {}
    for name, profile in profiles.items():
        results[name] = _score_against_profile(runtime_feats, profile)

    return results


def score_file(wav_path: str | Path,
               profiles: dict | None = None) -> dict:
    """
    Convenience wrapper: load a .wav file and score against all profiles.
    """
    audio, sr = sf.read(str(wav_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=-1)
    return score_against_all(audio, sr, profiles=profiles)
