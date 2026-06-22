# The Canary — Technical Architecture

> **Problem Statement:** Real-Time Multi-User Smart Assistant for Dynamic and Noisy Smart Environments

The Canary is a real-time, multi-user voice assistant that separates up to three overlapping speakers from a single microphone, identifies who spoke, resolves command conflicts between users, and speaks a personalized response — all on commodity CPU hardware with no cloud dependency.

---

## Design Philosophy

**Sequential Gated Modular Pipeline** — cheap deterministic gates run first. Heavy neural models only run when genuine, device-directed speech is confirmed. Every stage sits behind a stable internal API so individual models can be swapped without touching the rest of the system.

---

## High-Level Data Flow

```
mic / file upload (16 kHz mono)
        │
        ▼
┌──────────────────────────────────┐
│  STAGE 0 — GATING                │  Silero VAD · energy pre-screen
│  computation/audio/vad_*         │  per-speaker adaptive silence tolerance
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  ACOUSTIC RAG (DTW)              │  first-chance ASR bypass for enrolled users
│  computation/intelligence/       │  no-op until a user enrolls commands
│    acoustic_rag.py               │
└──────────────┬───────────────────┘
               │ no confident match
               ▼
┌──────────────────────────────────┐
│  DENOISE                         │  noisereduce spectral gating (0 params, DSP)
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│  SPEAKER COUNT ESTIMATION        │  spectral features + greedy agglomerative
│  computation/audio/              │  clustering · 1–3 speakers
│    speaker_counter.py            │
└──────────────┬───────────────────┘
               │
       ┌───────┴───────┐
  1 speaker         ≥2 speakers
  enhance direct    │
                    ▼
        ┌──────────────────────────────────┐
        │  MULTI-SPEAKER SEPARATION        │  Asteroid ConvTasNet (5.067M params)
        │  run_canary._run_separation()    │  process-level cache · warm xRT ~0.11
        │  + Gram-Schmidt cross-talk        │  ghost-stream RMS gate
        │    reduction                     │
        └──────────────┬───────────────────┘
                       ▼
        ┌──────────────────────────────────┐
        │  PER-STREAM ENHANCEMENT          │  HPF 80Hz · denoise · presence boost
        │  run_canary.enhance_stream()     │  soft-knee compressor · RMS normalize
        │  → outputs/<ts>/speaker_N.wav    │
        └──────────────┬───────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────────────┐
    │ ASR      │ │ SPEAKER  │ │ WAKEWORD         │
    │ Whisper  │ │ IDENTITY │ │ C++ weighted-    │
    │ tiny +   │ │ ECAPA +  │ │ Levenshtein      │
    │ quality  │ │ MFCC/    │ │ phonetic matcher │
    │ gates    │ │ pitch    │ │                  │
    └────┬─────┘ └────┬─────┘ └────────┬─────────┘
         └────────────┼────────────────┘
                      ▼
        ┌──────────────────────────────────┐
        │  INTELLIGENCE LAYER (rules)      │  utterance_analyzer · conflict_detector
        │  computation/intelligence/*      │  context_builder · DRS (Mode A/B/C)
        │  + Lisp Matrix phonetic repair   │
        └──────────────┬───────────────────┘
                       ▼
        ┌──────────────────────────────────┐
        │  ARBITRATION ENGINE              │  priority = 0.4·wakeword
        │                                  │           + 0.4·identity_conf
        │  EXECUTE / CLARIFY /             │           + 0.2·known_user
        │  MULTI_EXECUTE / IGNORE          │
        └──────────────┬───────────────────┘
                       ▼
        ┌──────────────────────────────────┐
        │  AGENTIC TOOL LAYER              │  get_weather · get_news · play_media
        │  backend/mcp_server.py           │  real public-API calls (wttr.in,
        │  → gTTS spoken response          │  Google News RSS, iTunes)
        └──────────────────────────────────┘
```

---

## Stage-by-Stage Detail

