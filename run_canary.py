#!/usr/bin/env python3
"""
run_canary.py  –  The Canary Speaker Separation
================================================
Run:  python3 run_canary.py

Two smart paths:
  • 1 speaker  → direct enhancement of raw recording (no SepFormer artifacts)
  • 2 speakers → SepFormer separation + per-stream enhancement
"""

import sys, time, datetime, warnings
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SAMPLE_RATE = 16000
DURATION    = 7
MODEL_CACHE = "pretrained_models"


# ─────────────────────────────────────────────────────────────────────────────
#  RECORD
# ─────────────────────────────────────────────────────────────────────────────
def record(duration=DURATION, sr=SAMPLE_RATE):
    print(f"\n● Recording {duration}s — speak now")
    frames = []
    with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                        blocksize=int(sr * 0.1),
                        callback=lambda d, f, t, s: frames.append(d.copy())):
        for i in range(duration, 0, -1):
            print(f"  {i}s ...", end="\r", flush=True)
            time.sleep(1)
    print("  Recording done.     ")
    return np.concatenate(frames).squeeze().astype(np.float32), sr


# ─────────────────────────────────────────────────────────────────────────────
#  SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _highpass(sig, cutoff=80.0, sr=SAMPLE_RATE):
    """Remove DC and sub-bass rumble below cutoff Hz."""
    from scipy.signal import butter, sosfilt
    sos = butter(2, cutoff, btype="highpass", fs=sr, output="sos")
    return sosfilt(sos, sig)


def _presence_boost(sig, shelf_freq=2000.0, gain_db=3.5, sr=SAMPLE_RATE):
    """
    High-frequency shelf boost above shelf_freq Hz.
    Restores crispness lost in SepFormer's 8kHz internal SR round-trip,
    and adds air/presence to single-speaker recordings.
    """
    from scipy.signal import butter, sosfilt
    shelf_gain = 10 ** (gain_db / 20.0)
    lp  = butter(2, shelf_freq, btype="lowpass", fs=sr, output="sos")
    lo  = sosfilt(lp, sig)
    hi  = sig - lo
    return lo + hi * shelf_gain


def _soft_compress(sig, threshold_db=-18.0, ratio=3.0, sr=SAMPLE_RATE):
    """
    Soft-knee dynamic range compressor.
    Brings up quiet speech without touching loud peaks.
    attack=5ms, release=150ms, knee=6dB.
    """
    threshold  = 10 ** (threshold_db / 20.0)
    knee_db    = 6.0
    knee_lower = 10 ** ((threshold_db - knee_db / 2) / 20.0)
    knee_upper = 10 ** ((threshold_db + knee_db / 2) / 20.0)

    attack_coef  = np.exp(-1.0 / (0.005 * sr))   # 5 ms
    release_coef = np.exp(-1.0 / (0.150 * sr))   # 150 ms

    env    = 0.0
    gain   = 1.0
    out    = np.zeros_like(sig)

    for n, x in enumerate(sig):
        level = abs(x)
        # envelope follower
        if level > env:
            env = attack_coef  * env + (1 - attack_coef)  * level
        else:
            env = release_coef * env + (1 - release_coef) * level

        # soft-knee gain computation
        if env <= knee_lower:
            gain = 1.0
        elif env <= knee_upper:
            # interpolate in knee region
            t    = (env - knee_lower) / (knee_upper - knee_lower)
            gain = 1.0 + (1.0 / ratio - 1.0) * t * t
        else:
            gain = (threshold / (env + 1e-10)) * (1.0 - 1.0 / ratio) + 1.0 / ratio

        out[n] = x * gain

    return out


def _normalize(sig, target_rms_db=-18.0, peak_limit_db=-1.0):
    """
    Loudness normalization: targets a comfortable RMS level (-18 dBFS)
    rather than just peak normalization.

    This is what makes a -34 dBFS quiet recording jump to a loud,
    clear -18 dBFS without any distortion — pure gain, no clipping.
    A hard peak limiter at -1 dBFS prevents any overflow.
    """
    rms = np.sqrt(np.mean(sig.astype(np.float64) ** 2))
    if rms < 1e-8:
        return sig
    # How much gain do we need to reach target RMS?
    gain_db = target_rms_db - 20.0 * np.log10(rms)
    gain    = 10 ** (gain_db / 20.0)
    sig     = sig * gain
    # Hard-limit peak so we never clip
    peak_limit = 10 ** (peak_limit_db / 20.0)
    peak       = np.max(np.abs(sig))
    if peak > peak_limit:
        sig = sig / peak * peak_limit
    return sig.astype(np.float32)


