import time
import sys
from pathlib import Path
import soundfile as sf
import warnings

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from computation.audio.transcribe import transcribe

FIX = ROOT / "data" / "test_audio" / "ref_a.wav"
if not FIX.exists():
    print("Fixture not found!")
    sys.exit(1)

audio, sr = sf.read(str(FIX), dtype="float32")
if audio.ndim > 1:
    audio = audio.mean(axis=1)
dur = len(audio) / sr

models = ["tiny", "base", "small", "turbo"]

for m in models:
    print(f"Loading {m}...")
    # warm up
    res = transcribe(str(FIX), model_name=m)
    
    # measure
    t0 = time.perf_counter()
    res = transcribe(str(FIX), model_name=m)
    elapsed = time.perf_counter() - t0
    print(f"Model: {m:<10} | xRT: {elapsed/dur:6.3f} | Text: {res.get('text', '')}")