### Stage 0 — Gating
- **Silero VAD** (`computation/audio/vad_segmenter.py`) drives stop-on-silence recording. 0.463M params, sub-ms per frame.
- **Adaptive VAD** — per-speaker disfluency profiles (`default` / `disfluent` / `stutter`) widen the silence tolerance so a mid-utterance block isn't cut off and split into two fragments.
- **Energy pre-screen** — rejects silent/near-silent streams before any heavy model runs (RMS < −52 dBFS or voiced frame ratio < 15%).

### Acoustic RAG (ASR-bypass accessibility fallback)
`computation/intelligence/acoustic_rag.py` matches incoming audio against a user's enrolled anchor-command MFCC templates with **FastDTW**. On a confident match the intent fires immediately — no separation, no ASR. Designed for speakers whose speech is too atypical for a neural STT model (severe dysarthria, profound stutter). Zero-cost no-op until a user enrolls commands.

### Denoise
`noisereduce` non-stationary spectral gating removes fans, HVAC hum, and room reverb while preserving speech. No model parameters.

### Speaker Count Estimation
`computation/audio/speaker_counter.py` — 500 ms sliding window, 6-dim spectral feature vector per voiced frame, greedy agglomerative clustering across multiple thresholds. Median cluster count = speaker estimate (1–3). No model parameters.

### Multi-Speaker Separation
- Model: **Asteroid ConvTasNet** `JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k`, **5.067M params**.
- Thread-safe process-level cache (`_get_separation_model`) — loads once per process, warmed at backend startup. Warm **xRT ≈ 0.11** (5× headroom under the 0.5 real-time target).
- **3-speaker path** — runs the 2-mix model, then keeps streams whose speech-band RMS (300–3400 Hz) ≥ 25% of the loudest. Down-routes to single-speaker if only one real stream survives.
- **Cross-talk reduction** — Gram-Schmidt orthogonalization removes shared energy between streams; faint "ghost" artifact streams are dropped via an energy-ratio gate.

### ASR
**OpenAI Whisper tiny** (`computation/audio/transcribe.py`) with two-sided gating:
- Pre-screen: RMS and voiced-ratio check before Whisper runs.
- Post-screen: avg log-prob threshold (−1.2), repetition check, compression-ratio check — suppresses hallucination loops.

### Speaker Identity
5-group feature fusion in `computation/voice/` — **ECAPA-TDNN** 192-d embedding (95% weight) + pitch + energy + speaking-rate + MFCC. Cosine/Gaussian similarity against enrolled profiles in `database/Voices/`. Only voiced frames (RMS > 2.5× noise floor) are fed to the matcher.

### Wakeword
C++ **weighted-Levenshtein phonetic matcher** (`computation/wakeword/`) with a fuzzy mis-transcription table (>40 common Whisper errors). Zero neural parameters.

### Intelligence Layer
`utterance_analyzer.py` — classifies into COMMAND / QUESTION / CONVERSATION / UNKNOWN across 15 smart-home domains.
`conflict_detector.py` — antonym-action and override-command conflict detection.
`context_builder.py` — aggregates everything into `context.json`.
**Dynamic Resource Scaler (DRS)** — classifies the acoustic scene into Mode A/B/C from overlap probability, noise level, and speaker count.
**Lisp Matrix** (`phonetic_matcher.py`) — when the rule-based classifier fails because ASR garbled a keyword, the transcript is re-matched in phonetic space (Double Metaphone + Needleman-Wunsch) using the speaker's per-user confusion matrix.

### Arbitration + Tool Layer
Arbitration scores each speaker `priority = 0.4·wakeword + 0.4·identity_conf + 0.2·known_user` and routes to EXECUTE / CLARIFY / MULTI_EXECUTE / IGNORE.

`backend/mcp_server.py` exposes `get_weather`, `get_news`, `play_media`, `stop_media` — chained from the classified intent + resolved speaker + entities. Calls real public APIs (wttr.in, Google News RSS, iTunes). Responds via gTTS.