def _denoise(sig, sr, prop_decrease, stationary=False,
             n_fft=1024, hop=256, t_smooth=80, f_smooth=300):
    import noisereduce as nr
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return nr.reduce_noise(
            y=sig.astype(np.float32), sr=sr,
            stationary=stationary,
            prop_decrease=prop_decrease,
            n_fft=n_fft, win_length=n_fft, hop_length=hop,
            time_mask_smooth_ms=t_smooth,
            freq_mask_smooth_hz=f_smooth,
        )


def si_snr(estimate: np.ndarray, reference: np.ndarray) -> float:
    """
    Scale-Invariant Signal-to-Noise Ratio (dB).
    Measures how well `estimate` reconstructs `reference`.
    Higher = better separation quality.
    Formula: SI-SNR = 10 * log10( ||s_target||² / ||e_noise||² )
    """
    ref = reference.astype(np.float64) - np.mean(reference)
    est = estimate.astype(np.float64)  - np.mean(estimate)
    alpha  = np.dot(est, ref) / (np.dot(ref, ref) + 1e-10)
    target = alpha * ref
    noise  = est - target
    return float(10.0 * np.log10(
        (np.dot(target, target) + 1e-10) / (np.dot(noise, noise) + 1e-10)
    ))


# ─────────────────────────────────────────────────────────────────────────────
#  PATH A – SINGLE SPEAKER  (direct enhancement, no SepFormer involved)
# ─────────────────────────────────────────────────────────────────────────────
def enhance_single(raw, sr):
    """
    Full enhancement pipeline for a single-speaker recording.
    No separation needed — we work directly on the raw signal so there
    are zero separation artifacts to work around.

    Steps:
      1.  High-pass 80 Hz       — removes rumble / DC
      2a. Non-stationary denoise pass 1 (prop=0.55, wide FFT)
          — removes broadband background noise adaptively
      2b. Non-stationary denoise pass 2 (prop=0.40, narrower FFT)
          — targeted residual clean in speech band
      3.  Presence boost +3.5 dB above 2 kHz
          — adds crispness and intelligibility
      4.  Soft-knee compressor (thresh=-18 dB, ratio 3:1)
          — brings up quiet moments, evens out volume
      5.  Normalise to -3 dBFS
    """
    sig = raw.astype(np.float64)

    # 1. Remove rumble
    sig = _highpass(sig, cutoff=80.0, sr=sr)

    # 2a. Broad noise sweep (targets stationary hiss, fan noise, etc.)
    sig = _denoise(sig, sr,
                   prop_decrease=0.55,
                   stationary=False,
                   n_fft=2048, hop=512,
                   t_smooth=120, f_smooth=200).astype(np.float64)

    # 2b. Residual clean in speech band — gentler, adaptive
    sig = _denoise(sig, sr,
                   prop_decrease=0.40,
                   stationary=False,
                   n_fft=1024, hop=256,
                   t_smooth=60, f_smooth=400).astype(np.float64)

    # 3. Presence boost — speech clarity
    sig = _presence_boost(sig, shelf_freq=2000.0, gain_db=3.5, sr=sr)

    # 4. Soft compressor — even out dynamics
    sig = _soft_compress(sig.astype(np.float32), threshold_db=-18.0,
                         ratio=3.0, sr=sr).astype(np.float64)

    # 5. Normalise
    sig = _normalize(sig)   # RMS loudness to -18 dBFS, peak limited at -1 dBFS
    return sig.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  SPEAKER DETECTION  (runs SepFormer, checks if 1 or 2 real speakers)
