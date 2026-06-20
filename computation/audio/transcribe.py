
from __future__ import annotations

import os
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

_DEFAULT_MODEL = os.environ.get("CANARY_ASR_MODEL", "tiny")

_INITIAL_PROMPT = (
    "Smart home voice assistant transcript. Wake words: canary, jarvis. "
    "Common commands: what is the weather in my city, what's the time, "
    "play some music, set a timer, turn on the lights, what's the news today. "
    "Speakers: Hemang, Deepkumar, Sanchit. Use clear punctuation."
)


def _load_model(model_name: str = _DEFAULT_MODEL):
    if model_name not in _model_cache:
        import whisper
        _model_cache[model_name] = whisper.load_model(model_name)
    return _model_cache[model_name]


def pre_screen(
    wav_path: str | Path,
    rms_threshold_db: float   = -52.0,
    speech_ratio_threshold: float = 0.15,
    frame_ms: int             = 30,
) -> dict:
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    rms    = float(np.sqrt(np.mean(audio ** 2)))
    rms_db = 20.0 * np.log10(rms + 1e-10)

    if rms_db < rms_threshold_db:
        return {
            "rms_db": round(rms_db, 1),
            "speech_ratio": 0.0,
            "verdict": "REJECTED",
            "reason": f"RMS {rms_db:.1f} dBFS below threshold {rms_threshold_db} dBFS — silent stream",
        }

    frame_len   = max(1, int(sr * frame_ms / 1000))
    n_frames    = len(audio) // frame_len
    if n_frames == 0:
        return {"rms_db": round(rms_db,1), "speech_ratio": 0.0,
                "verdict": "REJECTED", "reason": "Audio too short for VAD"}

    frame_rms   = np.array([
        np.sqrt(np.mean(audio[i * frame_len : (i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
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
    text     = result.get("text", "").strip()
    segments = result.get("segments", [])

    if not text or not segments:
        return "NOISE" if has_vad_speech else "NO_SPEECH"

    avg_no_speech = float(np.mean([s.get("no_speech_prob", 0.0) for s in segments]))
    if avg_no_speech > 0.65:
        return "NOISE" if has_vad_speech else "NO_SPEECH"

    lp_values = [s.get("avg_logprob", -0.5) for s in segments if "avg_logprob" in s]
    if lp_values:
        avg_logprob = float(np.mean(lp_values))
        if avg_logprob < -1.2:
            return "LOW_CONFIDENCE"

    if _is_repetitive(text):
        return "REPETITIVE"
    if _compression_ratio(text) > 2.8 and len(text) > 80:
        return "REPETITIVE"

    if len(set(text.lower().split())) < 3:
        return "NOISE"

    return "SPEECH"


def transcribe(
    wav_path: str | Path,
    model_name: str = _DEFAULT_MODEL,
    language: Optional[str] = "en",
    has_vad_speech: bool = False,
) -> dict:
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
            beam_size=5,
            best_of=5,
            temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            compression_ratio_threshold=2.4,
            logprob_threshold=-1.0,
            no_speech_threshold=0.5,
            condition_on_previous_text=False,
            initial_prompt=_INITIAL_PROMPT,
            verbose=False,
            fp16=False,
        )

    segments = []
    text_parts = []
    for seg in result.get("segments", []):
        segments.append({
            "start":          round(seg.get("start", 0.0), 2),
            "end":            round(seg.get("end", 0.0), 2),
            "text":           seg.get("text", "").strip(),
            "no_speech_prob": round(seg.get("no_speech_prob", 0.0), 3),
            "avg_logprob":    round(seg.get("avg_logprob", -0.5), 3),
        })
        text_parts.append(seg.get("text", ""))

    raw = {
        "text":     (result.get("text", "") or " ".join(text_parts)).strip(),
        "language": result.get("language", language or "unknown"),
        "segments": segments,
    }
    raw["status"] = classify_speech(raw, has_vad_speech=has_vad_speech)

    if raw["status"] in ("REPETITIVE", "LOW_CONFIDENCE"):
        raw["text"] = ""

    return raw


_STATUS_LABELS = {
    "SPEECH":         "✓  READY — meaningful speech detected",
    "NO_SPEECH":      "✗  REJECTED — no speech (silence)",
    "NOISE":          "✗  REJECTED — non-speech audio (cough / background noise)",
    "LOW_CONFIDENCE": "✗  REJECTED — Whisper confidence too low (noise/artifacts)",
    "REPETITIVE":     "✗  REJECTED — Whisper hallucination loop (distorted audio)",
    "PRE_REJECTED":   "✗  REJECTED — failed pre-screening (insufficient speech)",
}


def transcribe_and_save(
    wav_path: str | Path,
    model_name: str = _DEFAULT_MODEL,
    language: Optional[str] = "en",
) -> tuple[str, str]:
    wav_path = Path(wav_path)
    txt_path = wav_path.with_suffix(".txt")

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

    result = transcribe(wav_path, model_name=model_name, language=language)
    status = result["status"]
    text   = result["text"].lower() if result["text"] else result["text"]
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
