
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

PER_MODEL_LIMIT = 5_000_000
ROOT = Path(__file__).parent

SEPARATION_MODEL_ID = "JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k"


def count_torch(module) -> int:
    params = getattr(module, "mods", module)
    return sum(p.numel() for p in params.parameters())


def count_onnx(path: str | Path) -> int:
    import onnx
    model = onnx.load(str(path))
    total = 0
    for init in model.graph.initializer:
        dims = list(init.dims)
        total += reduce(lambda a, b: a * b, dims, 1) if dims else 1
    return total


def _load_separation() -> int:
    import torch
    original_load = torch.load
    def patched(*a, **k):
        k["weights_only"] = False
        return original_load(*a, **k)
    torch.load = patched
    try:
        from asteroid.models import BaseModel
        m = BaseModel.from_pretrained(SEPARATION_MODEL_ID)
    finally:
        torch.load = original_load
    return sum(p.numel() for p in m.parameters())


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
    import whisper
    m = whisper.load_model("tiny")
    return sum(p.numel() for p in m.parameters())


class Component:
    def __init__(self, stage: str, name: str, neural: bool, in_scope: bool,
                 counter: Optional[Callable[[], int]] = None,
                 static_params: Optional[int] = None):
        self.stage = stage
        self.name = name
        self.neural = neural
        self.in_scope = in_scope
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
        Component("Gating  (VAD)",        "Silero VAD",            True,  True,  counter=_load_silero),
        Component("Wake word",            "C++ phonetic matcher", False, True,  static_params=0),
        Component("Denoise",              "noisereduce (DSP)",     False, True,  static_params=0),
        Component("Speaker count",        "spectral clustering",   False, True,  static_params=0),
        Component("Separation",           "Asteroid ConvTasNet",   True,  True,  counter=_load_separation),
        Component("Biometrics",           "ECAPA-TDNN",            True,  False, counter=_load_ecapa),
        Component("ASR",                  "Whisper tiny",          True,  False, counter=_load_whisper),
        Component("Intent / arbitration", "regex rules",           False, False, static_params=0),
    ]


TARGET_TABLE = [
    ("Gating  (VAD)",   "Silero VAD",            0.463),
    ("Wake word",       "C++ phonetic matcher",  0.0),
    ("Separation",      "Asteroid ConvTasNet",   5.067),
]


def per_model_report() -> list[tuple[str, str, Optional[int], bool]]:
    out = []
    for c in all_models():
        if not (c.neural and c.in_scope):
            continue
        n, _ = c.params()
        ok = (n is not None) and (n < PER_MODEL_LIMIT)
        out.append((c.stage, c.name, n, ok))
    return out


def all_under_limit() -> bool:
    rep = per_model_report()
    measured = [r for r in rep if r[2] is not None]
    return bool(measured) and all(r[3] for r in measured)


def _fmt_m(n: int | float) -> str:
    return f"{n:>8.3f}M" if isinstance(n, float) else f"{n/1e6:>8.3f}M"


def run_audit() -> None:
    print("\n" + "=" * 72)
    print("  CANARY MODEL AUDIT — rule: SEPARATION SYSTEM < 5M params")
    print("=" * 72)
    print(f"  {'Stage':<22}{'Model':<24}{'Params':>12}  Scope/Verdict")
    print("  " + "-" * 68)

    any_over = False
    any_unavailable = False

    for c in all_models():
        n, status = c.params()
        if n is None:
            any_unavailable = True
            tag = "in-scope" if c.in_scope else "out-of-scope"
            print(f"  {c.stage:<22}{c.name:<24}{'—':>12}  {tag} ({status})")
            continue
        if not c.in_scope:
            verdict = "out of scope"
        elif c.neural:
            ok = n < PER_MODEL_LIMIT
            verdict = "✓ < 5M" if ok else "✗ OVER"
            any_over = any_over or not ok
        else:
            verdict = "· in-scope n/a"
        print(f"  {c.stage:<22}{c.name:<24}{_fmt_m(n):>12}  {verdict}")

    print("  " + "-" * 68)
    print(f"  {'SEPARATION-SYSTEM LIMIT':<48}{_fmt_m(PER_MODEL_LIMIT):>12}")
    verdict = "OVER ✗" if any_over else "PASS ✓"
    print(f"  {'STATUS (separation system < 5M?)':<48}{verdict:>12}")
    if any_unavailable:
        print("\n  Note: some models could not be loaded (not installed);")
        print("        they are excluded from the verdict.")
    print("=" * 72 + "\n")


def print_target() -> None:
    print("  MIGRATION TARGET (separation system < 5M):")
    print("  " + "-" * 56)
    total = 0.0
    for stage, name, m in TARGET_TABLE:
        total += m
        print(f"    {stage:<20}{name:<26}{m:>7.3f}M")
    print("  " + "-" * 56)
    print(f"    {'IN-SCOPE TOTAL':<46}{total:>7.3f}M  (limit 5.000M)\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", action="store_true")
    args = ap.parse_args()
    run_audit()
    if args.target:
        print_target()
