
from __future__ import annotations

import argparse
import re
import sys
import tempfile
import warnings
from itertools import permutations
from pathlib import Path

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import soundfile as sf

from run_canary import _run_separation, _reduce_crosstalk
from computation.audio.transcribe import transcribe

SR = 16000


def _norm(text: str) -> list[str]:
    text = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return text.split()


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


def _transcribe_array(audio: np.ndarray) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        sf.write(path, audio.astype(np.float32), SR, subtype="PCM_16")
        return transcribe(path, model_name="base").get("text", "")
    finally:
        try:
            Path(path).unlink()
        except OSError:
            pass


def _best_pair_wer(hyps: list[str], refs: list[str]) -> float:
    k = min(len(hyps), len(refs))
    best = 1e9
    for p in permutations(range(k)):
        best = min(best, float(np.mean([wer(refs[i], hyps[p[i]]) for i in range(k)])))
    return best


def _load(path: Path) -> np.ndarray:
    import librosa
    a, sr = sf.read(str(path), dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    if sr != SR:
        a = librosa.resample(a, orig_sr=sr, target_sr=SR)
    return a.astype(np.float32)


def run_librimix(n: int) -> None:
    base = ROOT / "models" / "MiniLibriMix" / "val"
    mix_dir, s1_dir, s2_dir = base / "mix_clean", base / "s1", base / "s2"
    if not mix_dir.exists():
        print("MiniLibriMix not found — run the SI-SNR setup first.")
        return

    files = sorted(mix_dir.glob("*.wav"))[:n]
    sep_wers, mix_wers = [], []
    print(f"WER eval on {len(files)} MiniLibriMix mixtures (real speech)...\n")

    for idx, mf in enumerate(files, 1):
        s1, s2 = s1_dir / mf.name, s2_dir / mf.name
        if not (s1.exists() and s2.exists()):
            continue
        mix = _load(mf)
        refs = [_transcribe_array(_load(s1)), _transcribe_array(_load(s2))]

        streams = _run_separation(mix, SR, n_mix=2)
        streams = _reduce_crosstalk(streams)
        hyps = [_transcribe_array(s) for s in streams]
        sep_wers.append(_best_pair_wer(hyps, refs))

        mix_txt = _transcribe_array(mix)
        mix_wers.append(min(wer(refs[0], mix_txt), wer(refs[1], mix_txt)))
        if idx % 5 == 0:
            print(f"  ...{idx}/{len(files)}", flush=True)

    print("\n" + "=" * 60)
    print(f"  WER — separation + ASR on MiniLibriMix ({len(sep_wers)} mix)")
    print("=" * 60)
    print(f"  raw mixture vs clean-source ASR : {np.mean(mix_wers)*100:6.1f} %")
    print(f"  separated  vs clean-source ASR : {np.mean(sep_wers)*100:6.1f} %  (lower = better)")
    print("=" * 60)
    print("  Reference = ASR on the clean isolated source (no dataset")
    print("  transcripts needed). Separation should reduce WER vs the raw mix.\n")


_TTS_SENTENCES = [
    "what is the weather today",
    "play some music please",
    "tell me the latest news",
    "turn off the living room lights",
    "set a timer for ten minutes",
    "what is the temperature outside",
    "stop the music",
    "remind me to call mom at six",
]


def run_tts() -> None:
    try:
        from gtts import gTTS
        import librosa
    except Exception as e:
        print(f"gTTS unavailable: {e}")
        return

    cache = ROOT / "data" / "wer_tts"
    cache.mkdir(parents=True, exist_ok=True)

    def synth(text: str) -> np.ndarray:
        mp3 = cache / (re.sub(r"\W+", "_", text)[:40] + ".mp3")
        if not mp3.exists():
            gTTS(text=text, lang="en").save(str(mp3))
        a, sr = librosa.load(str(mp3), sr=SR, mono=True)
        peak = float(np.max(np.abs(a))) + 1e-9
        return (a / peak * 0.9).astype(np.float32)

    wers = []
    print(f"WER eval on {len(_TTS_SENTENCES)//2} TTS 2-speaker mixtures...\n")
    pairs = list(zip(_TTS_SENTENCES[::2], _TTS_SENTENCES[1::2]))
    for t1, t2 in pairs:
        a1, a2 = synth(t1), synth(t2)
        L = min(len(a1), len(a2))
        a1, a2 = a1[:L], a2[:L]
        mix = a1 + a2
        mix = (mix / (np.max(np.abs(mix)) + 1e-9) * 0.9).astype(np.float32)
        streams = _run_separation(mix, SR, n_mix=2)
        streams = _reduce_crosstalk(streams)
        hyps = [_transcribe_array(s) for s in streams]
        print(f"\nREF: {t1} | {t2}")
        print(f"HYP: {hyps[0]} | {hyps[1]}")
        wers.append(_best_pair_wer(hyps, [t1, t2]))

    print("\n" + "=" * 60)
    print(f"  ABSOLUTE WER — TTS commands, separation + ASR")
    print("=" * 60)
    print(f"  WER : {np.mean(wers)*100:6.1f} %   (exact ground-truth text)")
    print("  Note: TTS speech is very clean, so this is an optimistic bound.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["librimix", "tts"], default="librimix")
    ap.add_argument("--n", type=int, default=10)
    args = ap.parse_args()
    if args.mode == "librimix":
        run_librimix(args.n)
    else:
        run_tts()
