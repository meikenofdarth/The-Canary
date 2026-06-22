
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent

from computation.audio.vad_segmenter import get_vad_segments, adaptive_vad_config

SR = 16000


def _speech_with_block() -> np.ndarray:
    a, sr = sf.read(str(ROOT / "data" / "test_audio" / "ref_a.wav"), dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    half = len(a) // 2
    gap = np.zeros(int(1.2 * sr), dtype=np.float32)
    return np.concatenate([a[:half], gap, a[half:]]).astype(np.float32)


def test_profile_config_widens_for_stutter():
    d = adaptive_vad_config("default")
    s = adaptive_vad_config("stutter")
    assert s["min_silence_ms"] > d["min_silence_ms"]
    assert s["silence_timeout"] > d["silence_timeout"]


def test_stutter_block_not_split():
    audio = _speech_with_block()
    default_segs = get_vad_segments(audio, SR, profile="default")
    stutter_segs = get_vad_segments(audio, SR, profile="stutter")

    print(f"\n  default profile -> {len(default_segs)} segment(s)")
    print(f"  stutter profile -> {len(stutter_segs)} segment(s)")

    assert len(default_segs) >= 2
    assert len(stutter_segs) < len(default_segs)


def test_backward_compatible_default():
    audio = _speech_with_block()
    assert len(get_vad_segments(audio, SR)) == len(get_vad_segments(audio, SR, profile="default"))
