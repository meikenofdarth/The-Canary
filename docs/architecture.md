# The Canary — Technical Architecture

> Problem Statement: **Real-Time Multi-User Smart Assistant for Dynamic and Noisy
> Smart Environments**

The Canary is a real-time, multi-user smart assistant that ingests mono/stereo
audio from a chaotic environment, separates up to three overlapping speakers,
distinguishes device-directed commands from ambient chatter, identifies *who*
spoke, resolves conflicts between users, and produces a personalized spoken
response — all on commodity CPU hardware.

The design philosophy is a **Sequential Gated Modular Pipeline**: cheap,
deterministic gates run first and only escalate to heavier neural stages when
genuine, device-directed speech is detected. Every stage is a swappable module
behind a stable internal API, which is what let us iterate on the separation
model without touching the rest of the system.

---

## 1. High-level data flow

```
                 ┌──────────────────────────────────────────────────────────┐
   mic / upload  │  AUDIO INGESTION  (16 kHz mono)                            │
  ───────────────►  run_canary.record_until_silence()  /  POST /api/command  │
                 └───────────────┬──────────────────────────────────────────┘
                                 ▼
                 ┌──────────────────────────────┐
                 │  STAGE 0 — GATING            │  Silero VAD (stop-on-silence,
                 │  computation/audio/vad_*     │  per-speaker adaptive thresholds)
                 └───────────────┬──────────────┘  energy pre-screen
                                 ▼
                 ┌──────────────────────────────┐
                 │  ACOUSTIC RAG (DTW)          │  first-chance ASR bypass for
                 │  intelligence/acoustic_rag   │  enrolled anchor commands;
                 └───────────────┬──────────────┘  no-op until enrolled
                                 ▼  (no confident match → continue)
                 ┌──────────────────────────────┐
                 │  DENOISE                     │  noisereduce (spectral gating)
                 │  run_canary._light_denoise   │
                 └───────────────┬──────────────┘
                                 ▼
                 ┌──────────────────────────────┐
                 │  SPEAKER COUNT ESTIMATION    │  spectral features + greedy
                 │  speaker_counter.py          │  agglomerative clustering (1–3)
                 └───────────────┬──────────────┘
                                 ▼
          ┌──────────────────────┴───────────────────────┐
          │  1 speaker → direct enhance (no separation)   │
          │  ≥2 speakers → SEPARATION                      │
          └──────────────────────┬───────────────────────┘
                                 ▼
                 ┌──────────────────────────────┐
                 │  MULTI-SPEAKER SEPARATION    │  Asteroid ConvTasNet (5.067M)
                 │  run_canary._run_sepformer   │  cached, warm xRT ~0.11
                 │  + cross-talk reduction      │  Gram-Schmidt + RMS ghost gate
                 └───────────────┬──────────────┘
                                 ▼
                 ┌──────────────────────────────┐
                 │  PER-STREAM ENHANCEMENT      │  HPF + denoise + presence boost
                 │  → outputs/<ts>/speaker_N.wav│
                 └───────────────┬──────────────┘
                                 ▼
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                         ▼
┌───────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ ASR           │      │ SPEAKER IDENTITY │      │ WAKEWORD          │
│ Whisper tiny  │      │ ECAPA-TDNN +     │      │ C++ weighted-     │
│ + quality     │      │ pitch/energy/    │      │ Levenshtein       │
│ gates         │      │ rate/MFCC fusion │      │ phonetic matcher  │
└───────┬───────┘      └────────┬─────────┘      └────────┬─────────┘
        └───────────────────────┼─────────────────────────┘
                                 ▼
                 ┌──────────────────────────────┐
                 │  INTELLIGENCE LAYER (rules)  │  utterance analyzer,
                 │  computation/intelligence/*  │  conflict detector, context
                 │  + Lisp Matrix phonetic      │  builder, DRS; phonetic intent
                 │    intent fallback           │  recovery for garbled ASR
                 └───────────────┬──────────────┘
                                 ▼
                 ┌──────────────────────────────┐
                 │  ARBITRATION ENGINE          │  priority = 0.4·wakeword
                 │  → EXECUTE / CLARIFY /        │           + 0.4·id_conf
                 │    MULTI_EXECUTE / IGNORE     │           + 0.2·known_user
                 └───────────────┬──────────────┘
                                 ▼
                 ┌──────────────────────────────┐
                 │  AGENTIC TOOL LAYER          │  weather / news / music tools
                 │  backend/mcp_server.py       │  (real public-API calls)
                 │  → gTTS spoken response      │
                 └──────────────────────────────┘
```

