
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from computation.intelligence.intent_engine import analyze_intent


def test_lisped_keyword_recovered_under_lisp_profile():
    r = analyze_intent("tell me the newth", phonetic_profile="lisp")
    assert r["domain"] == "NEWS"
    assert any(s.startswith("phonetic:") for s in r["raw_signals"])


def test_weather_recovered_from_lisped_sunny():
    r = analyze_intent("ith it thunny today", phonetic_profile="lisp")
    assert r["domain"] == "WEATHER"


def test_clean_speech_uses_rulebased_not_fallback():
    r = analyze_intent("tell me the news", phonetic_profile="default")
    assert r["domain"] == "NEWS"
    assert not any(s.startswith("phonetic:") for s in r["raw_signals"])


def test_ambient_chatter_not_falsely_recovered():
    r = analyze_intent("i think we should grab lunch later sometime", phonetic_profile="lisp")
    assert r["domain"] == "UNKNOWN"


def test_signature_backward_compatible():
    r = analyze_intent("play some music")
    assert r["domain"] == "SONGS"
