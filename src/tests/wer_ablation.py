"""
Ablation study: find the best post-processing + ASR combo to minimise WER.

Strategies tested:
  A. Raw separation only (baseline)
  B. Separation + spectral denoise (noisereduce)
  C. Separation + Wiener mask re-extraction from mixture STFT
  D. Separation + Wiener mask + denoise
  E. Each of the above x Whisper {tiny, base}
"""
from __future__ import annotations

import re, sys, warnings, time
from itertools import permutations
from pathlib import Path

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import noisereduce as nr

SR = 16000


# --- helpers ---------------------------------------------------------------
def _norm(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", (text or "").lower()).split()


def wer(ref: str, hyp: str) -> float:
    r, h = _norm(ref), _norm(hyp)
    if not r:
        return 0.0 if not h else 1.0
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[len(r)][len(h)] / len(r)


def _best_pair_wer(hyps, refs):
    k = min(len(hyps), len(refs))
    best = 1e9
    for p in permutations(range(k)):
        best = min(best, float(np.mean([wer(refs[i], hyps[p[i]]) for i in range(k)])))
    return best


# --- ASR -------------------------------------------------------------------
_whisper_cache = {}

def _load_whisper(model_name):
    if model_name not in _whisper_cache:
        import whisper
        _whisper_cache[model_name] = whisper.load_model(model_name)
    return _whisper_cache[model_name]


def _transcribe(audio, model_name="tiny"):
    model = _load_whisper(model_name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = model.transcribe(
            audio.astype(np.float32),
            language="en",
            task="transcribe",
            beam_size=5,
            best_of=5,
            temperature=0.0,
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            no_speech_threshold=0.5,
            condition_on_previous_text=False,
            verbose=False,
            fp16=False,
        )
    return result.get("text", "").strip()


# --- separation ------------------------------------------------------------
from run_canary import _run_separation


# --- post-processing strategies -------------------------------------------
def _spectral_denoise(stream):
    denoised = nr.reduce_noise(
        y=stream.astype(np.float32),
        sr=SR,
        stationary=False,
        prop_decrease=0.6,
        n_fft=512,
        win_length=512,
        hop_length=128,
        time_mask_smooth_ms=50,
        freq_mask_smooth_hz=500,
    )
    return denoised.astype(np.float32)


def _wiener_reextract(streams, mix):
    from scipy.signal import stft as _stft, istft as _istft
    n_fft = 1024
    hop = 256
    L = min(len(mix), min(len(s) for s in streams))

    _, _, mix_Z = _stft(mix[:L].astype(np.float64), fs=SR, nperseg=n_fft, noverlap=n_fft - hop)

    est_mags = []
    for s in streams:
        _, _, Z = _stft(s[:L].astype(np.float64), fs=SR, nperseg=n_fft, noverlap=n_fft - hop)
        est_mags.append(np.abs(Z))

    total_mag = sum(est_mags) + 1e-10

    result = []
    for mag in est_mags:
        mask = np.clip(mag / total_mag, 0.0, 1.0)
        extracted_Z = mix_Z * mask
        _, extracted = _istft(extracted_Z, fs=SR, nperseg=n_fft, noverlap=n_fft - hop)
        extracted = extracted.astype(np.float32)
        if len(extracted) > L:
            extracted = extracted[:L]
        elif len(extracted) < L:
            extracted = np.pad(extracted, (0, L - len(extracted)))
        result.append(extracted)
    return result


def _highpass_filter(audio, cutoff=100.0):
    from scipy.signal import butter, sosfilt
    sos = butter(4, cutoff, btype="highpass", fs=SR, output="sos")
    return sosfilt(sos, audio.astype(np.float64)).astype(np.float32)


def _normalize_peak(audio, target=0.9):
    peak = float(np.max(np.abs(audio)))
    if peak > 1e-6:
        return (audio / peak * target).astype(np.float32)
    return audio


STRATEGIES = {
    "A_raw":             lambda streams, mix: streams,
    "B_denoise":         lambda streams, mix: [_spectral_denoise(s) for s in streams],
    "C_wiener":          lambda streams, mix: _wiener_reextract(streams, mix),
    "D_wiener+denoise":  lambda streams, mix: [_spectral_denoise(s) for s in _wiener_reextract(streams, mix)],
    "E_denoise+wiener":  lambda streams, mix: _wiener_reextract([_spectral_denoise(s) for s in streams], mix),
}


# --- TTS data --------------------------------------------------------------
_TTS_SENTENCES = [
    "stop the music",
    "remind me to call mom at six",
]


def _synth_pairs():
    from gtts import gTTS
    import librosa

    cache = ROOT / "data" / "wer_tts"
    cache.mkdir(parents=True, exist_ok=True)

    def synth(text):
        mp3 = cache / (re.sub(r"\W+", "_", text)[:40] + ".mp3")
        if not mp3.exists():
            gTTS(text=text, lang="en").save(str(mp3))
        a, sr = librosa.load(str(mp3), sr=SR, mono=True)
        peak = float(np.max(np.abs(a))) + 1e-9
        return (a / peak * 0.9).astype(np.float32)

    pairs = []
    for t1, t2 in zip(_TTS_SENTENCES[::2], _TTS_SENTENCES[1::2]):
        a1, a2 = synth(t1), synth(t2)
        L = min(len(a1), len(a2))
        a1, a2 = a1[:L], a2[:L]
        mix = a1 + a2
        mix = (mix / (np.max(np.abs(mix)) + 1e-9) * 0.9).astype(np.float32)
        pairs.append((t1, t2, mix))
    return pairs


def main():
    pairs = _synth_pairs()

    whisper_models = ["tiny", "base"]

    print("Separating mixtures ...\n")
    separated = []
    for t1, t2, mix in pairs:
        streams = _run_separation(mix, SR, n_mix=2)
        separated.append((t1, t2, mix, streams))

    results = {}
    for strat_name, strat_fn in STRATEGIES.items():
        for wmodel in whisper_models:
            key = f"{strat_name} | whisper-{wmodel}"
            print(f"\n{'='*60}")
            print(f"  Testing: {key}")
            print(f"{'='*60}")

            pair_wers = []
            t0 = time.time()
            for t1, t2, mix, streams in separated:
                processed = strat_fn([s.copy() for s in streams], mix)
                processed = [_normalize_peak(_highpass_filter(s)) for s in processed]
                hyps = [_transcribe(s, model_name=wmodel) for s in processed]
                pw = _best_pair_wer(hyps, [t1, t2])
                pair_wers.append(pw)
                print(f"  REF: {t1} | {t2}")
                print(f"  HYP: {hyps[0]} | {hyps[1]}")
                print(f"  WER: {pw*100:.1f}%\n")

            elapsed = time.time() - t0
            avg_wer = float(np.mean(pair_wers))
            results[key] = avg_wer
            print(f"  -> AVG WER: {avg_wer*100:.1f}%  ({elapsed:.1f}s)")

    print(f"\n\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    for key, v in sorted(results.items(), key=lambda x: x[1]):
        bar = "#" * int(v * 50)
        print(f"  {v*100:5.1f}% | {key:40s} {bar}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
