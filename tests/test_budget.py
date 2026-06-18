"""
tests/test_budget.py
====================
HARD GATE: every individual ML model must be strictly under 5M parameters.

The rule applies to ALL stages — gating, separation, biometrics, AND ASR.
There is no constraint on the sum, only the per-model maximum.

This stays RED until SepFormer, ECAPA, and the ASR model are each replaced
with a sub-5M model (or a 0-param classical method). Run after every swap:

    pytest tests/test_budget.py -v -s
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import param_audit

LIMIT = param_audit.PER_MODEL_LIMIT


def test_every_model_under_5m():
    report = param_audit.per_model_report()

    print("\n  Per-model parameter audit (rule: each < 5M):")
    offenders = []
    for stage, name, n, ok in report:
        if n is None:
            print(f"    {stage:<22}{name:<26}{'unavailable':>12}")
            continue
        flag = "✓" if ok else "✗ OVER"
        print(f"    {stage:<22}{name:<26}{n/1e6:>8.3f}M  {flag}")
        if not ok:
            offenders.append(f"{name} ({n/1e6:.3f}M)")

    assert not offenders, (
        "These models exceed the 5M per-model limit: " + ", ".join(offenders)
    )


def test_models_are_actually_measured():
    """Guard against a false pass where models silently failed to load."""
    report = param_audit.per_model_report()
    measured = [r for r in report if r[2] is not None]
    assert measured, "No neural models could be measured — audit not trustworthy."
