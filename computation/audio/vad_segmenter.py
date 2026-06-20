
from __future__ import annotations

import queue
import threading

import numpy as np


_SILERO_CHUNK = 512

_VAD_THRESHOLD = 0.40

_MIN_SPEECH_MS = 250

_MIN_SILENCE_MS = 400

_SPEECH_PAD_MS = 120


_VAD_PROFILES: dict[str, dict] = {
    "default":   {"silence_timeout": 1.8, "min_silence_ms": 400,  "threshold": 0.40, "max_duration": 15.0},
    "disfluent": {"silence_timeout": 2.5, "min_silence_ms": 1200, "threshold": 0.35, "max_duration": 22.0},
    "stutter":   {"silence_timeout": 3.0, "min_silence_ms": 1800, "threshold": 0.35, "max_duration": 25.0},
}


def adaptive_vad_config(profile: str = "default") -> dict:
    return dict(_VAD_PROFILES.get(profile, _VAD_PROFILES["default"]))


_vad_model = None
_vad_lock   = threading.Lock()


def _get_vad_model():
    global _vad_model
    if _vad_model is None:
        with _vad_lock:
            if _vad_model is None:
                from silero_vad import load_silero_vad
                _vad_model = load_silero_vad()
    return _vad_model


def record_until_silence(
    max_duration:    float | None = None,
    silence_timeout: float | None = None,
    sr:              int   = 16_000,
    profile:         str   = "default",
) -> np.ndarray:
    import sounddevice as sd
    import torch

    cfg = adaptive_vad_config(profile)
    if max_duration is None:
        max_duration = cfg["max_duration"]
    if silence_timeout is None:
        silence_timeout = cfg["silence_timeout"]

    model = _get_vad_model()
    model.reset_states()

    audio_q:   queue.Queue = queue.Queue()
    frames_all: list       = []
    stop_evt               = threading.Event()

    def _sd_callback(indata, frames, time_info, status):
        audio_q.put(indata[:, 0].copy())

    print(
        f"\n● Listening — speak now  "
        f"(auto-stops after {silence_timeout:.1f}s silence | max {max_duration:.0f}s max)"
    )

    vad_buf             = np.zeros(0, dtype=np.float32)
    speech_started      = False
    consecutive_silent  = 0
    total_samples       = 0
    max_samples         = int(max_duration * sr)
    silence_threshold   = int(silence_timeout * sr)

    with sd.InputStream(
        samplerate = sr,
        channels   = 1,
        dtype      = "float32",
        blocksize  = _SILERO_CHUNK,
        callback   = _sd_callback,
    ):
        while not stop_evt.is_set():
            try:
                chunk = audio_q.get(timeout=0.5)
            except queue.Empty:
                continue

            frames_all.append(chunk)
            vad_buf       = np.concatenate([vad_buf, chunk])
            total_samples += len(chunk)

            while len(vad_buf) >= _SILERO_CHUNK:
                frame   = vad_buf[:_SILERO_CHUNK]
                vad_buf = vad_buf[_SILERO_CHUNK:]

                tensor   = torch.from_numpy(frame.copy())
                speech_p = float(model(tensor, sr).item())

                if speech_p > _VAD_THRESHOLD:
                    speech_started     = True
                    consecutive_silent = 0
                    elapsed            = total_samples / sr
                    print(f"  ● {elapsed:.1f}s", end="\r", flush=True)
                else:
                    if speech_started:
                        consecutive_silent += _SILERO_CHUNK
                        sil_s = consecutive_silent / sr
                        print(
                            f"  ○ silence {sil_s:.1f}s / {silence_timeout:.1f}s  ",
                            end="\r", flush=True
                        )

                if speech_started and consecutive_silent >= silence_threshold:
                    print(
                        f"\n  Recording stopped — silence detected "
                        f"({silence_timeout:.1f}s).     "
                    )
                    stop_evt.set()
                    break

                if total_samples >= max_samples:
                    print(
                        f"\n  Recording stopped — max duration "
                        f"({max_duration:.0f}s) reached."
                    )
                    stop_evt.set()
                    break

    if not frames_all:
        return np.zeros(sr, dtype=np.float32)

    return np.concatenate(frames_all).astype(np.float32)


def get_vad_segments(
    audio:          np.ndarray,
    sr:             int   = 16_000,
    threshold:      float | None = None,
    min_speech_ms:  int   = _MIN_SPEECH_MS,
    min_silence_ms: int | None = None,
    pad_ms:         int   = _SPEECH_PAD_MS,
    profile:        str   = "default",
) -> list[dict]:
    cfg = adaptive_vad_config(profile)
    if threshold is None:
        threshold = cfg["threshold"]
    if min_silence_ms is None:
        min_silence_ms = cfg["min_silence_ms"]

    import torch
    from silero_vad import get_speech_timestamps

    model = _get_vad_model()

    wav = torch.from_numpy(audio.astype(np.float32))

    raw_ts = get_speech_timestamps(
        wav,
        model,
        sampling_rate       = sr,
        threshold           = threshold,
        min_speech_duration_ms  = min_speech_ms,
        min_silence_duration_ms = min_silence_ms,
        speech_pad_ms       = pad_ms,
        return_seconds      = False,
    )

    if not raw_ts:
        total = len(audio)
        return [{
            "start_s":      0.0,
            "end_s":        round(total / sr, 3),
            "start_sample": 0,
            "end_sample":   total,
            "duration_s":   round(total / sr, 3),
        }]

    segments = []
    n = len(audio)
    for ts in raw_ts:
        st = max(0, int(ts["start"]))
        en = min(n, int(ts["end"]))
        if en <= st:
            continue
        dur = (en - st) / sr
        segments.append({
            "start_s":      round(st / sr, 3),
            "end_s":        round(en / sr, 3),
            "start_sample": st,
            "end_sample":   en,
            "duration_s":   round(dur, 3),
        })

    return segments


def print_segments(segments: list[dict]) -> None:
    print(f"  Found {len(segments)} speech segment(s):")
    for i, seg in enumerate(segments, 1):
        bar = "─" * max(1, int(seg["duration_s"] * 8))
        print(
            f"    Seg {i:02d}  [{seg['start_s']:>5.2f}s → {seg['end_s']:>5.2f}s]"
            f"  {seg['duration_s']:.2f}s  {bar}"
        )
