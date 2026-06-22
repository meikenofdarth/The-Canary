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
  <img src="https://github.com/user-attachments/assets/df805357-094f-4b49-950a-f67fbd122c29" alt="System architecture" width="860" />
</p>

---

## Interface

<!-- Row 1: Web (70%) + Mobile (30%) -->
<table width="100%" cellspacing="0" cellpadding="0" border="0">
  <tr>
    <td width="68%" valign="top">
      <img src="https://your-image-host.com/canary-web.png"
           alt="Web dashboard"
           width="100%" />
    </td>
    <td width="4%"></td>
    <td width="28%" valign="top">
      <img src="https://your-image-host.com/canary-mobile.png"
           alt="Mobile app"
           width="100%" />
    </td>
  </tr>
</table>

<br/>

<!-- Row 2: Interface screenshot (40%) + feature list (60%) -->
<table width="100%" cellspacing="0" cellpadding="0" border="0">
  <tr>
    <td width="38%" valign="top">
      <img src="https://your-image-host.com/canary-interface.png"
           alt="Live interface"
           width="100%" />
    </td>
    <td width="4%"></td>
    <td width="58%" valign="top">
      <h3>What you can do</h3>
      <p>
        <b>Speak naturally.</b> No button press needed. The assistant
        listens, detects your voice, and stops recording automatically
        after you finish talking.
      </p>
      <p>
        <b>Multi-user, one device.</b> Up to three people can speak at
        once. Each voice is separated, identified, and handled
        independently. Conflicting commands trigger a clarification
        prompt; compatible commands run in sequence.
      </p>
      <p>
        <b>Personalized responses.</b> Enroll once via the web or mobile
        app — three short recordings. From that point the assistant knows
        your city, your news region, and your music preference and
        tailors every answer to you.
      </p>
      <p>
        <b>Change the wakeword live.</b> Record yourself saying any word
        three times in the UI. No retraining — the system builds a fuzzy
        phonetic lookup table and activates it immediately.
      </p>
    </td>
  </tr>
</table>

---

## Demo

[![Watch the demo](https://img.youtube.com/vi/VIDEO_ID/maxresdefault.jpg)](https://youtu.be/VIDEO_ID)

| Case | Timestamp |
|---|---|
| Registering Users | [0:00](https://youtu.be/VIDEO_ID?t=0) |
| 2 users Sequential Commands | [0:34](https://youtu.be/VIDEO_ID?t=34) |
| 2 users Conflicting Commands, Unequal Priority | [1:05](https://youtu.be/VIDEO_ID?t=65) |
| 2 users Conflicting Commands, Equal Priority | [1:33](https://youtu.be/VIDEO_ID?t=93) |
| 3 users | [2:05](https://youtu.be/VIDEO_ID?t=125) |
| Single user with lot of noise | [2:32](https://youtu.be/VIDEO_ID?t=152) |
| Single user silent environment | [2:56](https://youtu.be/VIDEO_ID?t=176) |

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
