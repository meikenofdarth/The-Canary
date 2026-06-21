# The Canary — backend API image (FastAPI + separation/ASR/biometrics pipeline).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
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

# Bake model weights into the image (offline + warm first request).
RUN python src/scripts/prefetch_models.py

EXPOSE 8000

# Security note: this API has no authentication. Do not expose it directly to
# the public internet — put it behind an authenticating reverse proxy / gateway.
CMD ["uvicorn", "backend.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
