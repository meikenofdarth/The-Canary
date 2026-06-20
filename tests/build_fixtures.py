
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "test_audio"
SR = 16_000

SRC_A = ROOT / "models" / "speaker_embeddings" / "hemang.wav"
SRC_B = ROOT / "models" / "speaker_embeddings" / "sanchit.wav"


def _load_16k_mono(path: Path) -> np.ndarray:
    import librosa
    audio, sr = sf.read(str(path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SR)
    peak = float(np.max(np.abs(audio))) + 1e-9
    return (audio / peak * 0.9).astype(np.float32)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    a = _load_16k_mono(SRC_A)
    b = _load_16k_mono(SRC_B)

    n = min(len(a), len(b))
    a, b = a[:n], b[:n]

    mix = a + b
    peak = float(np.max(np.abs(mix))) + 1e-9
    scale = 0.9 / peak if peak > 0.9 else 1.0
    mix = (mix * scale).astype(np.float32)

    sf.write(str(OUT / "ref_a.wav"), a, SR, subtype="PCM_16")
    sf.write(str(OUT / "ref_b.wav"), b, SR, subtype="PCM_16")
    sf.write(str(OUT / "mix.wav"), mix, SR, subtype="PCM_16")

    print(f"Wrote fixtures to {OUT}")
    print(f"  ref_a.wav  {len(a)/SR:.2f}s")
    print(f"  ref_b.wav  {len(b)/SR:.2f}s")
    print(f"  mix.wav    {len(mix)/SR:.2f}s  (2-speaker overlap)")


if __name__ == "__main__":
    main()
