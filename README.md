# The Canary

Real-time multi-speaker voice assistant for noisy, multi-user environments.
Separates overlapping voices, identifies who spoke, resolves command conflicts,
and delivers a personalized spoken response — entirely on-device, no cloud.

- **Problem Statement Number** - 11
- **Problem Statement Title** - *Multi-Speaker Audio Intelligence Pipeline for Smart Assistants*
- **Team name** - *Gada Electronics*
- **Team members (Names)** - *Sanchit Kumar Dogra*, *Hemang Seth*
- **Institute/College Name** - 
- **Final Presentation Google Drive Link** - 
- **Full Submission Demo Video Link** - 
- **Setup & Result Reproducibility Video Link** - 

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

## Project Artefacts

- **Technical Documentation** — All technical details (architecture, tech stack, OSS libraries, implementation, installation, user guide) are in the [`docs/`](docs/) folder:
  - [`docs/architecture.md`](docs/architecture.md) — Full pipeline diagram, tech stack, and OSS library list with links
  - [`docs/ax.md`](docs/ax.md) — Agentic AI setup, open-weight model selection, what worked and what didn't
  - [`docs/plan.md`](docs/plan.md) — Stage-by-stage design decisions and implementation log
- **Source Code** — All project source code is in the [`src/`](src/) folder, including backend, computation modules, frontend, and benchmark evaluation scripts.
- **Models Used:**
  - [Asteroid ConvTasNet (JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k)](https://huggingface.co/JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k) — Speaker separation
  - [Asteroid ConvTasNet (JorisCos/ConvTasNet_Libri2Mix_sepclean_16k)](https://huggingface.co/JorisCos/ConvTasNet_Libri2Mix_sepclean_16k) — Speaker separation (clean variant)
  - [OpenAI Whisper Tiny](https://huggingface.co/openai/whisper-tiny) — Speech-to-text
  - [SpeechBrain ECAPA-TDNN (spkrec-ecapa-voxceleb)](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) — Speaker identification
  - [Silero VAD](https://github.com/snakers4/silero-vad) — Voice activity detection
- **Models Published** — No new models were published. We performed runtime optimizations and integration on existing open-weight models.
- **Datasets Used:**
  - [LibriMix / MiniLibriMix](https://github.com/JorisCos/LibriMix) — Separation benchmarking and WER evaluation
  - [VoxCeleb](https://www.robots.ox.ac.uk/~vgg/data/voxceleb/) — Implicit via ECAPA-TDNN pretrained weights
- **Datasets Published** — No new datasets were published. All evaluation uses existing open datasets.

---

## Attribution

This project was built from scratch and is not a fork of any existing open-source project. The following open-source libraries and pretrained models were used as building blocks:

- [Asteroid](https://github.com/asteroid-team/asteroid) — Audio source separation toolkit (ConvTasNet pretrained weights)
- [OpenAI Whisper](https://github.com/openai/whisper) — Automatic speech recognition
- [SpeechBrain](https://github.com/speechbrain/speechbrain) — Speaker verification (ECAPA-TDNN pretrained weights)
- [Silero VAD](https://github.com/snakers4/silero-vad) — Voice activity detection
- [FastAPI](https://github.com/tiangolo/fastapi) — Backend API framework
- [Next.js](https://github.com/vercel/next.js) — Web frontend framework
- [React Native / Expo](https://github.com/expo/expo) — Mobile app framework

All new features (multi-speaker arbitration, accessibility layers, phonetic wakeword matching, priority-weighted conflict resolution, Acoustic RAG, Lisp Matrix) were developed by the team.

---

## License

MIT
