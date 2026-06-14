"""
voice_computation/enroll.py
============================
Speaker Enrollment Engine for Voice Identity Engine.

Given a speaker name and a list of audio file paths, this module:
  1.  Migrates old flat-file layouts  (Voices/name/name.wav → recordings/sample_1.wav)
  2.  Extracts all 5 feature groups from every recording
  3.  Computes per-feature statistics and centroid embedding
  4.  Writes:
        Voices/<Name>/profile.json
        Voices/<Name>/features/embeddings.npy   — (N, 192) all embeddings
        Voices/<Name>/features/pitch.npy        — (N, 4) per-recording pitch stats
        Voices/<Name>/features/energy.npy       — (N, 2) per-recording energy stats
        Voices/<Name>/features/mfcc_mean.npy    — (N, 40) per-recording MFCC means
        Voices/<Name>/features/stats.json       — aggregated scalar statistics

Public API
----------
  enroll_speaker(name: str, audio_paths: list[str | Path]) -> dict
      Returns the completed profile dict.

  get_profile(name: str) -> dict | None
      Load an existing profile from disk. Returns None if not enrolled.

  list_enrolled() -> list[str]
      Returns names of all enrolled speakers.
"""

from __future__ import annotations

import json
import shutil
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

# Ensure project root is importable so database.canary_db can be found
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

VOICES_ROOT = Path(__file__).parent.parent.parent / "database" / "Voices"
SAMPLE_RATE = 16_000


# ─────────────────────────────────────────────────────────────────────────────
#  Folder helpers
# ─────────────────────────────────────────────────────────────────────────────

def _speaker_dir(name: str) -> Path:
    """Canonical speaker directory (case-preserving, lookup is case-insensitive)."""
    # First: look for an exact match
    exact = VOICES_ROOT / name
    if exact.exists():
        return exact
    # Second: case-insensitive scan
    for p in VOICES_ROOT.iterdir():
        if p.is_dir() and p.name.lower() == name.lower():
            return p
    # Third: create new
    return exact


def _recordings_dir(spk_dir: Path) -> Path:
    rd = spk_dir / "recordings"
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def _features_dir(spk_dir: Path) -> Path:
    fd = spk_dir / "features"
    fd.mkdir(parents=True, exist_ok=True)
    return fd


# ─────────────────────────────────────────────────────────────────────────────
#  Migration  —  old flat layout → new recordings/ layout
# ─────────────────────────────────────────────────────────────────────────────

def _migrate_old_layout(name: str) -> None:
    """
    If a speaker folder contains a top-level .wav file (old layout),
    move it to recordings/sample_1.wav so the new system can process it.

    Old:  Voices/hemang/hemang.wav
    New:  Voices/hemang/recordings/sample_1.wav
    """
    spk_dir = VOICES_ROOT / name
    if not spk_dir.exists():
        return

    # Find .wav files directly under the speaker directory (not in subdirs)
    top_wavs = [f for f in spk_dir.glob("*.wav") if f.is_file()]
    if not top_wavs:
        return

    rec_dir = _recordings_dir(spk_dir)
    for idx, wav in enumerate(sorted(top_wavs), start=1):
        dest = rec_dir / f"sample_{idx}.wav"
        if dest.exists():
            continue   # already migrated
        shutil.move(str(wav), str(dest))
        print(f"  [enroll] Migrated {wav.name} → recordings/sample_{idx}.wav")


# ─────────────────────────────────────────────────────────────────────────────
#  Core enrollment
# ─────────────────────────────────────────────────────────────────────────────

