#!/usr/bin/env python3

import sys, time, datetime, warnings, threading, os
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path

# Suppress Hugging Face unauthenticated request warning
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
warnings.filterwarnings("ignore", message=".*unauthenticated.*")

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))  # project root → finds database/

SAMPLE_RATE = 16000
DURATION    = 7
MODEL_CACHE = "pretrained_models"


def record(sr=SAMPLE_RATE):
    from computation.audio.vad_segmenter import record_until_silence
    raw = record_until_silence(
        max_duration    = 15.0,
        silence_timeout = 1.8,
        sr              = sr,
    )
    return raw, sr


def _highpass(sig, cutoff=80.0, sr=SAMPLE_RATE):
    from scipy.signal import butter, sosfilt
    sos = butter(2, cutoff, btype="highpass", fs=sr, output="sos")
    return sosfilt(sos, sig)


def _presence_boost(sig, shelf_freq=2000.0, gain_db=3.5, sr=SAMPLE_RATE):
    from scipy.signal import butter, sosfilt
    shelf_gain = 10 ** (gain_db / 20.0)
    lp  = butter(2, shelf_freq, btype="lowpass", fs=sr, output="sos")
    lo  = sosfilt(lp, sig)
    hi  = sig - lo
    return lo + hi * shelf_gain


def _soft_compress(sig, threshold_db=-18.0, ratio=3.0, sr=SAMPLE_RATE):
    threshold  = 10 ** (threshold_db / 20.0)
    knee_db    = 6.0
    knee_lower = 10 ** ((threshold_db - knee_db / 2) / 20.0)
    knee_upper = 10 ** ((threshold_db + knee_db / 2) / 20.0)

    attack_coef  = np.exp(-1.0 / (0.005 * sr))
    release_coef = np.exp(-1.0 / (0.150 * sr))

    env    = 0.0
    gain   = 1.0
    out    = np.zeros_like(sig)

    for n, x in enumerate(sig):
        level = abs(x)
        if level > env:
            env = attack_coef  * env + (1 - attack_coef)  * level
        else:
            env = release_coef * env + (1 - release_coef) * level

        if env <= knee_lower:
            gain = 1.0
        elif env <= knee_upper:
            t    = (env - knee_lower) / (knee_upper - knee_lower)
            gain = 1.0 + (1.0 / ratio - 1.0) * t * t
        else:
            gain = (threshold / (env + 1e-10)) * (1.0 - 1.0 / ratio) + 1.0 / ratio

        out[n] = x * gain

    return out


def _normalize(sig, target_rms_db=-18.0, peak_limit_db=-1.0):
    rms = np.sqrt(np.mean(sig.astype(np.float64) ** 2))
    if rms < 1e-8:
        return sig
    gain_db = target_rms_db - 20.0 * np.log10(rms)
    gain    = 10 ** (gain_db / 20.0)
    sig     = sig * gain
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
    ref = reference.astype(np.float64) - np.mean(reference)
    est = estimate.astype(np.float64)  - np.mean(estimate)
    alpha  = np.dot(est, ref) / (np.dot(ref, ref) + 1e-10)
    target = alpha * ref
    noise  = est - target
    return float(10.0 * np.log10(
        (np.dot(target, target) + 1e-10) / (np.dot(noise, noise) + 1e-10)
    ))


def enhance_single(raw, sr):
    sig = raw.astype(np.float64)

    sig = _highpass(sig, cutoff=80.0, sr=sr)

    sig = _denoise(sig, sr,
                   prop_decrease=0.55,
                   stationary=False,
                   n_fft=2048, hop=512,
                   t_smooth=120, f_smooth=200).astype(np.float64)

    sig = _denoise(sig, sr,
                   prop_decrease=0.40,
                   stationary=False,
                   n_fft=1024, hop=256,
                   t_smooth=60, f_smooth=400).astype(np.float64)

    sig = _presence_boost(sig, shelf_freq=2000.0, gain_db=3.5, sr=sr)

    sig = _soft_compress(sig.astype(np.float32), threshold_db=-18.0,
                         ratio=3.0, sr=sr).astype(np.float64)

    sig = _normalize(sig)
    return sig.astype(np.float32)