---

## Phenotypic-Inclusive Accessibility Stack

Three deterministic, zero-extra-parameter layers adapt the pipeline to each speaker's physiology:

```
audio → [Adaptive VAD]      per-speaker silence tolerance (stutters not truncated)
      → [Acoustic RAG/DTW]  confident match → intent (ASR bypassed entirely)
               │ no match
               ▼
      separate → ASR → [Lisp Matrix phonetic repair] → intent
```

| Layer | Module | Failure mode fixed |
|---|---|---|
| Adaptive VAD | `audio/vad_segmenter.py` | Mid-word blocks truncated by rigid silence threshold |
| Acoustic RAG | `intelligence/acoustic_rag.py` | Speech too atypical for ASR (profound dysarthria) |
| Lisp Matrix | `intelligence/phonetic_matcher.py` | ASR garbles keyword phonetically (lisp, accent) |

All three key off the same per-speaker profile loaded after ECAPA identification, so a household with a neurotypical, a lisping, and a stuttering speaker share one device and the pipeline self-reconfigures per utterance.

---

## Service Topology

```
frontend/web (Next.js 16)   ─┐
frontend/mobile (React Native)─┼── HTTP/JSON ──► FastAPI (backend/api.py :8000)
                               │                  ├─ POST /api/command
                               │                  ├─ POST /api/enroll
                               │                  ├─ POST /api/change-wakeword
                               │                  ├─ GET  /api/users
                               │                  ├─ GET  /api/status
                               │                  └─ POST /api/run  (CLI trigger)
                               │               run_canary.py  (CLI orchestrator)
                               │               computation/*  (audio/voice/intel)
                               │               backend/mcp_server.py (tool layer)
                               │               database/canary.db (SQLite)
```

