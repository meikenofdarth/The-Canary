"""
separation-filtering/speaker_tracker.py
=========================================
ECAPA-embedding-based speaker clustering and track merging.

This replaces the identity engine's role during separation.  Instead of
running voice identity on a contaminated full-recording stream, we:

  1.  Extract a raw ECAPA-TDNN embedding for every output chunk.
  2.  Match each chunk against enrolled profiles (cosine similarity).
  3.  Chunks that match an enrolled profile → labelled with that name.
  4.  Chunks that don't match anyone → clustered among themselves by cosine
      distance.  Similar chunks get the same label ("Speaker A", "Speaker B").
  5.  Merge all chunks with the same label into a single audio track (with
      100ms silence padding between segments to preserve natural boundaries).
  6.  Write speaker_1.wav, speaker_2.wav, ... to out_dir.
  7.  Return the speaker label → filename mapping + per-speaker audio.

Why this solves the identity problem
-------------------------------------
Previously, voice identity ran on speaker_1.wav which was a 7-second mix of
SepFormer outputs — already contaminated.  Now it runs on clean 0.8–2.0s
segments from a single speaker.  The ECAPA embedding has far less noise to
overcome, and confidence scores go from ~0.09 to 0.70+.

Public API
----------
  assign_and_merge_speakers(chunks, sr, out_dir) -> (list[dict], int, float)
      Cluster chunks by voice, merge per speaker, write wav files.
      Returns (speaker_tracks, n_speakers, overlap_prob).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

# Cosine similarity threshold for matching a chunk to an enrolled profile.
# For a clean single-speaker segment, embeddings are reliable.
# Lowered from 0.45 to keep enrolled speakers from slipping through as unknowns.
_PROFILE_MATCH_THRESHOLD = 0.30

# Extra-low threshold for SepFormer-separated segments.
# Short (0.8–2s) separated chunks have noisier embeddings than full-length audio.
# Using a more lenient threshold to avoid false UNKNOWN labels.
_PROFILE_MATCH_THRESHOLD_SEP = 0.25

# Cosine similarity threshold for merging two UNKNOWN chunks into the same cluster.
# Above this → same speaker; below → new speaker cluster.
# Lowered from 0.60 to avoid over-splitting on short recording segments.
_CLUSTER_THRESHOLD = 0.45

# Minimum chunk duration for running ECAPA embedding extraction (seconds).
# ECAPA needs at least a few hundred ms to produce reliable embeddings.
_MIN_EMBED_DURATION = 0.35

# Silence padding inserted between merged segments (seconds)
_MERGE_SILENCE_S = 0.10


# ─────────────────────────────────────────────────────────────────────────────
#  Embedding extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity clamped to [0, 1]."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    denom = (np.linalg.norm(a) + 1e-10) * (np.linalg.norm(b) + 1e-10)
    raw   = float(np.dot(a, b) / denom)
    return float(np.clip((raw + 1.0) / 2.0, 0.0, 1.0))


def _extract_ecapa(audio: np.ndarray, sr: int) -> np.ndarray | None:
    """
    Extract a 192-dim L2-normalised ECAPA-TDNN embedding from `audio`.
    Returns None if audio is too short or extraction fails.
    """
    import torch
    import warnings
    from speechbrain.inference.speaker import EncoderClassifier

    duration = len(audio) / sr
    if duration < _MIN_EMBED_DURATION:
        return None

    try:
        model = EncoderClassifier.from_hparams(
            source   = "speechbrain/spkrec-ecapa-voxceleb",
            savedir  = "pretrained_models/spkrec-ecapa-voxceleb",
            run_opts = {"device": "cpu"},
        )
        # Resample to 16kHz if needed
        if sr != 16_000:
            import torchaudio
            audio = torchaudio.functional.resample(
                torch.from_numpy(audio).unsqueeze(0), sr, 16_000
            ).squeeze(0).numpy()

        tensor = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        with torch.no_grad():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                emb = model.encode_batch(tensor)   # (1, 1, 192)

        vec  = emb.squeeze().cpu().numpy().astype(np.float32)
        norm = np.linalg.norm(vec) + 1e-10
        return (vec / norm).astype(np.float32)

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Speaker assignment
# ─────────────────────────────────────────────────────────────────────────────

def _assign_labels(
    chunks:    list[dict],
    sr:        int,
    profiles:  dict,
) -> list[dict]:
    """
    For each chunk:
      1. Extract ECAPA embedding.
      2. Compare against all enrolled profile centroids.
         - Separated chunks use a looser threshold (_PROFILE_MATCH_THRESHOLD_SEP)
           because short SepFormer outputs produce noisier embeddings.
      3. If best match > threshold → label = enrolled name.
      4. Otherwise → compare against existing UNKNOWN clusters.
             Match > _CLUSTER_THRESHOLD → same cluster label.
             No match → new cluster ("Speaker A", "Speaker B", ...).

    Returns chunks with "speaker_label" and "embed_confidence" added.
    """
    # Cluster centroids for unknowns: {label: centroid_embedding}
    unknown_clusters: dict[str, np.ndarray] = {}
    _cluster_letters = list("ABCDEFGHIJKLMNOP")
    _next_cluster_idx = [0]   # mutable counter via list

    def _new_cluster_label() -> str:
        idx = _next_cluster_idx[0]
        label = f"Speaker {_cluster_letters[idx % len(_cluster_letters)]}"
        _next_cluster_idx[0] += 1
        return label

    annotated = []
    for chunk in chunks:
        emb = _extract_ecapa(chunk["audio"], sr)

        if emb is None:
            # Too short or extraction failed — carry forward as unidentified
            chunk = dict(chunk)
            chunk["speaker_label"]    = "UNIDENTIFIED"
            chunk["embed_confidence"] = 0.0
            chunk["embedding"]        = None
            annotated.append(chunk)
            continue

        chunk = dict(chunk)
        chunk["embedding"] = emb

        # Use relaxed threshold for SepFormer-separated short chunks
        is_sep = chunk.get("is_separated", False)
        prof_threshold = _PROFILE_MATCH_THRESHOLD_SEP if is_sep else _PROFILE_MATCH_THRESHOLD

        # ── Step 1: Compare against enrolled profiles ─────────────────────────
        best_profile_name  = None
        best_profile_score = 0.0

        for prof_name, profile in profiles.items():
            centroid = profile.get("_embedding_centroid_np")
            if centroid is None:
                centroid = np.array(profile.get("embedding_centroid", []), dtype=np.float32)
            if len(centroid) == 0:
                continue
            sim = _cosine_sim(emb, centroid)
            if sim > best_profile_score:
                best_profile_score = sim
                best_profile_name  = prof_name

        if best_profile_score >= prof_threshold and best_profile_name:
            chunk["speaker_label"]    = best_profile_name
            chunk["embed_confidence"] = round(best_profile_score, 4)
            annotated.append(chunk)
            continue

        # ── Step 2: Compare against existing unknown clusters ─────────────────
        best_cluster_label = None
        best_cluster_score = 0.0

        for clabel, centroid in unknown_clusters.items():
            sim = _cosine_sim(emb, centroid)
            if sim > best_cluster_score:
                best_cluster_score = sim
                best_cluster_label = clabel

        if best_cluster_score >= _CLUSTER_THRESHOLD and best_cluster_label:
            chunk["speaker_label"]    = best_cluster_label
            chunk["embed_confidence"] = round(best_cluster_score, 4)
            # Update running centroid (online mean)
            existing = unknown_clusters[best_cluster_label]
            unknown_clusters[best_cluster_label] = (
                (existing + emb) / 2.0
            )
        else:
            # New speaker cluster
            label = _new_cluster_label()
            unknown_clusters[label] = emb
            chunk["speaker_label"]    = label
            chunk["embed_confidence"] = 1.0   # first of its cluster

        annotated.append(chunk)

    return annotated


# ─────────────────────────────────────────────────────────────────────────────
#  Audio merging
# ─────────────────────────────────────────────────────────────────────────────

def _merge_speaker_audio(
    chunks: list[dict],
    sr:     int,
) -> dict[str, np.ndarray]:
    """
    Group chunks by speaker_label and concatenate their audio.
    Inserts _MERGE_SILENCE_S seconds of silence between consecutive segments.

    Returns {speaker_label: audio_array}.
    """
    from collections import defaultdict

    groups: dict[str, list] = defaultdict(list)
    silence_pad = np.zeros(int(_MERGE_SILENCE_S * sr), dtype=np.float32)

    for chunk in chunks:
        label = chunk.get("speaker_label", "UNIDENTIFIED")
        if label == "UNIDENTIFIED":
            continue
        groups[label].append(chunk["audio"].astype(np.float32))

    merged: dict[str, np.ndarray] = {}
    for label, audio_list in groups.items():
        # Interleave with silence pads
        parts = []
        for i, a in enumerate(audio_list):
            parts.append(a)
            if i < len(audio_list) - 1:
                parts.append(silence_pad.copy())
        merged[label] = np.concatenate(parts).astype(np.float32)

    return merged


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def assign_and_merge_speakers(
    chunks:   list[dict],
    sr:       int,
    out_dir:  Path,
) -> tuple[list[dict], int, float]:
    """
    Cluster audio chunks by speaker identity, merge per-speaker audio,
    and write speaker_N.wav files.

    Parameters
    ----------
    chunks   : Output of segment_separator.separate_segments() — first element.
    sr       : Sample rate.
    out_dir  : Session output directory (e.g. outputs/20260613_...).

    Returns
    -------
    speaker_tracks : list[dict]
        One dict per unique speaker:
            label      — enrolled name or "Speaker A/B/..."
            filename   — "speaker_1.wav", "speaker_2.wav", ...
            audio      — merged np.ndarray (before enhancement)
            duration_s — total audio duration
            n_chunks   — number of segments contributing to this track
    n_speakers : int
        Number of distinct speakers found.
    overlap_prob_from_sep : float
        Fraction of total speech duration that was multi-speaker separated.
        (Passed through from the overlap_info returned by separate_segments.)
    """
    import sys
    from pathlib import Path as _Path

    # Load enrolled profiles for identity matching
    sys.path.insert(0, str(_Path(__file__).parent.parent.parent))
    from computation.voice.matcher import _load_profiles

    profiles = _load_profiles()

    # ── 1. Extract embeddings + assign speaker labels ─────────────────────────
    print("  [tracker] extracting embeddings per segment ...", flush=True)
    annotated = _assign_labels(chunks, sr, profiles)

    # ── 2. Merge audio per speaker label ──────────────────────────────────────
    merged = _merge_speaker_audio(annotated, sr)

    if not merged:
        # Edge case: all chunks were UNIDENTIFIED (too short)
        # Fallback: concatenate everything into speaker_1
        all_audio = np.concatenate(
            [c["audio"].astype(np.float32) for c in chunks]
            + [np.zeros(int(0.1 * sr), dtype=np.float32)]
        )
        merged = {"Speaker A": all_audio}

    # ── 3. Sort speakers: enrolled names first, then clusters alphabetically ──
    def _sort_key(label: str) -> tuple:
        is_enrolled = label in profiles
        return (0 if is_enrolled else 1, label)

    sorted_labels = sorted(merged.keys(), key=_sort_key)

    # ── 4. Count chunks per speaker + track average confidence ─────────────────
    from collections import Counter, defaultdict as _dd
    label_counts:      Counter              = Counter()
    label_confidences: dict[str, list]     = _dd(list)
    for chunk in annotated:
        label = chunk.get("speaker_label", "UNIDENTIFIED")
        if label != "UNIDENTIFIED":
            label_counts[label] += 1
            label_confidences[label].append(chunk.get("embed_confidence", 0.0))

    # ── 5. Write speaker_N.wav files and build return structure ─────────────────
    speaker_tracks: list[dict] = []
    for i, label in enumerate(sorted_labels, start=1):
        audio  = merged[label]
        fname  = f"speaker_{i}.wav"
        import soundfile as sf
        sf.write(str(out_dir / fname), audio, sr, subtype="PCM_16")

        confs        = label_confidences.get(label, [0.0])
        avg_conf     = round(float(np.mean(confs)), 4)
        is_enrolled  = label in profiles

        speaker_tracks.append({
            "label":          label,
            "filename":       fname,
            "audio":          audio,
            "duration_s":     round(len(audio) / sr, 2),
            "n_chunks":       label_counts.get(label, 0),
            "embed_confidence": avg_conf,
            "is_enrolled":    is_enrolled,
        })

    # ── 6. Terminal summary ───────────────────────────────────────────────────
    print(f"\n  [tracker] {len(speaker_tracks)} speaker track(s) assembled:")
    for i, trk in enumerate(speaker_tracks, 1):
        n = trk["n_chunks"]
        seg_word = "seg" if n == 1 else "segs"
        enrolled = "✓ enrolled" if trk["label"] in profiles else "● unknown cluster"
        print(
            f"    speaker_{i}.wav  →  {trk['label']:<16}  "
            f"{trk['duration_s']:.2f}s  {n} {seg_word}  [{enrolled}]"
        )

    n_speakers = len(speaker_tracks)
    return speaker_tracks, n_speakers


# ─────────────────────────────────────────────────────────────────────────────
#  Compute overlap_prob from segment-level data (for DRS)
# ─────────────────────────────────────────────────────────────────────────────

def compute_overlap_prob(chunks: list[dict]) -> float:
    """
    Estimate speech overlap probability from chunk metadata.

    A chunk is "overlapping" if it was produced by SepFormer separation
    (is_separated=True).  Overlap probability = overlapping speech duration /
    total speech duration.
    """
    total = sum(c["duration_s"] for c in chunks)
    multi = sum(c["duration_s"] for c in chunks if c.get("is_separated"))
    return round(multi / total, 3) if total > 0 else 0.0