def enroll_speaker(name: str, audio_paths: list) -> dict:
    """
    Enroll or re-enroll a speaker.

    Parameters
    ----------
    name        : str
        Speaker display name (e.g. "Hemang"). Used as folder name.
    audio_paths : list of str or Path
        Paths to enrollment recordings (1–5 supported, 3 recommended).

    Returns
    -------
    dict
        Completed profile dict (also written to disk).
    """
    from computation.voice.features import extract

    name_clean = name.strip()
    spk_dir    = VOICES_ROOT / name_clean
    spk_dir.mkdir(parents=True, exist_ok=True)

    # Migrate old flat recordings if present
    _migrate_old_layout(name_clean)

    rec_dir  = _recordings_dir(spk_dir)
    feat_dir = _features_dir(spk_dir)

    # Copy provided audio files into recordings/ if they are not already there
    for idx, src_path in enumerate(audio_paths, start=1):
        src = Path(src_path)
        dst = rec_dir / f"sample_{idx}.wav"
        if src.resolve() != dst.resolve():
            shutil.copy2(str(src), str(dst))
            print(f"  [enroll] Saved recording {idx} → {dst.name}")

    # Collect all recordings (existing + new)
    all_recs = sorted(rec_dir.glob("sample_*.wav"))
    if not all_recs:
        raise FileNotFoundError(f"No recordings found for '{name_clean}' in {rec_dir}")

    print(f"\n  [enroll] Building profile for '{name_clean}' from {len(all_recs)} recording(s) ...")

    embeddings = []
    pitches    = []
    energies   = []
    rates      = []
    mfcc_means = []
    mfcc_stds  = []
    centroids  = []
    bandwidths = []

    for rec in all_recs:
        print(f"  [enroll] Processing {rec.name} ...")
        audio, sr = sf.read(str(rec), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=-1)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            feats = extract(audio, sr)

        embeddings.append(feats["embedding"])
        pitches.append([
            feats["pitch"]["mean_pitch"],
            feats["pitch"]["std_pitch"],
            feats["pitch"]["min_pitch"],
            feats["pitch"]["max_pitch"],
        ])
        energies.append([
            feats["energy"]["mean_rms"],
            feats["energy"]["std_rms"],
        ])
        rates.append(feats["speaking_rate"]["syllables_per_second"])
        mfcc_means.append(feats["spectral"]["mfcc_mean"])
        mfcc_stds.append(feats["spectral"]["mfcc_std"])
        centroids.append(feats["spectral"]["centroid"])
        bandwidths.append(feats["spectral"]["bandwidth"])

    # ── Compute centroid embedding (mean of all, re-normalised) ───────────
    emb_arr     = np.array(embeddings, dtype=np.float32)   # (N, 192)
    emb_centroid = emb_arr.mean(axis=0)
    emb_norm     = np.linalg.norm(emb_centroid) + 1e-10
    emb_centroid = (emb_centroid / emb_norm).astype(np.float32)

    pitch_arr = np.array(pitches,    dtype=np.float32)     # (N, 4)
    energy_arr = np.array(energies,  dtype=np.float32)     # (N, 2)
    mfcc_mean_arr = np.array(mfcc_means, dtype=np.float32) # (N, 40)
    mfcc_std_arr  = np.array(mfcc_stds,  dtype=np.float32) # (N, 40)

    # ── Write numpy arrays ────────────────────────────────────────────────
    np.save(str(feat_dir / "embeddings.npy"),  emb_arr)
    np.save(str(feat_dir / "embedding_centroid.npy"), emb_centroid)
    np.save(str(feat_dir / "pitch.npy"),       pitch_arr)
    np.save(str(feat_dir / "energy.npy"),      energy_arr)
    np.save(str(feat_dir / "mfcc_mean.npy"),   mfcc_mean_arr)
    np.save(str(feat_dir / "mfcc_std.npy"),    mfcc_std_arr)

    # ── Aggregated scalar stats ───────────────────────────────────────────
    stats = {
        "pitch_mean": float(np.mean(pitch_arr[:, 0])),
        "pitch_std":  float(np.mean(pitch_arr[:, 1])),
        "pitch_min":  float(np.min(pitch_arr[:, 2])),
        "pitch_max":  float(np.max(pitch_arr[:, 3])),

        "energy_mean": float(np.mean(energy_arr[:, 0])),
        "energy_std":  float(np.mean(energy_arr[:, 1])),

        "speech_rate_mean": float(np.mean(rates)),
        "speech_rate_std":  float(np.std(rates)),

        "spectral_centroid_mean": float(np.mean(centroids)),
        "spectral_bandwidth_mean": float(np.mean(bandwidths)),

        "mfcc_centroid": mfcc_mean_arr.mean(axis=0).tolist(),    # list[40]
    }

    with open(feat_dir / "stats.json", "w") as fh:
        json.dump(stats, fh, indent=2)

    # ── Master profile.json ───────────────────────────────────────────────
    profile = {
        "name":           name_clean,
        "recording_count": len(all_recs),
        "recordings":     [r.name for r in all_recs],

        "embedding_centroid": emb_centroid.tolist(),   # 192 floats

        "pitch": {
            "mean": stats["pitch_mean"],
            "std":  stats["pitch_std"],
            "min":  stats["pitch_min"],
            "max":  stats["pitch_max"],
        },

        "energy": {
            "mean": stats["energy_mean"],
            "std":  stats["energy_std"],
        },

        "speech_rate": stats["speech_rate_mean"],

        "mfcc_mean": stats["mfcc_centroid"],           # list[40]

        "spectral": {
            "centroid":  stats["spectral_centroid_mean"],
            "bandwidth": stats["spectral_bandwidth_mean"],
        },
    }

    with open(spk_dir / "profile.json", "w") as fh:
        json.dump(profile, fh, indent=2)

    print(f"  [enroll] ✓ Profile saved → {spk_dir / 'profile.json'}")

    # ── Sync to SQLite DB ─────────────────────────────────────────────────
    try:
        from database.canary_db import upsert_user
        speaker_id = upsert_user(name_clean, profile)
        print(f"  [enroll] ✓ DB synced → speaker_id={speaker_id}")
    except Exception as db_err:
        # Non-fatal: disk files are the authoritative source for the matcher
        print(f"  [enroll] ⚠ DB sync failed (non-fatal): {db_err}")

    return profile