# ─────────────────────────────────────────────────────────────────────────────
def _light_denoise_for_sep(audio, sr):
    """Very light denoise before feeding to SepFormer — preserve signal shape."""
    sig = _denoise(audio, sr,
                   prop_decrease=0.25,
                   stationary=False,
                   n_fft=2048, hop=512,
                   t_smooth=150, f_smooth=200)
    # restore original peak
    orig_peak = np.max(np.abs(audio))
    peak = np.max(np.abs(sig))
    if peak > 1e-6:
        sig = sig / peak * orig_peak
    return sig.astype(np.float32)


def _apply_vad_gate(audio: np.ndarray, sr: int, frame_ms: int = 30) -> np.ndarray:
    """
    Zero out non-speech regions in the audio to prevent background noise
    and artifacts from contaminating the separation model.
    """
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
    # Slightly sensitive threshold to preserve weak/onset speech components
    voiced_frames = rms_frames > noise_floor * 2.5

    gated_audio = audio.copy()
    for i, is_voiced in enumerate(voiced_frames):
        if not is_voiced:
            gated_audio[i * frame_len:(i + 1) * frame_len] = 0.0

    return gated_audio


def _run_sepformer(audio, sr, n_mix: int = 2):
    """
    Run SepFormer-libri{n_mix}mix.
    n_mix=2  → speechbrain/sepformer-libri2mix  (2 output streams)
    n_mix=3  → speechbrain/sepformer-libri3mix  (3 output streams)
    """
    import torch, torchaudio, logging
    logging.getLogger("speechbrain").setLevel(logging.ERROR)

    model_id = f"sepformer-libri{n_mix}mix"
    MODEL_SR  = 8000

    # VAD before separation: run only on speech regions to reduce artifacts/bleeding
    audio_gated = _apply_vad_gate(audio, sr)

    audio_8k  = torchaudio.functional.resample(
        torch.from_numpy(audio_gated).unsqueeze(0), sr, MODEL_SR)

    from speechbrain.inference.separation import SepformerSeparation
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SepformerSeparation.from_hparams(
            source=f"speechbrain/{model_id}",
            savedir=f"{MODEL_CACHE}/{model_id}",
            run_opts={"device": "cpu"},
        )

    with torch.no_grad():
        est = model.separate_batch(audio_8k)   # (1, T_8k, n_mix)

    streams = []
    for i in range(n_mix):
        s8 = est[0, :, i].cpu().numpy()
        s  = torchaudio.functional.resample(
            torch.from_numpy(s8).unsqueeze(0), MODEL_SR, sr
        ).squeeze(0).numpy()
        if len(s) > len(audio):   s = s[:len(audio)]
        elif len(s) < len(audio): s = np.pad(s, (0, len(audio) - len(s)))
        streams.append(s.astype(np.float32))
    return streams


def _speech_band_rms(audio, sr, lo=300, hi=3400):
    from scipy.signal import butter, sosfilt
    sos = butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    return float(np.sqrt(np.mean(sosfilt(sos, audio.astype(np.float64)) ** 2)))


def _reduce_crosstalk(streams: list) -> list:
    """
    Gram-Schmidt cross-talk suppression between separated streams.

    SepFormer almost always leaves some bleed-through: a little of speaker B
    leaks into the speaker A stream and vice-versa.  This function removes
    the linear projection of each stream onto every other stream, making the
    outputs orthogonal.  Peak level is preserved so no loudness change occurs.
    """
    if len(streams) < 2:
        return streams
    clean = [s.astype(np.float64) for s in streams]
    for i in range(len(clean)):
        for j in range(len(clean)):
            if i == j:
                continue
            denom    = np.dot(clean[j], clean[j]) + 1e-10
            alpha    = np.dot(clean[i], clean[j]) / denom
            clean[i] = clean[i] - alpha * clean[j]
    result = []
    for orig, c in zip(streams, clean):
        orig_peak = float(np.max(np.abs(orig))) + 1e-10
        c_peak    = float(np.max(np.abs(c)))    + 1e-10
        result.append((c * (orig_peak / c_peak)).astype(np.float32))
    return result


