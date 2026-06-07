"""
asr/transcribe.py
-----------------
Whisper-based speech-to-text for The Canary pipeline.

Model hierarchy (tries highest accuracy first, falls back gracefully):
  large-v3  → best accuracy, multilingual, ~1.5 GB
  medium    → good accuracy, faster, ~300 MB

Handles:
  • Multilingual audio (auto-detects language)
  • Long audio (Whisper handles chunking internally)
  • Noisy separated streams (already denoised by pipeline)
"""

from __future__ import annotations

import warnings
import logging
from pathlib import Path
from typing import Optional

# Suppress noisy model loading logs
logging.getLogger("whisper").setLevel(logging.ERROR)

# ── Module-level model cache (load once per process) ──────────────────────────
_model_cache: dict = {}


def _load_model(model_name: str):
    """Load and cache a Whisper model."""
    if model_name not in _model_cache:
        import whisper
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            print(f"    [ASR] Loading Whisper {model_name} ...")
            _model_cache[model_name] = whisper.load_model(model_name)
    return _model_cache[model_name]


def transcribe(
    wav_path: str | Path,
    model_name: str = "large-v3",
    language: Optional[str] = None,
) -> dict:
    """
    Transcribe a speaker WAV file using OpenAI Whisper.

    Parameters
    ----------
    wav_path   : Path to the speaker WAV file.
    model_name : Whisper model to use. Defaults to 'large-v3' (best accuracy).
    language   : ISO-639 language code or None for auto-detection.

    Returns
    -------
    dict with keys:
      text      : Full transcript string
      language  : Detected language code
      segments  : List of timed segments [{start, end, text}, ...]
    """
    import whisper

    wav_path = str(wav_path)
    model    = _load_model(model_name)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = model.transcribe(
            wav_path,
            language=language,      # None = auto-detect
            task="transcribe",
            fp16=False,             # CPU-safe (no CUDA needed)
            verbose=False,
            # Whisper decode options for best accuracy
            beam_size=5,
            best_of=5,
            temperature=0.0,        # greedy decode → most deterministic
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            no_speech_threshold=0.6,
            condition_on_previous_text=True,
        )

    return {
        "text":     result["text"].strip(),
        "language": result.get("language", "unknown"),
        "segments": [
            {
                "start": round(seg["start"], 2),
                "end":   round(seg["end"],   2),
                "text":  seg["text"].strip(),
            }
            for seg in result.get("segments", [])
        ],
    }


def transcribe_and_save(
    wav_path: str | Path,
    model_name: str = "large-v3",
    language: Optional[str] = None,
) -> str:
    """
    Transcribe wav_path and save the transcript as a .txt file next to the WAV.

    The .txt file format:
        [Language: en]

        Speaker transcript here in full.

        --- Segments ---
        [0.00s → 2.34s] Hello, this is speaker one.
        [2.50s → 4.10s] Can you hear me clearly?

    Returns the full transcript text.
    """
    wav_path = Path(wav_path)
    result   = transcribe(wav_path, model_name=model_name, language=language)

    txt_path = wav_path.with_suffix(".txt")

    lines = [
        f"[Language: {result['language']}]",
        "",
        result["text"],
        "",
        "--- Segments ---",
    ]
    for seg in result["segments"]:
        lines.append(f"[{seg['start']:.2f}s → {seg['end']:.2f}s] {seg['text']}")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return result["text"]
