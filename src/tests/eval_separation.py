
from __future__ import annotations

import argparse
import sys
import warnings
from itertools import permutations
from pathlib import Path

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import soundfile as sf

from computation.audio.metrics import si_snr
from run_canary import (_run_separation, _reduce_crosstalk,
                        mixture_consistency_scaled as _mc_scaled)

EVAL_SR = 16000


def find_dataset(prefer_mix: str = "mix_clean") -> tuple[Path, Path, Path]:
    base = ROOT / "models" / "MiniLibriMix"
    if not base.exists():
        raise FileNotFoundError(f"{base} not found — download/extract MiniLibriMix first.")

    candidates = []
    for s1 in base.rglob("s1"):
        parent = s1.parent
        s2 = parent / "s2"
        if not s2.is_dir():
            continue
        mix = None
        for name in (prefer_mix, "mix_clean", "mix_both", "mix_single", "mix"):
            if (parent / name).is_dir():
                mix = parent / name
                break
        if mix is None:
            continue
        score = (("val" in str(parent).lower()) * 2) + (mix.name == prefer_mix)
        candidates.append((score, mix, s1, s2))

    if not candidates:
        raise FileNotFoundError(f"No (mix, s1, s2) triplet found under {base}")
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, mix, s1, s2 = candidates[0]
    return mix, s1, s2


def _load(path: Path) -> np.ndarray:
    import librosa
    a, sr = sf.read(str(path), dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    if sr != EVAL_SR:
        a = librosa.resample(a, orig_sr=sr, target_sr=EVAL_SR)
    return a.astype(np.float32)


def _match_len(arrs: list[np.ndarray], n: int) -> list[np.ndarray]:
    out = []
    for a in arrs:
        if len(a) > n:
            a = a[:n]
        elif len(a) < n:
            a = np.pad(a, (0, n - len(a)))
        out.append(a.astype(np.float32))
    return out


def best_perm_sisnr(streams: list[np.ndarray], refs: list[np.ndarray]) -> float:
    k = min(len(streams), len(refs))
    s = streams[:k]
    r = refs[:k]
    return max(float(np.mean([si_snr(s[i], r[p[i]]) for i in range(k)]))
               for p in permutations(range(k)))


def mixture_consistency(streams: list[np.ndarray], mix: np.ndarray) -> list[np.ndarray]:
    n = len(streams)
    if n == 0:
        return streams
    L = min(len(mix), min(len(s) for s in streams))
    mix = mix[:L]
    st = [s[:L] for s in streams]
    residual = (mix - np.sum(st, axis=0)) / n
    return [(s + residual).astype(np.float32) for s in st]


def mixture_consistency_scaled(streams: list[np.ndarray], mix: np.ndarray) -> list[np.ndarray]:
    return _mc_scaled(streams, mix)


def wiener_postfilter(streams: list[np.ndarray], mix: np.ndarray,
                      sr: int = EVAL_SR, n_fft: int = 512, hop: int = 128,
                      power: float = 2.0) -> list[np.ndarray]:
    import librosa
    L = min(len(mix), min(len(s) for s in streams))
    mix = mix[:L].astype(np.float32)
    st = [s[:L].astype(np.float32) for s in streams]

    Y = librosa.stft(mix, n_fft=n_fft, hop_length=hop)
    Ss = [librosa.stft(s, n_fft=n_fft, hop_length=hop) for s in st]
    mags = [np.abs(S) ** power for S in Ss]
    denom = np.sum(mags, axis=0) + 1e-8

    out = []
    for m in mags:
        mask = m / denom
        rec = librosa.istft(mask * Y, hop_length=hop, length=L)
        out.append(rec.astype(np.float32))
    return out


VARIANTS = ("raw", "+mixconsist", "+mixconsist2", "+crosstalk", "+both", "+wiener")


def apply_variant(name: str, streams: list[np.ndarray], mix: np.ndarray) -> list[np.ndarray]:
    if name == "raw":
        return streams
    if name == "+mixconsist":
        return mixture_consistency(streams, mix)
    if name == "+mixconsist2":
        return mixture_consistency_scaled(streams, mix)
    if name == "+crosstalk":
        return _reduce_crosstalk(streams)
    if name == "+both":
        return mixture_consistency_scaled(_reduce_crosstalk(streams), mix)
    if name == "+wiener":
        return wiener_postfilter(streams, mix)
    raise ValueError(name)


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64); b = b.astype(np.float64)
    d = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-10
    return float(np.dot(a, b) / d)