def _temporal_overlap(s1: np.ndarray, s2: np.ndarray, sr: int,
                      frame_ms: int = 30) -> float:
    """
    Fraction of time both streams have active speech simultaneously.

      0.00 = pure turn-taking (speakers never talk at the same time)
      1.00 = both always talking at once (fully overlapping speech)

    Uses the same energy-VAD logic as the pre-screening gate:
    voiced = frame RMS > 3 × noise floor (10th percentile).
    """
    frame_len = max(1, int(sr * frame_ms / 1000))
    n = min(len(s1), len(s2)) // frame_len
    if n == 0:
        return 0.0

    def voiced(sig):
        rms_f = np.array([
            np.sqrt(np.mean(sig[i * frame_len:(i + 1) * frame_len] ** 2))
            for i in range(n)
        ])
        floor = float(np.percentile(rms_f, 10)) + 1e-10
        return rms_f > floor * 3.0

    v1     = voiced(s1.astype(np.float32))
    v2     = voiced(s2.astype(np.float32))
    both   = float(np.sum(v1 & v2))
    either = float(np.sum(v1 | v2)) + 1e-10
    return float(both / either)


def detect_and_separate(raw, sr):
    """
    2-speaker auto-detection using SepFormer-libri2mix.
    Calibrated on 10 real recordings — default path, unchanged.

    Returns (n_speakers, streams_list).
      n_speakers==1 → streams_list is empty (caller uses raw directly)
      n_speakers==2 → streams_list has 2 separated numpy arrays
    """
    mix     = _light_denoise_for_sep(raw, sr)
    streams = _run_sepformer(mix, sr, n_mix=2)

    corr  = float(np.corrcoef(streams[0], streams[1])[0, 1])
    sb    = [_speech_band_rms(s, sr) for s in streams]
    ratio = min(sb) / (max(sb) + 1e-10)

    if abs(corr) < 0.03:   # clearly 2 independent sources
        return 2, streams
    if abs(corr) > 0.80:   # same source
        return 1, []
    return (2, streams) if ratio >= 0.35 else (1, [])


def detect_and_separate_3spk(raw, sr):
    """
    3-speaker mode using SepFormer-libri3mix.
    Downloads speechbrain/sepformer-libri3mix on first use (~same size as libri2mix).

    SepFormer-libri3mix always produces 3 output streams.
    Real speaker streams are identified by speech-band RMS:
      - Reference = loudest stream's speech-band RMS
      - Any stream with RMS ≥ 25% of reference → real speaker
      - Any stream with RMS <  25% of reference → ghost/artifact → discarded

    Returns (n_real_speakers, real_streams).
    n_real_speakers is always ≥ 1.
    """
    print("  (using sepformer-libri3mix)")
    mix     = _light_denoise_for_sep(raw, sr)
    streams = _run_sepformer(mix, sr, n_mix=3)

    sb      = [_speech_band_rms(s, sr) for s in streams]
    max_sb  = max(sb) + 1e-10

    # Keep any stream whose speech-band RMS is ≥ 25% of the loudest stream
    real = [(s, r) for s, r in zip(streams, sb) if r / max_sb >= 0.25]

    if not real:
        # Fallback: just keep the loudest
        best = int(np.argmax(sb))
        real = [(streams[best], sb[best])]

    real_streams = [s for s, _ in real]
    return len(real_streams), real_streams


# ─────────────────────────────────────────────────────────────────────────────
#  PATH B – MULTI-SPEAKER  (enhance each separated stream individually)
# ─────────────────────────────────────────────────────────────────────────────
def enhance_stream(stream, sr):
    """
    Enhancement for a single separated speaker stream.
    More conservative than single-speaker path because SepFormer already
    did the heavy lifting; we just clean up its residuals.

    Steps:
      1.  High-pass 80 Hz
      2.  Gentle non-stationary denoise (prop=0.38)
          — removes cross-talk residuals and SepFormer frame artifacts
          — non-stationary so quiet consonants survive
      3.  Presence boost +3.5 dB above 2 kHz
      4.  Soft-knee compressor — even out per-speaker dynamics
      5.  Normalise to -3 dBFS
    """
    sig = stream.astype(np.float64)

    # 1. Rumble removal
    sig = _highpass(sig, cutoff=80.0, sr=sr)

    # 2. Residual clean
    sig = _denoise(sig, sr,
                   prop_decrease=0.38,
                   stationary=False,
                   n_fft=1024, hop=256,
                   t_smooth=60, f_smooth=350).astype(np.float64)

    # 3. Presence boost
    sig = _presence_boost(sig, shelf_freq=2000.0, gain_db=3.5, sr=sr)

    # 4. Soft compression
    sig = _soft_compress(sig.astype(np.float32), threshold_db=-18.0,
                         ratio=3.0, sr=sr).astype(np.float64)

    # 5. Normalise
    sig = _normalize(sig)   # RMS loudness to -18 dBFS, peak limited at -1 dBFS
    return sig.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  DRS SHADOW  (pure observer — no routing changes)
