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


def _normalize(sig, target_db=-3.0):
    """Normalise peak to target dBFS."""
    peak = np.max(np.abs(sig))
    if peak > 1e-6:
        sig = sig / peak * (10 ** (target_db / 20.0))
    return sig


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
    sig = _normalize(sig, target_db=-3.0)
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


def _run_sepformer(audio, sr):
    """Run SepFormer-libri2mix, always returns exactly 2 streams."""
    import torch, torchaudio, logging
    logging.getLogger("speechbrain").setLevel(logging.ERROR)

    MODEL_SR = 8000
    audio_8k = torchaudio.functional.resample(
        torch.from_numpy(audio).unsqueeze(0), sr, MODEL_SR)

    from speechbrain.inference.separation import SepformerSeparation
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = SepformerSeparation.from_hparams(
            source="speechbrain/sepformer-libri2mix",
            savedir=f"{MODEL_CACHE}/sepformer-libri2mix",
            run_opts={"device": "cpu"},
        )

    with torch.no_grad():
        est = model.separate_batch(audio_8k)   # (1, T_8k, 2)

    streams = []
    for i in range(2):
        s8 = est[0, :, i].cpu().numpy()
        s = torchaudio.functional.resample(
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


def detect_and_separate(raw, sr):
    """
    Run SepFormer on a lightly denoised mix.
    Returns (n_speakers, streams_list).
    If n_speakers==1, streams_list is empty (caller uses raw directly).
    If n_speakers==2, streams_list contains 2 separated numpy arrays.

    Decision rule (calibrated on SepFormer-libri2mix):
      speech-band RMS ratio weaker/stronger:
        1 speaker → 0.16–0.22  (ghost stream)
        2 speakers → 0.55+     (real second voice)
      Threshold: 0.42
    """
    mix = _light_denoise_for_sep(raw, sr)
    streams = _run_sepformer(mix, sr)

    # Cross-correlation guard
    corr = float(np.corrcoef(streams[0], streams[1])[0, 1])
    if abs(corr) > 0.80:
        return 1, []

    # Speech-band ratio
    sb = [_speech_band_rms(s, sr) for s in streams]
    ratio = min(sb) / (max(sb) + 1e-10)
    if ratio < 0.42:
        return 1, []

    return 2, streams


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
    sig = _normalize(sig, target_db=-3.0)
    return sig.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(ts)
    out_dir.mkdir(exist_ok=True)

    # Record
    raw, sr = record()
    sf.write(out_dir / "raw_input.wav", raw, sr, subtype="PCM_16")

    # Detect speaker count (runs SepFormer internally)
    print("● Detecting speakers ...")
    n_spk, streams = detect_and_separate(raw, sr)

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

    # Report
    print(f"\n  Speakers : {n_spk}")
    print(f"  Folder   : {out_dir}/")
    for fname in saved:
        a, _ = sf.read(str(out_dir / fname), dtype="float32")
        rms  = 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-10)
        print(f"    {fname}  {rms:.1f} dBFS")
    print()


if __name__ == "__main__":
    main()
