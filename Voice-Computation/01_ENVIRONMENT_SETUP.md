# 01 — Environment Setup
### The Canary | Mac M3 Apple Silicon | Python 3.12 + ONNX Runtime

---

## 0. Pre-flight Checklist

Before touching any code, verify these facts about your machine:

```bash
# 1. Confirm Apple Silicon
uname -m
# Expected: arm64

# 2. Confirm macOS version (Ventura or later recommended)
sw_vers -productVersion
# Expected: 13.x or 14.x or 15.x

# 3. Confirm Xcode Command Line Tools are installed
xcode-select --version
# If missing: xcode-select --install

# 4. Confirm microphone access is not blocked
# System Settings → Privacy & Security → Microphone → allow Terminal
```

---

## 1. Homebrew Foundation

Homebrew is the package manager for everything below. If you do not have it:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After install, add Homebrew to your PATH (M3 Macs use `/opt/homebrew`):

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

Install system-level audio dependencies:

```bash
# PortAudio — required by sounddevice
brew install portaudio

# FFmpeg — required as audio backend for torchaudio
brew install ffmpeg

# libsndfile — required by soundfile (alternative audio I/O)
brew install libsndfile

# pkg-config — helps Python find the above libraries
brew install pkg-config
```

---

## 2. Python 3.12 via pyenv

**Why pyenv and not the system Python?**  
macOS ships Python 3.9 or 3.10. The ML ecosystem (ONNX Runtime, PyTorch MPS, torchaudio) is best tested on Python 3.12 as of 2025. Do not pollute your system Python.

```bash
# Install pyenv
brew install pyenv

# Add to ~/.zprofile
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zprofile
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zprofile
echo 'eval "$(pyenv init -)"' >> ~/.zprofile
source ~/.zprofile

# Install Python 3.12.11 (current stable as of 2025)
pyenv install 3.12.11
pyenv global 3.12.11

# Verify
python --version   # Should output: Python 3.12.11
which python       # Should output: ~/.pyenv/shims/python
```

---

## 3. Create The Canary Virtual Environment

**Always work inside a virtual environment.** Never install into the base pyenv environment.

```bash
# Navigate to your project root
cd ~/projects/canary   # or wherever your project lives

# Create venv
python -m venv .venv

# Activate
source .venv/bin/activate

# Verify
which python   # Should point inside .venv
python --version   # 3.12.11
```

---

## 4. Core Python Libraries — Ordered Install

Install in this exact order. Dependency resolution matters.

### 4.1 — NumPy (Foundation for everything)
```bash
pip install "numpy>=1.26,<2.0"
```
NumPy 2.x introduced breaking changes with some audio libraries. Pin to 1.x for now.

### 4.2 — PyTorch (with MPS support for Apple Silicon)
```bash
# MPS (Metal Performance Shaders) is built into the standard macOS PyTorch build
# Do NOT install the CUDA version — it does not exist for ARM macOS
pip install torch torchvision torchaudio

# Verify MPS is available
python -c "import torch; print(torch.backends.mps.is_available())"
# Expected output: True
```

**Important note on MPS for Canary**:  
For Stages 0, 1, and DRS, you will NOT use MPS — models are too small to benefit, and MPS adds 5–15ms of dispatch overhead. MPS is reserved for future Mode C (TFPSNet separation). Stage 0–1 runs exclusively on CPU via ONNX Runtime.

### 4.3 — ONNX Runtime (CPU)
```bash
# CPU version — Silero VAD and openWakeWord use ONNX
pip install onnxruntime

# Verify
python -c "import onnxruntime; print(onnxruntime.__version__)"
python -c "import onnxruntime; print(onnxruntime.get_available_providers())"
# Expected providers: ['CoreMLExecutionProvider', 'CPUExecutionProvider']
# CoreMLExecutionProvider is automatically used on Apple Silicon — this is a bonus!
```

**CoreMLExecutionProvider**: ONNX Runtime on macOS Apple Silicon automatically uses CoreML for operators it can offload to the Neural Engine. You get ANE acceleration for free without any extra code. The VAD inference will be faster because of this.

### 4.4 — Silero VAD
```bash
pip install silero-vad

# Verify and download model (this caches the ONNX model locally)
python -c "from silero_vad import load_silero_vad; m = load_silero_vad(); print('Silero VAD loaded:', type(m))"
```

The model is cached at `~/.cache/torch/hub/snakers4_silero-vad_master/`. It is ~1.8MB.

### 4.5 — openWakeWord
```bash
pip install openwakeword

# Download pretrained models (run once)
python -c "import openwakeword; openwakeword.utils.download_models()"
```

**On Mac M3**: openWakeWord can run via either tflite or ONNX backend. Force ONNX:
```bash
# If tflite causes issues (common on ARM), install onnx backend explicitly:
pip install "openwakeword[onnx]"
```

Models are downloaded to `~/.local/share/openwakeword/`. They are 400–800KB each.

### 4.6 — sounddevice (Real-time audio I/O)
```bash
pip install sounddevice

# Verify your mic is visible
python -c "import sounddevice as sd; print(sd.query_devices())"
# You should see your built-in microphone listed
```