def _light_denoise_for_sep(audio, sr):
    sig = _denoise(audio, sr,
                   prop_decrease=0.25,
                   stationary=False,
                   n_fft=2048, hop=512,
                   t_smooth=150, f_smooth=200)
    orig_peak = np.max(np.abs(audio))
    peak = np.max(np.abs(sig))
    if peak > 1e-6:
        sig = sig / peak * orig_peak
    return sig.astype(np.float32)


def _apply_vad_gate(audio: np.ndarray, sr: int, frame_ms: int = 30) -> np.ndarray:
    frame_len = max(1, int(sr * frame_ms / 1000))
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        return audio.copy()

    rms_frames = np.array([
        np.sqrt(np.mean(audio[i * frame_len:(i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    noise_floor = float(np.percentile(rms_frames, 10)) + 1e-10
    voiced_frames = rms_frames > noise_floor * 2.5

    gated_audio = audio.copy()
    for i, is_voiced in enumerate(voiced_frames):
        if not is_voiced:
            gated_audio[i * frame_len:(i + 1) * frame_len] = 0.0

    return gated_audio


_SEP_MODELS: dict = {}
_SEP_LOCK = threading.Lock()


def _get_separation_model(model_id: str):
    model = _SEP_MODELS.get(model_id)
    if model is not None:
        return model

    with _SEP_LOCK:
        model = _SEP_MODELS.get(model_id)
        if model is not None:
            return model

        import torch
        original_load = torch.load
        def _patched_load(*args, **kwargs):
            kwargs["weights_only"] = False
            return original_load(*args, **kwargs)
        torch.load = _patched_load
        try:
            from asteroid.models import BaseModel
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = BaseModel.from_pretrained(model_id)
                model.eval()
        finally:
            torch.load = original_load

        _SEP_MODELS[model_id] = model

    return model


def warmup_separation() -> None:
    _get_separation_model("JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k")


def _run_separation(audio, sr, n_mix: int = 2):
    from computation.audio.separator import separate_waveform, _MODEL_SR
    import torch, torchaudio
    frame = max(1, int(sr * 0.030))
    nf = len(audio) // frame
    if nf >= 2:
        rms = np.array([np.sqrt(np.mean(audio[i*frame:(i+1)*frame]**2)) for i in range(nf)])
        snr_db = 20.0 * np.log10((np.percentile(rms, 90) + 1e-10) / (np.percentile(rms, 25) + 1e-10))
        variant = "noisy" if snr_db < 18.0 else "clean"
    else:
        variant = "clean"
    work = audio.astype(np.float32)
    if sr != _MODEL_SR:
        work = torchaudio.functional.resample(
            torch.from_numpy(work).unsqueeze(0), sr, _MODEL_SR
        ).squeeze(0).numpy()
    streams_16k = separate_waveform(work, variant=variant, device="cpu")
    streams = []
    for s in streams_16k:
        if _MODEL_SR != sr:
            s = torchaudio.functional.resample(
                torch.from_numpy(s).unsqueeze(0), _MODEL_SR, sr
            ).squeeze(0).numpy()
        if len(s) > len(audio):    s = s[:len(audio)]
        elif len(s) < len(audio):  s = np.pad(s, (0, len(audio) - len(s)))
        streams.append(s.astype(np.float32))
    return streams


def mixture_consistency_scaled(streams: list, mix) -> list:
    n = len(streams)
    if n < 2:
        return streams
    L = min(len(mix), min(len(s) for s in streams))
    m = mix[:L].astype(np.float64)
    st = [s[:L].astype(np.float64) for s in streams]
    S = np.sum(st, axis=0)
    g = float(np.dot(m, S) / (np.dot(S, S) + 1e-10))
    st = [g * s for s in st]
    residual = (m - np.sum(st, axis=0)) / n
    out = [(s + residual).astype(np.float32) for s in st]
    fixed = []
    for orig, proj in zip(streams, out):
        if len(orig) > L:
            proj = np.concatenate([proj, orig[L:].astype(np.float32)])
        fixed.append(proj.astype(np.float32))
    return fixed


def wiener_reextract(streams: list, mix, sr: int = 16000) -> list:
    """Re-extract sources from the mixture STFT using Wiener-style masks
    derived from the ConvTasNet estimates. Preserves the original phase
    and drastically suppresses cross-talk artifacts."""
    from scipy.signal import stft as _stft, istft as _istft
    n_fft = 1024
    hop = 256
    L = min(len(mix), min(len(s) for s in streams))
    _, _, mix_Z = _stft(mix[:L].astype(np.float64), fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
    est_mags = []
    for s in streams:
        _, _, Z = _stft(s[:L].astype(np.float64), fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
        est_mags.append(np.abs(Z))
    total_mag = sum(est_mags) + 1e-10
    result = []
    for mag in est_mags:
        mask = np.clip(mag / total_mag, 0.0, 1.0)
        _, extracted = _istft(mix_Z * mask, fs=sr, nperseg=n_fft, noverlap=n_fft - hop)
        extracted = extracted.astype(np.float32)
        if len(extracted) > L:
            extracted = extracted[:L]
        elif len(extracted) < L:
            extracted = np.pad(extracted, (0, L - len(extracted)))
        result.append(extracted)
    return result


def _spectral_denoise_stream(stream, sr: int = 16000):
    """Aggressive spectral gating to suppress remaining crosstalk artifacts."""
    import noisereduce as nr
    denoised = nr.reduce_noise(
        y=stream.astype(np.float32),
        sr=sr,
        stationary=False,
        prop_decrease=0.6,
        n_fft=512,
        win_length=512,
        hop_length=128,
        time_mask_smooth_ms=50,
        freq_mask_smooth_hz=500,
    )
    return denoised.astype(np.float32)


def _speech_band_rms(audio, sr, lo=300, hi=3400):
    from scipy.signal import butter, sosfilt
    sos = butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    return float(np.sqrt(np.mean(sosfilt(sos, audio.astype(np.float64)) ** 2)))


def _reduce_crosstalk(streams: list) -> list:
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
    from computation.audio.separator import is_ghost_split

    mix     = _light_denoise_for_sep(raw, sr)
    streams = _run_separation(mix, sr, n_mix=2)

    if is_ghost_split(streams, sr):
        return 1, []

    corr  = float(np.corrcoef(streams[0], streams[1])[0, 1])
    sb    = [_speech_band_rms(s, sr) for s in streams]
    ratio = min(sb) / (max(sb) + 1e-10)

    if abs(corr) < 0.03:
        return 2, streams
    if abs(corr) > 0.80:
        return 1, []
    return (2, streams) if ratio >= 0.35 else (1, [])


def detect_and_separate_3spk(raw, sr):
    print("  (3-speaker mode: 2-source separation + ghost filter)")
    mix     = _light_denoise_for_sep(raw, sr)
    streams = _run_separation(mix, sr, n_mix=2)

    sb      = [_speech_band_rms(s, sr) for s in streams]
    max_sb  = max(sb) + 1e-10

    real = [(s, r) for s, r in zip(streams, sb) if r / max_sb >= 0.25]

    if not real:
        best = int(np.argmax(sb))
        real = [(streams[best], sb[best])]

    real_streams = [s for s, _ in real]
    return len(real_streams), real_streams


def enhance_stream(stream, sr):
    sig = stream.astype(np.float64)

    sig = _highpass(sig, cutoff=80.0, sr=sr)

    sig = _denoise(sig, sr,
                   prop_decrease=0.38,
                   stationary=False,
                   n_fft=1024, hop=256,
                   t_smooth=60, f_smooth=350).astype(np.float64)

    sig = _presence_boost(sig, shelf_freq=2000.0, gain_db=3.5, sr=sr)

    sig = _soft_compress(sig.astype(np.float32), threshold_db=-18.0,
                         ratio=3.0, sr=sr).astype(np.float64)

    sig = _normalize(sig)
    return sig.astype(np.float32)


def drs_shadow(raw: np.ndarray, sr: int, n_spk: int, streams: list) -> dict:
    frame_len = max(1, int(sr * 0.030))
    n_frames  = len(raw) // frame_len
    if n_frames > 0:
        frame_rms   = np.array([
            np.sqrt(np.mean(raw[i * frame_len:(i + 1) * frame_len] ** 2))
            for i in range(n_frames)
        ])
        noise_floor = float(np.percentile(frame_rms, 25)) + 1e-10
        speech_peak = float(np.percentile(frame_rms, 90)) + 1e-10
        raw_snr_db  = 20.0 * np.log10(speech_peak / noise_floor)
        noise_level = float(np.clip(1.0 - (raw_snr_db - 5.0) / 30.0, 0.0, 1.0))
    else:
        noise_level = 0.5

    if n_spk >= 2 and len(streams) >= 2:
        overlap_prob = _temporal_overlap(streams[0], streams[1], sr)
    else:
        overlap_prob = 0.0

    speaker_score = float(np.clip((n_spk - 1) / 2.0, 0.0, 1.0))

    complexity = (
        overlap_prob  * 0.5 +
        noise_level   * 0.3 +
        speaker_score * 0.2
    )

    reasons = []

    if overlap_prob > 0.7:
        reasons.append("Critical overlap detected (> 0.7).")
    elif overlap_prob > 0.2:
        reasons.append("Moderate overlap detected.")
    else:
        reasons.append("Low or no speech overlap.")

    if n_spk >= 3:
        reasons.append("Three or more speakers present.")
    elif n_spk == 2:
        reasons.append("Multiple speakers present.")
    else:
        reasons.append("Single speaker.")

    if noise_level > 0.8:
        reasons.append("Critical noise level detected (> 0.8).")
    elif noise_level > 0.35:
        reasons.append("Noticeable noise detected.")
    else:
        reasons.append("Noise below critical threshold.")

    if noise_level > 0.85:
        mode, label = "C", "High Interference · Heavy Noise"
        detail = "critical background noise (> 0.85)"
        icon   = "🔴"
        reasons.insert(0, "Hard Rule: Critical noise level (> 0.85) forced Mode C.")
    elif overlap_prob > 0.90 and noise_level > 0.40:
        mode, label = "C", "High Interference · Heavy Noise"
        detail = "critical speech overlap (> 0.90) with high noise (> 0.40)"
        icon   = "🔴"
        reasons.insert(0, "Hard Rule: Critical overlap (> 0.90) and high noise forced Mode C.")
    elif n_spk >= 3:
        mode, label = "C", "High Interference · Heavy Noise"
        detail = "3+ speakers detected"
        icon   = "🔴"
        reasons.insert(0, "Hard Rule: 3+ speakers forced Mode C.")
    else:
        if complexity < 0.25:
            mode, label = "A", "Clean Scene"
            detail = "1 speaker · low noise · pure turn-taking"
            icon   = "🟢"
        elif complexity < 0.70:
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


def main():
    OUTPUT_ROOT = Path("outputs")
    OUTPUT_ROOT.mkdir(exist_ok=True)

    ts      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / ts
    out_dir.mkdir(exist_ok=True)

    raw, sr = record()
    sf.write(out_dir / "raw_input.wav", raw, sr, subtype="PCM_16")

    raw_rms_db = 20.0 * np.log10(np.sqrt(np.mean(raw ** 2)) + 1e-10)
    if raw_rms_db < -55.0:
        print("\n  No audio detected — please speak closer to the mic.")
        out_dir.rmdir()
        return

    print("● Estimating speaker count ...")
    try:
        from computation.audio.speaker_counter import SpeakerCountEstimator
        estimator = SpeakerCountEstimator(sample_rate=sr, max_speakers=3)
        est_spk = estimator.estimate(raw)
        print(f"  Estimated speakers in scene: Caliberating....")
    except Exception as e:
        print(f"  [SpeakerCountEstimator] failed: {e}. Defaulting to 2-speaker detection.")
        est_spk = 2

    print("● Separating speaker streams ...")
    if est_spk >= 3:
        n_spk, streams = detect_and_separate_3spk(raw, sr)
    else:
        n_spk, streams = detect_and_separate(raw, sr)

    overlap_prob = 0.0
    if n_spk >= 2 and len(streams) >= 2:
        streams = _reduce_crosstalk(streams)
        streams = sorted(streams,
                         key=lambda s: _speech_band_rms(s, sr), reverse=True)
        print("  (cross-talk reduced · dominant speaker → speaker_1)")
        overlap_prob = _temporal_overlap(streams[0], streams[1], sr)

    if n_spk >= 2 and len(streams) >= 2:
        print("  Si-SNR vs mix:")
        for i, s in enumerate(streams, 1):
            score = si_snr(s, raw)
            print(f"    Speaker {i}: {score:+.1f} dB")

    if n_spk == 1:
        print("● 1 speaker — enhancing directly (no separation) ...")
        enhanced = enhance_single(raw, sr)
        sf.write(out_dir / "speaker_1.wav", enhanced, sr, subtype="PCM_16")
        saved = ["speaker_1.wav"]

    else:
        print(f"● {n_spk} speakers — enhancing each stream ...")
        saved = []
        for i, s in enumerate(streams, 1):
            enhanced = enhance_stream(s, sr)
            fname = f"speaker_{i}.wav"
            sf.write(out_dir / fname, enhanced, sr, subtype="PCM_16")
            saved.append(fname)

    print("\n● Transcribing speech to text ...")
    from computation.audio.transcribe import transcribe_and_save, pre_screen
    ready_speakers = []
    for fname in saved:
        wav_p = out_dir / fname
        screen = pre_screen(wav_p)
        tag    = fname.replace("speaker_", "Spk").replace(".wav", "")
        rms    = screen["rms_db"]
        ratio  = screen["speech_ratio"]

        if screen["verdict"] == "REJECTED":
            print(f"  ✗ {fname}  [RMS:{rms:.0f}dBFS | Speech:{ratio:.0%}]  → REJECTED ({screen['reason'].split('—')[1].strip()})")
            transcribe_and_save(wav_p)
        else:
            print(f"  ▶ {fname}  [RMS:{rms:.0f}dBFS | Speech:{ratio:.0%}]  → READY — transcribing ...", flush=True)
            text, status = transcribe_and_save(wav_p)
            if status == "SPEECH":
                preview = text[:80] + ("…" if len(text) > 80 else "")
                print(f"    ✓ [{tag}] {preview}")
                ready_speakers.append(fname)
            else:
                print(f"    ✗ [{tag}] {status} — transcript discarded")

    print()
    if ready_speakers:
        print(f"  ✓ Speakers ready for processing : {', '.join(ready_speakers)}")
    else:
        print("  ✗ No speaker streams passed quality gate")

    voice_ids = {}
    try:
        from computation.voice.ranker import identify_speakers, print_result
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

    print(f"\n  Speakers : {n_spk}")
    print(f"  Folder   : {out_dir}/")
    for fname in saved:
        a, _ = sf.read(str(out_dir / fname), dtype="float32")
        rms  = 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-10)
        txt  = fname.replace(".wav", ".txt")
        print(f"    {fname}  {rms:.1f} dBFS  → {txt}")
    print()

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

    try:
        from computation.intelligence import build_context
        build_context(out_dir, drs, n_spk, voice_ids=voice_ids)
    except Exception as _ctx_err:
        print(f"  [Context Engine] skipped — {_ctx_err}")


if __name__ == "__main__":
    main()