---

## 2. Stage-by-stage detail

### Stage 0 — Gating (cheap, always on)
- **Silero VAD** (`computation/audio/vad_segmenter.py`) drives stop-on-silence
  recording and speech-segment timestamps. Tiny (0.463M params), sub-ms/frame.
- **Adaptive (disfluency-aware) VAD** — per-speaker profiles (default / disfluent
  / stutter) widen the silence tolerance and merge gap so a stuttering block is
  not truncated or split into two commands. See `docs/adaptive_vad.md`.
- **Energy pre-screen** (`computation/audio/transcribe.py::pre_screen`) rejects
  silent/low-voiced streams before any heavy model runs (RMS < −52 dBFS or
  voiced ratio < 15% → REJECTED).

### Acoustic RAG first-chance (ASR-bypass accessibility fallback)
- `computation/intelligence/acoustic_rag.py` matches the raw audio against a
  user's enrolled anchor-command MFCC templates with FastDTW. On a confident,
  time-warp-invariant match the intent fires immediately, bypassing separation
  and ASR — the deterministic fallback for speech too atypical to transcribe.
  Strict no-op (zero added latency) until a user enrolls commands. See
  `docs/acoustic_rag.md`.

### Denoise
- `noisereduce` non-stationary spectral gating removes fans/HVAC/room hum while
  preserving speech. Classical DSP, 0 parameters.

### Speaker count estimation
- `computation/audio/speaker_counter.py` slides a 500 ms window, extracts a
  6-dim spectral feature vector per voiced frame, standardizes, and runs greedy
  agglomerative clustering across multiple thresholds; the median cluster count
  is the estimate (1–3). Classical, 0 parameters.

### Multi-speaker separation (the budgeted model)
- **Asteroid ConvTasNet** (`JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k`,
  **5.067M params**) behind `run_canary._run_sepformer()`.
- **Process-level cache** (`_get_separation_model`): the model loads once per
  process (thread-safe), warmed at backend startup, so warm-call **xRT ≈ 0.11**.
- **3-speaker path** (`detect_and_separate_3spk`) runs the 2-mix model and keeps
  output streams whose speech-band (300–3400 Hz) RMS ≥ 25% of the loudest, then
  down-routes to single-speaker if only one real stream survives.
- **Cross-talk reduction** (`_reduce_crosstalk`, Gram-Schmidt) plus an
  energy-ratio gate to drop faint artifact ("ghost") streams.

### ASR
- **OpenAI Whisper (tiny)** (`computation/audio/transcribe.py`) with a
  two-sided quality gate: energy/VAD pre-screen before, and avg-logprob +
  repetition + compression-ratio checks after, to suppress hallucinations.

### Speaker identity / biometrics
- 5-group feature fusion (`computation/voice/features.py`, `matcher.py`,
  `ranker.py`): **ECAPA-TDNN** 192-d embedding (95% weight) + pitch + energy +
  speaking-rate + MFCC. Cosine/Gaussian similarity against enrolled profiles in
  `database/Voices/`, with a margin + per-feature-agreement decision gate.

### Wakeword
- C++ **weighted-Levenshtein phonetic matcher** (`computation/wakeword/`) with a
  fuzzy mis-transcription table — matches the active wakeword (e.g. "jarvis")
  against the (noisy) STT output. Zero neural parameters.

### Intelligence layer (deterministic)
- `utterance_analyzer.py` (COMMAND / QUESTION / CONVERSATION / UNKNOWN across 15
  smart-home domains), `conflict_detector.py` (antonym-action & override
  conflicts), `context_builder.py` (aggregates into `context.json`), and the
  **Dynamic Resource Scaler (DRS)** which classifies the acoustic scene into
  Mode A/B/C from overlap, noise, and speaker scores.
