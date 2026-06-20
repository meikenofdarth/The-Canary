
from __future__ import annotations

import json
import shutil
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

VOICES_ROOT = Path(__file__).parent.parent.parent / "database" / "Voices"
SAMPLE_RATE = 16_000


def _speaker_dir(name: str) -> Path:
    exact = VOICES_ROOT / name
    if exact.exists():
        return exact
    for p in VOICES_ROOT.iterdir():
        if p.is_dir() and p.name.lower() == name.lower():
            return p
    return exact


def _recordings_dir(spk_dir: Path) -> Path:
    rd = spk_dir / "recordings"
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def _features_dir(spk_dir: Path) -> Path:
    fd = spk_dir / "features"
    fd.mkdir(parents=True, exist_ok=True)
    return fd


def _migrate_old_layout(name: str) -> None:
    spk_dir = VOICES_ROOT / name
    if not spk_dir.exists():
        return

    top_wavs = [f for f in spk_dir.glob("*.wav") if f.is_file()]
    if not top_wavs:
        return

    rec_dir = _recordings_dir(spk_dir)
    for idx, wav in enumerate(sorted(top_wavs), start=1):
        dest = rec_dir / f"sample_{idx}.wav"
        if dest.exists():
            continue
        shutil.move(str(wav), str(dest))
        print(f"  [enroll] Migrated {wav.name} → recordings/sample_{idx}.wav")


def enroll_speaker(name: str, audio_paths: list) -> dict:
    from computation.voice.features import extract

    name_clean = name.strip()
    spk_dir    = VOICES_ROOT / name_clean
    spk_dir.mkdir(parents=True, exist_ok=True)

    _migrate_old_layout(name_clean)

    rec_dir  = _recordings_dir(spk_dir)
    feat_dir = _features_dir(spk_dir)

    for idx, src_path in enumerate(audio_paths, start=1):
        src = Path(src_path)
        dst = rec_dir / f"sample_{idx}.wav"
        if src.resolve() != dst.resolve():
            shutil.copy2(str(src), str(dst))
            print(f"  [enroll] Saved recording {idx} → {dst.name}")

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

    emb_arr     = np.array(embeddings, dtype=np.float32)
    emb_centroid = emb_arr.mean(axis=0)
    emb_norm     = np.linalg.norm(emb_centroid) + 1e-10
    emb_centroid = (emb_centroid / emb_norm).astype(np.float32)

    pitch_arr = np.array(pitches,    dtype=np.float32)
    energy_arr = np.array(energies,  dtype=np.float32)
    mfcc_mean_arr = np.array(mfcc_means, dtype=np.float32)
    mfcc_std_arr  = np.array(mfcc_stds,  dtype=np.float32)

    np.save(str(feat_dir / "embeddings.npy"),  emb_arr)
    np.save(str(feat_dir / "embedding_centroid.npy"), emb_centroid)
    np.save(str(feat_dir / "pitch.npy"),       pitch_arr)
    np.save(str(feat_dir / "energy.npy"),      energy_arr)
    np.save(str(feat_dir / "mfcc_mean.npy"),   mfcc_mean_arr)
    np.save(str(feat_dir / "mfcc_std.npy"),    mfcc_std_arr)

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

        "mfcc_centroid": mfcc_mean_arr.mean(axis=0).tolist(),
    }

    with open(feat_dir / "stats.json", "w") as fh:
        json.dump(stats, fh, indent=2)

    profile = {
        "name":           name_clean,
        "recording_count": len(all_recs),
        "recordings":     [r.name for r in all_recs],

        "embedding_centroid": emb_centroid.tolist(),

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

        "mfcc_mean": stats["mfcc_centroid"],

        "spectral": {
            "centroid":  stats["spectral_centroid_mean"],
            "bandwidth": stats["spectral_bandwidth_mean"],
        },
    }

    with open(spk_dir / "profile.json", "w") as fh:
        json.dump(profile, fh, indent=2)

    print(f"  [enroll] ✓ Profile saved → {spk_dir / 'profile.json'}")

    try:
        from database.canary_db import upsert_user
        speaker_id = upsert_user(name_clean, profile)
        print(f"  [enroll] ✓ DB synced → speaker_id={speaker_id}")
    except Exception as db_err:
        print(f"  [enroll] ⚠ DB sync failed (non-fatal): {db_err}")

    return profile


def get_profile(name: str) -> Optional[dict]:
    spk_dir     = _speaker_dir(name)
    profile_path = spk_dir / "profile.json"
    if not profile_path.exists():
        return None
    with open(profile_path) as fh:
        return json.load(fh)


def list_enrolled() -> list:
    try:
        from database.canary_db import list_enrolled as db_list_enrolled
        db_names = db_list_enrolled()
        if db_names:
            return db_names
    except Exception:
        pass

    if not VOICES_ROOT.exists():
        return []
    names = []
    for d in sorted(VOICES_ROOT.iterdir()):
        if d.is_dir() and (d / "profile.json").exists():
            names.append(d.name)
    return names


def get_profile_from_db(name: str) -> Optional[dict]:
    try:
        from database.canary_db import get_user
        return get_user(name)
    except Exception:
        return None


def rebuild_all_profiles() -> None:
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
        enroll_speaker(spk_dir.name, [])
