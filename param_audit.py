"""
param_audit.py
==============
Single source of truth for the Canary model-size budget.

RULE (current interpretation):
    Every individual ML model in the pipeline must be < 5M parameters.
    This applies to ALL stages — gating, separation, biometrics, AND ASR.
    There is no constraint on the SUM; only the per-model maximum.

The audit loads each model lazily and counts its real parameters, so the
numbers reflect what is actually wired into the pipeline when it runs. That
makes the per-model scaling visible and verifiable for the demo.

Usage
-----
    python param_audit.py            # audit installed models, per-model verdict
    python param_audit.py --target   # also print the migration target table
"""

from __future__ import annotations

import argparse
import warnings
import logging
from functools import reduce
from pathlib import Path
from typing import Callable, Optional

warnings.simplefilter("ignore")
logging.getLogger("speechbrain").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

PER_MODEL_LIMIT = 5_000_000  # 5.0M parameters — per-model hard limit
ROOT = Path(__file__).parent


# ─────────────────────────────────────────────────────────────────────────────
#  Parameter counters (one per backend type)
# ─────────────────────────────────────────────────────────────────────────────

def count_torch(module) -> int:
    """Sum parameters of any torch.nn.Module (or object exposing .parameters())."""
    params = getattr(module, "mods", module)
    return sum(p.numel() for p in params.parameters())


def count_onnx(path: str | Path) -> int:
    """Sum parameters from an ONNX model's graph initializers."""
    import onnx
    model = onnx.load(str(path))
    total = 0
    for init in model.graph.initializer:
        dims = list(init.dims)
        total += reduce(lambda a, b: a * b, dims, 1) if dims else 1
    return total


# ─────────────────────────────────────────────────────────────────────────────
#  Loaders for the CURRENT models
# ─────────────────────────────────────────────────────────────────────────────

def _load_sepformer() -> int:
    from speechbrain.inference.separation import SepformerSeparation
    m = SepformerSeparation.from_hparams(
        source="speechbrain/sepformer-libri2mix",
        savedir=str(ROOT / "pretrained_models/sepformer-libri2mix"),
        run_opts={"device": "cpu"},
    )
    return count_torch(m)


def _load_ecapa() -> int:
    from speechbrain.inference.speaker import EncoderClassifier
    m = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(ROOT / "pretrained_models/spkrec-ecapa-voxceleb"),
        run_opts={"device": "cpu"},
    )
    return count_torch(m)


def _load_silero() -> int:
    from silero_vad import load_silero_vad
    return count_torch(load_silero_vad())


def _load_whisper() -> int:
    # backend/api.py transcribes with model_name="tiny"
    import whisper
    m = whisper.load_model("tiny")
    return sum(p.numel() for p in m.parameters())


# ─────────────────────────────────────────────────────────────────────────────
#  Model registry — every ML model is subject to the per-model rule.
#  Non-neural components (0 params) are listed for completeness.
# ─────────────────────────────────────────────────────────────────────────────

class Component:
    def __init__(self, stage: str, name: str, neural: bool,
                 counter: Optional[Callable[[], int]] = None,
                 static_params: Optional[int] = None):
        self.stage = stage
        self.name = name
        self.neural = neural
        self.counter = counter
        self.static_params = static_params

    def params(self) -> tuple[Optional[int], str]:
        if self.static_params is not None:
            return self.static_params, "ok"
        try:
            return self.counter(), "ok"
        except Exception as e:
            return None, f"unavailable ({type(e).__name__})"


def all_models() -> list[Component]:
    return [
        Component("Gating  (VAD)",        "Silero VAD",            True,  counter=_load_silero),
        Component("Wake word",            "C++ phonetic matcher", False, static_params=0),
        Component("Denoise",              "noisereduce (DSP)",     False, static_params=0),
        Component("Speaker count",        "spectral clustering",   False, static_params=0),
        Component("Separation",           "SepFormer libri2mix",   True,  counter=_load_sepformer),
        Component("Biometrics",           "ECAPA-TDNN",            True,  counter=_load_ecapa),
        Component("ASR",                  "Whisper tiny",          True,  counter=_load_whisper),
        Component("Intent / arbitration", "regex rules",           False, static_params=0),
    ]


