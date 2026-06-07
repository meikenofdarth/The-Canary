"""
asr/transcribe.py
-----------------
Whisper-based speech-to-text for The Canary pipeline.

Handles:
  • Multilingual audio (auto-detects language)
  • Hallucination loop detection and suppression
  • Speech quality classification: SPEECH / NO_SPEECH / NOISE / REPETITIVE
  • Meaningful conversation flagging
"""

from __future__ import annotations

import zlib
import warnings
import logging
from pathlib import Path
from typing import Optional
from collections import Counter

logging.getLogger("whisper").setLevel(logging.ERROR)

# Module-level model cache — load once per process
_model_cache: dict = {}


# ─────────────────────────────────────────────────────────────────────────────
#  MODEL LOADER
# ─────────────────────────────────────────────────────────────────────────────
def _load_model(model_name: str = "base"):
    if model_name not in _model_cache:
        import whisper
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            print(f"    [ASR] Loading Whisper {model_name} ...")
            _model_cache[model_name] = whisper.load_model(model_name)
    return _model_cache[model_name]


# ─────────────────────────────────────────────────────────────────────────────
#  SPEECH QUALITY CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────
def _is_repetitive(text: str, repeat_threshold: int = 4) -> bool:
    """
    Detect Whisper's hallucination loop — when it repeats the same phrase
    over and over. Checks if any 3-6 word n-gram appears ≥ repeat_threshold times.
    """
    words = text.split()
    if len(words) < 10:
        return False
    for n in (4, 5, 6):
        ngrams  = [" ".join(words[i : i + n]) for i in range(len(words) - n)]
        if ngrams and max(Counter(ngrams).values(), default=0) >= repeat_threshold:
            return True
    return False


def _compression_ratio(text: str) -> float:
    """
    Compute text compression ratio (zlib). Repetitive text compresses
    very aggressively (ratio > 3.0). Normal speech: ratio 1.0–2.0.
    """
    b = text.encode("utf-8")
    if len(b) < 10:
        return 1.0
    return len(b) / len(zlib.compress(b))


def classify_speech(result: dict) -> str:
    """
    Classify a Whisper result into one of four statuses:

    SPEECH      — clear, meaningful, non-repetitive speech detected
    NO_SPEECH   — silence or below Whisper's no-speech threshold
    NOISE       — audio present but not recognisable speech
                  (coughing, music, background rumble, etc.)
    REPETITIVE  — Whisper hallucination loop (discard transcript)

    Returns one of the status strings above.
    """
    text     = result.get("text", "").strip()
    segments = result.get("segments", [])

    # No output at all → silence
    if not text or not segments:
        return "NO_SPEECH"

    # Whisper's own no-speech probability
    no_speech_probs = [s.get("no_speech_prob", 0.0) for s in segments]
    avg_no_speech   = sum(no_speech_probs) / len(no_speech_probs)
    if avg_no_speech > 0.65:
        return "NO_SPEECH"

    # Repetition check (hallucination)
    if _is_repetitive(text):
        return "REPETITIVE"

    # Compression ratio check (another hallucination signal)
    if _compression_ratio(text) > 2.8 and len(text) > 80:
        return "REPETITIVE"

    # Too few unique words → noise, not speech
    unique_words = set(text.lower().split())
    if len(unique_words) < 3:
        return "NOISE"

    return "SPEECH"


# ─────────────────────────────────────────────────────────────────────────────
#  CORE TRANSCRIBE
# ─────────────────────────────────────────────────────────────────────────────
def transcribe(
    wav_path: str | Path,
    model_name: str = "base",
    language: Optional[str] = None,
) -> dict:
    """
    Transcribe a speaker WAV file.

    Returns dict:
      text     : transcript string (empty string if no speech)
      language : detected language code
      segments : [{start, end, text, no_speech_prob}, ...]
      status   : 'SPEECH' | 'NO_SPEECH' | 'NOISE' | 'REPETITIVE'
    """
    import soundfile as sf
    import numpy as np

    wav_path = Path(wav_path)
    model    = _load_model(model_name)

    # Load WAV directly as numpy — no ffmpeg dependency
    audio_np, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if audio_np.ndim == 2:
        audio_np = audio_np.mean(axis=1)

    if sr != 16000:
        import torchaudio, torch
        audio_np = torchaudio.functional.resample(
            torch.from_numpy(audio_np).unsqueeze(0), sr, 16000
        ).squeeze(0).numpy()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = model.transcribe(
            audio_np,
            language=language,
            task="transcribe",
            fp16=False,
            verbose=False,
            # ── Key anti-hallucination settings ──────────────────────────
            # Tuple → Whisper auto-increases temperature if compression
            # ratio is too high (repetition detected internally too).
            temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            # Tighter than default (2.4) — catches loops earlier
            compression_ratio_threshold=1.8,
            logprob_threshold=-1.2,
            no_speech_threshold=0.5,
            # CRITICAL: False prevents one hallucinated phrase from
            # cascading into the next segment
            condition_on_previous_text=False,
        )

    segments = [
        {
            "start":          round(seg["start"], 2),
            "end":            round(seg["end"],   2),
            "text":           seg["text"].strip(),
            "no_speech_prob": round(seg.get("no_speech_prob", 0.0), 3),
        }
        for seg in result.get("segments", [])
    ]

    raw = {
        "text":     result["text"].strip(),
        "language": result.get("language", "unknown"),
        "segments": segments,
    }
    raw["status"] = classify_speech(raw)

    # If classified as REPETITIVE, wipe the hallucinated text
    if raw["status"] == "REPETITIVE":
        raw["text"] = ""

    return raw


# ─────────────────────────────────────────────────────────────────────────────
#  SAVE TO .TXT
# ─────────────────────────────────────────────────────────────────────────────
_STATUS_LABELS = {
    "SPEECH":     "✓  Meaningful speech detected",
    "NO_SPEECH":  "✗  No speech — silence or below threshold",
    "NOISE":      "⚠  Audio detected but not meaningful speech (cough / noise)",
    "REPETITIVE": "⚠  Transcription unreliable (audio too distorted for ASR)",
}

def transcribe_and_save(
    wav_path: str | Path,
    model_name: str = "base",
    language: Optional[str] = None,
) -> tuple[str, str]:
    """
    Transcribe and write a .txt file next to the WAV.

    File format:
        [Language: en]
        [Status: ✓  Meaningful speech detected]

        Hello this is speaker one.

        --- Segments ---
        [0.00s → 1.23s] Hello this is speaker one.

    Returns (text, status) tuple.
    """
    wav_path = Path(wav_path)
    result   = transcribe(wav_path, model_name=model_name, language=language)

    status       = result["status"]
    status_label = _STATUS_LABELS.get(status, status)
    text         = result["text"]

    lines = [
        f"[Language: {result['language']}]",
        f"[Status: {status_label}]",
        "",
    ]

    if status == "SPEECH" and text:
        lines.append(text)
        lines.append("")
        lines.append("--- Segments ---")
        for seg in result["segments"]:
            nsp = seg["no_speech_prob"]
            flag = "  [low confidence]" if nsp > 0.4 else ""
            lines.append(f"[{seg['start']:.2f}s → {seg['end']:.2f}s] {seg['text']}{flag}")
    elif status == "REPETITIVE":
        lines.append("(audio too distorted — transcript suppressed to avoid hallucination)")
    elif status == "NO_SPEECH":
        lines.append("(no speech detected in this stream)")
    else:  # NOISE
        lines.append("(non-speech audio: cough, background noise, music, etc.)")

    wav_path.with_suffix(".txt").write_text("\n".join(lines), encoding="utf-8")
    return text, status
