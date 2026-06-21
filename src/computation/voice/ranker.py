
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

MIN_CONFIDENCE   = 0.35
MARGIN_THRESHOLD = 0.02

MIN_CONFIDENCE_MULTI   = 0.05
MARGIN_THRESHOLD_MULTI = 0.01


_FEATURE_KEYS = ["embedding", "pitch", "energy", "speech_rate", "mfcc"]

MIN_FEATURE_AGREEMENT = 3

EASY_MARGIN = 0.06


def _feature_agreement(scores: dict) -> tuple:
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


def rank(scores: dict, is_multi: bool = False) -> dict:
    if not scores:
        return {"speaker": "UNKNOWN", "confidence": 0.0, "margin": 0.0,
                "feature_votes": 0, "feature_winners": {}, "scores": [],
                "reason": "No enrolled speakers found."}

    ranked = sorted(
        [(name, info["final_score"]) for name, info in scores.items()],
        key=lambda x: x[1], reverse=True,
    )
    top_name, top_score = ranked[0]
    second_name = ranked[1][0] if len(ranked) > 1 else None
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = top_score - second_score

    emb_top    = float(scores[top_name].get("embedding", 0.0))
    emb_second = float(scores[second_name].get("embedding", 0.0)) if second_name else 0.0
    emb_margin = emb_top - emb_second

    agree_name, agree_count, feat_winners = _feature_agreement(scores)

    min_conf   = 0.40 if not is_multi else 0.28
    EMB_MARGIN = 0.06 if not is_multi else 0.04
    REL_MARGIN = 0.10

    base = {
        "confidence":      round(top_score, 4),
        "margin":          round(margin, 4),
        "feature_votes":   agree_count if agree_name == top_name else 0,
        "feature_winners": feat_winners,
        "scores":          ranked,
    }

    if top_score < min_conf:
        return {**base, "speaker": "UNKNOWN",
                "reason": f"Top score {top_score:.3f} < floor {min_conf}."}

    if len(ranked) == 1:
        return {**base, "speaker": top_name,
                "reason": f"Accepted (only enrolled speaker). Score={top_score:.3f}."}

    rel = emb_margin / (emb_top + 1e-9)
    if emb_top >= min_conf and (emb_margin >= EMB_MARGIN or rel >= REL_MARGIN):
        return {**base, "speaker": top_name,
                "reason": (f"Accepted (embedding margin). emb={emb_top:.3f} vs "
                           f"{emb_second:.3f} (Δ={emb_margin:.3f}). Score={top_score:.3f}.")}

    return {**base, "speaker": "UNKNOWN",
            "reason": (f"Embedding too close: {top_name}={emb_top:.3f} vs "
                       f"{second_name}={emb_second:.3f} (Δ={emb_margin:.3f} < {EMB_MARGIN}).")}


def identify(audio: np.ndarray, sr: int,
             profiles: dict | None = None, is_multi: bool = False) -> dict:
    from computation.voice.matcher import score_against_all, _load_profiles

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
    if cv < 0.3:
        return float(np.clip(cv / 0.3, 0.0, 1.0))
    elif cv > 1.2:
        return float(np.clip(1.0 - (cv - 1.2) / 1.0, 0.0, 1.0))
    else:
        return 1.0


def _map_si_snr(db: float) -> float:
    return float(np.clip((db - 0.0) / 10.0, 0.0, 1.0))


def _map_overlap(overlap: float) -> float:
    return float(np.clip(1.0 - (overlap - 0.3) * 0.8, 0.5, 1.0))


def separation_quality_score(
    audio: np.ndarray,
    raw_mix: np.ndarray,
    sr: int,
    overlap: float,
) -> dict:
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
    frame_ms = 30
    frame_len = max(1, int(sr * frame_ms / 1000))
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        return audio.copy()

    rms_frames = np.array([
        np.sqrt(np.mean(audio[i * frame_len:(i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    noise_floor = float(np.percentile(rms_frames, 10)) + 1e-10
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
    from computation.voice.matcher import _load_profiles

    profiles = _load_profiles()
    results  = {}
    assigned: set = set()

    sorted_files = sorted(saved_files)

    for fname in sorted_files:
        wav_path = out_dir / fname
        if not wav_path.exists():
            results[fname] = {"speaker": "UNKNOWN", "confidence": 0.0,
                              "margin": 0.0, "scores": [],
                              "reason": f"File not found: {wav_path}",
                              "separation_quality": 1.0}
            continue

        audio, file_sr = sf.read(str(wav_path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=-1)

        audio_voiced = _extract_voiced_segments(audio, file_sr)
        quality_score = 1.0
        q_info = {}

        if raw_mix is not None:
            raw_mix_aligned = raw_mix
            if len(raw_mix) != len(audio):
                raw_mix_aligned = raw_mix[:len(audio)] if len(raw_mix) > len(audio) else \
                    np.pad(raw_mix.astype(np.float32), (0, len(audio) - len(raw_mix)))
            q_info = separation_quality_score(audio, raw_mix_aligned, file_sr, overlap)

        is_multi = len(saved_files) > 1

        from computation.voice.matcher import score_against_all as _saa
        scores = _saa(audio_voiced, file_sr, profiles=profiles,
                      is_multi=is_multi, exclude=assigned)

        result = rank(scores, is_multi=is_multi)

        if result["speaker"] != "UNKNOWN":
            assigned.add(result["speaker"])

        result["separation_quality"] = quality_score
        if q_info:
            result["quality_details"] = q_info

        results[fname] = result

    return {f: results[f] for f in saved_files if f in results}


def print_result(fname: str, result: dict, scores_detail: dict | None = None) -> None:
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
        fw = result.get("feature_winners", {})
        if fw:
            feat_line = "  ".join(
                f"{f[:4]}:{w[0].split()[0]}" for f, w in fw.items()
            )
            print(f"       profile: [{feat_line}]")

    if scores_detail and spk != "UNKNOWN":
        for ranked_name, ranked_score in result.get("scores", []):
            bar = "█" * int(ranked_score * 20)
            print(f"       {ranked_name:<12} {ranked_score:.3f}  {bar}")

