"""
context_engine — The Canary Context Engine
==========================================
Converts raw pipeline outputs into a structured context.json.

Public API
----------
    from context_engine import build_context
    ctx = build_context(out_dir, drs, n_spk)
"""

from .context_builder import build_context

__all__ = ["build_context"]
