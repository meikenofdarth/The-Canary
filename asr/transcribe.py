"""
asr/transcribe.py
-----------------
Whisper-based speech-to-text for The Canary pipeline.

Pre-screening gate (runs BEFORE Whisper, very fast):
  Test 1: RMS energy        — is there enough signal?
  Test 2: Energy-based VAD  — is enough of it actually speech?

Post-transcription gate (runs AFTER Whisper, checks quality):
  Test 3: avg_logprob       — did Whisper actually understand it?
  Test 4: repetition check  — is it a hallucination loop?

Only streams that pass ALL gates are transcribed and flagged READY.
"""

from __future__ import annotations

import zlib
import warnings
import logging
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional
from collections import Counter

logging.getLogger("whisper").setLevel(logging.ERROR)

_model_cache: dict = {}


# ─────────────────────────────────────────────────────────────────────────────
#  MODEL LOADER
# ─────────────────────────────────────────────────────────────────────────────
def _load_model(model_name: str = "base"):
    if model_name not in _model_cache:
        try:
            import whisper
            if not hasattr(whisper, "load_model"):
                raise ImportError("The wrong 'whisper' package is installed.")
        except (ImportError, AttributeError) as e:
            print("\n" + "="*80)
            print("ERROR: The wrong 'whisper' package is installed on this system.")
            print("Please run the following commands to install the correct package:")
            print("  pip uninstall -y whisper")
            print("  pip install openai-whisper")
            print("="*80 + "\n")
            raise ImportError(
                "Whisper package mismatch. Run 'pip uninstall whisper' and 'pip install openai-whisper'."
            ) from e

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            print(f"    [ASR] Loading Whisper {model_name} ...")
            _model_cache[model_name] = whisper.load_model(model_name)
    return _model_cache[model_name]


