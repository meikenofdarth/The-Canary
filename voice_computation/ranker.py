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

# Decision thresholds for single speaker (clean path)
MIN_CONFIDENCE   = 0.35    # top score must be at least this high (lowered from 0.45)
MARGIN_THRESHOLD = 0.02    # top score must beat 2nd place by at least this much (lowered from 0.04)

# Decision thresholds for multi-speaker separated streams (applied after quality scaling)
MIN_CONFIDENCE_MULTI   = 0.05  # Lowered from 0.12 to allow identification under noise/multiple speakers
MARGIN_THRESHOLD_MULTI = 0.01  # Lowered from 0.03 because quality scaling compresses scores


# ─────────────────────────────────────────────────────────────────────────────
#  Comprehensive feature-agreement helper
# ─────────────────────────────────────────────────────────────────────────────

# Feature keys present in each speaker's score dict (from matcher.py)
_FEATURE_KEYS = ["embedding", "pitch", "energy", "speech_rate", "mfcc"]

# Minimum agreement count for the "tight-margin but feature-consistent" path.
# 3/5 means a majority of independent feature dimensions agree on the speaker.
MIN_FEATURE_AGREEMENT = 3

# The margin below which we require feature agreement (above this → accept directly)
EASY_MARGIN = 0.06


def _feature_agreement(scores: dict) -> tuple:
    """
    Count how many individual feature dimensions vote for the same speaker.

    For each of the 5 feature groups (embedding, pitch, energy, speech_rate,
    mfcc), find which enrolled speaker scores highest on that feature.
    Return (top_speaker_by_vote, vote_count, per_feature_winner_dict).

    Example:
        embedding → Hemang (0.90 vs Deepkumar 0.68)  → vote: Hemang
        pitch     → Hemang (0.82 vs Deepkumar 0.71)  → vote: Hemang
        energy    → Deepkumar (0.74 vs Hemang 0.72)  → vote: Deepkumar
        speech_rate→ Hemang (0.88 vs Deepkumar 0.80) → vote: Hemang
        mfcc      → Hemang (0.85 vs Deepkumar 0.79)  → vote: Hemang
        → Hemang wins 4/5 features → strong comprehensive agreement
    """
    from collections import Counter
    votes = Counter()
    feature_winners = {}

    for feat in _FEATURE_KEYS:
        best_name = None
        best_val  = -1.0
        for name, info in scores.items():
            val = float(info.get(feat, 0.0))
            if val > best_val:
                best_val  = val
                best_name = name
        if best_name:
            votes[best_name] += 1
            feature_winners[feat] = (best_name, round(best_val, 3))

    if not votes:
        return None, 0, {}

    top_name  = votes.most_common(1)[0][0]
    top_votes = votes[top_name]
    return top_name, top_votes, feature_winners


# ─────────────────────────────────────────────────────────────────────────────
#  Decision logic
# ─────────────────────────────────────────────────────────────────────────────

