"""
context_engine/wakeword_detector.py
=====================================
Simple, reliable exact-match wakeword detector.
Zero ML models — pure string matching.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
#  EXACT WAKEWORDS  (ordered longest-first so "hey canary" beats "canary")
# ─────────────────────────────────────────────────────────────────────────────
_WAKEWORDS: list[str] = [
    "hey canary",
    "hey, canary",
    "okay canary",
    "ok canary",
    "ok, canary",
    "canary",
]

# Common Whisper mis-transcriptions of "Canary"
_FUZZY_MAP: dict[str, float] = {
    "canry":   0.80,
    "canari":  0.80,
    "kenari":  0.70,
    "kanari":  0.70,
    "qanary":  0.70,
    "cannery": 0.65,
    "kennery": 0.65,
    "ganari":  0.65,
    "genari":  0.65,
    "konari":  0.65,
    "gonari":  0.60,
    "canery":  0.60,
}


def detect_wakeword(text: str) -> dict:
    """
    Detect whether the utterance contains a Canary wakeword.

    Returns
    -------
    {
        "wakeword":            bool,
        "wakeword_confidence": float,   # 1.0 exact  /  0.6–0.8 fuzzy  /  0.0 none
        "matched_phrase":      str | None
    }
    """
    lower = text.lower().strip()

    # ── Exact match ───────────────────────────────────────────────────────
    for phrase in _WAKEWORDS:
        if phrase in lower:
            return {
                "wakeword":            True,
                "wakeword_confidence": 1.0,
                "matched_phrase":      phrase,
            }

    # ── Fuzzy match (Whisper mis-transcription recovery) ──────────────────
    for token, conf in _FUZZY_MAP.items():
        if token in lower:
            return {
                "wakeword":            True,
                "wakeword_confidence": conf,
                "matched_phrase":      f"~{token}",
            }

    return {
        "wakeword":            False,
        "wakeword_confidence": 0.0,
        "matched_phrase":      None,
    }
