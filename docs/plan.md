# The Canary — Project Plan & Method

This document describes the goals, design decisions, and implementation methodology for each stage of the pipeline.

---

## Overview

The Canary is built around a single principle: **do the cheapest thing first**. Cheap deterministic gates run before any neural model. Heavy models only run when they are necessary. This keeps the system real-time on commodity CPU hardware even with multiple neural stages in the pipeline.

The < 5M parameter budget applies specifically to the **multi-speaker separation system** (separator + VAD gate). ASR and speaker ID are independent downstream stages outside that budget.

---

## Stage 1 — Stop-on-Silence Recording

**Goal:** Capture user speech dynamically instead of a fixed-duration buffer.

- Stream microphone audio in 32ms frames at 16 kHz.
- Feed each frame to Silero VAD (0.463M params).
- Start buffering on first speech frame.
- Stop recording after **1.8 seconds** of trailing silence, or at a hard 15-second cap.
- Module: `computation/audio/vad_segmenter.py` · function `record_until_silence()`.

**Why it matters:** Fixed-duration recording picks up unnecessary silence and room noise. VAD-gated recording gives the downstream denoiser and separator a cleaner, shorter clip to work with.

---

## Stage 2 — Speaker Count Estimation

**Goal:** Decide whether to run separation at all, and how many output streams to expect.

- Slide a 500 ms window (50% overlap) across the audio.
- Extract a 6-dimensional acoustic feature vector per voiced frame: log energy, zero-crossing rate, spectral centroid, spectral bandwidth, spectral rolloff, log flatness.
- Standardize features and run greedy agglomerative clustering across multiple distance thresholds.
- Take the median cluster count as the estimate (1–3 speakers).
- Module: `computation/audio/speaker_counter.py` · class `SpeakerCountEstimator`.

No model parameters. Entirely classical DSP. Fast enough to run synchronously before the separation model.

---

## Stage 3 — Speaker Source Separation

**Goal:** Separate overlapping speech into individual mono streams.

**Model:** Asteroid ConvTasNet `JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k` — 5.067M params, Apache-2.0.

**Routing logic:**
- **1 speaker:** Skip separation entirely. Run enhancement directly on the raw mix to avoid model artifacts on clean single-speaker input.
- **2 speakers:** Run ConvTasNet, get two output streams.
- **3 speakers (estimated):** Run the 2-source ConvTasNet (the highest-quality model available under budget), then filter output streams by speech-band RMS (300–3400 Hz). Any stream below 25% of the loudest is discarded as a ghost artifact. If only one real stream survives, down-route to single-speaker.

**Inference path:** Whole-clip inference for clips ≤ 20s (single forward pass). No overlap-add chunking — chunking rescales each window independently and introduces seam artifacts that cost ~4.8 dB SI-SNR. See `docs/ax.md` for the full A/B measurement.

**Caching:** `_get_separation_model()` loads the model once per process into a thread-safe cache. The backend warms it at startup so the first `/api/command` request pays no cold-load cost.

---

## Stage 4 — Cross-Talk Reduction and Enhancement

**Goal:** Remove leakage between separated streams and improve intelligibility.

**Cross-talk reduction:**
- Gram-Schmidt orthogonalization (`_reduce_crosstalk`) removes shared energy between streams.
- Sort output streams by speech-band RMS so the dominant speaker is always `speaker_1`.

**Per-stream enhancement (`enhance_stream`):**
1. High-pass filter at 80 Hz — removes DC offset and sub-speech rumble.
2. Non-stationary spectral gating via noisereduce — removes fans, HVAC, room hum.
3. Presence boost — +3.5 dB gain above 2 kHz for clarity.
4. Soft-knee dynamic range compression — threshold −18 dBFS, ratio 3:1, 5ms attack, 150ms release.
5. RMS normalization to −18 dBFS with peak limiting at −1.0 dBFS.

---

## Stage 5 — Automatic Speech Recognition

**Goal:** Transcribe each enhanced stream to text with hallucination suppression.

**Model:** OpenAI Whisper tiny (37.2M params, MIT). Chosen over Whisper base for speed on CPU while maintaining acceptable accuracy for command-style utterances.

**Pre-screen gate (before Whisper runs):**
- Reject stream if RMS < −52 dBFS (silent).
- Reject if voiced frame ratio < 15% (energy-based VAD check).

**Post-screen gate (after Whisper runs):**
- Reject if average segment log-probability < −1.2 (gibberish/noise input).
- Reject if transcript shows repetitive patterns (hallucination loop).
- Reject if text compression ratio > 2.8 for long strings (Whisper looping).

Streams that fail either gate are marked REJECTED and their transcripts discarded. Passing streams are marked SPEECH and forwarded to the context engine.

---

## Stage 6 — Voiced Segment Extraction for Speaker ID

**Goal:** Feed only active speech — not silence or noise — to the voice matcher.

- Compute RMS of 30ms frames in the output WAV.
- Estimate noise floor as the 10th percentile of frame RMS values.
- Keep only frames where RMS > noise_floor × 2.5.
- Concatenate voiced frames into a single array before calling the matcher.

Running embedding comparison on full files contaminates voice profiles with room silence and breath sounds. Voiced-only extraction improves match confidence in noisy conditions.

---

## Stage 7 — Voice Identification

**Goal:** Match separated speaker streams to enrolled users.

**Feature fusion (weighted cosine/Gaussian similarity):**
| Feature | Weight |
|---|---|
| ECAPA-TDNN embedding (192-d) | 95% |
| MFCC centroid | 2% |
| Pitch | 1% |
| Energy | 1% |
| Speaking rate | 1% |