def rank(scores: dict, is_multi: bool = False) -> dict:
    """
    Comprehensive profile-based decision to produce a final identification.

    Decision hierarchy:
      1. Floor gate  — top score must be ≥ MIN_CONFIDENCE or MIN_CONFIDENCE_MULTI
      2. Easy accept — margin ≥ EASY_MARGIN → accept immediately
      3. Feature agreement — margin < EASY_MARGIN but ≥ MARGIN_THRESHOLD:
             Count how many of the 5 feature dimensions independently vote
             for the top speaker. If ≥ 3/5 agree → accept (comprehensive profile).
      4. Tight margin + weak agreement → UNKNOWN

    This approach is more reliable than a single margin threshold because:
    - A speaker may have a tight overall margin but clear agreement across
      independent features (embedding, pitch, energy, rate, MFCC).
    - Real speaker identification from a known enrolled voice will typically
      show consistent per-feature advantage even when the weighted total is close.
    - Background noise / other speakers will scatter votes across features.

    Parameters
    ----------
    scores : dict[str, dict]
        Output of matcher.score_against_all().
        Each value must contain "final_score" and per-feature keys.
    is_multi : bool
        If True, applies relaxed multi-speaker thresholds.

    Returns
    -------
    dict with keys:
        speaker          — identified name or "UNKNOWN"
        confidence       — final_score of top candidate (0.0 if UNKNOWN)
        margin           — gap between 1st and 2nd final scores
        feature_votes    — how many features voted for the accepted speaker
        feature_winners  — per-feature winner breakdown (diagnostic)
        scores           — sorted list of (name, score) for all candidates
        reason           — human-readable decision explanation
    """
    if not scores:
        return {
            "speaker":         "UNKNOWN",
            "confidence":      0.0,
            "margin":          0.0,
            "feature_votes":   0,
            "feature_winners": {},
            "scores":          [],
            "reason":          "No enrolled speakers found.",
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

    # Compute feature agreement (always, for diagnostics)
    agree_name, agree_count, feat_winners = _feature_agreement(scores)

    # Dynamic thresholds based on whether we are in multi-speaker mode
    min_conf = MIN_CONFIDENCE_MULTI if is_multi else MIN_CONFIDENCE
    margin_thresh = MARGIN_THRESHOLD_MULTI if is_multi else MARGIN_THRESHOLD
    easy_margin = 0.03 if is_multi else EASY_MARGIN
    min_conf_feat_only = 0.35 if is_multi else 0.45

    base = {
        "confidence":      round(top_score,  4),
        "margin":          round(margin,     4),
        "feature_votes":   agree_count,
        "feature_winners": feat_winners,
        "scores":          ranked,
    }

    # ── Gate 1: floor confidence ─────────────────────────────────────────────
    if top_score < min_conf:
        return {**base, "speaker": "UNKNOWN",
                "reason": f"Top score {top_score:.3f} < minimum confidence {min_conf}."}

    # ── Gate 2: easy accept — clear margin, no ambiguity ────────────────────
    if len(ranked) <= 1 or margin >= easy_margin:
        return {**base, "speaker": top_name,
                "reason": (f"Accepted (clear margin). Score={top_score:.3f}, "
                           f"margin={margin:.3f} ≥ {easy_margin}.")}

    # ── Gate 3: tight margin — require feature-level agreement ───────────────
    # The top final-score speaker must also win the feature-agreement vote.
    # If 3+ independent features agree → comprehensive profile match → accept.
    if margin >= margin_thresh and agree_name == top_name and agree_count >= MIN_FEATURE_AGREEMENT:
        return {**base, "speaker": top_name,
                "reason": (f"Accepted (margin+features). Score={top_score:.3f}, "
                           f"margin={margin:.3f}, features={agree_count}/5 agree.")}

    # Tight margin but feature agreement is strong enough to override threshold.
    # IMPORTANT: require a higher confidence floor here because we are
    # bypassing the margin check. Ambient room noise can trick 3+ features into
    # agreeing (room acoustics ≈ enrolled sample acoustics) but the final score
    # will be low. Real enrolled-speaker speech scores higher.
    if (agree_name == top_name
            and agree_count >= MIN_FEATURE_AGREEMENT
            and top_score >= min_conf_feat_only):
        return {**base, "speaker": top_name,
                "reason": (f"Accepted (comprehensive profile). Score={top_score:.3f}, "
                           f"margin={margin:.3f} (tight but {agree_count}/5 features agree).")}

    # ── Gate 3.5: embedding+MFCC agree even with tight margin ──────────────
    # ECAPA embedding (60% weight) and MFCC (5% weight) are the two features
    # least affected by SepFormer processing artifacts.
    # If BOTH agree on the top speaker and confidence is decent → accept.
    # This handles the common case where pitch/energy/rate scatter due to
    # short or SepFormer-processed audio, but the two spectral features agree.
    emb_winner  = feat_winners.get("embedding", (None,))[0]
    mfcc_winner = feat_winners.get("mfcc",      (None,))[0]
    if (emb_winner == top_name
            and mfcc_winner == top_name
            and top_score >= min_conf):
        return {**base, "speaker": top_name,
                "reason": (
                    f"Accepted (ECAPA+MFCC agree). Score={top_score:.3f}, "
                    f"margin={margin:.3f} (tight but embedding+MFCC both → {top_name})."
                )}

    # ── Gate 4: insufficient evidence ───────────────────────────────────────
    feat_summary = ", ".join(
        f"{f}→{w[0].split()[0]}" for f, w in feat_winners.items()
    )
    return {**base, "speaker": "UNKNOWN",
            "reason": (
                f"Margin {margin:.3f} < {margin_thresh} and only "
                f"{agree_count}/5 features agree on {top_name}. "
                f"[{feat_summary}]"
            )}


# ─────────────────────────────────────────────────────────────────────────────
#  Full pipeline helper
# ─────────────────────────────────────────────────────────────────────────────

def identify(audio: np.ndarray, sr: int,
             profiles: dict | None = None, is_multi: bool = False) -> dict:
    """
    Full identify pipeline for a single audio buffer.

    Parameters
    ----------
    audio    : np.ndarray
    sr       : int
    profiles : pre-loaded profiles dict (optional, avoids re-loading)
    is_multi : bool
        If True, applies relaxed multi-speaker thresholds.

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
    return rank(scores, is_multi=is_multi)


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
    # Gentler overlap penalty: begins scaling down above 0.3, capped at 0.5 minimum
    return float(np.clip(1.0 - (overlap - 0.3) * 0.8, 0.5, 1.0))


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


def _extract_voiced_segments(audio: np.ndarray, sr: int) -> np.ndarray:
    """
    Extract and concatenate only the voiced speech segments inside the audio.
    This prevents silence and noise frames from diluting the feature profiles.
    """
    frame_ms = 30
    frame_len = max(1, int(sr * frame_ms / 1000))
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        return audio.copy()

    # Calculate RMS for each frame
    rms_frames = np.array([
        np.sqrt(np.mean(audio[i * frame_len:(i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    # Noise floor = 10th percentile
    noise_floor = float(np.percentile(rms_frames, 10)) + 1e-10
    # Keep frames with RMS > noise_floor * 2.5
    voiced_mask = rms_frames > noise_floor * 2.5

    voiced_chunks = []
    for i, is_voiced in enumerate(voiced_mask):
        if is_voiced:
            voiced_chunks.append(audio[i * frame_len:(i + 1) * frame_len])

    if not voiced_chunks:
        return audio.copy()

    return np.concatenate(voiced_chunks)


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

        # Extract voiced-only audio for speaker comparison/identification
        audio_voiced = _extract_voiced_segments(audio, file_sr)

        # ── Pre-gating and quality estimation ─────────────────────────────────
        quality_score = 1.0
        q_info = {}
        if raw_mix is not None:
            # Align raw_mix to speaker audio length.
            # Since the stop-on-silence recorder captures variable-length audio
            # and VAD trims the speaker wavs, lengths will differ.  SI-SNR
            # requires same-length arrays, so we trim or pad raw_mix to match.
            raw_mix_aligned = raw_mix
            if len(raw_mix) != len(audio):
                if len(raw_mix) > len(audio):
                    raw_mix_aligned = raw_mix[:len(audio)]
                else:
                    raw_mix_aligned = np.pad(
                        raw_mix.astype(np.float32),
                        (0, len(audio) - len(raw_mix))
                    )
            q_info = separation_quality_score(audio, raw_mix_aligned, file_sr, overlap)
            # Disable quality scaling (keep it 1.0) to prevent confidence score compression
            quality_score = 1.0

            # Rejection gates are disabled so valid speakers are never skipped due to separation quality metrics.
            # However, we still calculate q_info and log it for diagnostics.

        # ── Voice Matcher ─────────────────────────────────────────────────────
        is_multi = len(saved_files) > 1
        result = identify(audio_voiced, file_sr, profiles=profiles, is_multi=is_multi)

        # ── Score Fusion / Quality Scaling ────────────────────────────────────
        # Quality scaling is disabled (quality_score = 1.0).
        if raw_mix is not None and len(saved_files) > 1:
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

                if scaled_confidence < MIN_CONFIDENCE_MULTI:
                    result["speaker"] = "UNKNOWN"
                    result["reason"] = f"Top scaled score {scaled_confidence:.3f} < minimum confidence {MIN_CONFIDENCE_MULTI}."
                else:
                    result["reason"] = (
                        f"Accepted with separation quality. Score={scaled_confidence:.3f}, margin={margin:.3f}, "
                        f"Quality={quality_score:.2f}."
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
    spk    = result["speaker"]
    conf   = result["confidence"]
    margin = result["margin"]
    sep_q  = result.get("separation_quality", 1.0)
    fvotes = result.get("feature_votes", 0)

    icon = "✓" if spk != "UNKNOWN" else "✗"
    print(f"  {icon}  {fname:<18}  →  {spk:<12}  conf: {conf:.2f}  margin: {margin:.2f}  features: {fvotes}/5")

    if spk == "UNKNOWN":
        print(f"       reason: {result['reason']}")
    else:
        # Show the per-feature breakdown for accepted speakers
        fw = result.get("feature_winners", {})
        if fw:
            feat_line = "  ".join(
                f"{f[:4]}:{w[0].split()[0]}" for f, w in fw.items()
            )
            print(f"       profile: [{feat_line}]")

    # Detailed score breakdown (optional, verbose mode)
    if scores_detail and spk != "UNKNOWN":
        for ranked_name, ranked_score in result.get("scores", []):
            bar = "█" * int(ranked_score * 20)
            print(f"       {ranked_name:<12} {ranked_score:.3f}  {bar}")

