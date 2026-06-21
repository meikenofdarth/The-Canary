import sys
import time
from pathlib import Path
import soundfile as sf
import warnings

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from run_canary import detect_and_separate
from computation.audio.transcribe import transcribe

FIX = ROOT / "data" / "test_audio" / "mix.wav"

audio, sr = sf.read(str(FIX), dtype="float32")
if audio.ndim > 1:
    audio = audio.mean(axis=1)
dur = len(audio) / sr

print("Warming up models...")
import numpy as np
detect_and_separate(np.zeros(sr, dtype=np.float32), sr)
transcribe(str(FIX), model_name="base")

print("\n--- MEASURING END-TO-END PIPELINE ---")
t0 = time.perf_counter()

# 1. Separate
n_spk, streams = detect_and_separate(audio, sr)
t_sep = time.perf_counter() - t0

# 2. Transcribe streams
t1 = time.perf_counter()
hyps = []
for i, s in enumerate(streams):
    tmp_path = f"tmp_stream_{i}.wav"
    sf.write(tmp_path, s, sr, subtype="PCM_16")
    res = transcribe(tmp_path, model_name="base")
    hyps.append(res.get("text", ""))
    Path(tmp_path).unlink()

t_asr = time.perf_counter() - t1
total_time = time.perf_counter() - t0

print(f"Audio Duration   : {dur:.2f}s")
print(f"Separation xRT   : {t_sep / dur:.3f}")
print(f"ASR (Base) xRT   : {t_asr / dur:.3f} (for both streams sequentially)")
print(f"End-to-End xRT   : {total_time / dur:.3f}   (Target < 0.5)")
print(f"Transcripts      : {hyps}")
