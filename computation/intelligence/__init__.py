"""
computation.intelligence — The Canary Context Engine + User Arbitration Engine
===============================================================================
Converts raw pipeline outputs into a structured context.json and runs
the User Arbitration Engine to produce a priority-scored decision.

Public API
----------
    from computation.intelligence import build_context
    ctx = build_context(out_dir, drs, n_spk, voice_ids=voice_ids)
"""

from .context_builder    import build_context
from .arbitration_engine import arbitrate, print_arbitration

__all__ = ["build_context", "arbitrate", "print_arbitration"]
