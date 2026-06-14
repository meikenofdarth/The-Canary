"""
context_engine/wakeword_detector.py
=====================================
Weighted Phonetic Wakeword Detector.

Default mode (Canary):
    Exact match against _CANARY_WAKEWORDS + fallback to _CANARY_FUZZY_MAP.
    Zero external dependencies. Works out-of-the-box, unchanged from before.

Custom wakeword mode (after running change_wakeword.py):
    Loads wakeword/wakeword_config.json written by the C++ engine.
    Uses the pre-computed lookup_table for O(1) fast dict lookup.
    For novel tokens not in the table: calls the C++ binary via subprocess
    for a live weighted-DP similarity score.

Architecture:
    Hot path  → dict lookup  (< 1 µs)
    Cold path → C++ subprocess (< 5 ms, only for unseen tokens)

How to trigger custom mode:
    python3 change_wakeword.py        ← records + builds wakeword_config.json
    python3 change_wakeword.py --reset ← deletes config, reverts to Canary
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  CANARY DEFAULTS  (unchanged — these run when no custom config is present)
# ─────────────────────────────────────────────────────────────────────────────
_CANARY_WAKEWORDS: list[str] = [
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
_CANARY_FUZZY_MAP: dict[str, float] = {
    # 0.80 — extremely close phonetic/spelling variants
    "canari":      0.80,
    "canarie":     0.80,
    "canaries":    0.80,
    "canree":      0.80,
    "canry":       0.80,
    # 0.75 — direct vowel shifts / common distortions
    "canara":      0.75,
    "canaras":     0.75,
    "canaria":     0.75,
    "kanary":      0.75,
    "kannary":     0.75,
    "kenary":      0.75,
    "kennary":     0.75,
    # 0.70 — consonant substitutions (K/Q)
    "kanari":      0.70,
    "kenari":      0.70,
    "qanari":      0.70,
    "qanary":      0.70,
    # 0.65 — double consonant / G/C shifts
    "canere":      0.65,
    "canerie":     0.65,
    "canery":      0.65,
    "cannery":     0.65,
    "canneries":   0.65,
    "conary":      0.65,
    "conery":      0.65,
    "connery":     0.65,
    "ganari":      0.65,
    "ganery":      0.65,
    "genari":      0.65,
    "genery":      0.65,
    "kennery":     0.65,
    "kannery":     0.65,
    "konari":      0.65,
    "konary":      0.65,
    # 0.60 — more distant phonetic matches
    "camari":      0.60,
    "camary":      0.60,
    "camry":       0.60,
    "can airy":    0.60,
    "can ali":     0.60,
    "can aly":     0.60,
    "can area":    0.60,
    "can areas":   0.60,
    "can early":   0.60,
    "can erase":   0.60,
    "can hurry":   0.60,
    "canali":      0.60,
    "canaly":      0.60,
    "cenari":      0.60,
    "cenary":      0.60,
    "ceneri":      0.60,
    "cranberries": 0.60,
    "cranberry":   0.60,
    "ganary":      0.60,
    "genary":      0.60,
    "gonari":      0.60,
    "gonary":      0.60,
    "gonery":      0.60,
    "kanali":      0.60,
    "kanaly":      0.60,
    "kinari":      0.60,
    "kinary":      0.60,
    "kinery":      0.60,
    # 0.55 — dropped initial consonant / weak phonetic match
    "anari":       0.55,
    "anary":       0.55,
    "unari":       0.55,
    "unary":       0.55,
    # ── C++ Weighted Phonetic Engine scored variants ─────────────────────
    # Scores from: ./wakeword/build/wakeword_matcher --benchmark canary
    # These override the old conservative 0.65 scores above
    "cannery":     0.979,   # /kænəri/ → double-n + er, very common mishear
    "canerie":     0.975,
    "canere":      0.975,
    "cenary":      0.983,   # c+a→ce vowel shift
    "kennedy":     0.807,   # can→ken (c→k, a→e) + ary→edy  (accent + vowel)
    "kinnedy":     0.775,
    "cannedy":     0.790,
    "conary":      0.975,
    "konary":      0.975,
    "cinary":      0.975,
    "ganary":      0.975,
    "qanary":      0.983,
    "qannary":     0.971,
    "canarry":     0.971,
    "canarey":     0.979,
    "kanarey":     0.971,
    "kanarie":     0.971,
    "kanneri":     0.971,
    "kenery":      0.950,
    "kenari":      0.950,
    "kenarie":     0.940,
    "kenary":      0.975,   # already above at 0.75 — raise to engine score
    "cannary":     0.986,   # double-n: "canary"→"cannary"
    "kannary":     0.979,   # k+double-n
    "kannery":     0.971,
    "kennery":     0.971,
    "kennary":     0.971,
    "canory":      0.975,
    "kanory":      0.971,
    "cenery":      0.950,
    "qaneri":      0.975,
    "kaneri":      0.971,
}


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOM CONFIG LOADER
#  Reads wakeword/wakeword_config.json written by change_wakeword.py.
#  Falls back to default_wakeword_config.json in the root directory.
# ─────────────────────────────────────────────────────────────────────────────
_CONFIG_PATH   = Path(__file__).parent.parent / "wakeword" / "wakeword_config.json"
_DEFAULT_PATH  = Path(__file__).parent.parent.parent / "default_wakeword_config.json"
_BINARY_PATH   = Path(__file__).parent.parent / "wakeword" / "build" / "wakeword_matcher"

def _load_custom_config() -> dict | None:
    """
    Load wakeword_config.json from the custom path if it exists.
    Otherwise, fall back to default_wakeword_config.json in the root directory.
    """
    path = _CONFIG_PATH if _CONFIG_PATH.exists() else _DEFAULT_PATH
    if not path.exists():
        return None
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        word = cfg.get("word", "").strip().lower()
        if not word:
            return None
        return cfg
    except Exception:
        return None


def _build_custom_wakewords(word: str) -> list[str]:
    """
    Build the exact-match wakeword list for a custom word.
    Covers common greeting prefixes (hey, ok, hi, hello, yo).
    """
    prefixes = ["hey", "ok", "hi", "hello", "yo", "okay", "hey,",
                "ok,", "hi,", "yo,", "hello,", "okay,"]
    phrases = [word]
    for p in prefixes:
        phrases.append(f"{p} {word}")
    # longest-first so prefix variants don't shadow the bare word
    phrases.sort(key=len, reverse=True)
    return phrases


# ─────────────────────────────────────────────────────────────────────────────
#  MODULE-LEVEL INIT  (runs once on import)
# ─────────────────────────────────────────────────────────────────────────────
_custom_cfg = _load_custom_config()

if _custom_cfg:
    _ACTIVE_WORD:      str         = _custom_cfg["word"]
    _ACTIVE_WAKEWORDS: list[str]   = _build_custom_wakewords(_ACTIVE_WORD)
    _ACTIVE_FUZZY:     dict[str, float] = _custom_cfg.get("lookup_table", {})
    _ACTIVE_THRESHOLD: float       = float(_custom_cfg.get("threshold", 0.75))
    _IS_CANARY:        bool        = (_ACTIVE_WORD == "canary")
else:
    _ACTIVE_WORD      = "canary"
    _ACTIVE_WAKEWORDS = _CANARY_WAKEWORDS
    _ACTIVE_FUZZY     = _CANARY_FUZZY_MAP
    _ACTIVE_THRESHOLD = 0.75
    _IS_CANARY        = True


# ─────────────────────────────────────────────────────────────────────────────
#  C++ COLD-PATH LOOKUP
#  Called only for custom wakeword mode AND a token that isn't in the table.
#  Returns confidence [0.0, 1.0].
# ─────────────────────────────────────────────────────────────────────────────
def _cpp_similarity(wakeword: str, token: str) -> float:
    """
    Call the C++ wakeword_matcher binary for a live weighted-DP score.
    Returns 0.0 on any failure (safe degradation to rejection).
    """
    if not _BINARY_PATH.exists():
        return 0.0
    try:
        result = subprocess.run(
            [str(_BINARY_PATH), wakeword, token,
             "--threshold", str(_ACTIVE_THRESHOLD)],
            capture_output=True, text=True, timeout=2.0
        )
        data = json.loads(result.stdout)
        return float(data.get("confidence", 0.0))
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
def detect_wakeword(text: str) -> dict:
    """
    Detect whether the utterance contains the active wakeword.

    Detection strategy:
      1. Exact match against _ACTIVE_WAKEWORDS list       → confidence 1.0
      2. Fast dict lookup in _ACTIVE_FUZZY (lookup_table) → confidence from table
      3. (Custom mode only) C++ DP call for unseen tokens → live confidence score

    Returns
    -------
    {
        "wakeword":            bool,
        "wakeword_confidence": float,   # 1.0 exact / scored / 0.0 none
        "matched_phrase":      str | None
    }
    """
    lower = text.lower().strip()

    # ── 1. Exact match ────────────────────────────────────────────────────
    for phrase in _ACTIVE_WAKEWORDS:
        if phrase in lower:
            return {
                "wakeword":            True,
                "wakeword_confidence": 1.0,
                "matched_phrase":      phrase,
            }

    # ── 2. Fast dict lookup (hot path) ────────────────────────────────────
    # Check every whitespace-separated token against the lookup table
    tokens = lower.split()
    for token in tokens:
        # strip leading/trailing punctuation from token
        clean = token.strip(".,!?;:\"'")
        if clean in _ACTIVE_FUZZY:
            conf = float(_ACTIVE_FUZZY[clean])
            if conf >= _ACTIVE_THRESHOLD:
                return {
                    "wakeword":            True,
                    "wakeword_confidence": conf,
                    "matched_phrase":      f"~{clean}",
                }

    # Also try bigrams (handles split transcriptions like "can ary")
    for i in range(len(tokens) - 1):
        bigram = tokens[i].strip(".,!?") + tokens[i+1].strip(".,!?")
        if bigram in _ACTIVE_FUZZY:
            conf = float(_ACTIVE_FUZZY[bigram])
            if conf >= _ACTIVE_THRESHOLD:
                return {
                    "wakeword":            True,
                    "wakeword_confidence": conf,
                    "matched_phrase":      f"~{bigram}",
                }

    # ── 3. C++ cold-path then Python difflib fallback (custom mode only) ──
    if not _IS_CANARY:
        for token in tokens:
            clean = token.strip(".,!?;:\"'")
            if len(clean) >= 2:
                # Try C++ binary first
                conf = _cpp_similarity(_ACTIVE_WORD, clean)
                # Fallback: Python difflib similarity when binary not available
                if conf == 0.0:
                    import difflib
                    conf = difflib.SequenceMatcher(
                        None, _ACTIVE_WORD, clean).ratio()
                if conf >= _ACTIVE_THRESHOLD:
                    return {
                        "wakeword":            True,
                        "wakeword_confidence": round(conf, 4),
                        "matched_phrase":      f"~{clean}",
                    }

    # ── No match ──────────────────────────────────────────────────────────
    return {
        "wakeword":            False,
        "wakeword_confidence": 0.0,
        "matched_phrase":      None,
    }


def get_active_wakeword() -> str:
    """Returns the currently active wakeword (e.g. 'canary' or custom word)."""
    return _ACTIVE_WORD


def is_canary_default() -> bool:
    """Returns True if running on Canary defaults (no custom config loaded)."""
    return _IS_CANARY
