# The Canary

Real-time multi-speaker voice assistant for noisy, multi-user environments.
Separates overlapping voices, identifies who spoke, resolves command conflicts,
and delivers a personalized spoken response — entirely on-device, no cloud.

---

## System Architecture

<!--
  Export your Excalidraw diagram as PNG, drag it into a GitHub Issue comment
  box to get a hosted URL, paste it below. The image stays on GitHub's CDN
  but never lands in the repo.
-->
<p align="center">
  <img src="https://your-image-host.com/canary-architecture.png" alt="System architecture" width="860" />
</p>

---

## Interface

<p align="center">
  <img src="https://your-image-host.com/canary-web.png" alt="Web dashboard" width="280" />
  &nbsp;&nbsp;
  <img src="https://your-image-host.com/canary-mobile.png" alt="Mobile app" width="140" />
  &nbsp;&nbsp;
  <img src="https://your-image-host.com/canary-interface.png" alt="Interface overview" width="280" />
</p>

---

## Demo

[![Watch the demo](https://img.youtube.com/vi/VIDEO_ID/maxresdefault.jpg)](https://drive.google.com/file/d/1y8rIrVrkTVBlN-P_CSordjezVDIYnnL3/view)

| Case | Timestamp |
|---|---|
| Single speaker, clean room | 0:00 |
| Single speaker with background noise | 1:30 |
| Two users, sequential compatible commands | 3:00 |
| Two users, conflicting commands, equal priority | 4:45 |
| Two users, conflicting commands, different priority | 6:15 |
| Three simultaneous users | 8:00 |

[Presentation slides](https://docs.google.com/presentation/d/1aMzsGiX8F2eQ8FbLGe-t9eNzmhFhq9vJsc6Ogl-ugK8/edit?usp=sharing)

---

## How It Works

One microphone. Multiple people. The pipeline records until silence, estimates
speaker count, separates voices with a 5M-parameter on-device neural model,
identifies each speaker from enrolled biometric profiles, detects the wakeword,
classifies intent, resolves command conflicts through a priority-weighted
arbitration engine, and speaks a personalized answer — weather, news, or music
— through the system speaker. Every stage is deterministic and real-time on CPU.

Three accessibility layers handle atypical speech at zero extra parameter cost:
**Acoustic RAG** (DTW-based ASR bypass for severe dysarthria), the **Lisp Matrix**
(phonetic intent repair via Double Metaphone + Needleman-Wunsch per-speaker
confusion matrices), and **Adaptive VAD** (per-speaker silence tolerance so
stutter blocks are not truncated mid-sentence).

---

## Measured Results

| Metric | Result |
|---|---|
| Separation parameters | 5.067M |
| Warm real-time factor | ~0.11 (5x headroom) |
| SI-SNR clean (MiniLibriMix) | 14.97 dB |
| SI-SNRi noisy (MiniLibriMix) | 12.75 dB |
| WER on 2-speaker mixture | 70.8% raw → 27.2% separated (2.6x) |

---

## Project Structure

```
The-Canary/
├── src/
│   ├── run_canary.py           CLI pipeline entry point
│   ├── add_voicer.py           Interactive speaker enrollment studio
│   ├── param_audit.py          Per-stage parameter budget audit
│   ├── backend/                FastAPI server, tool layer (weather/news/music), TTS
│   ├── computation/
│   │   ├── audio/              VAD, denoiser, ConvTasNet separator, Whisper ASR
│   │   ├── voice/              ECAPA-TDNN enrollment, feature extraction, matching
│   │   ├── intelligence/       Intent engine, Lisp Matrix, Acoustic RAG, conflict
│   │   │                       detection, arbitration, context builder
│   │   └── wakeword/           C++ weighted-Levenshtein phonetic matcher
│   ├── frontend/
│   │   ├── web/                Next.js 16 + React 19 + Tailwind CSS dashboard
│   │   └── mobile/             React Native app
│   └── tests/                  SI-SNR eval, WER eval, xRT report, unit tests
├── database/
│   ├── canary.db               SQLite — users, preferences, priorities
│   └── Voices/<name>/          Per-speaker recordings and biometric feature files
├── docs/
│   ├── architecture.md         Full pipeline diagram and tech stack
│   ├── ax.md                   Agentic AI setup and open-weight model selection log
│   └── plan.md                 Stage-by-stage design decisions
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Installation

**Prerequisites**

```bash
# macOS
brew install portaudio ffmpeg

# Linux
sudo apt-get install portaudio19-dev ffmpeg libsndfile1
```

**Python environment**

```bash
git clone https://github.com/your-org/The-Canary.git
cd The-Canary

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Models download automatically from Hugging Face on first run and are cached locally.

**Web frontend** (Node.js 18+ required)

```bash
cd src/frontend/web
pnpm install
```

---

## Running

**CLI — microphone**

```bash
source .venv/bin/activate
python src/run_canary.py
```

**API + Web dashboard**

```bash
# Terminal 1
source .venv/bin/activate
python -m backend.server        # http://localhost:8000

# Terminal 2
cd src/frontend/web
pnpm dev                        # http://localhost:3000
```

**Docker**

```bash
# Build and run locally
docker compose up --build

# Or pull from Docker Hub
docker pull your-dockerhub-username/canary-api:latest
docker pull your-dockerhub-username/canary-web:latest
docker compose up
```

> Replace `your-dockerhub-username` with the actual Hub username once pushed.
> The Docker image pre-fetches all model weights at build time — first request is warm.

**Enroll a speaker**

```bash
python src/add_voicer.py
# Guides through 3 scripted recordings, quality checks, and preference setup
```

---

## Troubleshooting

**First request is slow** — The backend warms the separation model at startup.
Wait for `[SEP] ... loaded & cached` in the server log. Subsequent calls run at ~0.11 xRT.

**Whisper import error** — Two packages share the name `whisper`.

```bash
pip uninstall -y whisper && pip install openai-whisper
```

**No audio detected** — Ensure `portaudio` is installed and the microphone is set
as the default input device in system audio settings.

**Speaker always returns UNKNOWN** — Enroll at least one user first.

```bash
python src/add_voicer.py
```

**Docker has no audio output** — The container runs `pygame` in headless mode
(`SDL_AUDIODRIVER=dummy`). TTS text is returned in the API response.
Live playback requires the host audio device.

---

## License

MIT