# ─────────────────────────────────────────────────────────────────────────────
def drs_shadow(raw: np.ndarray, sr: int, n_spk: int, streams: list) -> dict:
    """
    Dynamic Resource Scaler — shadow / observe mode only.
    Reads signals already produced by the pipeline; changes nothing.

    Complexity score:
        complexity = overlap_probability * 0.5
                   + noise_level        * 0.3
                   + speaker_score      * 0.2

    Thresholds (calibrated on real recordings):
        < 0.30  → Mode A  Clean Scene
        < 0.70  → Mode B  Moderate Interference
        ≥ 0.70  → Mode C  High Interference · Heavy Noise
    """
    # ── Noise level (0–1) via in-band SNR of raw signal ──────────────────
    frame_len = max(1, int(sr * 0.030))           # 30 ms frames
    n_frames  = len(raw) // frame_len
    if n_frames > 0:
        frame_rms   = np.array([
            np.sqrt(np.mean(raw[i * frame_len:(i + 1) * frame_len] ** 2))
            for i in range(n_frames)
        ])
        noise_floor = float(np.percentile(frame_rms, 25)) + 1e-10
        speech_peak = float(np.percentile(frame_rms, 90)) + 1e-10
        raw_snr_db  = 20.0 * np.log10(speech_peak / noise_floor)
        # Map: SNR ≥ 35 dB → 0.0 (clean),  SNR ≤ 5 dB → 1.0 (very noisy)
        noise_level = float(np.clip(1.0 - (raw_snr_db - 5.0) / 30.0, 0.0, 1.0))
    else:
        noise_level = 0.5

    # ── Temporal overlap (0–1): fraction of frames both streams are voiced ─
    # Measures how often speakers talk at the same time (simultaneous speech).
    # 0.0 = pure turn-taking · 1.0 = always talking simultaneously.
    # NOTE: computed AFTER cross-talk reduction so streams reflect real activity.
    if n_spk >= 2 and len(streams) >= 2:
        overlap_prob = _temporal_overlap(streams[0], streams[1], sr)
    else:
        overlap_prob = 0.0   # single speaker → no overlap by definition

    # ── Speaker count score (0–1) ─────────────────────────────────────────
    speaker_score = float(np.clip((n_spk - 1) / 2.0, 0.0, 1.0))

    # ── Complexity score ──────────────────────────────────────────────────
    complexity = (
        overlap_prob  * 0.5 +
        noise_level   * 0.3 +
        speaker_score * 0.2
    )

    # ── Mode assignment with heuristics (Canary Way) ───────────────────────
    reasons = []

    # Overlap Reason
    if overlap_prob > 0.7:
        reasons.append("Critical overlap detected (> 0.7).")
    elif overlap_prob > 0.2:
        reasons.append("Moderate overlap detected.")
    else:
        reasons.append("Low or no speech overlap.")

    # Speaker Count Reason
    if n_spk >= 3:
        reasons.append("Three or more speakers present.")
    elif n_spk == 2:
        reasons.append("Multiple speakers present.")
    else:
        reasons.append("Single speaker.")

    # Noise Reason
    if noise_level > 0.8:
        reasons.append("Critical noise level detected (> 0.8).")
    elif noise_level > 0.35:
        reasons.append("Noticeable noise detected.")
    else:
        reasons.append("Noise below critical threshold.")

    # Apply heuristics
    if noise_level > 0.8:
        mode, label = "C", "High Interference · Heavy Noise"
        detail = "critical background noise (> 0.80)"
        icon   = "🔴"
        reasons.insert(0, "Hard Rule: Critical noise level (> 0.80) forced Mode C.")
    elif overlap_prob > 0.7:
        mode, label = "C", "High Interference · Heavy Noise"
        detail = "critical speech overlap (> 0.70)"
        icon   = "🔴"
        reasons.insert(0, "Hard Rule: Critical overlap (> 0.70) forced Mode C.")
    elif n_spk >= 3:
        mode, label = "C", "High Interference · Heavy Noise"
        detail = "3+ speakers detected"
        icon   = "🔴"
        reasons.insert(0, "Hard Rule: 3+ speakers forced Mode C.")
    else:
        # SCS threshold fallback
        if complexity < 0.25:
            mode, label = "A", "Clean Scene"
            detail = "1 speaker · low noise · pure turn-taking"
            icon   = "🟢"
        elif complexity < 0.55:
            mode, label = "B", "Moderate Interference"
            detail = "2 speakers · some simultaneous speech · mild noise"
            icon   = "🟡"
        else:
            mode, label = "C", "High Interference · Heavy Noise"
            detail = "heavy simultaneous speech · high noise · 3+ speakers"
            icon   = "🔴"

    return {
        "mode":             mode,
        "label":            label,
        "detail":           detail,
        "icon":             icon,
        "complexity_score": round(complexity,    3),
        "noise_level":      round(noise_level,   3),
        "overlap_prob":     round(overlap_prob,  3),
        "speaker_score":    round(speaker_score, 3),
        "speaker_count":    n_spk,
        "reasons":          reasons,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    OUTPUT_ROOT = Path("outputs")
    OUTPUT_ROOT.mkdir(exist_ok=True)

    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / ts
    out_dir.mkdir(exist_ok=True)

    # Record
    raw, sr = record()
    sf.write(out_dir / "raw_input.wav", raw, sr, subtype="PCM_16")

    # ── Silence gate ─────────────────────────────────────────────────────────
    raw_rms_db = 20.0 * np.log10(np.sqrt(np.mean(raw ** 2)) + 1e-10)
    if raw_rms_db < -55.0:
        print("\n  No audio detected — please speak closer to the mic.")
        out_dir.rmdir()   # clean up the empty folder
        return

    # Estimate speaker count using the windowed speaker count estimator
    print("● Estimating speaker count ...")
    try:
        sys.path.insert(0, str(Path(__file__).parent / "separation-filtering"))
        from speaker_counter import SpeakerCountEstimator
        estimator = SpeakerCountEstimator(sample_rate=sr, max_speakers=3)
        est_spk = estimator.estimate(raw)
        print(f"  Estimated speakers in scene: {est_spk}")
    except Exception as e:
        print(f"  [SpeakerCountEstimator] failed: {e}. Defaulting to 2-speaker detection.")
        est_spk = 2

    print("● Separating speaker streams ...")
    if est_spk >= 3:
        n_spk, streams = detect_and_separate_3spk(raw, sr)
    else:
        n_spk, streams = detect_and_separate(raw, sr)

    # ── Cross-talk reduction + rank by speech content (dominant → first) ──
    # This ensures speaker_1.wav is always the main/loudest speaker,
    # and reduces SepFormer bleed-through before enhancement.
    overlap_prob = 0.0
    if n_spk >= 2 and len(streams) >= 2:
        streams = _reduce_crosstalk(streams)
        streams = sorted(streams,
                         key=lambda s: _speech_band_rms(s, sr), reverse=True)
        print("  (cross-talk reduced · dominant speaker → speaker_1)")
        overlap_prob = _temporal_overlap(streams[0], streams[1], sr)

    # ── Si-SNR vs raw mix ─────────────────────────────────────────────────
    if n_spk >= 2 and len(streams) >= 2:
        print("  Si-SNR vs mix:")
        for i, s in enumerate(streams, 1):
            score = si_snr(s, raw)
            print(f"    Speaker {i}: {score:+.1f} dB")

    if n_spk == 1:
        # ── Single speaker: direct enhancement ───────────────────────────
        print("● 1 speaker — enhancing directly (no separation) ...")
        enhanced = enhance_single(raw, sr)
        sf.write(out_dir / "speaker_1.wav", enhanced, sr, subtype="PCM_16")
        saved = ["speaker_1.wav"]

    else:
        # ── Multiple speakers: enhance each separated stream ──────────────
        print(f"● {n_spk} speakers — enhancing each stream ...")
        saved = []
        for i, s in enumerate(streams, 1):
            enhanced = enhance_stream(s, sr)
            fname = f"speaker_{i}.wav"
            sf.write(out_dir / fname, enhanced, sr, subtype="PCM_16")
            saved.append(fname)

    print("\n● Transcribing speech to text ...")
    from asr.transcribe import transcribe_and_save, pre_screen
    ready_speakers = []
    for fname in saved:
        wav_p = out_dir / fname
        # Quick pre-screen first (no model, <0.1s)
        screen = pre_screen(wav_p)
        tag    = fname.replace("speaker_", "Spk").replace(".wav", "")
        rms    = screen["rms_db"]
        ratio  = screen["speech_ratio"]

        if screen["verdict"] == "REJECTED":
            print(f"  ✗ {fname}  [RMS:{rms:.0f}dBFS | Speech:{ratio:.0%}]  → REJECTED ({screen['reason'].split('—')[1].strip()})")
            # Still write the rejection .txt
            transcribe_and_save(wav_p, model_name="base")
        else:
            print(f"  ▶ {fname}  [RMS:{rms:.0f}dBFS | Speech:{ratio:.0%}]  → READY — transcribing ...", flush=True)
            text, status = transcribe_and_save(wav_p, model_name="base")
            if status == "SPEECH":
                preview = text[:80] + ("…" if len(text) > 80 else "")
                print(f"    ✓ [{tag}] {preview}")
                ready_speakers.append(fname)
            else:
                print(f"    ✗ [{tag}] {status} — transcript discarded")

    # Final verdict summary
    print()
    if ready_speakers:
        print(f"  ✓ Speakers ready for processing : {', '.join(ready_speakers)}")
    else:
        print("  ✗ No speaker streams passed quality gate")

    # ── Voice Identity Engine ─────────────────────────────────────────────
    # Runs after ASR, completely independent of DRS / separation / context.
    # Never crashes the main pipeline — wrapped in try/except.
    voice_ids = {}
    try:
        from voice_computation.ranker import identify_speakers, print_result
        print("\n● Identifying speakers ...")
        voice_ids = identify_speakers(saved, out_dir, raw_mix=raw, sr=sr, overlap=overlap_prob)
        print()
        print("  " + "─" * 46)
        print("  VOICE IDENTITY")
        print()
        for fname, result in voice_ids.items():
            print_result(fname, result)
        print("  " + "─" * 46)
    except Exception as _vid_err:
        print(f"  [Voice ID] skipped — {_vid_err}")

    # ── Report ───────────────────────────────────────────────────────────
    print(f"\n  Speakers : {n_spk}")
    print(f"  Folder   : {out_dir}/")
    for fname in saved:
        a, _ = sf.read(str(out_dir / fname), dtype="float32")
        rms  = 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-10)
        txt  = fname.replace(".wav", ".txt")
        print(f"    {fname}  {rms:.1f} dBFS  → {txt}")
    print()

    # ── DRS Shadow Report ─────────────────────────────────────────────────
    drs = drs_shadow(raw, sr, n_spk, streams)
    print("  " + "─" * 46)
    print("  DRS ANALYSIS")
    print()
    print(f"  Noise Score     : {drs['noise_level']:.3f}")
    print(f"  Overlap Score   : {drs['overlap_prob']:.3f}")
    print(f"  Speaker Score   : {drs['speaker_score']:.3f}")
    print()
    print(f"  SCS             : {drs['complexity_score']:.3f}")
    print()
    print(f"  Mode            : {drs['mode']}  {drs['icon']}  ({drs['label']})")
    print()
    print("  Reason:")
    for r in drs["reasons"]:
        print(f"  - {r}")
    print("  " + "─" * 46)
    print()

    # ── Context Engine (shadow — never crashes the main pipeline) ─────────
    try:
        from context_engine import build_context
        build_context(out_dir, drs, n_spk)
    except Exception as _ctx_err:
        print(f"  [Context Engine] skipped — {_ctx_err}")


if __name__ == "__main__":
    main()