**Finding your built-in microphone device ID**:
```python
import sounddevice as sd

devices = sd.query_devices()
for i, dev in enumerate(devices):
    if dev['max_input_channels'] > 0:
        print(f"[{i}] {dev['name']} — inputs: {dev['max_input_channels']}, "
              f"rate: {dev['default_samplerate']}")
```

Look for `MacBook Pro Microphone` or similar. Note its device ID — you will hardcode it.

### 4.7 — librosa (Feature extraction for Stage 1)
```bash
pip install "librosa>=0.10"

# Verify
python -c "import librosa; print('librosa version:', librosa.__version__)"
```

librosa is CPU-only and uses numpy internally. This is correct for Stage 1.

### 4.8 — scipy (Signal processing utilities)
```bash
pip install scipy
```

Used for high-pass filtering in pre-processing and correlation-based speaker estimation.

### 4.9 — Supporting libraries
```bash
# soundfile — alternative audio read/write backend
pip install soundfile

# webrtcvad — lightweight GMM VAD as fallback / sanity check
pip install webrtcvad

# Rich — for beautiful terminal logging (optional but helps debugging)
pip install rich

# pytest — for unit testing your pipeline
pip install pytest
```

---

## 5. Project Directory Structure

Create this structure **before writing any code**:

```
canary/
├── .venv/                          # Virtual environment (git-ignored)
├── config/
│   └── pipeline_config.yaml        # All tunable parameters in one place
├── stage0/
│   ├── __init__.py
│   ├── audio_capture.py            # sounddevice stream + ring buffer
│   ├── vad_engine.py               # Silero VAD wrapper
│   ├── wakeword_engine.py          # openWakeWord wrapper
│   └── passive_gate.py             # 3-bit output + PASS/FAIL logic
├── stage1/
│   ├── __init__.py
│   ├── preprocessor.py             # Resample, normalise, high-pass filter
│   ├── feature_extractor.py        # ZCR, spectral flatness, MFCC, SNR
│   ├── speaker_count_estimator.py  # Correlation + energy-based counting
│   └── acoustic_intelligence.py   # Combines features → P_overlap, N_norm, U_spkr
├── drs/
│   ├── __init__.py
│   ├── scs_calculator.py           # SCS = w1*P_ov + w2*N_norm + w3*U_spkr
│   └── mode_router.py              # Mode A / B / C dispatch
├── models/
│   └── cache/                      # Downloaded ONNX models go here (git-ignored)
├── tests/
│   ├── test_stage0.py
│   ├── test_stage1.py
│   └── test_drs.py
├── scripts/
│   ├── verify_env.py               # Run this to confirm everything works
│   └── live_test.py                # End-to-end mic test with terminal output
├── requirements.txt
└── README.md
```

---

## 6. Pipeline Configuration File

Create `config/pipeline_config.yaml` — ALL tunable parameters live here:

```yaml
# config/pipeline_config.yaml
# The Canary — Pipeline Configuration
# Centralising all thresholds makes tuning systematic, not guesswork.

audio:
  sample_rate: 16000          # Hz — fixed for all models
  chunk_size: 512             # samples (32ms) — Silero VAD optimal
  channels: 1                 # mono
  dtype: float32
  mic_device_id: null         # null = default; set to int after checking sd.query_devices()

stage0:
  # Silero VAD thresholds
  vad_threshold: 0.5          # speech probability threshold (0–1)
  vad_min_speech_ms: 250      # ignore speech segments shorter than this
  vad_min_silence_ms: 100     # silence needed to close a speech segment

  # Wake-word detection
  wakeword_model: "hey_jarvis"   # or your custom model name
  wakeword_threshold: 0.5        # τ1 in the PASS formula
  wakeword_window_ms: 1000       # rolling window for wake-word probability

  # Noise floor gate
  noise_floor_threshold: 0.8     # τ3; if Nf > this, stay idle even if speech detected
  noise_floor_window_chunks: 10  # average over last N chunks

  # Gate logic
  require_wakeword: true         # if false, any speech passes (useful for testing)

stage1:
  # Pre-processing
  highpass_cutoff_hz: 80         # remove sub-80Hz rumble
  highpass_order: 4              # Butterworth filter order
  normalize_target_db: -23       # LUFS target for normalisation

  # Feature extraction window
  feature_window_samples: 1600   # 100ms at 16kHz (must be multiple of chunk_size)
  feature_hop_samples: 512       # 32ms hop between windows

  # Speaker count estimation
  speaker_count_min_correlation: 0.3   # cross-correlation threshold for 2nd speaker
  speaker_count_mfcc_bins: 13          # number of MFCC coefficients
  max_speaker_count: 3                 # we support up to 3 as per problem statement

  # SNR estimation
  snr_noise_percentile: 10       # use bottom 10% of energy frames as noise estimate

dynamic_resource_scaler:
  # SCS formula: SCS = w1*P_overlap + w2*N_norm + w3*U_speaker
  weight_overlap: 0.45           # w1
  weight_noise: 0.35             # w2
  weight_speaker_uncertainty: 0.20  # w3
  # weights must sum to 1.0

  # Mode boundaries
  mode_a_threshold: 0.25         # SCS below this → MODE A
  mode_c_threshold: 0.65         # SCS above this → MODE C
  # SCS between → MODE B

  # Hysteresis (prevents rapid mode switching)
  hysteresis_margin: 0.05        # ±5% deadband around boundaries
  mode_hold_ms: 500              # minimum time to stay in a mode
```

