# The Canary — Installation Guide

## Prerequisites

- macOS 14+ (Apple Silicon recommended) or Ubuntu 22.04+
- Python 3.10+
- Homebrew (macOS)
- Git
- ~4GB disk space (for models)

## Step 1: Clone and Set Up Environment

```bash
git clone git@github.com:meikenofdarth/The-Canary.git
cd The-Canary

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Install Redis

```bash
# macOS
brew install redis
brew services start redis

# Verify
redis-cli ping  # Should return: PONG
```

## Step 3: Install Ollama + SLM

```bash
# macOS
brew install ollama
brew services start ollama

# Pull the quantized model (~1GB)
ollama pull qwen2.5:1.5b

# Verify
ollama list  # Should show qwen2.5:1.5b
```

## Step 4: Download ASR Model

```bash
# Download SenseVoiceSmall for sherpa-onnx
cd models/
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
tar -xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
cd ..
```

## Step 5: Verify Installation

```bash
# Run core module tests (FAISS, Redis, Arbitration)
python3 -m tests.test_core_modules

# Run end-to-end integration tests
python3 -m tests.test_e2e

# Run ASR tests (requires model)
python3 -m tests.test_asr

# Test SLM agent
python3 -m src.agent.slm_agent
```

## Step 6: Run the Demo

```bash
# Interactive demo with Rich UI
python3 -m src.demo.ui

# Full pipeline demo
python3 -m src.demo.full_demo
```

## Troubleshooting

### Redis connection refused
```bash
brew services restart redis
# Or check: brew services list
```

### Ollama timeout on first request
This is normal — the first request loads the model into GPU memory. We handle this with a `warmup()` call.

### SenseVoiceSmall model not found
Ensure the model is extracted to `models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/`. The directory should contain `model.int8.onnx` and `tokens.txt`.

### FAISS import error
```bash
pip install faiss-cpu
```

## Directory Structure After Setup

```
The-Canary/
├── .venv/                          # Python virtual environment
├── models/
│   ├── sherpa-onnx-sense-voice-*/  # ASR model (downloaded)
│   └── speaker_embeddings/         # Speaker enrollment .npy files
├── src/
│   ├── agent/                      # MCP server + SLM agent
│   ├── arbitration/                # Rule-based conflict resolution
│   ├── asr/                        # SenseVoiceSmall engine
│   ├── common/                     # Shared models + config
│   ├── demo/                       # Rich terminal UI
│   └── execution/                  # Queue + Redis + FAISS
├── tests/                          # Test suites
├── docs/                           # Documentation
├── requirements.txt
└── README.md
```
