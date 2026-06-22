# The Canary — backend API image (FastAPI + separation/ASR/biometrics pipeline).
# Docker Hub: https://hub.docker.com/r/knightstriker/the-canary
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    TRANSFORMERS_OFFLINE=0 \
    SDL_AUDIODRIVER=dummy \
    CANARY_ASR_MODEL=tiny

# System libs: ffmpeg (audio decode), libsndfile1 (soundfile),
# libportaudio2 (sounddevice import in run_canary), git (some pip installs).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        libportaudio2 \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch first so the rest of requirements reuses it (no CUDA bloat).
RUN pip install --no-cache-dir torch torchaudio \
        --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source (see .dockerignore for what's excluded).
COPY . .

# Bake ALL model weights into the image — Silero VAD, ConvTasNet, ECAPA-TDNN, Whisper tiny.
# After this step the image runs fully offline; first request is warm.
RUN python src/scripts/prefetch_models.py

EXPOSE 8000

CMD ["uvicorn", "backend.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