---

## 7. Verification Script

Create `scripts/verify_env.py` and run it after setup:

```python
#!/usr/bin/env python3
"""
verify_env.py — Run this to confirm the environment is ready.
Every check must PASS before writing any pipeline code.
"""

import sys
import time
from rich.console import Console
from rich.table import Table

console = Console()
results = []

def check(name, fn):
    try:
        result = fn()
        results.append((name, "✅ PASS", str(result)))
    except Exception as e:
        results.append((name, "❌ FAIL", str(e)))

# --- checks ---

check("Python version (need 3.12)",
    lambda: f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

check("numpy import",
    lambda: __import__("numpy").__version__)

check("torch import + MPS check",
    lambda: (lambda t: f"torch {t.__version__}, MPS={'yes' if t.backends.mps.is_available() else 'NO'}")
            (__import__("torch")))

check("onnxruntime import",
    lambda: (lambda o: f"version {o.__version__}, providers: {o.get_available_providers()}")
            (__import__("onnxruntime")))

check("silero_vad model load",
    lambda: (lambda s: f"Loaded: {type(s.load_silero_vad()).__name__}")
            (__import__("silero_vad")))

check("openwakeword import",
    lambda: __import__("openwakeword").__version__)

check("sounddevice + mic query",
    lambda: (lambda sd: f"Default input: {sd.query_devices(kind='input')['name']}")
            (__import__("sounddevice")))

check("librosa import",
    lambda: __import__("librosa").__version__)

check("scipy import",
    lambda: __import__("scipy").__version__)

check("5-second mic capture test",
    lambda: _capture_test())

def _capture_test():
    import sounddevice as sd
    import numpy as np
    captured = []
    def cb(indata, frames, time, status):
        captured.append(indata.copy())
    with sd.InputStream(samplerate=16000, channels=1, dtype='float32',
                        blocksize=512, callback=cb):
        time.sleep(1.0)
    total = sum(len(c) for c in captured)
    rms = float(np.sqrt(np.mean(np.concatenate(captured)**2)))
    return f"{total} samples captured, RMS={rms:.6f}"

# --- output ---
table = Table(title="Canary Environment Check", show_header=True)
table.add_column("Check", style="cyan")
table.add_column("Status", style="bold")
table.add_column("Details", style="dim")

for name, status, detail in results:
    table.add_row(name, status, detail)

console.print(table)

if all("PASS" in r[1] for r in results):
    console.print("\n[bold green]✅ Environment is READY. Proceed to Stage 0.[/bold green]")
else:
    console.print("\n[bold red]❌ Fix the failing checks before proceeding.[/bold red]")
```

Run it:
```bash
python scripts/verify_env.py
```

---

## 8. Common M3 Issues and Fixes

### Issue: `sounddevice` cannot find PortAudio
```bash
# Fix:
brew reinstall portaudio
pip install --force-reinstall sounddevice
```

### Issue: `openwakeword` tflite backend crashes on ARM
```bash
# Fix: force ONNX backend
pip uninstall openwakeword -y
pip install "openwakeword[onnx]"
# In code, always pass: inference_framework='onnx'
```

### Issue: Silero VAD returns all zeros / always silence
This is caused by incorrect audio normalisation. Silero expects float32 audio in the range `[-1.0, 1.0]`. Mac M3 mic delivers in this range by default via sounddevice, but if you resample or chain audio, verify:
```python
assert audio.dtype == np.float32
assert audio.min() >= -1.0 and audio.max() <= 1.0
```

### Issue: PyTorch MPS not detected
```bash
# Fix: ensure you installed the macOS (CPU+MPS) build, not CUDA
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio  # standard pip install auto-detects macOS
```

### Issue: `webrtcvad` crashes on ARM Python
```bash
# Fix: install from source
pip install --no-binary webrtcvad webrtcvad
```

---

## 9. Requirements File

Create `requirements.txt`:

```
# Core
numpy>=1.26,<2.0
scipy>=1.13

# PyTorch (MPS support built-in for macOS arm64)
torch>=2.3
torchaudio>=2.3
torchvision>=0.18

# ONNX Runtime (CoreML EP automatic on Apple Silicon)
onnxruntime>=1.19

# Audio I/O
sounddevice>=0.4.7
soundfile>=0.12

# VAD + Wake Word
silero-vad>=5.0
openwakeword>=0.6.0

# Feature Extraction
librosa>=0.10
webrtcvad>=2.0.10

# Utilities
PyYAML>=6.0
rich>=13.0
pytest>=8.0
```

Install all at once:
```bash
pip install -r requirements.txt
```

---

*Next → Read `02_STAGE0_PASSIVE_IDLE.md`*