- Enrolled profiles stored in `database/Voices/<name>/features/` as `.npy` files.
- Confidence floor for multi-speaker scenes: 0.05 (permissive — separation artifacts compress scores).
- Quality gates (SI-SNR, speech ratio, RMS) are disabled during matching — valid speakers should never be rejected because of a noisy separation.
- UNKNOWN returned if no enrolled user exceeds threshold.

---

## Stage 8 — Dynamic Resource Scaler (DRS)

**Goal:** Classify the acoustic scene complexity to inform downstream routing.

Complexity score:
```
complexity = overlap_prob × 0.5  +  noise_level × 0.3  +  speaker_score × 0.2
```

Mode assignment:
| Complexity | Mode | Label |
|---|---|---|
| < 0.25 | A | Clean Scene |
| 0.25 – 0.70 | B | Moderate Interference |
| ≥ 0.70 | C | High Interference · Heavy Noise |

Hard overrides:
- noise_level > 0.85 → force Mode C regardless of overlap.
- overlap_prob > 0.90 AND noise_level > 0.40 → force Mode C.
- 3+ speakers detected → force Mode C.

The overlap hard rule requires **both** conditions (overlap AND noise) to be met before forcing Mode C. This prevents moderate turn-taking scenes (high overlap, low noise) from being misclassified as Mode C — they land in Mode B where they belong.

---

## Stage 9 — Intelligence Layer

**Goal:** Classify intent, detect conflicts, build routing context.

**Utterance analyzer** — regex classifier over 15 smart-home domains (Media, Lighting, Climate, Security, Appliances, Entertainment, Communication, Shopping, Timers, Navigation, Routines, Search, Volume, Open/Close, Health). Classifies each transcript as COMMAND / QUESTION / CONVERSATION / UNKNOWN.

**Wakeword detector** — weighted-Levenshtein fuzzy matcher with a table of >40 common Whisper mis-transcriptions of each wakeword (e.g. "cannery", "qanary", "anari"). Confidence weights 0.55–0.80.

**Conflict detector** — scans commands from different speakers for antonym action pairs (play/stop, on/off, open/close, warmer/cooler) and override phrases ("listen to me", "ignore him").

**Lisp Matrix phonetic fallback** — if wakeword is detected but the literal transcript doesn't classify:
1. Encode transcript and each command with Double Metaphone.
2. Apply per-speaker confusion matrix (e.g. lisp profile: S ↔ 0, /s/ ↔ /th/ cost 0).
3. Run Needleman-Wunsch alignment; normalized distance < threshold → intent matched.
Result: "play thome muthic" → "play some music" at distance 0.0 under the lisp profile.

---

## Stage 10 — Arbitration and Tool Execution

**Goal:** Decide which command(s) to execute and call the appropriate tool.

Priority score per speaker:
```
priority = 0.4 × wakeword_conf  +  0.4 × identity_conf  +  0.2 × known_user
```

Routing decisions:
| Commands | Conflict | Route |
|---|---|---|
| 0 | — | IGNORE |
| 1 | No | EXECUTE |
| ≥ 2 | Yes | CLARIFY |
| ≥ 2 | No | MULTI_EXECUTE |

Tool execution (`backend/mcp_server.py`):
- WEATHER → `get_weather(location)` → wttr.in JSON API
- NEWS → `get_news(location)` → Google News RSS
- SONGS (positive) → `play_media(query)` → iTunes Search + pygame
- SONGS (negative) → `stop_media()` → pygame.mixer.music.stop()

Location resolution: if the user says "my city" or "near me", the identified speaker's enrolled `location` preference is substituted. Unknown speakers fall back to the default city.

Response spoken via gTTS, played back through the system audio device.

---

## Accessibility Design

Three complementary layers handle atypical speech — one for each failure mode:

```
audio
 → [Adaptive VAD]       — physiological speech blocks not truncated
 → [Acoustic RAG/DTW]   — profound dysarthria: intent from raw acoustics
         │ no match
         ▼
 separate → ASR → [Lisp Matrix]  — phonetic ASR errors repaired per speaker
```

All three read from the same enrolled speaker profile loaded after ECAPA identification. No additional calibration overhead beyond the one-time voice enrollment.

---

## Testing

```bash
# Full test suite
pytest tests/ -v          # 18 passed, 1 xfailed (ConvTasNet budget gate)

# Parameter audit
python param_audit.py

# Separation quality on MiniLibriMix
python tests/eval_separation.py --n 50 --mix mix_clean
python tests/eval_separation.py --n 50 --mix mix_both

# xRT + sanity check
python tests/kpi_report.py

# WER on real speech
python tests/eval_wer.py --mode librimix --n 10
```

---

## Key Design Decisions Summary

| Decision | Rationale |
|---|---|
| ConvTasNet over SepFormer | 5× under xRT target; SepFormer fails both budget and real-time |
| Whole-clip inference, no overlap-add | Chunking costs ~4.8 dB via per-chunk rescaling |
| Remove STFT mask + mixture-consistency | Both degraded SI-SNR; naive form collapsed output to ~0 dB |
| Deterministic intent routing (no LLM) | LLM adds 1–3s latency on CPU; rules are ms-fast |
| Permissive voice ID thresholds | Separation artifacts compress scores; strict gates reject real users |
| Accessibility stack is zero-parameter | No new model budget consumed; deterministic and testable in isolation |
| Process-level model cache | Eliminates 0.47s cold-start cost on every API call |