def separate_overlap_add(mix: np.ndarray, sr: int,
                         win_s: float = 3.0, hop_s: float = 1.5) -> list[np.ndarray]:
    W = int(win_s * sr)
    H = int(hop_s * sr)
    if len(mix) <= W:
        return _run_separation(mix, sr, n_mix=2)

    n_src = 2
    out = [np.zeros(len(mix), dtype=np.float64) for _ in range(n_src)]
    wsum = np.zeros(len(mix), dtype=np.float64)
    window = np.hanning(W)

    starts = list(range(0, len(mix) - W + 1, H))
    if starts[-1] != len(mix) - W:
        starts.append(len(mix) - W)

    prev_streams = None
    prev_start = 0
    for si in starts:
        seg = mix[si:si + W]
        streams = [s[:W] for s in _run_separation(seg, sr, n_mix=2)]
        if prev_streams is not None:
            ov = prev_start + W - si
            if ov > 0:
                a0, a1 = streams[0][:ov], streams[1][:ov]
                p0, p1 = prev_streams[0][W - ov:], prev_streams[1][W - ov:]
                if (_corr(a0, p1) + _corr(a1, p0)) > (_corr(a0, p0) + _corr(a1, p1)):
                    streams = [streams[1], streams[0]]
        for k in range(n_src):
            out[k][si:si + W] += streams[k] * window
        wsum[si:si + W] += window
        prev_streams, prev_start = streams, si

    wsum[wsum < 1e-8] = 1e-8
    return [(out[k] / wsum).astype(np.float32) for k in range(n_src)]


def main(n_mix_files: int, prefer_mix: str = "mix_clean", ola: bool = False) -> None:
    mix_dir, s1_dir, s2_dir = find_dataset(prefer_mix=prefer_mix)
    print(f"Dataset: {mix_dir.relative_to(ROOT)}  (s1={s1_dir.name}, s2={s2_dir.name})")

    mix_files = sorted(mix_dir.glob("*.wav"))[:n_mix_files]
    print(f"Evaluating {len(mix_files)} mixtures at {EVAL_SR} Hz "
          f"({'overlap-add' if ola else 'whole-clip'} inference) ...\n")

    agg_sisnr = {v: [] for v in VARIANTS}
    agg_sisnri = {v: [] for v in VARIANTS}

    for idx, mf in enumerate(mix_files, 1):
        s1 = s1_dir / mf.name
        s2 = s2_dir / mf.name
        if not (s1.exists() and s2.exists()):
            continue

        mix = _load(mf)
        refs = [_load(s1), _load(s2)]
        L = min(len(mix), *[len(r) for r in refs])
        mix = mix[:L]
        refs = _match_len(refs, L)

        mix_sisnr = best_perm_sisnr([mix, mix], refs)

        raw_streams = (separate_overlap_add(mix, EVAL_SR)
                       if ola else _run_separation(mix, EVAL_SR, n_mix=2))
        raw_streams = _match_len(raw_streams, L)

        for v in VARIANTS:
            streams = apply_variant(v, [s.copy() for s in raw_streams], mix)
            streams = _match_len(streams, L)
            val = best_perm_sisnr(streams, refs)
            agg_sisnr[v].append(val)
            agg_sisnri[v].append(val - mix_sisnr)

        if idx % 10 == 0:
            print(f"  ...{idx}/{len(mix_files)}", flush=True)

    print("\n" + "=" * 56)
    print(f"  SEPARATION EVAL — MiniLibriMix ({len(agg_sisnr['raw'])} mixtures)")
    print("=" * 56)
    print(f"  {'variant':<14}{'SI-SNR (dB)':>14}{'SI-SNRi (dB)':>16}")
    print("  " + "-" * 52)
    for v in VARIANTS:
        if not agg_sisnr[v]:
            continue
        print(f"  {v:<14}{np.mean(agg_sisnr[v]):>14.2f}{np.mean(agg_sisnri[v]):>16.2f}")
    print("=" * 56)
    print("  Targets: SI-SNR >25 clean / >18 noisy (<=2 spk)")
    print("  (SI-SNRi is the standard separation metric — improvement over the mixture)\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50, help="number of mixtures to evaluate")
    ap.add_argument("--mix", choices=["mix_clean", "mix_both"], default="mix_clean",
                    help="mix_clean (clean KPI) or mix_both (noisy KPI)")
    ap.add_argument("--ola", action="store_true",
                    help="use overlap-add windowed inference instead of whole-clip")
    args = ap.parse_args()
    main(args.n, prefer_mix=args.mix, ola=args.ola)