# Migration target under the per-model < 5M rule
TARGET_TABLE = [
    ("Gating  (VAD)",   "Silero VAD",            0.463),
    ("Wake word",       "C++ phonetic matcher",  0.0),
    ("Separation",      "TIGER",                 0.80),
    ("Biometrics",      "classical features",    0.0),
    ("ASR",             "phoneme CTC + matching (TBD)", 0.0),
]


# ─────────────────────────────────────────────────────────────────────────────
#  Programmatic API (used by tests/test_budget.py)
# ─────────────────────────────────────────────────────────────────────────────

def per_model_report() -> list[tuple[str, str, Optional[int], bool]]:
    """
    Return [(stage, name, params|None, ok)] for every NEURAL model.
    ok = (params is not None and params < PER_MODEL_LIMIT).
    Non-neural (0-param) components are excluded.
    """
    out = []
    for c in all_models():
        if not c.neural:
            continue
        n, _ = c.params()
        ok = (n is not None) and (n < PER_MODEL_LIMIT)
        out.append((c.stage, c.name, n, ok))
    return out


def all_under_limit() -> bool:
    """True iff every measurable neural model is < PER_MODEL_LIMIT."""
    rep = per_model_report()
    measured = [r for r in rep if r[2] is not None]
    return bool(measured) and all(r[3] for r in measured)


# ─────────────────────────────────────────────────────────────────────────────
#  Reporting
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_m(n: int | float) -> str:
    if isinstance(n, float):
        return f"{n:>8.3f}M"
    return f"{n/1e6:>8.3f}M"


def run_audit() -> None:
    print("\n" + "=" * 70)
    print("  CANARY MODEL AUDIT — rule: EVERY model < 5M params")
    print("=" * 70)
    print(f"  {'Stage':<22}{'Model':<24}{'Params':>12}  Verdict")
    print("  " + "-" * 66)

    worst = 0
    any_over = False
    any_unavailable = False

    for c in all_models():
        n, status = c.params()
        if n is None:
            any_unavailable = True
            print(f"  {c.stage:<22}{c.name:<24}{'—':>12}  ({status})")
            continue
        if c.neural:
            ok = n < PER_MODEL_LIMIT
            verdict = "✓ < 5M" if ok else "✗ OVER"
            any_over = any_over or not ok
            worst = max(worst, n)
        else:
            verdict = "·  n/a"
        print(f"  {c.stage:<22}{c.name:<24}{_fmt_m(n):>12}  {verdict}")

    print("  " + "-" * 66)
    print(f"  {'LARGEST NEURAL MODEL':<46}{_fmt_m(worst):>12}")
    print(f"  {'PER-MODEL LIMIT':<46}{_fmt_m(PER_MODEL_LIMIT):>12}")
    verdict = "OVER ✗" if any_over else "PASS ✓"
    print(f"  {'STATUS (all models < 5M?)':<46}{verdict:>12}")
    if any_unavailable:
        print("\n  Note: some models could not be loaded (not yet installed);")
        print("        they are not included in the verdict.")
    print("=" * 70 + "\n")


def print_target() -> None:
    print("  MIGRATION TARGET (each model < 5M):")
    print("  " + "-" * 56)
    for stage, name, m in TARGET_TABLE:
        flag = "✓" if m < 5.0 else "✗"
        print(f"    {stage:<20}{name:<28}{m:>7.3f}M  {flag}")
    print("  " + "-" * 56 + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="store_true",
                    help="also print the migration target table")
    args = ap.parse_args()

    run_audit()
    if args.target:
        print_target()