- **Lisp Matrix phonetic fallback** (`phonetic_matcher.py`, wired into
  `intent_engine.analyze_intent`): when the rule-based classifier finds no domain
  because the ASR garbled the keyword (e.g. a lisp turns "news"→"newth"), the
  transcript is matched in *phonetic* space (Double Metaphone + Needleman-Wunsch)
  against the command lexicon, under the speaker's per-user confusion matrix. See
  `docs/lisp_matrix.md`.

### Arbitration + agentic tool layer
- The **arbitration engine** scores each speaker
  `priority = 0.4·wakeword + 0.4·identity_conf + 0.2·known_user` and routes to
  EXECUTE / CLARIFY / MULTI_EXECUTE / IGNORE (this is where Role-Based Access
  Control / hierarchical resolution lives).
- The **tool layer** (`backend/mcp_server.py`) exposes `get_weather`,
  `get_news`, `play_media`, `stop_media`, chained from the classified intent +
  resolved speaker + entities, calling real public APIs (wttr.in, Google News
  RSS, iTunes) and speaking the result via gTTS. See `docs/ax.md`.

---

## 2b. Phenotypic-inclusive accessibility stack

A layered, deterministic, zero-extra-parameter stack adapts the pipeline to each
speaker's physiology — the project's main innovation theme:

```
audio → [Adaptive VAD]           per-speaker silence tolerance (no truncation)
      → [Acoustic RAG / DTW]     --confident--> intent (ASR bypassed entirely)
              │ no match
              ▼
        separate → ASR → [Lisp Matrix phonetic repair] → intent
```

| Layer | Module | Failure mode it fixes |
|---|---|---|
| Adaptive VAD | `audio/vad_segmenter.py` | stutter blocks truncated/split by rigid silence thresholds |
| Acoustic RAG (DTW) | `intelligence/acoustic_rag.py` | speech too atypical for ASR at all (profound dysarthria) |
| Lisp Matrix | `intelligence/phonetic_matcher.py` | ASR garbles the keyword phonetically (lisp, accent) |

All three key off the **same per-speaker profile** loaded after ECAPA speaker
identification, so a household with a neurotypical speaker, a lisping speaker,
and a stuttering speaker share one device and the pipeline reconfigures per
utterance. Details: `docs/acoustic_rag.md`, `docs/lisp_matrix.md`,
`docs/adaptive_vad.md`.

---

## 3. Service topology

```
frontend/web (Next.js)  ─┐
frontend/mobile (RN)    ─┼── HTTP/JSON ──►  FastAPI backend (backend/api.py, :8000)
                          │                   ├─ /api/command   (full pipeline)
                          │                   ├─ /api/enroll     (voice profiles)
                          │                   ├─ /api/change-wakeword
                          │                   ├─ /api/users, /api/status
                          │                   └─ /api/run, /api/run/result
                          │                 run_canary.py  (CLI orchestrator)
                          │                 computation/*  (audio, voice, intel)
                          │                 backend/mcp_server.py (tool layer)
```

The FastAPI layer is a thin wrapper over the same `run_canary` functions used by
the CLI, so the API and CLI exercise an identical pipeline. Request/response
schemas (e.g. `/api/command` → `{route, transcript, speaker, domain, entities,
execution_result, drs_mode}`) are stable and were preserved across all model
swaps.

---

## 4. Design decisions that shaped the architecture

- **Decoupled, gated pipeline** so the 5M parameter budget applies only to the
  separation system; ASR and biometrics run as separate downstream stages.
- **Single chokepoint for separation** (`_run_sepformer`) so the model could be
  swapped (SepFormer → ConvTasNet, and DPRNN/TIGER trials) without touching any
  caller or API contract.
- **Deterministic intelligence/arbitration** (rules, not an LLM) to stay within
  real-time and on-device constraints — see the rationale and trade-offs in
  `docs/ax.md`.

See `docs/separation_results.md` for measured KPIs and the model-selection
benchmark log.
