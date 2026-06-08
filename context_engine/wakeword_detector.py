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
    "hello, canary",
    "hello canary",
    "okay canary",
    "hey, canary",
    "yo, canary",
    "ok, canary",
    "hey canary",
    "hi, canary",
    "ok canary",
    "yo canary",
    "hi canary",
    "canary",
]

# Common Whisper mis-transcriptions of "Canary"
_FUZZY_MAP: dict[str, float] = {
    # 0.80 Confidence: Extremely close phonetic/spelling variants
    "canari":     0.80,
    "canarie":    0.80,
    "canaries":   0.80,
    "canree":     0.80,
    "canry":      0.80,

    # 0.75 Confidence: Direct vowel shifts or common spelling distortions
    "canara":     0.75,
    "canaras":    0.75,
    "canaria":    0.75,
    "kanary":     0.75,
    "kannary":    0.75,
    "kenary":     0.75,
    "kennary":    0.75,

    # 0.70 Confidence: Consonant substitutions (K/Q)
    "kanari":     0.70,
    "kenari":     0.70,
    "qanari":     0.70,
    "qanary":     0.70,

    # 0.65 Confidence: Double consonant variations and G/C shifts
    "canere":     0.65,
    "canerie":    0.65,
    "canery":     0.65,
    "cannery":    0.65,
    "canneries":  0.65,
    "conary":     0.65,
    "conery":     0.65,
    "connery":    0.65,
    "ganari":     0.65,
    "ganery":     0.65,
    "genari":     0.65,
    "genery":     0.65,
    "kennery":    0.65,
    "kannery":    0.65,
    "konari":     0.65,
    "konary":     0.65,

    # 0.60 Confidence: More distant phonetic matches, similar sounding words, and split words
    "camari":     0.60,
    "camary":     0.60,
    "camry":      0.60,
    "can airy":   0.60,
    "can ali":    0.60,
    "can aly":    0.60,
    "can area":   0.60,
    "can areas":  0.60,
    "can early":  0.60,
    "can erase":  0.60,
    "can hurry":  0.60,
    "canali":     0.60,
    "canaly":     0.60,
    "cenari":     0.60,
    "cenary":     0.60,
    "ceneri":     0.60,
    "cranberries":0.60,
    "cranberry":  0.60,
    "ganary":     0.60,
    "genary":     0.60,
    "gonari":     0.60,
    "gonary":     0.60,
    "gonery":     0.60,
    "kanali":     0.60,
    "kanaly":     0.60,
    "kinari":     0.60,
    "kinary":     0.60,
    "kinery":     0.60,

    # 0.55 Confidence: Dropped initial consonant or very weak phonetic similarities
    "anari":      0.55,
    "anary":      0.55,
    "unari":      0.55,
    "unary":      0.55,
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
