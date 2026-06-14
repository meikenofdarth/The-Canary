"""
separation-filtering/vad_segmenter.py
=======================================
Silero VAD-based recording and speech segmentation.

This is the architectural replacement for the fixed 7-second `record()` function.
It mirrors what Alexa, Siri, and Google Assistant do:

  1.  Stream microphone audio continuously.
  2.  Feed each 32ms frame to Silero VAD (lightweight, on-device).
  3.  Stop recording when trailing silence exceeds `silence_timeout` seconds
      (or `max_duration` hard limit is hit).
  4.  Run Silero VAD over the complete buffer to produce speech-segment timestamps
      with millisecond precision.

Public API
----------
  record_until_silence(max_duration, silence_timeout, sr) -> np.ndarray
      Live microphone recording that stops on silence.

  get_vad_segments(audio, sr, ...) -> list[dict]
      Runs Silero VAD on a buffer and returns speech segment timestamps.
      Each dict:
          start_s       — segment start (seconds)
          end_s         — segment end   (seconds)
          start_sample  — start in samples
          end_sample    — end in samples
          duration_s    — segment length (seconds)
"""

from __future__ import annotations

import queue
import threading

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

# Silero VAD requires EXACTLY 512 samples per inference call at 16 kHz
# (= 32 ms frame).  Do not change this unless also resampling to 8 kHz.
_SILERO_CHUNK = 512

# VAD probability above this → speech; below → silence
_VAD_THRESHOLD = 0.40

# Minimum speech segment to keep (ms) — very short bursts are noise
_MIN_SPEECH_MS = 250

# Silence gap smaller than this merges adjacent segments (ms)
_MIN_SILENCE_MS = 400

# Each kept segment is padded by this many ms on both sides (avoid clipping)
_SPEECH_PAD_MS = 120


# ─────────────────────────────────────────────────────────────────────────────
#  Model loader (cached — loaded once per process)
# ─────────────────────────────────────────────────────────────────────────────

_vad_model = None
_vad_lock   = threading.Lock()


def _get_vad_model():
    """Load Silero VAD model once and cache it."""
    global _vad_model
    if _vad_model is None:
        with _vad_lock:
            if _vad_model is None:
                from silero_vad import load_silero_vad
                _vad_model = load_silero_vad()
    return _vad_model


# ─────────────────────────────────────────────────────────────────────────────
#  Stop-on-silence recorder
# ─────────────────────────────────────────────────────────────────────────────

def record_until_silence(
    max_duration:    float = 15.0,
    silence_timeout: float = 2.5,
    sr:              int   = 16_000,
) -> np.ndarray:
    """
    Record microphone audio until silence or timeout — exactly how
    Alexa and Siri do it.

    Parameters
    ----------
    max_duration    : Hard upper limit (seconds).  Recording always stops here.
    silence_timeout : Seconds of consecutive non-speech that trigger stop.
                      Only active AFTER the first speech is detected —
                      so pre-speech silence (e.g. walking to the mic) is ignored.
    sr              : Sample rate.  Must be 16000 for Silero VAD.

    Returns
    -------
    np.ndarray  — float32 mono audio at `sr`.

    Terminal output
    ---------------
    ● Listening — speak now  (auto-stops after Xs silence | max Ys)
      ● 1.2s          ← while speech detected
      ○ silence 0.4s  ← while silent after first speech
      Recording stopped — silence detected (2.5s).
    """
    import sounddevice as sd
    import torch

    model = _get_vad_model()
    model.reset_states()   # clear LSTM hidden state from any previous call

    audio_q:   queue.Queue = queue.Queue()
    frames_all: list       = []
    stop_evt               = threading.Event()

    def _sd_callback(indata, frames, time_info, status):
        audio_q.put(indata[:, 0].copy())   # keep mono

    print(
        f"\n● Listening — speak now  "
        f"(auto-stops after {silence_timeout:.1f}s silence | max {max_duration:.0f}s max)"
    )

    vad_buf             = np.zeros(0, dtype=np.float32)  # accumulate until _SILERO_CHUNK
    speech_started      = False
    consecutive_silent  = 0    # samples of silence seen after first speech
    total_samples       = 0
    max_samples         = int(max_duration * sr)
    silence_threshold   = int(silence_timeout * sr)

    with sd.InputStream(
        samplerate = sr,
        channels   = 1,
        dtype      = "float32",
        blocksize  = _SILERO_CHUNK,   # sounddevice delivers _SILERO_CHUNK frames per callback
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

            # Process every complete _SILERO_CHUNK frame through the VAD
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

                # ── Stop conditions ───────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
#  VAD segmenter — run on a complete buffer
# ─────────────────────────────────────────────────────────────────────────────

def get_vad_segments(
    audio:          np.ndarray,
    sr:             int   = 16_000,
    threshold:      float = _VAD_THRESHOLD,
    min_speech_ms:  int   = _MIN_SPEECH_MS,
    min_silence_ms: int   = _MIN_SILENCE_MS,
    pad_ms:         int   = _SPEECH_PAD_MS,
) -> list[dict]:
    """
    Run Silero VAD over `audio` and return a list of speech segments.

    Parameters
    ----------
    audio          : float32 mono audio at `sr`.
    sr             : Sample rate (must be 16000).
    threshold      : VAD speech probability threshold (0–1).
    min_speech_ms  : Discard segments shorter than this (ms).
    min_silence_ms : Merge segments with gaps shorter than this (ms).
    pad_ms         : Add this many ms of context to each segment boundary.

    Returns
    -------
    list[dict]  — sorted by start time, each dict has:
        start_s       — start time (seconds)
        end_s         — end   time (seconds)
        start_sample  — start in samples (clipped to audio bounds)
        end_sample    — end   in samples (clipped to audio bounds)
        duration_s    — segment length   (seconds)

    Notes
    -----
    If no speech is found, returns a single segment spanning the full audio.
    This prevents downstream code from processing an empty segment list.
    """
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
        return_seconds      = False,    # we get samples; convert ourselves
    )

    # ── Fallback: no speech found → single full-audio segment ────────────────
    if not raw_ts:
        total = len(audio)
        return [{
            "start_s":      0.0,
            "end_s":        round(total / sr, 3),
            "start_sample": 0,
            "end_sample":   total,
            "duration_s":   round(total / sr, 3),
        }]

    # ── Convert + clip to audio length ───────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
#  Pretty-print for terminal
# ─────────────────────────────────────────────────────────────────────────────

def print_segments(segments: list[dict]) -> None:
    """Print segment timestamps to terminal."""
    print(f"  Found {len(segments)} speech segment(s):")
    for i, seg in enumerate(segments, 1):
        bar = "─" * max(1, int(seg["duration_s"] * 8))
        print(
            f"    Seg {i:02d}  [{seg['start_s']:>5.2f}s → {seg['end_s']:>5.2f}s]"
            f"  {seg['duration_s']:.2f}s  {bar}"
        )
