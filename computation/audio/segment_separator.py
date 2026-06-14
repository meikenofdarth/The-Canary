"""
separation-filtering/segment_separator.py
==========================================
Per-segment speech separation dispatcher.

Instead of running SepFormer on the full 7-second recording (which it was
never designed for), this module:

  1.  Receives a list of VAD-detected speech segments (with timestamps).
  2.  For each segment, estimates whether it contains 1 or 2+ speakers
      using the fast SpeakerCountEstimator on just that segment's audio.
  3.  Single-speaker segments → no SepFormer needed.
  4.  Multi-speaker segments  → SepFormer runs on only that short window.
  5.  Returns a flat list of "chunks" (dicts with audio + time metadata).

Why this is better than whole-recording separation
---------------------------------------------------
SepFormer-libri2mix was trained on 4–8s clips of SIMULTANEOUSLY speaking
voices.  A 7s recording where speakers take turns confuses it badly:
the model sees long silences and turn-taking, can't assign consistent
source labels across time, and produces two streams each containing
both speakers.

Running SepFormer on a 1.2s overlap window is a completely different and
much easier task — exactly the scenario it was trained on.

Public API
----------
  separate_segments(audio, sr, segments) -> (list[dict], dict)
      Process all VAD segments and return chunks + overlap info.

  Each output chunk dict:
      audio        — np.ndarray float32  (the separated/raw audio)
      start_s      — segment start (seconds into original recording)
      end_s        — segment end   (seconds into original recording)
      duration_s   — length of this chunk
      n_speakers   — 1 or 2 (as estimated for this segment)
      stream_idx   — 0 or 1 (which SepFormer output, or 0 for non-separated)
      is_separated — bool (True if SepFormer was applied)
"""

from __future__ import annotations

import warnings

import numpy as np

# Minimum segment duration to run speaker count estimation (seconds)
# Shorter clips don't have enough audio for the estimator.
_MIN_SEG_FOR_ESTIMATE = 0.6

# Minimum segment duration to run SepFormer (seconds)
# SepFormer needs at least ~0.5s of audio to be meaningful.
_MIN_SEG_FOR_SEPFORMER = 0.8


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _estimate_n_speakers(segment_audio: np.ndarray, sr: int) -> int:
    """
    Estimate speaker count for a single VAD segment.
    Returns 1 or 2.

    Uses DOUBLE CONFIRMATION to avoid over-triggering SepFormer:
    - First pass: standard threshold agglomerative clustering.
    - Second pass: stricter threshold (higher distance required to split).
    - Only returns 2 if BOTH passes agree there are 2 speakers.
    - Otherwise returns 1 (safe fallback: never corrupt single-speaker audio).

    Rationale: SpeakerCountEstimator counts spectral variance clusters.
    In a noisy room, a single speaker's energy variance can look like 2
    acoustic sources, causing SepFormer to run unnecessarily and corrupting
    the acoustic features needed for identity matching.
    """
    from computation.audio.speaker_counter import SpeakerCountEstimator

    # Pass 1: standard estimator
    est_std = SpeakerCountEstimator(sample_rate=sr, max_speakers=2)
    n_std   = est_std.estimate(segment_audio)

    if n_std == 1:
        return 1   # both passes would agree: definitely 1

    # Pass 2: stricter estimator (tighter distance_threshold → harder to split)
    est_strict = SpeakerCountEstimator(
        sample_rate=sr, max_speakers=2, distance_threshold=0.90,
    )
    n_strict = est_strict.estimate(segment_audio)

    if n_strict == 2:
        return 2   # double confirmed: two distinct acoustic sources

    return 1   # conservative: single speaker wins on disagreement


def _run_sepformer_segment(audio: np.ndarray, sr: int) -> list[np.ndarray]:
    """
    Run SepFormer-libri2mix on a single short audio segment.
    Returns a list of 2 separated numpy arrays at `sr`.

    The audio is resampled to 8kHz internally (SepFormer's native SR),
    then back to `sr` after separation.
    """
    import torch
    import torchaudio
    import logging
    logging.getLogger("speechbrain").setLevel(logging.ERROR)

    MODEL_SR = 8_000
    model_id = "sepformer-libri2mix"

    # Import from run_canary for the model path constant
    from pathlib import Path
    MODEL_CACHE = str(Path(__file__).parent.parent / "pretrained_models")

    from speechbrain.inference.separation import SepformerSeparation
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SepformerSeparation.from_hparams(
            source   = f"speechbrain/{model_id}",
            savedir  = f"{MODEL_CACHE}/{model_id}",
            run_opts = {"device": "cpu"},
        )

    audio_8k = torchaudio.functional.resample(
        torch.from_numpy(audio).unsqueeze(0), sr, MODEL_SR
    )

    with torch.no_grad():
        est = model.separate_batch(audio_8k)  # (1, T_8k, 2)

    streams = []
    for i in range(2):
        s8 = est[0, :, i].cpu().numpy()
        s  = torchaudio.functional.resample(
            torch.from_numpy(s8).unsqueeze(0), MODEL_SR, sr
        ).squeeze(0).numpy()
        # Pad/trim to original length
        if len(s) > len(audio):
            s = s[:len(audio)]
        elif len(s) < len(audio):
            s = np.pad(s, (0, len(audio) - len(s)))
        streams.append(s.astype(np.float32))

    return streams


