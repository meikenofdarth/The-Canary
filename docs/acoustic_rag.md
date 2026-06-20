# Acoustic RAG — DTW Command Matching (ASR-bypass fallback)

The deterministic accessibility fallback for speech so atypical (profound
dysarthria, severe stutter) that neural ASR fails entirely. Instead of trying to
*transcribe*, we *match the raw acoustic pattern* of the utterance against a
small set of per-user anchor commands using Dynamic Time Warping — firing the
command directly, bypassing ASR and the intent engine.

> Module: `computation/intelligence/acoustic_rag.py` · Tests:
> `tests/test_acoustic_rag.py` · Pure algorithmic (MFCC + FastDTW), 0 parameters,
> fully on-device.

## How it works

1. **Calibration (~60s, once per user).** The user records a handful of anchor
   commands (e.g. "turn on the lights", "what's the weather"). Each is stored as
   a sequence of 13-dim **MFCC** frames (cepstral-mean-normalized), under
   `database/acoustic_rag/<user>/<label>.npy`.
2. **Runtime match.** The incoming utterance's MFCCs are compared to each stored
   template with **FastDTW** (O(N) approximate Dynamic Time Warping). DTW *warps
   the time axis*, so a slow, hesitated, or stuttered repetition still aligns to
   the template. The per-frame-normalized DTW distance ranks the candidates.
3. **Gated firing.** If the best distance is below a threshold, the mapped intent
   is fired immediately — no ASR, no LLM, near-zero latency.

## Demonstration (from the test suite)

Enroll `lights_on` (command A) and `weather` (command B), then query with a
**0.7× time-stretched** (slowed, stutter-like) repetition of command A:

```
warped A  ->  lights_on   (per-frame DTW distance 41.3)
              weather      (per-frame DTW distance 124.3)
```

The heavily time-warped repetition still matches the correct command (41.3,
below the 55 threshold) and is ~3× closer than the different command. An
unenrolled user returns no match.

## Why it's novel & complementary

- **Bypasses ASR entirely** — works even when transcription is impossible, the
  one regime the Lisp Matrix (which repairs ASR *text*) cannot cover.
- **Per-user, zero-parameter, deterministic** — a 60-second calibration, no
  training, no model weights, fully private/on-device.
- **Time-warp invariant** — DTW absorbs the prolongations and pauses that break
  fixed-alignment ASR models.

## Integration

`AcousticRAG.open_set_match(audio, sr)` runs as a **live first-chance** in
`backend/api.py` `/api/command`: right after the silence gate, the raw audio is
matched against every enrolled user's templates; on a confident match the intent
is fired (and `execute_intent` run for WEATHER/NEWS/SONGS) and the response
returns immediately, bypassing separation + ASR. It is a strict **no-op** until a
user enrolls DTW commands, so it adds zero risk/latency to the existing pipeline.
Otherwise the request falls through to the normal separate → ASR →
(Lisp Matrix) → intent path. Together they form a layered accessibility stack:

```
audio → [Acoustic RAG / DTW] --confident--> intent (ASR bypassed)
                  | no match
                  ▼
        separate → ASR → [Lisp Matrix phonetic repair] → intent
```
