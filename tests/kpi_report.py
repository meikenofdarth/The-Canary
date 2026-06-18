"""
tests/kpi_report.py
==================
Performance harness for before/after comparison across model swaps.

Measures the KPIs that the swaps could affect, on fixed fixtures, so you can
run it once on the baseline (SepFormer + ECAPA) and again after each swap
(TIGER / CAM++) and compare apples to apples.

Reports:
  1. SEPARATION  — SI-SNR (dB) of separated streams vs ground-truth references,
                   using the best stream<->reference permutation.
  2. xRT         — real-time factor of the separation call (target < 0.5).
  3. SPEAKER ID  — identify() result on each clean reference clip.

Run:
    python tests/build_fixtures.py      # once, to create fixtures
    python tests/kpi_report.py          # baseline, then re-run after each swap
"""

from __future__ import annotations

import sys
import time
import warnings
from itertools import permutations
from pathlib import Path

import numpy as np
import soundfile as sf

warnings.simplefilter("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from computation.audio.metrics import si_snr  # noqa: E402

FIX = ROOT / "data" / "test_audio"
SR = 16_000


def _read(name: str) -> np.ndarray:
    audio, _ = sf.read(str(FIX / name), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32)


def _best_permutation_si_snr(streams: list[np.ndarray],
                             refs: list[np.ndarray]) -> float:
    """Average SI-SNR under the best stream->reference assignment."""
    k = min(len(streams), len(refs))
    streams = streams[:k]
    refs = refs[:k]
    best = -1e9
    for perm in permutations(range(k)):
        vals = [si_snr(streams[i], refs[perm[i]]) for i in range(k)]
        best = max(best, float(np.mean(vals)))
    return best


def test_separation_and_xrt() -> None:
    print("\n[1] SEPARATION + xRT")
    mix = _read("mix.wav")
    refs = [_read("ref_a.wav"), _read("ref_b.wav")]
    dur = len(mix) / SR

    # Route through the SAME entry point the backend uses.
    from run_canary import detect_and_separate

    t0 = time.perf_counter()
    n_spk, streams = detect_and_separate(mix, SR)
    elapsed = time.perf_counter() - t0

    if not streams:
        print("    separator returned 1 speaker (no streams) — check mix")
        return

    sisnr = _best_permutation_si_snr(streams, refs)
    xrt = elapsed / dur
    print(f"    n_speakers detected : {n_spk}")
    print(f"    SI-SNR (best perm)  : {sisnr:6.2f} dB   (target >25 clean / >10 dense)")
    print(f"    elapsed             : {elapsed:6.2f} s for {dur:.2f}s audio")
    print(f"    xRT                 : {xrt:6.3f}        (target < 0.5)")


def test_speaker_id() -> None:
    print("\n[2] SPEAKER ID (clean reference clips)")
    from computation.voice.ranker import identify
    from computation.voice.matcher import _load_profiles

    profiles = _load_profiles()
    print(f"    enrolled profiles: {list(profiles.keys())}")
    for name in ("ref_a.wav", "ref_b.wav"):
        audio = _read(name)
        res = identify(audio, SR, profiles=profiles)
        print(f"    {name:<12} -> {res['speaker']:<14} "
              f"conf={res['confidence']:.3f} margin={res['margin']:.3f}")


if __name__ == "__main__":
    if not (FIX / "mix.wav").exists():
        print("Fixtures missing. Run: python tests/build_fixtures.py")
        sys.exit(1)
    test_separation_and_xrt()
    test_speaker_id()
    print("\nDone. Re-run this after each swap and compare the numbers above.\n")
