#!/usr/bin/env python3
"""
run_canary.py  –  The Canary Speaker Separation
================================================
Run:  python3 run_canary.py

Records 7 seconds, denoises the mix, separates speakers,
post-processes each speaker stream, saves .wav files in a
timestamped folder next to this script.
"""

import sys, time, datetime, warnings
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SAMPLE_RATE  = 16000
DURATION     = 7        # seconds
MODEL_CACHE  = "pretrained_models"


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 – RECORD
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
    audio = np.concatenate(frames).squeeze().astype(np.float32)
    return audio, sr


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2 – LIGHT DENOISE (just knock the noise floor, don't touch speech)
# ─────────────────────────────────────────────────────────────────────────────
def light_denoise(audio, sr):
    """Gentle noise floor reduction on the mix before separation."""
    import noisereduce as nr
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cleaned = nr.reduce_noise(
            y=audio, sr=sr,
            stationary=False,
            prop_decrease=0.55,          # gentle — preserve speech character
            n_fft=1024, win_length=1024, hop_length=256,
            time_mask_smooth_ms=100, freq_mask_smooth_hz=300,
        )
    # hard-clip prevention
    peak = np.max(np.abs(cleaned))
    if peak > 1e-6:
        cleaned = cleaned / peak * np.max(np.abs(audio)) * 0.98
    return cleaned.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3 – SPEAKER SEPARATION  (SepFormer libri2mix, always 2 outputs)
# ─────────────────────────────────────────────────────────────────────────────
def separate(audio, sr):
    """
    Uses SepFormer-libri2mix to produce 2 separated streams.
    Always use the 2-speaker model — it's higher quality than libri3mix
    and avoids spurious 3rd-stream artifacts.
    """
    import torch, torchaudio, logging
    logging.getLogger("speechbrain").setLevel(logging.ERROR)

    MODEL_SR = 8000
    audio_8k = torchaudio.functional.resample(
        torch.from_numpy(audio).unsqueeze(0), sr, MODEL_SR
    )

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
        s  = torchaudio.functional.resample(
            torch.from_numpy(s8).unsqueeze(0), MODEL_SR, sr
        ).squeeze(0).numpy()

        # match length to input
        if len(s) > len(audio):   s = s[:len(audio)]
        elif len(s) < len(audio): s = np.pad(s, (0, len(audio) - len(s)))
        streams.append(s.astype(np.float32))

    return streams


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 4 – POST-PROCESS EACH STREAM
#   • second-pass denoising (stationary, removes SepFormer residual artifacts)
#   • Wiener-style spectral smoothing
#   • normalise to -1 dBFS
# ─────────────────────────────────────────────────────────────────────────────
def post_process(stream, sr):
    """Clean up each separated speaker stream."""
    import noisereduce as nr
    from scipy.signal import wiener

    # 1. Stationary denoise — removes residual cross-talk / SepFormer artifacts
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cleaned = nr.reduce_noise(
            y=stream, sr=sr,
            stationary=True,             # assume artifact noise is stationary
            prop_decrease=0.80,
            n_fft=512, win_length=512, hop_length=128,
            time_mask_smooth_ms=50, freq_mask_smooth_hz=500,
        )

    # 2. Wiener filter — smooths spectral irregularities
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        smoothed = wiener(cleaned, mysize=5).astype(np.float32)

    # 3. Normalise to -1 dBFS
    peak = np.max(np.abs(smoothed))
    if peak > 1e-6:
        smoothed = smoothed / peak * 0.891   # -1 dBFS
    return smoothed


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 5 – DECIDE HOW MANY REAL SPEAKERS  (energy-based, not clustering)
# ─────────────────────────────────────────────────────────────────────────────
def filter_real_streams(streams):
    """
    After SepFormer gives 2 outputs, decide if both are real speakers.
    Rule: if one stream is >14 dB quieter than the other → 1 speaker only.
    This handles the case where only 1 person was speaking.
    """
    rms = [20 * np.log10(np.sqrt(np.mean(s**2)) + 1e-10) for s in streams]
    max_rms = max(rms)
    real = [s for s, r in zip(streams, rms) if (max_rms - r) < 14.0]
    return real if real else [streams[0]]


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(ts)
    out_dir.mkdir(exist_ok=True)

    # ── Record ───────────────────────────────────────────────────────────────
    raw, sr = record()
    sf.write(out_dir / "raw_input.wav", raw, sr, subtype="PCM_16")

    # ── Light denoise the mix ─────────────────────────────────────────────
    print("● Denoising mix ...")
    mix_clean = light_denoise(raw, sr)
    sf.write(out_dir / "denoised_mix.wav", mix_clean, sr, subtype="PCM_16")

    # ── Separate (always 2 streams from libri2mix) ────────────────────────
    print("● Separating speakers ...")
    streams = separate(mix_clean, sr)

    # ── Filter out silent/fake streams ───────────────────────────────────
    streams = filter_real_streams(streams)
    n_real  = len(streams)

    # ── Post-process + save ───────────────────────────────────────────────
    print(f"● Post-processing {n_real} speaker stream(s) ...")
    for i, s in enumerate(streams, 1):
        enhanced = post_process(s, sr)
        out_path = out_dir / f"speaker_{i}.wav"
        sf.write(out_path, enhanced, sr, subtype="PCM_16")

    # ── Report ────────────────────────────────────────────────────────────
    print(f"\n  Speakers : {n_real}")
    print(f"  Folder   : {out_dir}/")
    for i in range(1, n_real + 1):
        a, _ = sf.read(str(out_dir / f"speaker_{i}.wav"), dtype="float32")
        rms  = 20 * np.log10(np.sqrt(np.mean(a**2)) + 1e-10)
        print(f"    speaker_{i}.wav  {rms:.1f} dBFS")
    print()


if __name__ == "__main__":
    main()
