
from __future__ import annotations

import json
import subprocess
from pathlib import Path

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

_CANARY_FUZZY_MAP: dict[str, float] = {
    "canari":      0.80,
    "canarie":     0.80,
    "canaries":    0.80,
    "canree":      0.80,
    "canry":       0.80,
    "canara":      0.75,
    "canaras":     0.75,
    "canaria":     0.75,
    "kanary":      0.75,
    "kannary":     0.75,
    "kenary":      0.75,
    "kennary":     0.75,
    "kanari":      0.70,
    "kenari":      0.70,
    "qanari":      0.70,
    "qanary":      0.70,
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
    "anari":       0.55,
    "anary":       0.55,
    "unari":       0.55,
    "unary":       0.55,
    "cannery":     0.979,
    "canerie":     0.975,
    "canere":      0.975,
    "cenary":      0.983,
    "kennedy":     0.807,
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
    "kenary":      0.975,
    "cannary":     0.986,
    "kannary":     0.979,
    "kannery":     0.971,
    "kennery":     0.971,
    "kennary":     0.971,
    "canory":      0.975,
    "kanory":      0.971,
    "cenery":      0.950,
    "qaneri":      0.975,
    "kaneri":      0.971,
}


_CONFIG_PATH   = Path(__file__).parent.parent / "wakeword" / "wakeword_config.json"
_DEFAULT_PATH  = Path(__file__).parent.parent.parent / "default_wakeword_config.json"
_BINARY_PATH   = Path(__file__).parent.parent / "wakeword" / "build" / "wakeword_matcher"

def _load_custom_config() -> dict | None:
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
    prefixes = ["hey", "ok", "hi", "hello", "yo", "okay", "hey,",
                "ok,", "hi,", "yo,", "hello,", "okay,"]
    phrases = [word]
    for p in prefixes:
        phrases.append(f"{p} {word}")
    phrases.sort(key=len, reverse=True)
    return phrases


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

def reload_config() -> None:
    global _ACTIVE_WORD, _ACTIVE_WAKEWORDS, _ACTIVE_FUZZY, _ACTIVE_THRESHOLD, _IS_CANARY
    cfg = _load_custom_config()
    if cfg:
        _ACTIVE_WORD = cfg["word"]
        _ACTIVE_WAKEWORDS = _build_custom_wakewords(_ACTIVE_WORD)
        _ACTIVE_FUZZY = cfg.get("lookup_table", {})
        _ACTIVE_THRESHOLD = float(cfg.get("threshold", 0.75))
        _IS_CANARY = (_ACTIVE_WORD == "canary")
    else:
        _ACTIVE_WORD = "canary"
        _ACTIVE_WAKEWORDS = _CANARY_WAKEWORDS
        _ACTIVE_FUZZY = _CANARY_FUZZY_MAP
        _ACTIVE_THRESHOLD = 0.75
        _IS_CANARY = True


def _cpp_similarity(wakeword: str, token: str) -> float:
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


def detect_wakeword(text: str) -> dict:
    reload_config()

    lower = text.lower().strip()

    for phrase in _ACTIVE_WAKEWORDS:
        if phrase in lower:
            return {
                "wakeword":            True,
                "wakeword_confidence": 1.0,
                "matched_phrase":      phrase,
            }

    tokens = lower.split()
    for token in tokens:
        clean = token.strip(".,!?;:\"'")
        if clean in _ACTIVE_FUZZY:
            conf = float(_ACTIVE_FUZZY[clean])
            if conf >= _ACTIVE_THRESHOLD:
                return {"wakeword": True, "wakeword_confidence": conf,
                        "matched_phrase": f"~{clean}"}

        if len(clean) > len(_ACTIVE_WORD) + 1:
            for start in range(len(clean) - len(_ACTIVE_WORD) + 1):
                sub = clean[start: start + len(_ACTIVE_WORD) + 1]
                if sub in _ACTIVE_FUZZY:
                    conf = float(_ACTIVE_FUZZY[sub])
                    if conf >= _ACTIVE_THRESHOLD:
                        return {"wakeword": True, "wakeword_confidence": conf,
                                "matched_phrase": f"~{sub}"}
                sub2 = clean[start: start + len(_ACTIVE_WORD)]
                if sub2 in _ACTIVE_FUZZY:
                    conf = float(_ACTIVE_FUZZY[sub2])
                    if conf >= _ACTIVE_THRESHOLD:
                        return {"wakeword": True, "wakeword_confidence": conf,
                                "matched_phrase": f"~{sub2}"}

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

    if not _IS_CANARY:
        for token in tokens:
            clean = token.strip(".,!?;:\"'")
            if len(clean) >= 2:
                conf = _cpp_similarity(_ACTIVE_WORD, clean)
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

    return {
        "wakeword":            False,
        "wakeword_confidence": 0.0,
        "matched_phrase":      None,
    }


def get_active_wakeword() -> str:
    for path in (_CONFIG_PATH, _DEFAULT_PATH):
        if path.exists():
            try:
                cfg = json.loads(path.read_text(encoding="utf-8"))
                word = cfg.get("word", "").strip().lower()
                if word:
                    return word
            except Exception:
                continue
    return "canary"


def is_canary_default() -> bool:
    return _IS_CANARY