# ─────────────────────────────────────────────────────────────────────────────
#  TEST 1 + 2 — PRE-SCREENING GATE  (no model needed, runs in <0.1s)
# ─────────────────────────────────────────────────────────────────────────────
def pre_screen(
    wav_path: str | Path,
    rms_threshold_db: float   = -52.0,   # minimum overall loudness
    speech_ratio_threshold: float = 0.15, # min 15% of frames must be voiced
    frame_ms: int             = 30,       # VAD frame length in ms
) -> dict:
    """
    Quick two-test pre-screening gate.  No model needed.

    Test 1 — RMS energy
        If the entire stream is too quiet → pure silence/artifacts → REJECTED.
        Threshold set at -52 dBFS (well below normalised speech at -18 dBFS).

    Test 2 — Energy-based VAD speech ratio
        Divide audio into 30ms frames.
        Adaptive noise floor = 10th percentile of frame RMS values.
        A frame is "voiced" if its RMS > 3× noise floor.
        speech_ratio = voiced_frames / total_frames.
        If < 15% of frames are voiced → mostly noise → REJECTED.

    Returns dict:
        rms_db          : overall RMS in dBFS
        speech_ratio    : fraction of voiced frames (0–1)
        verdict         : 'READY' | 'REJECTED'
        reason          : human-readable explanation
    """
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    rms    = float(np.sqrt(np.mean(audio ** 2)))
    rms_db = 20.0 * np.log10(rms + 1e-10)

    # ── Test 1: overall energy ────────────────────────────────────────────
    if rms_db < rms_threshold_db:
        return {
            "rms_db": round(rms_db, 1),
            "speech_ratio": 0.0,
            "verdict": "REJECTED",
            "reason": f"RMS {rms_db:.1f} dBFS below threshold {rms_threshold_db} dBFS — silent stream",
        }

    # ── Test 2: energy-based VAD ──────────────────────────────────────────
    frame_len   = max(1, int(sr * frame_ms / 1000))
    n_frames    = len(audio) // frame_len
    if n_frames == 0:
        return {"rms_db": round(rms_db,1), "speech_ratio": 0.0,
                "verdict": "REJECTED", "reason": "Audio too short for VAD"}

    frame_rms   = np.array([
        np.sqrt(np.mean(audio[i * frame_len : (i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    # Noise floor = quietest 10% of frames; voiced = 3× above that
    noise_floor     = float(np.percentile(frame_rms, 10)) + 1e-10
    voiced_thresh   = noise_floor * 3.0
    voiced_frames   = int(np.sum(frame_rms > voiced_thresh))
    speech_ratio    = voiced_frames / n_frames

    if speech_ratio < speech_ratio_threshold:
        return {
            "rms_db": round(rms_db, 1),
            "speech_ratio": round(speech_ratio, 3),
            "verdict": "REJECTED",
            "reason": (
                f"Speech ratio {speech_ratio:.0%} < {speech_ratio_threshold:.0%} "
                f"— mostly residual noise/artifacts"
            ),
        }

    return {
        "rms_db": round(rms_db, 1),
        "speech_ratio": round(speech_ratio, 3),
        "verdict": "READY",
        "reason": f"RMS {rms_db:.1f} dBFS, {speech_ratio:.0%} voiced — passed pre-screening",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  TEST 3 + 4 — POST-WHISPER QUALITY GATE
# ─────────────────────────────────────────────────────────────────────────────
def _is_repetitive(text: str, repeat_threshold: int = 4) -> bool:
    words = text.split()
    if len(words) < 10:
        return False
    for n in (4, 5, 6):
        ngrams = [" ".join(words[i : i + n]) for i in range(len(words) - n)]
        if ngrams and max(Counter(ngrams).values(), default=0) >= repeat_threshold:
            return True
    return False


def _compression_ratio(text: str) -> float:
    b = text.encode("utf-8")
    if len(b) < 10:
        return 1.0
    return len(b) / len(zlib.compress(b))


def classify_speech(result: dict, has_vad_speech: bool = False) -> str:
    """
    Classify Whisper output after transcription.

    has_vad_speech: True when VAD pre-screen already confirmed ≥15% voiced
                    frames. In that case Whisper's no_speech_prob alone cannot
                    reclassify to NO_SPEECH — it becomes NOISE instead
                    (audio IS present, just too distorted to transcribe).

    Returns: 'SPEECH' | 'NO_SPEECH' | 'NOISE' | 'LOW_CONFIDENCE' | 'REPETITIVE'
    """
    text     = result.get("text", "").strip()
    segments = result.get("segments", [])

    if not text or not segments:
        # VAD confirmed speech was present → audio exists but indecipherable
        return "NOISE" if has_vad_speech else "NO_SPEECH"

    avg_no_speech = float(np.mean([s.get("no_speech_prob", 0.0) for s in segments]))
    if avg_no_speech > 0.65:
        # VAD says speech was there → distorted audio, not true silence
        return "NOISE" if has_vad_speech else "NO_SPEECH"

    # ── Test 3: avg_logprob ────────────────────────────────────────────────
    # Whisper returns avg_logprob per segment (log-probability of the tokens).
    # Confident speech:  > -0.5
    # Uncertain:        -0.5 to -1.0
    # Gibberish/noise:  < -1.2
    lp_values = [s.get("avg_logprob", -0.5) for s in segments if "avg_logprob" in s]
    if lp_values:
        avg_logprob = float(np.mean(lp_values))
        if avg_logprob < -1.2:
            return "LOW_CONFIDENCE"

    # ── Test 4: repetition / compression ──────────────────────────────────
    if _is_repetitive(text):
        return "REPETITIVE"
    if _compression_ratio(text) > 2.8 and len(text) > 80:
        return "REPETITIVE"

    if len(set(text.lower().split())) < 3:
        return "NOISE"

    return "SPEECH"


# ─────────────────────────────────────────────────────────────────────────────
#  CORE TRANSCRIBE
# ─────────────────────────────────────────────────────────────────────────────
def transcribe(
    wav_path: str | Path,
    model_name: str = "base",
    language: Optional[str] = None,
    has_vad_speech: bool = False,
) -> dict:
    """
    Transcribe a speaker WAV using Whisper.
    has_vad_speech: passed through to classify_speech to fix NO_SPEECH false positives.
    """
    wav_path = Path(wav_path)
    model    = _load_model(model_name)

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
            temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            compression_ratio_threshold=1.8,
            logprob_threshold=-1.2,
            no_speech_threshold=0.5,
            condition_on_previous_text=False,
        )

    segments = [
        {
            "start":          round(seg["start"], 2),
            "end":            round(seg["end"],   2),
            "text":           seg["text"].strip(),
            "no_speech_prob": round(seg.get("no_speech_prob", 0.0), 3),
            "avg_logprob":    round(seg.get("avg_logprob", -0.5), 3),
        }
        for seg in result.get("segments", [])
    ]

    raw = {
        "text":     result["text"].strip(),
        "language": result.get("language", "unknown"),
        "segments": segments,
    }
    raw["status"] = classify_speech(raw, has_vad_speech=has_vad_speech)

    if raw["status"] in ("REPETITIVE", "LOW_CONFIDENCE"):
        raw["text"] = ""

    return raw


# ─────────────────────────────────────────────────────────────────────────────
#  SAVE TO .TXT  (called from run_canary main)
# ─────────────────────────────────────────────────────────────────────────────
_STATUS_LABELS = {
    "SPEECH":         "✓  READY — meaningful speech detected",
    "NO_SPEECH":      "✗  REJECTED — no speech (silence)",
    "NOISE":          "✗  REJECTED — non-speech audio (cough / background noise)",
    "LOW_CONFIDENCE": "✗  REJECTED — Whisper confidence too low (noise/artifacts)",
    "REPETITIVE":     "✗  REJECTED — Whisper hallucination loop (distorted audio)",
    # Pre-screen rejections
    "PRE_REJECTED":   "✗  REJECTED — failed pre-screening (insufficient speech)",
}


def transcribe_and_save(
    wav_path: str | Path,
    model_name: str = "base",
    language: Optional[str] = None,
) -> tuple[str, str]:
    """
    Full pipeline: pre-screen → Whisper → post-screen → save .txt.
    Returns (transcript_text, status_string).
    """
    import math
    wav_path = Path(wav_path)
    txt_path = wav_path.with_suffix(".txt")

    # ── Pre-screening (Tests 1 + 2) ──────────────────────────────────────────
    screen = pre_screen(wav_path)

    if screen["verdict"] == "REJECTED":
        lines = [
            f"[Status: {_STATUS_LABELS['PRE_REJECTED']}]",
            f"[Detail: {screen['reason']}]",
            f"[RMS: {screen['rms_db']} dBFS | Speech ratio: {screen['speech_ratio']:.0%}]",
            "",
            "(stream flagged as noise — Whisper not invoked)",
        ]
        txt_path.write_text("\n".join(lines), encoding="utf-8")
        return "", "PRE_REJECTED"

    # ── Whisper transcription (Tests 3 + 4 inside) ────────────────────────
    result = transcribe(wav_path, model_name=model_name, language=language)
    status = result["status"]
    text   = result["text"]
    label  = _STATUS_LABELS.get(status, status)

    lines = [
        f"[Language: {result['language']}]",
        f"[Status: {label}]",
        f"[RMS: {screen['rms_db']} dBFS | Speech ratio: {screen['speech_ratio']:.0%}]",
        "",
    ]

    if status == "SPEECH" and text:
        lines.append(text)
        lines.append("")
        lines.append("--- Segments ---")
        for seg in result["segments"]:
            lp   = seg["avg_logprob"]
            nsp  = seg["no_speech_prob"]
            flag = "  [low confidence]" if lp < -0.8 or nsp > 0.4 else ""
            lines.append(f"[{seg['start']:.2f}s → {seg['end']:.2f}s] {seg['text']}{flag}")
    else:
        messages = {
            "NO_SPEECH":      "(no speech detected in this stream)",
            "NOISE":          "(non-speech audio — cough, background noise, music, etc.)",
            "LOW_CONFIDENCE": "(Whisper confidence too low — stream is mostly noise/artifacts)",
            "REPETITIVE":     "(Whisper hallucination detected — audio too distorted for ASR)",
        }
        lines.append(messages.get(status, "(no meaningful speech)"))

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return text, status
