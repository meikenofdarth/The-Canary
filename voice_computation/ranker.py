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


def si_snr(estimate: np.ndarray, reference: np.ndarray) -> float:
    """
    Scale-Invariant Signal-to-Noise Ratio (dB).
    Measures how well `estimate` reconstructs `reference`.
    """
    ref = reference.astype(np.float64) - np.mean(reference)
    est = estimate.astype(np.float64)  - np.mean(estimate)
    alpha  = np.dot(est, ref) / (np.dot(ref, ref) + 1e-10)
    target = alpha * ref
    noise  = est - target
    return float(10.0 * np.log10(
        (np.dot(target, target) + 1e-10) / (np.dot(noise, noise) + 1e-10)
    ))


def _calc_speech_ratio(audio: np.ndarray, sr: int) -> float:
    frame_len = max(1, int(sr * 0.030))
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        return 0.0
    frame_rms = np.array([
        np.sqrt(np.mean(audio[i * frame_len:(i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    noise_floor = float(np.percentile(frame_rms, 10)) + 1e-10
    voiced_frames = frame_rms > noise_floor * 3.0
    return float(np.sum(voiced_frames) / n_frames)


def _calc_energy_consistency(audio: np.ndarray, sr: int) -> float:
    frame_len = max(1, int(sr * 0.030))
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        return 1.0
    frame_rms = np.array([
        np.sqrt(np.mean(audio[i * frame_len:(i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    mean_rms = float(np.mean(frame_rms))
    std_rms = float(np.std(frame_rms))
    if mean_rms < 1e-5:
        return 0.0
    cv = std_rms / mean_rms
    # Natural speech CV is typically between 0.3 and 1.2
    if cv < 0.3:
        return float(np.clip(cv / 0.3, 0.0, 1.0))
    elif cv > 1.2:
        return float(np.clip(1.0 - (cv - 1.2) / 1.0, 0.0, 1.0))
    else:
        return 1.0


def _map_si_snr(db: float) -> float:
    # SI-SNR: 0 dB or below -> 0.0, 10 dB or above -> 1.0
    return float(np.clip((db - 0.0) / 10.0, 0.0, 1.0))


def _map_overlap(overlap: float) -> float:
    # Overlap penalty: overlap > 0.2 begins scaling down, overlap >= 0.8 is capped at 0.2
    return float(np.clip(1.0 - (overlap - 0.2) * 1.333, 0.2, 1.0))


def separation_quality_score(
    audio: np.ndarray,
    raw_mix: np.ndarray,
    sr: int,
    overlap: float,
) -> dict:
    """
    Compute separation quality metric using speech ratio, energy consistency, SI-SNR, and overlap.
    """
    speech_rat = _calc_speech_ratio(audio, sr)
    speech_ratio_score = float(np.clip(speech_rat / 0.25, 0.0, 1.0))

    energy_const = _calc_energy_consistency(audio, sr)

    db = si_snr(audio, raw_mix)
    si_snr_score = _map_si_snr(db)

    overlap_mult = _map_overlap(overlap)

    quality_score = float(speech_ratio_score * energy_const * si_snr_score * overlap_mult)

    return {
        "quality_score":      round(quality_score, 4),
        "speech_ratio":       round(speech_rat, 4),
        "energy_consistency": round(energy_const, 4),
        "si_snr_db":          round(db, 2),
        "overlap":            round(overlap, 4),
    }


def identify_speakers(
    saved_files: list,
    out_dir: Path,
    raw_mix: np.ndarray | None = None,
    sr: int = 16000,
    overlap: float = 0.0,
) -> dict:
    """
    Batch-identify all speaker .wav files from a run_canary.py output session,
    incorporating separation quality gating and score fusion.

    Parameters
    ----------
    saved_files : list[str]
        Filenames such as ["speaker_1.wav", "speaker_2.wav"] produced by the pipeline.
    out_dir     : Path
        Session output directory (e.g. outputs/20260611_214500/).
    raw_mix     : np.ndarray | None
        The original unseparated raw mixture. If provided, enables quality checks.
    sr          : int
        Sample rate (default 16000).
    overlap     : float
        Overlap probability from the scene detection/DRS.

    Returns
    -------
    dict[str, dict]
        {filename: {"speaker": ..., "confidence": ..., "margin": ..., "scores": ..., "reason": ..., "separation_quality": ...}}
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
                "separation_quality": 1.0,
            }
            continue

        audio, file_sr = sf.read(str(wav_path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=-1)

        # ── Pre-gating and quality estimation ─────────────────────────────────
        quality_score = 1.0
        q_info = {}
        if raw_mix is not None:
            q_info = separation_quality_score(audio, raw_mix, file_sr, overlap)
            quality_score = q_info["quality_score"]

            # Gate: Reject poor separation/low-quality streams when multiple speakers exist
            if len(saved_files) > 1:
                rms_val = np.sqrt(np.mean(audio.astype(np.float64) ** 2))
                rms_db = 20.0 * np.log10(rms_val + 1e-10)

                if q_info["speech_ratio"] < 0.25:
                    results[fname] = {
                        "speaker":    "UNKNOWN",
                        "confidence": 0.0,
                        "margin":     0.0,
                        "scores":     [],
                        "reason":     f"poor separation (speech ratio {q_info['speech_ratio']:.2%}-VAD < 25%)",
                        "separation_quality": quality_score,
                        "quality_details": q_info,
                    }
                    continue
                if q_info["si_snr_db"] < 2.0:
                    results[fname] = {
                        "speaker":    "UNKNOWN",
                        "confidence": 0.0,
                        "margin":     0.0,
                        "scores":     [],
                        "reason":     f"poor separation (SI-SNR {q_info['si_snr_db']:.1f} dB < 2.0 dB)",
                        "separation_quality": quality_score,
                        "quality_details": q_info,
                    }
                    continue
                if rms_db < -45.0:
                    results[fname] = {
                        "speaker":    "UNKNOWN",
                        "confidence": 0.0,
                        "margin":     0.0,
                        "scores":     [],
                        "reason":     f"poor separation (RMS level {rms_db:.1f} dBFS is too low)",
                        "separation_quality": quality_score,
                        "quality_details": q_info,
                    }
                    continue

        # ── Voice Matcher ─────────────────────────────────────────────────────
        result = identify(audio, file_sr, profiles=profiles)

        # ── Score Fusion / Quality Scaling ────────────────────────────────────
        if raw_mix is not None:
            original_confidence = result["confidence"]
            scaled_confidence = original_confidence * quality_score

            scaled_scores = []
            for name, score in result.get("scores", []):
                scaled_scores.append((name, round(score * quality_score, 4)))

            result["confidence"] = round(scaled_confidence, 4)
            result["scores"] = scaled_scores

            # Re-evaluate top decision under scaled values
            top_name = result["speaker"]
            if top_name != "UNKNOWN":
                second_score = scaled_scores[1][1] if len(scaled_scores) > 1 else 0.0
                margin = scaled_confidence - second_score
                result["margin"] = round(margin, 4)

                if scaled_confidence < MIN_CONFIDENCE:
                    result["speaker"] = "UNKNOWN"
                    result["reason"] = f"Top scaled score {scaled_confidence:.3f} < minimum confidence {MIN_CONFIDENCE}."
                elif len(scaled_scores) > 1 and margin < MARGIN_THRESHOLD:
                    result["speaker"] = "UNKNOWN"
                    result["reason"] = (
                        f"Scaled margin {margin:.3f} < threshold {MARGIN_THRESHOLD}. "
                        f"Top: {top_name}={scaled_confidence:.3f}, "
                        f"2nd: {scaled_scores[1][0]}={second_score:.3f}."
                    )
                else:
                    result["reason"] = (
                        f"Accepted with separation quality. Score={scaled_confidence:.3f}, margin={margin:.3f} "
                        f"(threshold={MARGIN_THRESHOLD}), Quality={quality_score:.2f}."
                    )

            result["separation_quality"] = quality_score
            result["quality_details"] = q_info
        else:
            result["separation_quality"] = 1.0

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
    sep_q = result.get("separation_quality", 1.0)

    icon = "✓" if spk != "UNKNOWN" else "✗"
    print(f"  {icon}  {fname:<18}  →  {spk:<12}  conf: {conf:.2f}  margin: {margin:.2f}  sep_quality: {sep_q:.2f}")

    if spk == "UNKNOWN":
        print(f"       reason: {result['reason']}")

    # Detailed score breakdown (optional, verbose mode)
    if scores_detail and spk != "UNKNOWN":
        for ranked_name, ranked_score in result.get("scores", []):
            bar = "█" * int(ranked_score * 20)
            print(f"       {ranked_name:<12} {ranked_score:.3f}  {bar}")
