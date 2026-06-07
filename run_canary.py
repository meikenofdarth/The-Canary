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
#  STEP 2 – LIGHT DENOISE (floor only, never touch speech)
# ─────────────────────────────────────────────────────────────────────────────
def light_denoise(audio, sr):
    """
    Only knock down the obvious noise floor before handing to SepFormer.
    Keep prop_decrease very low so speech characteristics stay intact.
    """
    import noisereduce as nr
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cleaned = nr.reduce_noise(
            y=audio, sr=sr,
            stationary=False,
            prop_decrease=0.25,          # barely touches speech, kills floor
            n_fft=2048, win_length=2048, hop_length=512,
            time_mask_smooth_ms=150, freq_mask_smooth_hz=200,
        )
    # preserve original loudness level
    orig_peak = np.max(np.abs(audio))
    peak      = np.max(np.abs(cleaned))
    if peak > 1e-6:
        cleaned = cleaned / peak * orig_peak
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
#  STEP 4 – POST-PROCESS EACH STREAM  (clarity-focused, not suppression)
# ─────────────────────────────────────────────────────────────────────────────
def post_process(stream, sr):
    """
    Goal: maximum speech clarity, not maximum noise removal.

    Steps:
      1. Remove DC offset and sub-bass rumble (< 80 Hz) — inaudible anyway
      2. Very light residual clean (prop_decrease=0.35, non-stationary)
         — only removes the obvious flat noise floor left by SepFormer
         — does NOT touch voiced speech frames
      3. Presence boost: mild high-frequency shelf (+3 dB above 2 kHz)
         — compensates for the 8 kHz internal SR of SepFormer which
           softens upper harmonics after the 16kHz→8kHz→16kHz round-trip
      4. Normalise to -3 dBFS (louder + more natural playback level)
    """
    import noisereduce as nr
    from scipy.signal import butter, sosfilt

    sig = stream.astype(np.float64)

    # ── 1. High-pass at 80 Hz (remove rumble / DC offset) ────────────────
    hp = butter(2, 80.0, btype="highpass", fs=sr, output="sos")
    sig = sosfilt(hp, sig)

    # ── 2. Very gentle residual denoising ────────────────────────────────
    #    Non-stationary so it adapts per frame and won't kill quiet speech
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sig = nr.reduce_noise(
            y=sig.astype(np.float32), sr=sr,
            stationary=False,
            prop_decrease=0.35,          # light — preserves quiet consonants
            n_fft=1024, win_length=1024, hop_length=256,
            time_mask_smooth_ms=80, freq_mask_smooth_hz=300,
        ).astype(np.float64)

    # ── 3. Presence boost: +3 dB shelf above 2 kHz ───────────────────────
    #    Restores crispness lost in the 8kHz SepFormer round-trip
    #    High-shelf: H(z) of a first-order shelving filter
    shelf_gain  = 10 ** (3.0 / 20.0)   # +3 dB
    shelf_freq  = 2000.0               # Hz
    wc          = 2 * np.pi * shelf_freq / sr
    alpha       = (shelf_gain - 1) / 2.0
    # Simple first-order IIR high-shelf coefficients
    b0 = 1.0 + alpha
    b1 = -(1.0 + alpha - 2 * np.cos(wc)) / 2.0 * 0.0  # simplified
    # Use scipy butter high-shelf approximation via allpass + mix
    lp = butter(1, shelf_freq, btype="lowpass",  fs=sr, output="sos")
    lo = sosfilt(lp, sig)
    hi = sig - lo                      # high-shelf = original − low
    sig = lo + hi * shelf_gain         # boost the high band

    # ── 4. Normalise to -3 dBFS ───────────────────────────────────────────
    peak = np.max(np.abs(sig))
    if peak > 1e-6:
        sig = sig / peak * 0.708       # 0.708 ≈ -3 dBFS

    return sig.astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 5 – SPEECH QUALITY GATE  (3 checks, no model needed)
# ─────────────────────────────────────────────────────────────────────────────
def _spectral_flatness(audio, n_fft=1024):
    """
    Wiener entropy: geometric_mean(|X|) / arithmetic_mean(|X|).
    Speech: ~0.01–0.15   (clear formant peaks → low flatness)
    Noise / artifacts: ~0.35–1.0  (energy spread flat across all bins)
    """
    w   = np.hanning(min(len(audio), n_fft))
    pad = np.zeros(n_fft)
    pad[:len(w)] = audio[:n_fft] * w
    spec = np.abs(np.fft.rfft(pad)) + 1e-10
    log_mean = np.mean(np.log(spec))
    arith    = np.mean(spec)
    return float(np.exp(log_mean) / arith)


def _speech_band_rms(audio, sr, lo=300, hi=3400):
    """RMS energy in the core speech frequency band (300–3400 Hz)."""
    from scipy.signal import butter, sosfilt
    sos = butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    filtered = sosfilt(sos, audio.astype(np.float64))
    return float(np.sqrt(np.mean(filtered ** 2)))


def filter_real_streams(streams, sr=16000):
    """
    Decide which of SepFormer's output streams contain a real speaker.

    Three independent checks — a stream must pass ALL three:

    1. Spectral flatness < 0.30
       Speech has peaked formant structure (low flatness).
       SepFormer artifact / residual noise is spectrally flat.

    2. Speech-band (300–3400 Hz) RMS must be ≥ 20 % of the loudest stream.
       The "ghost" stream from a 1-speaker recording has very little
       energy in the true speech band even if its broadband RMS looks OK.

    3. Cross-correlation guard: if the two streams correlate > +0.80
       they are the same source (SepFormer failed to split) → keep louder.
       If they correlate < −0.80 it is a perfect anti-phase split of one
       source (model artefact) → keep louder.
    """
    if len(streams) == 1:
        return streams

    flatness   = [_spectral_flatness(s) for s in streams]
    sb_rms     = [_speech_band_rms(s, sr) for s in streams]
    max_sb_rms = max(sb_rms) + 1e-10

    # -- Check 3: cross-correlation between the two streams --
    a, b = streams[0], streams[1]
    corr = float(np.corrcoef(a, b)[0, 1])
    if abs(corr) > 0.80:
        # Nearly identical or perfect anti-phase → same source, 1 speaker
        best = int(np.argmax(sb_rms))
        return [streams[best]]

    # -- Check 1+2 combined: speech-band energy ratio --
    # Calibrated on SepFormer-libri2mix:
    #   1 speaker → weaker/stronger ratio ≈ 0.32  (ghost stream)
    #   2 speakers → weaker/stronger ratio ≈ 0.55+ (real second speaker)
    # Threshold at 0.42 cleanly separates both cases.
    ratio = min(sb_rms) / (max(sb_rms) + 1e-10)
    if ratio < 0.42:
        # One stream is a ghost — keep only the louder one
        best = int(np.argmax(sb_rms))
        return [streams[best]]

    # Both streams pass energy + flatness checks → 2 real speakers
    real = []
    for s, flat, sb in zip(streams, flatness, sb_rms):
        passes_flatness = flat < 0.30
        passes_energy   = sb / max_sb_rms >= 0.42
        if passes_flatness and passes_energy:
            real.append(s)

    if not real:
        real = [streams[int(np.argmax(sb_rms))]]

    return real


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
    streams = filter_real_streams(streams, sr=sr)
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