# ─────────────────────────────────────────────────────────────────────────────
#  Profile I/O helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_profile(name: str) -> Optional[dict]:
    """
    Load an existing speaker profile from disk.

    Returns None if the speaker is not enrolled or profile.json is missing.
    """
    spk_dir     = _speaker_dir(name)
    profile_path = spk_dir / "profile.json"
    if not profile_path.exists():
        return None
    with open(profile_path) as fh:
        return json.load(fh)


def list_enrolled() -> list:
    """
    Return names of all enrolled speakers.
    Uses database.canary_db as the primary source; falls back to disk scan if DB is empty.
    """
    # Primary: DB
    try:
        from database.canary_db import list_enrolled as db_list_enrolled
        db_names = db_list_enrolled()
        if db_names:
            return db_names
    except Exception:
        pass

    # Fallback: disk scan (those with a profile.json)
    if not VOICES_ROOT.exists():
        return []
    names = []
    for d in sorted(VOICES_ROOT.iterdir()):
        if d.is_dir() and (d / "profile.json").exists():
            names.append(d.name)
    return names


def get_profile_from_db(name: str) -> Optional[dict]:
    """
    Load a speaker profile from canary.db.
    Returns None if the user is not found or the DB is unavailable.
    """
    try:
        from database.canary_db import get_user
        return get_user(name)
    except Exception:
        return None


def rebuild_all_profiles() -> None:
    """
    Utility: re-extract features and rebuild profile.json for every speaker
    that has at least one recording in recordings/.

    Useful after upgrading the feature extractor or changing model weights.
    """
    if not VOICES_ROOT.exists():
        print("[enroll] Voices/ directory not found.")
        return

    for spk_dir in sorted(VOICES_ROOT.iterdir()):
        if not spk_dir.is_dir():
            continue
        _migrate_old_layout(spk_dir.name)
        rec_dir = spk_dir / "recordings"
        if not rec_dir.exists():
            continue
        recs = sorted(rec_dir.glob("sample_*.wav"))
        if not recs:
            continue
        print(f"\n[enroll] Rebuilding profile for '{spk_dir.name}' ...")
        enroll_speaker(spk_dir.name, [])   # audio_paths=[] → use existing
