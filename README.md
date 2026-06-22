# The Canary

Real-time multi-speaker voice assistant for noisy, multi-user environments.
Separates overlapping voices, identifies who spoke, resolves command conflicts,
and delivers a personalized spoken response — entirely on-device, no cloud.

* **Problem Statement Number** — 11

* **Problem Statement Title** — *Real-Time Multi-User Smart Assistant for Dynamic and Noisy Smart Environments*

* **Team Name** — *GadaElectronics*

* **Team Members** — *Sanchit Kumar Dogra*, *Hemang Seth*

* **Institute** — *IIIT Bangalore*

* **Final Presentation** — [View Presentation Deck](https://drive.google.com/file/d/1sIRl4GkE25K4YfsFRbzA4nKEIGjBaOX1/view?usp=sharing)

* **Full Submission Demo Video** (Please refer below for exact Timestamps)

  * **Scenarios Addressed**

    * [Watch on YouTube](https://www.youtube.com/watch?v=05QvroEQ3sA)
    * [Watch on Google Drive](https://drive.google.com/file/d/1y8rIrVrkTVBlN-P_CSordjezVDIYnnL3/view?usp=sharing)

  * **Canary Architecture**

    * [Watch on YouTube](https://youtu.be/dQkT4lMXtuU)
    * [Watch on Google Drive](https://drive.google.com/file/d/1PjfOLPFI2sn0qQb11eXi8ZB_W9kbdSBN/view?usp=sharing)

* **Setup & Result Reproducibility Video** — *(add YouTube link here — public or unlisted)*

---

## System Architecture

<!--
  Export your Excalidraw diagram as PNG.
  Drag it into a GitHub Issue comment box to get a CDN-hosted URL, then paste it in src below.
  Close the issue without submitting — the image stays hosted permanently.
-->
<p align="center">
  <img src="https://github.com/user-attachments/assets/df805357-094f-4b49-950a-f67fbd122c29" alt="System architecture" width="860" />

</p>

---

## Interface

<!-- Row 1: Web (70%) + Mobile (30%) -->
<table width="100%">
<tr>
<td align="center" width="68%">
<b>Web Dashboard</b>
</td>

<td width="4%"></td>

<td align="center" width="28%">
<b>Mobile App</b>
</td>
</tr>

<tr>
<td>
<img src="https://github.com/user-attachments/assets/1699479e-0cdc-4ced-b72f-2d9ab644196e" width="100%">
</td>

<td></td>

<td>
<img src="https://github.com/user-attachments/assets/9c1e463a-1ba9-4229-83e6-43526ef78a60" width="100%">
</td>
</tr>
</table>

<br/>
<!-- Full-width interface image -->
<p align="center">
  <img src="https://github.com/user-attachments/assets/57d0d9b6-8142-474c-a594-6f28c240226e"
       alt="Live Interface"
       width="100%" />
</p>

<h3>What you can do</h3>

<ul>
  <li>
    <b>Speak naturally.</b> No button press needed. The assistant listens,
    detects your voice, and automatically stops recording when you finish speaking.
  </li>

  <li>
    <b>Multi-user, one device.</b> Up to three people can speak simultaneously.
    Voices are separated, identified, and processed independently.
    Conflicting commands trigger clarification; compatible commands execute sequentially.
  </li>

  <li>
    <b>Personalized responses.</b> After a quick voice enrollment,
    the assistant tailors news, music, and responses to each recognized user.
  </li>

  <li>
    <b>Custom wake words.</b> Record any phrase three times through the UI.
    The assistant activates it immediately without retraining.
  </li>
</ul>


## Use Cases Demonstration



[![Watch the demo](https://img.youtube.com/vi/05QvroEQ3sA/maxresdefault.jpg)](https://youtu.be/05QvroEQ3sA)



<table width="100%">

<tr>

<th>Case</th>

<th align="center">Timestamp</th>

</tr>



<tr>

<td>Registering Users</td>

<td align="center"><a href="https://youtu.be/05QvroEQ3sA?t=0">0:00</a></td>

</tr>



<tr>

<td>2 Users Sequential Commands</td>

<td align="center"><a href="https://youtu.be/05QvroEQ3sA?t=34">0:34</a></td>

</tr>



<tr>

<td>2 Users Conflicting Commands, Unequal Priority</td>

<td align="center"><a href="https://youtu.be/05QvroEQ3sA?t=65">1:05</a></td>

</tr>



<tr>

<td>2 Users Conflicting Commands, Equal Priority</td>

<td align="center"><a href="https://youtu.be/05QvroEQ3sA?t=93">1:33</a></td>

</tr>



<tr>

<td>3 Users</td>

<td align="center"><a href="https://youtu.be/05QvroEQ3sA?t=125">2:05</a></td>

</tr>



<tr>

<td>Single User with Background Noise</td>

<td align="center"><a href="https://youtu.be/05QvroEQ3sA?t=152">2:32</a></td>

</tr>



<tr>

<td>Single User, Silent Environment</td>

<td align="center"><a href="https://youtu.be/05QvroEQ3sA?t=176">2:56</a></td>

</tr>

</table>



---



## Dive Through Our System Architecture for Better Understanding



[![Watch the demo](https://github.com/user-attachments/assets/9de9b0ee-f1dd-4e5d-b26b-6e34fc733c48)](https://youtu.be/dQkT4lMXtuU)



<table width="100%">

<tr>

<th>Section</th>

<th align="center">Timestamp</th>

</tr>



<tr>

<td>Problems Faced</td>

<td align="center"><a href="https://youtu.be/dQkT4lMXtuU?t=15">0:15</a></td>

</tr>



<tr>

<td>Overview</td>

<td align="center"><a href="https://youtu.be/dQkT4lMXtuU?t=25">0:25</a></td>

</tr>



<tr>

<td>System Design & Architecture</td>

<td align="center"><a href="https://youtu.be/dQkT4lMXtuU?t=76">1:16</a></td>

</tr>



<tr>

<td>Proof of Working</td>

<td align="center"><a href="https://youtu.be/dQkT4lMXtuU?t=119">1:59</a></td>

</tr>



<tr>

<td>Why Canary?</td>

<td align="center"><a href="https://youtu.be/dQkT4lMXtuU?t=162">2:42</a></td>

</tr>



<tr>

<td>KPIs, Optimizations & Results</td>

<td align="center"><a href="https://youtu.be/dQkT4lMXtuU?t=246">4:06</a></td>

</tr>



<tr>

<td>Research Papers Read & Access Canary</td>

<td align="center"><a href="https://youtu.be/dQkT4lMXtuU?t=397">6:37</a></td>

</tr>



</table>



---
## How It Works

One microphone. Multiple people. The pipeline records until silence, estimates
speaker count, separates voices with a 5M-parameter on-device neural model,
identifies each speaker from enrolled biometric profiles, detects the wakeword,
classifies intent, resolves command conflicts through a priority-weighted
arbitration engine, and speaks a personalized answer — weather, news, or music
— through the system speaker. Every stage runs in real time on a standard CPU.

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
| Warm real-time factor of ConvTasNet xRT | ~0.11  |
| Real-time factor of entire Pipeline xRT | ~0.505 |
| SI-SNR clean (MiniLibriMix, 50 mixtures) | 14.97 dB |
| SI-SNRi noisy (MiniLibriMix, mix_both) | 12.75 dB |
| WER on 2-speaker mixture | 70.8% raw → 21.4% separated (2.6x reduction) |
| WER on 2-speaker mixture (Clean Audio) | As low as 14.1% (Complete Clean Audio) |

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
│   │   ├── intelligence/       Intent engine, Lisp Matrix, Acoustic RAG,
│   │   │                       conflict detection, arbitration, context builder
│   │   └── wakeword/           C++ weighted-Levenshtein phonetic matcher
│   ├── frontend/
│   │   ├── web/                Next.js 16 + React 19 + Tailwind CSS dashboard
│   │   └── mobile/             React Native app
│   └── tests/                  SI-SNR eval, WER eval, xRT report, unit tests
├── database/
│   ├── canary.db               SQLite — users, preferences, priorities
│   └── Voices/<name>/          Per-speaker recordings and biometric feature files
├── docs/
│   ├── architecture.md         Full pipeline diagram, tech stack, OSS library list
│   ├── ax.md                   Agentic AI setup, model selection log, what worked/didn't
│   └── plan.md                 Stage-by-stage design decisions
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Installation & Setup

> All commands run from the **project root** (`The-Canary/`).

### Step 1 — System dependencies

```bash
# macOS
brew install portaudio ffmpeg

# Linux (Debian/Ubuntu)
sudo apt-get install portaudio19-dev ffmpeg libsndfile1
```

### Step 2 — Clone and install

```bash
https://github.com/meikenofdarth/The-Canary.git
cd The-Canary

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Step 2b — Pre-fetch all model weights (do this once, avoids mid-run downloads)

```bash
python3 src/scripts/prefetch_models.py
```

This downloads ConvTasNet, Whisper tiny, ECAPA-TDNN, and Silero VAD to the local cache.
Every run after this is instant — no downloads, no Hugging Face warnings.

### Step 3 — Start the backend API

```bash
source .venv/bin/activate
python3 -m uvicorn backend.api:app --app-dir src --host 0.0.0.0 --port 8000 --reload
# http://localhost:8000 — wait for [SEP] loaded & cached before sending requests
```

### Step 4 — Start the web frontend (Node.js 18+ required)

```bash
cd src/frontend/web
npm install
npm run dev                        # http://localhost:3000
```

> Use `npm run dev`. Running `npm start` without a prior `npm run build` will error.

### Step 4b — Mobile app (Expo Go)

> Phone and laptop must be on the **same WiFi or hotspot**.

```bash
# 1. Get your machine's local IP
ipconfig getifaddr en0             # macOS

# 2. Set it in src/frontend/mobile/.env
echo "EXPO_PUBLIC_CANARY_API=http://<YOUR_LOCAL_IP>:8000" > src/frontend/mobile/.env

# 3. Start with --lan (NOT --tunnel — tunnel requires ngrok and fails on slow networks)
cd src/frontend/mobile
npm install
npx expo start --lan
```

Scan the QR code with **Expo Go** on your phone.

### Step 5 — Enroll speakers

```bash
source .venv/bin/activate
python3 src/add_voicer.py
# Interactive studio: 3 scripted recordings, live quality check, preference setup
```

### Step 6 — Run CLI pipeline (microphone, no server needed)

```bash
source .venv/bin/activate
python3 src/run_canary.py
```

---

## Docker

All model weights are baked into the image at build time — first request is warm, no downloads.

```bash
# Pull the pre-built image from Docker Hub (fastest — no build needed)
docker pull knightstriker/the-canary:latest
docker compose up

# Or build locally
docker compose up --build

# API → http://localhost:8000   Web → http://localhost:3000
```

Docker Hub: [hub.docker.com/r/knightstriker/the-canary](https://hub.docker.com/r/knightstriker/the-canary)

> Audio playback inside the container is headless (`SDL_AUDIODRIVER=dummy`).
> TTS text is returned in the API response JSON.

---

## Testing & KPI Verification

All commands from the **project root**. These verify the results claimed in this README.

```bash
source .venv/bin/activate

# 1. Parameter budget audit — prints per-stage param count and PASS/FAIL
python3 src/param_audit.py

# 2. Unit + integration tests
pytest src/tests/ -v
# Expected: 18 passed, 1 xfailed
# The xfail is test_budget.py — ConvTasNet is 5.067M (1.3% over 5M), documented intentionally

# 3. Real-time factor + speaker ID smoke test
python3 src/tests/kpi_report.py
# Note: SI-SNR here uses a synthetic fixture (~11-12 dB). For the official KPI run eval_separation below.

# 4. SI-SNR on MiniLibriMix — this is the official 14.97 dB benchmark (download ~640 MB once)
mkdir -p src/models
curl -L -o src/models/MiniLibriMix.zip \
  "https://zenodo.org/records/3871592/files/MiniLibriMix.zip"
cd src/models && unzip -q MiniLibriMix.zip && cd ../..
python3 src/tests/eval_separation.py --n 50 --mix mix_clean
python3 src/tests/eval_separation.py --n 50 --mix mix_both
# Expected: SI-SNR clean ~14.97 dB, SI-SNRi noisy ~12.75 dB

# 5. Word Error Rate on separated vs raw mixture
python3 src/tests/eval_wer.py --mode librimix --n 10
# Expected: ~27.2% separated vs ~70.8% raw (2.6x reduction)
```

**Note on SI-SNR:** `kpi_report.py` uses a small synthetic fixture (two recordings summed) and reports ~11-12 dB — this is a **smoke test only**. The official KPI of **14.97 dB SI-SNR clean** is measured by `eval_separation.py` on the real MiniLibriMix benchmark with ground-truth isolated sources. Both numbers are honest — they measure different things.

---

## Project Artefacts

**Technical Documentation** — [`docs/`](docs/) folder:
- [`docs/architecture.md`](docs/architecture.md) — Full pipeline diagram, tech stack, OSS libraries with links, implementation details, installation guide, user guide
- [`docs/ax.md`](docs/ax.md) — Agentic AI setup, open-weight model selection, reasoning pipelines, tool chaining, what worked and what did not
- [`docs/plan.md`](docs/plan.md) — Stage-by-stage design decisions and methodology

**Source Code** — [`src/`](src/) — All backend, computation, frontend, and evaluation scripts. Runs end-to-end from CLI or Docker.

**Models Used**
- [JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k](https://huggingface.co/JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k) — Multi-speaker separation (5.067M params, Apache-2.0)
- [JorisCos/ConvTasNet_Libri2Mix_sepclean_16k](https://huggingface.co/JorisCos/ConvTasNet_Libri2Mix_sepclean_16k) — Separation clean variant (Apache-2.0)
- [openai/whisper-tiny](https://huggingface.co/openai/whisper-tiny) — Automatic speech recognition (MIT)
- [speechbrain/spkrec-ecapa-voxceleb](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) — Speaker identity embeddings (Apache-2.0)
- [Silero VAD](https://github.com/snakers4/silero-vad) — Voice activity detection (MIT)

**Models Published** — No new models published. Runtime optimizations and integration only.

**Datasets Used**
- [MiniLibriMix](https://zenodo.org/records/3871592) — Separation benchmarking and WER evaluation (CC BY 4.0)
- [VoxCeleb](https://www.robots.ox.ac.uk/~vgg/data/voxceleb/) — Implicit via ECAPA-TDNN pretrained weights

**Datasets Published** — No new datasets published. All evaluation uses existing open datasets.

---

## Troubleshooting

**First request is slow** — The backend warms the separation model at startup. Wait for `[SEP] ... loaded & cached` in the server log. Subsequent calls run at ~0.11 xRT.

**Whisper import error** — Two packages share the name `whisper`.

```bash
pip uninstall -y whisper && pip install openai-whisper
```

**No audio detected** — Ensure `portaudio` is installed and the microphone is the default input device in system audio settings.

**Speaker always returns UNKNOWN** — Enroll at least one user first.

```bash
python3 src/add_voicer.py
```

**Docker has no audio output** — The container runs `pygame` in headless mode (`SDL_AUDIODRIVER=dummy`). TTS text is returned in the API response. Live playback requires the host audio device.

---

## Attribution

Built from scratch by the GadaElectronics team. Not a fork of any existing project.
The following open-source libraries and pretrained model weights were used as components:

- [Asteroid](https://github.com/asteroid-team/asteroid) — ConvTasNet pretrained weights
- [OpenAI Whisper](https://github.com/openai/whisper) — ASR
- [SpeechBrain](https://github.com/speechbrain/speechbrain) — ECAPA-TDNN pretrained weights
- [Silero VAD](https://github.com/snakers4/silero-vad) — VAD
- [FastAPI](https://github.com/tiangolo/fastapi) — Backend API
- [Next.js](https://github.com/vercel/next.js) — Web frontend
- [React Native / Expo](https://github.com/expo/expo) — Mobile app

All new features — multi-speaker conflict arbitration, Acoustic RAG, Lisp Matrix phonetic intent repair, Adaptive VAD, priority-weighted arbitration engine, wakeword live reconfiguration, and the full REST API + web/mobile interface — were developed by the team.

---

## Acknowledgements

We would like to express our sincere gratitude to **Samsung Research** for organizing this challenge and providing us with the opportunity to work on a real-world problem in intelligent voice systems.

We also thank the **faculty members of IIIT Bangalore** for their continuous guidance, mentorship, and support throughout the development of this project.


## License

MIT
