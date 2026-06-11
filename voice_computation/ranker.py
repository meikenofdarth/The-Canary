"""
voice_computation/ranker.py
============================
Score Fusion & Decision Engine for Voice Identity Engine.

Takes raw per-speaker scores from matcher.py and applies:
  1.  Sorting by final_score (descending)
  2.  Margin gate — top score must beat 2nd place by ≥ MARGIN_THRESHOLD
  3.  Floor gate  — top score must be ≥ MIN_CONFIDENCE
  4.  Returns:  {"speaker": "Hemang", "confidence": 0.87}
      or:       {"speaker": "UNKNOWN", "confidence": 0.00}

Public API
----------
  rank(scores: dict) -> dict
      Pure decision logic on pre-computed scores.

  identify(audio, sr) -> dict
      Full pipeline: extract → score → rank.

  identify_speakers(saved_files, out_dir) -> dict[str, dict]
      Batch: identify each speaker file in a run_canary output directory.
      Returns {filename: {"speaker": ..., "confidence": ...}}
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

# Decision thresholds
MIN_CONFIDENCE  = 0.45    # top score must be at least this high
MARGIN_THRESHOLD = 0.15   # top score must beat 2nd place by at least this much


# ─────────────────────────────────────────────────────────────────────────────
#  Decision logic
# ─────────────────────────────────────────────────────────────────────────────

def rank(scores: dict) -> dict:
    """
    Apply margin-based decision logic to produce a final identification result.

    Parameters
    ----------
    scores : dict[str, dict]
        Output of matcher.score_against_all().
        Each value must contain a "final_score" key.

    Returns
    -------
    dict with keys:
        speaker     — identified name or "UNKNOWN"
        confidence  — final_score of top candidate (0.0 if UNKNOWN)
        margin      — gap between 1st and 2nd scores
        scores      — sorted list of (name, score) for all candidates (diagnostic)
        reason      — human-readable decision explanation
    """
    if not scores:
        return {
            "speaker":    "UNKNOWN",
            "confidence": 0.0,
            "margin":     0.0,
            "scores":     [],
            "reason":     "No enrolled speakers found.",
        }

    # Sort descending by final_score
    ranked = sorted(
        [(name, info["final_score"]) for name, info in scores.items()],
        key=lambda x: x[1],
        reverse=True,
    )

    top_name, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin       = top_score - second_score

    # Gate 1: floor confidence
    if top_score < MIN_CONFIDENCE:
        return {
            "speaker":    "UNKNOWN",
            "confidence": round(top_score, 4),
            "margin":     round(margin, 4),
            "scores":     ranked,
            "reason":     f"Top score {top_score:.3f} < minimum confidence {MIN_CONFIDENCE}.",
        }

    # Gate 2: margin check (only when > 1 profile enrolled)
    if len(ranked) > 1 and margin < MARGIN_THRESHOLD:
        return {
            "speaker":    "UNKNOWN",
            "confidence": round(top_score, 4),
            "margin":     round(margin, 4),
            "scores":     ranked,
            "reason": (
                f"Margin {margin:.3f} < threshold {MARGIN_THRESHOLD}. "
                f"Top: {top_name}={top_score:.3f}, "
                f"2nd: {ranked[1][0]}={second_score:.3f}."
            ),
        }

    return {
        "speaker":    top_name,
        "confidence": round(top_score, 4),
        "margin":     round(margin, 4),
        "scores":     ranked,
        "reason":     (
            f"Accepted. Score={top_score:.3f}, margin={margin:.3f} "
            f"(threshold={MARGIN_THRESHOLD})."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Full pipeline helper
# ─────────────────────────────────────────────────────────────────────────────

def identify(audio: np.ndarray, sr: int,
             profiles: dict | None = None) -> dict:
    """
    Full identify pipeline for a single audio buffer.

    Parameters
    ----------
    audio    : np.ndarray
    sr       : int
    profiles : pre-loaded profiles dict (optional, avoids re-loading)

    Returns
    -------
    dict — same format as rank()
    """
    from voice_computation.matcher import score_against_all, _load_profiles

    if profiles is None:
        profiles = _load_profiles()

    if not profiles:
        return {
            "speaker":    "UNKNOWN",
            "confidence": 0.0,
            "margin":     0.0,
            "scores":     [],
            "reason":     "No profiles enrolled. Run add_voicer.py first.",
        }

    scores = score_against_all(audio, sr, profiles=profiles)
    return rank(scores)


def identify_speakers(saved_files: list, out_dir: Path) -> dict:
    """
    Batch-identify all speaker .wav files from a run_canary.py output session.

    Parameters
    ----------
    saved_files : list[str]
        Filenames such as ["speaker_1.wav", "speaker_2.wav"] produced by the pipeline.
    out_dir     : Path
        Session output directory (e.g. outputs/20260611_214500/).

    Returns
    -------
    dict[str, dict]
        {filename: {"speaker": ..., "confidence": ..., "margin": ..., "scores": ..., "reason": ...}}
    """
    from voice_computation.matcher import _load_profiles

    # Load profiles once for the entire batch
    profiles = _load_profiles()
    results  = {}

    for fname in saved_files:
        wav_path = out_dir / fname
        if not wav_path.exists():
            results[fname] = {
                "speaker":    "UNKNOWN",
                "confidence": 0.0,
                "margin":     0.0,
                "scores":     [],
                "reason":     f"File not found: {wav_path}",
            }
            continue

        audio, sr = sf.read(str(wav_path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=-1)

        result        = identify(audio, sr, profiles=profiles)
        results[fname] = result

    return results


# ─────────────────────────────────────────────────────────────────────────────
#  Pretty print utility
# ─────────────────────────────────────────────────────────────────────────────

def print_result(fname: str, result: dict, scores_detail: dict | None = None) -> None:
    """
    Print a nicely formatted identification result to stdout.
    Called from run_canary.py.
    """
    spk  = result["speaker"]
    conf = result["confidence"]
    margin = result["margin"]

    icon = "✓" if spk != "UNKNOWN" else "✗"
    print(f"  {icon}  {fname:<18}  →  {spk:<12}  conf: {conf:.2f}  margin: {margin:.2f}")

    if spk == "UNKNOWN":
        print(f"       reason: {result['reason']}")

    # Detailed score breakdown (optional, verbose mode)
    if scores_detail and spk != "UNKNOWN":
        for ranked_name, ranked_score in result.get("scores", []):
            bar = "█" * int(ranked_score * 20)
            print(f"       {ranked_name:<12} {ranked_score:.3f}  {bar}")