The FastAPI layer is a thin wrapper over the same functions used by the CLI, so both paths exercise an identical pipeline.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 · TypeScript |
| API server | FastAPI + Uvicorn |
| Web UI | Next.js 16 + React 19 + Tailwind CSS |
| Mobile | React Native |
| ML runtime | PyTorch · torchaudio · ONNX Runtime |
| Audio DSP | librosa · scipy · soundfile · sounddevice · noisereduce |
| Separation | [Asteroid ConvTasNet](https://github.com/asteroid-team/asteroid) |
| ASR | [OpenAI Whisper tiny](https://github.com/openai/whisper) |
| Speaker ID | [SpeechBrain ECAPA-TDNN](https://github.com/speechbrain/speechbrain) |
| VAD | [Silero VAD](https://github.com/snakers4/silero-vad) |
| Wakeword | Custom C++ weighted-Levenshtein |
| Phonetic repair | [metaphone](https://github.com/oubiwann/metaphone) + Needleman-Wunsch |
| Acoustic RAG | MFCC + [fastdtw](https://github.com/slaypni/fastdtw) |
| TTS | [gTTS](https://github.com/pndurette/gTTS) + pygame |
| Persistence | SQLite · per-speaker profile files |

---

## Open-Source Libraries

| Library | Purpose | Link |
|---|---|---|
| Asteroid | ConvTasNet separation model | https://github.com/asteroid-team/asteroid |
| SpeechBrain | ECAPA-TDNN speaker embeddings | https://github.com/speechbrain/speechbrain |
| OpenAI Whisper | ASR | https://github.com/openai/whisper |
| Silero VAD | Voice activity detection | https://github.com/snakers4/silero-vad |
| noisereduce | Spectral-gating denoiser | https://github.com/timsainb/noisereduce |
| PyTorch | Deep-learning runtime | https://github.com/pytorch/pytorch |
| torchaudio | Audio I/O & resampling | https://github.com/pytorch/audio |
| librosa | Feature extraction | https://github.com/librosa/librosa |
| SciPy / NumPy | DSP & numerics | https://scipy.org |
| soundfile / sounddevice | WAV I/O & mic capture | https://github.com/bastibe/python-soundfile |
| FastAPI | REST API framework | https://github.com/fastapi/fastapi |
| gTTS | Text-to-speech | https://github.com/pndurette/gTTS |
| pygame | Audio playback | https://github.com/pygame/pygame |
| feedparser | Google News RSS | https://github.com/kurtmckee/feedparser |
| metaphone | Double Metaphone encoding | https://github.com/oubiwann/metaphone |
| fastdtw | Approximate DTW | https://github.com/slaypni/fastdtw |
| Next.js | Web UI | https://github.com/vercel/next.js |
| React Native | Mobile UI | https://github.com/facebook/react-native |

---

## Open-Weight Models Used

| Model | Role | Params | License |
|---|---|---|---|
| `JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k` | Multi-speaker separation | 5.067M | Apache-2.0 |
| `openai/whisper-tiny` | ASR | 37.2M | MIT |
| `speechbrain/spkrec-ecapa-voxceleb` | Speaker embedding | 22.2M | Apache-2.0 |
| Silero VAD | Voice activity detection | 0.463M | MIT |

### Evaluated but not shipped
| Model | Params | Reason rejected |
|---|---|---|
| SepFormer libri2mix | 25.679M | Over 5M budget + warm xRT 0.617 (fails real-time) |
| DPRNNTasNet WHAM | 3.651M | Warm xRT 0.85 — LSTM is sequential on CPU |
| TIGER-speech | 0.822M | Warm xRT 8.03 — attention is compute-heavy on CPU |

---

## Measured KPIs

| KPI | Result | Target |
|---|---|---|
| Separation params | 5.067M | < 5M (separation system) |
| xRT (warm) | ~0.11 | < 0.5 |
| SI-SNR clean (MiniLibriMix) | 14.97 dB | — |
| SI-SNRi noisy (MiniLibriMix) | 12.75 dB | — |
| WER (2-speaker separated) | 27.2% | — |

Separation reduces WER 70.8% → 27.2% (2.6× improvement) on 2-speaker audio.

---

## Routing Decision Table

| Wake-word commands | Conflict | Route | Behavior |
|---|---|---|---|
| 0 | — | IGNORE | Ambient conversation, no action |
| 1 | No | EXECUTE | Single command executed |
| ≥ 2 | Yes | CLARIFY | Opposing intents, asks for clarification |
| ≥ 2 | No | MULTI_EXECUTE | Compatible commands executed in sequence |

---

## Installation

### Prerequisites
- Python 3.10+
- macOS: `brew install portaudio` / Linux: `apt-get install portaudio19-dev`
- Node.js 18+ and `pnpm` for the web frontend
- Internet access on first run (models auto-download from Hugging Face)

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### CLI pipeline

```bash
python src/run_canary.py
```

### REST API + Web UI

```bash
# Terminal 1 — API server (warms separation model on startup)
python -m backend.server

# Terminal 2 — Web frontend
cd src/frontend/web
pnpm install
pnpm dev          # http://localhost:3000
```

### Docker

```bash
docker compose up --build
```

### Key API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/command` | POST (audio) | Full pipeline: separate → ID → transcribe → route → respond |
| `/api/enroll` | POST (name + audio) | Enroll a voice profile |
| `/api/change-wakeword` | POST (3 recordings) | Update the active wakeword |
| `/api/users` | GET | List enrolled users |
| `/api/status` | GET | Wakeword, enrolled count, DB path |

---

## Output Files

Each run produces a timestamped folder:

```
outputs/20260622_101530/
├── raw_input.wav      # Original recording
├── speaker_1.wav      # Enhanced stream — dominant speaker
├── speaker_1.txt      # Transcript + quality gate metadata
├── speaker_2.wav      # Enhanced stream — second speaker (if detected)
├── speaker_2.txt      # Transcript + quality gate metadata
├── context.json       # Full pipeline state + routing decision
└── response.json      # Execution result
```
