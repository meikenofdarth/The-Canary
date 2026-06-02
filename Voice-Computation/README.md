# Voice-Computation Module — The Canary

## What This Module Does

This is **Stage 0 + Pre-Processing + Scene Analysis + Dynamic Resource Scaler** of the Canary pipeline.
Everything up to the point where audio gets routed to Sanchit's AI models (TIGER, CAM++, ASR).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        YOUR SCOPE (This Module)                        │
│                                                                        │
│  Mic → Ring Buffer → Silero VAD → Wake-Word → Pre-Processing →        │
│  Scene Analysis → Dynamic Resource Scaler → MODE A/B/C routing        │
│                                                                        │
│  OUTPUT: Cleaned audio buffer + mode decision + metadata               │
│          (handed off to Sanchit's TIGER/CAM++/ASR)                     │
└─────────────────────────────────────────────────────────────────────────┘
```

## Architecture

### 1. Audio Capture (`audio/capture.py`)
- Uses `sounddevice` to capture 16kHz mono audio
- Implements a **ring buffer** that holds rolling 30ms chunks
- Compiles chunks into 1-2 second windows for processing
- Thread-safe with proper locking

### 2. Silero VAD (`vad/silero_vad.py`)
- ONNX INT8 quantized model (~0.5M params)
- Processes 30ms chunks, outputs speech probability [0.0-1.0]
- If silence → buffer is dropped, system stays idle (saves power)
- If speech detected → buffer expands and passes to wake-word

### 3. Wake-Word Detection (`wakeword/detector.py`)
- Lightweight keyword spotting
- Uses `openwakeword` (open-source, TFLite backend)
- Processes sliding windows of spectrogram features
- Requires consecutive detections over multiple windows to trigger (prevents false positives)
- Outputs: `wakeword_detected` (bool), `wakeword_confidence` (float)

### 4. Pre-Processing (`preprocessing/`)
- **Noise Estimator** (`noise_estimator.py`): Tracks ambient noise floor using spectral subtraction
- **Audio Normalizer** (`normalizer.py`): Peak normalization, DC offset removal, pre-emphasis filter
- **Feature Extractor** (`features.py`): Extracts mel-spectrograms, energy, ZCR for downstream analysis

### 5. Scene Analyzer (`scene/analyzer.py`)
- Computes the **Scene Complexity Score (SCS)**:
  ```
  SCS = w1 * overlap_probability + w2 * normalized_noise_floor + w3 * (1 - wakeword_certainty)
  ```
- Estimates speaker count from spectral features
- Detects overlap probability
- Routes to Mode A/B/C based on SCS thresholds

### 6. Dynamic Resource Scaler (`scaler/resource_scaler.py`)
- Takes scene analysis output and decides the compute path:
  - **Mode A** (SCS < 0.20): Clean single speaker → lightweight DSP only, skip separation
  - **Mode B** (0.20 ≤ SCS < 0.45): Moderate noise → adaptive DSP + speaker verification
  - **Mode C** (SCS ≥ 0.45): Heavy overlap → full TIGER separation pipeline
- Outputs a `ScalerDecision` with the mode, processed audio, and all metadata

## How It Works (Flow)

```
1. Microphone captures audio at 16kHz mono
2. Audio goes into a ring buffer (30ms chunks)
3. Every chunk → Silero VAD checks for speech
   - No speech? Drop buffer, stay idle
   - Speech detected? Continue...
4. Accumulated audio → Wake-word detector
   - No wake-word? Keep listening (or track as ambient)
   - Wake-word detected? System ACTIVATES
5. Active audio → Pre-processing
   - Remove DC offset, normalize amplitude
   - Estimate and subtract noise floor
   - Extract spectral features (mel-spectrogram, energy, ZCR)
6. Features → Scene Analyzer
   - How many speakers? (spectral clustering heuristic)
   - How much overlap? (energy variance analysis)
   - How noisy? (SNR estimation)
   - Compute Scene Complexity Score
7. SCS → Dynamic Resource Scaler
   - Route to Mode A, B, or C
   - Package everything into a ScalerDecision
8. ScalerDecision → OUTPUT (goes to Sanchit's pipeline)
```

## File Structure

```
Voice-Computation/
├── README.md                    # This file
├── requirements.txt             # Dependencies for this module
├── config.py                    # Central configuration
├── __init__.py
├── audio/
│   ├── __init__.py
│   ├── capture.py               # Mic capture + ring buffer
│   └── ring_buffer.py           # Thread-safe ring buffer
├── vad/
│   ├── __init__.py
│   └── silero_vad.py            # Silero VAD wrapper
├── wakeword/
│   ├── __init__.py
│   └── detector.py              # Wake-word detection
├── preprocessing/
│   ├── __init__.py
│   ├── noise_estimator.py       # Noise floor tracking
│   ├── normalizer.py            # Audio normalization
│   └── features.py              # Feature extraction
├── scene/
│   ├── __init__.py
│   └── analyzer.py              # Scene complexity scoring
├── scaler/
│   ├── __init__.py
│   └── resource_scaler.py       # Mode A/B/C routing
├── pipeline.py                  # Orchestrates everything
├── models.py                    # Data classes (contracts)
└── demo.py                      # Demo runner (test with mic or wav files)
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Download Silero VAD model (auto-downloads on first run)
# The model is fetched from torch.hub automatically

# 3. Run the demo
python -m Voice-Computation.demo

# 4. Run with a WAV file instead of mic
python -m Voice-Computation.demo --input path/to/test.wav

# 5. Run individual modules for testing
python -m Voice-Computation.vad.silero_vad          # Test VAD alone
python -m Voice-Computation.preprocessing.features  # Test feature extraction
```

## How to Integrate with Sanchit's Code

```python
from voice_computation.pipeline import VoiceComputationPipeline
from voice_computation.models import ScalerDecision

# Initialize
pipeline = VoiceComputationPipeline()

# Process audio (returns ScalerDecision)
decision = pipeline.process(audio_chunk)  # numpy float32, 16kHz

# What Sanchit receives:
# decision.mode          → PipelineMode.MODE_A / B / C
# decision.audio         → cleaned numpy array (float32, 16kHz)
# decision.metadata      → dict with all scores and features
# decision.speaker_count → estimated number of speakers
```
