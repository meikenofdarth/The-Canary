
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent

from computation.intelligence.acoustic_rag import AcousticRAG

SR = 16000


def _load(name: str) -> np.ndarray:
    a, sr = sf.read(str(ROOT / "data" / "test_audio" / name), dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    return a.astype(np.float32)


def _time_stretch(a: np.ndarray, rate: float) -> np.ndarray:
    import librosa
    return librosa.effects.time_stretch(a, rate=rate).astype(np.float32)


def test_dtw_matches_timewarped_command_and_rejects_other():
    cmd_a = _load("ref_a.wav")
    cmd_b = _load("ref_b.wav")

    with tempfile.TemporaryDirectory() as d:
        rag = AcousticRAG(store_dir=d)
        rag.enroll("user1", "lights_on", cmd_a, SR, intent="LIGHTS")
        rag.enroll("user1", "weather", cmd_b, SR, intent="WEATHER")

        warped_a = _time_stretch(cmd_a, 0.7)
        res = rag.match(warped_a, SR, "user1")
        print(f"\n  warped A -> {res['label']} (d={res['distance']}) ranking={res['ranking']}")

        assert res["label"] == "lights_on"
        assert res["intent"] == "LIGHTS"
        assert res["matched"] is True

        ranking = dict(res["ranking"])
        assert ranking["lights_on"] < ranking["weather"]


def test_unenrolled_user_returns_no_match():
    with tempfile.TemporaryDirectory() as d:
        rag = AcousticRAG(store_dir=d)
        res = rag.match(_load("ref_a.wav"), SR, "ghost")
        assert res["matched"] is False
        assert res["label"] is None


def test_open_set_match_noop_when_empty():
    with tempfile.TemporaryDirectory() as d:
        rag = AcousticRAG(store_dir=d)
        res = rag.open_set_match(_load("ref_a.wav"), SR)
        assert res["matched"] is False
        assert res["user"] is None


def test_open_set_match_finds_right_user_and_intent():
    cmd_a = _load("ref_a.wav")
    cmd_b = _load("ref_b.wav")
    with tempfile.TemporaryDirectory() as d:
        rag = AcousticRAG(store_dir=d)
        rag.enroll("alice", "weather", cmd_a, SR, intent="WEATHER")
        rag.enroll("bob",   "music",   cmd_b, SR, intent="SONGS")

        res = rag.open_set_match(cmd_a, SR)
        assert res["matched"] is True
        assert res["user"] == "alice"
        assert res["intent"] == "WEATHER"