def _is_ghost_stream(stream: np.ndarray, reference: np.ndarray, sr: int) -> bool:
    """
    Return True if `stream` is a ghost/artifact rather than a real speaker.
    A ghost stream is mostly background noise split off by SepFormer.

    Criteria (any one failing → ghost):
      • Speech-band RMS < 20% of the louder stream's RMS.
      • Pearson correlation with reference > 0.80 (same source, not separated).
    """
    from scipy.signal import butter, sosfilt

    sos = butter(4, [300, 3400], btype="bandpass", fs=sr, output="sos")
    sb_stream = float(np.sqrt(np.mean(sosfilt(sos, stream.astype(np.float64)) ** 2)))
    sb_ref    = float(np.sqrt(np.mean(sosfilt(sos, reference.astype(np.float64)) ** 2)))

    # Ghost if too quiet relative to reference
    if sb_ref > 1e-8 and sb_stream / (sb_ref + 1e-10) < 0.20:
        return True

    # Ghost if nearly identical to reference (not actually separated)
    corr = float(np.corrcoef(stream, reference)[0, 1])
    if abs(corr) > 0.85:
        return True

    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def separate_segments(
    audio:    np.ndarray,
    sr:       int,
    segments: list[dict],
) -> tuple[list[dict], dict]:
    """
    Dispatch each VAD segment through the appropriate path:
      - 1 speaker (or too short for SepFormer) → return segment audio as-is.
      - 2 speakers                              → run SepFormer on just that segment.

    Parameters
    ----------
    audio    : Full recording buffer (float32 mono at `sr`).
    sr       : Sample rate.
    segments : Output of vad_segmenter.get_vad_segments().

    Returns
    -------
    chunks : list[dict]
        Each chunk has: audio, start_s, end_s, duration_s,
                        n_speakers, stream_idx, is_separated.
    overlap_info : dict
        overlap_prob — fraction of speech time that was multi-speaker.
        n_multi_segs — number of segments where SepFormer was used.
    """
    chunks: list[dict] = []

    total_speech_duration = sum(seg["duration_s"] for seg in segments)
    multi_speaker_duration = 0.0
    n_multi_segs = 0

    for seg_idx, seg in enumerate(segments):
        st  = seg["start_sample"]
        en  = seg["end_sample"]
        seg_audio = audio[st:en].copy().astype(np.float32)
        dur = seg["duration_s"]

        # ── Short segment: treat as single-speaker directly ───────────────────
        if dur < _MIN_SEG_FOR_ESTIMATE:
            chunks.append({
                "audio":        seg_audio,
                "start_s":      seg["start_s"],
                "end_s":        seg["end_s"],
                "duration_s":   dur,
                "n_speakers":   1,
                "stream_idx":   0,
                "is_separated": False,
            })
            continue

        # ── Estimate speaker count for this segment ───────────────────────────
        try:
            n_spk = _estimate_n_speakers(seg_audio, sr)
        except Exception:
            n_spk = 1   # safe fallback

        # ── Single speaker → pass through as-is ──────────────────────────────
        if n_spk == 1 or dur < _MIN_SEG_FOR_SEPFORMER:
            chunks.append({
                "audio":        seg_audio,
                "start_s":      seg["start_s"],
                "end_s":        seg["end_s"],
                "duration_s":   dur,
                "n_speakers":   1,
                "stream_idx":   0,
                "is_separated": False,
            })
            continue

        # ── Multi-speaker → SepFormer on just this segment ───────────────────
        n_multi_segs       += 1
        multi_speaker_duration += dur

        sep_label = f"Seg {seg_idx + 1:02d} ({dur:.2f}s)"
        print(f"    ↳ {sep_label} → 2 speakers — separating ...", flush=True)

        try:
            streams = _run_sepformer_segment(seg_audio, sr)

            # Gram-Schmidt cross-talk suppression (same as original pipeline)
            a = streams[0].astype(np.float64)
            b = streams[1].astype(np.float64)
            alpha = np.dot(a, b) / (np.dot(b, b) + 1e-10)
            a_clean = a - alpha * b
            # Restore level
            orig_pk = float(np.max(np.abs(streams[0]))) + 1e-10
            c_pk    = float(np.max(np.abs(a_clean))) + 1e-10
            streams[0] = (a_clean * (orig_pk / c_pk)).astype(np.float32)

            # Discard ghost streams
            valid_streams = []
            for idx, s in enumerate(streams):
                if not _is_ghost_stream(s, seg_audio, sr):
                    valid_streams.append((idx, s))

            if not valid_streams:
                # Both rejected → treat as single-speaker
                valid_streams = [(0, seg_audio)]

            for stream_idx, stream_audio in valid_streams:
                chunks.append({
                    "audio":        stream_audio,
                    "start_s":      seg["start_s"],
                    "end_s":        seg["end_s"],
                    "duration_s":   dur,
                    "n_speakers":   n_spk,
                    "stream_idx":   stream_idx,
                    "is_separated": True,
                })

        except Exception as e:
            # SepFormer failed on this segment — fall back to single-speaker
            print(f"    ↳ SepFormer failed on {sep_label}: {e} — using raw segment")
            chunks.append({
                "audio":        seg_audio,
                "start_s":      seg["start_s"],
                "end_s":        seg["end_s"],
                "duration_s":   dur,
                "n_speakers":   1,
                "stream_idx":   0,
                "is_separated": False,
            })

    overlap_prob = (
        multi_speaker_duration / total_speech_duration
        if total_speech_duration > 0 else 0.0
    )

    overlap_info = {
        "overlap_prob":   round(overlap_prob, 3),
        "n_multi_segs":   n_multi_segs,
        "total_speech_s": round(total_speech_duration, 2),
        "multi_speech_s": round(multi_speaker_duration, 2),
    }

    return chunks, overlap_info
