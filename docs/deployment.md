# Deployment (Docker)

The Canary ships as two containers: the **API** (FastAPI pipeline) and the
**web UI** (Next.js). A `docker-compose.yml` wires them together.

## Quick start

```bash
docker compose up --build
```

- API  → http://localhost:8000  (also serves `wave.html` at `/`)
- Web  → http://localhost:3000

First build is large and slow: it installs CPU PyTorch, the audio stack, and
**pre-downloads the model weights** (ConvTasNet clean+noisy, ECAPA-TDNN,
Whisper-tiny) into the image so the container runs offline and the first request
is already warm.

## Images

| Image | Build context | Port | Purpose |
|---|---|---|---|
| `canary-api` | `./Dockerfile` | 8000 | separation → ASR → voice ID → intent |
| `canary-web` | `./frontend/web/Dockerfile` | 3000 | dashboard, enroll, manage, wake-word UI |

Build just the API:

```bash
docker build -t canary-api .
docker run -p 8000:8000 -v "$(pwd)/database:/app/database" canary-api
```

## Persistence

Enrolled users live in SQLite (`database/canary.db`) and voice profiles in
`database/Voices/`. The compose file mounts `./database` as a volume so
enrollments survive container restarts. Without the volume, each fresh container
starts with an empty user table.

## Configuration

| Variable | Default | Where |
|---|---|---|
| `CANARY_ASR_MODEL` | `tiny` | api runtime — Whisper model size |
| `NEXT_PUBLIC_CANARY_API` | `http://localhost:8000` | web **build arg** — inlined into the client bundle |

Because `NEXT_PUBLIC_*` is baked at build time, changing the API URL means
rebuilding the web image. The browser runs on the host, so it reaches the API
through the host-mapped port (`localhost:8000`).

## Notes & limitations

- **No authentication.** The API is unauthenticated. Do not expose it directly
  to the public internet — front it with an authenticating reverse proxy.
- **No microphone in containers.** The live-mic CLI (`run_canary.py`) and TTS
  audio playback don't work headless (`SDL_AUDIODRIVER=dummy` keeps pygame from
  erroring). The containerized product is the **HTTP API + web UI**, which take
  uploaded audio via `POST /api/command`.
- **Image size** is large (PyTorch + models, ~2–3 GB). `.dockerignore` excludes
  `.venv`, `node_modules`, `outputs/`, `models/MiniLibriMix/`, and local audio.
- **CPU only.** Torch is installed from the CPU wheel index; no GPU is required
  (separation runs at xRT ~0.11 on CPU).
