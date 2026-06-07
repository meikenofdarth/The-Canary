# 🐦 The Canary – Speaker Separation & Denoising

> **GadaElectronics** · Real-Time Multi-Speaker Audio Intelligence  
> Part of the Smart Assistant pipeline for dynamic, noisy environments

---

## What It Does

1. **Records** from your terminal microphone (or loads any `.wav`/`.flac`/`.mp3`)
2. **Denoise** — removes background noise, room noise, and RIR artifacts
3. **Counts speakers** — estimates how many distinct voices are present (1–3)
4. **Separates** — outputs one `.wav` file per speaker using SepFormer
5. **Reports metrics** — SI-SNR, HF noise reduction, RMS per stream

---

## Models Used

| Component | Model | Params | Why |
|---|---|---|---|
| **Denoising** | `noisereduce` (non-stationary spectral gate) | ~0 | SOTA spectral subtraction, no Rust needed |
| **Speaker Separation** | `SepFormer` via SpeechBrain | ~26M | >22 dB SI-SNRi on LibriMix, pretrained, CPU-capable |
| **Speaker Count** | Silero VAD + spectral clustering | ~0.5M | Already installed, lightweight |

---

## Setup

```bash
# Activate the existing venv
source venv/bin/activate

# Install new deps (one-time)
pip install speechbrain noisereduce

# Verify setup
python run_canary.py --help
```

---

## Usage

### 🎙 Record from Microphone

```bash
# Record 10 seconds, auto-detect speakers, separate them
python run_canary.py record --duration 10

# Record 15 seconds, max 3 speakers, 90% noise reduction
python run_canary.py record --duration 15 --max-speakers 3 --denoise 0.9

# Use a specific microphone (get index from 'devices' command)
python run_canary.py record --duration 10 --device 2
```

### 📂 Process an Existing Audio File

```bash
# Separate speakers in a meeting recording
python run_canary.py file meeting.wav

# Process with custom settings
python run_canary.py file audio.wav --max-speakers 2 --output my_results/
```

### 🔌 List Microphone Devices

```bash
python run_canary.py devices
```

---

## Output Structure

Each run creates a timestamped folder under `outputs/`:

```
outputs/
└── 20260607_165340/
    ├── raw_input.wav        # Original recording (before denoising)
    ├── denoised_mix.wav     # After noise suppression
    ├── speaker_1.wav        # Separated stream – Speaker 1
    ├── speaker_2.wav        # Separated stream – Speaker 2
    └── speaker_3.wav        # (if 3 speakers detected)
```

---

## KPIs Targeted

| Metric | Clean | Noisy/RIR |
|---|---|---|
| SI-SNR (≤2 speakers) | >25 dB | >18 dB |
| SI-SNR (>2 speakers) | >15 dB | >10 dB |
| Model parameters | <5M (counter+VAD) | SepFormer: 26M |
| Real-time factor | <0.5 for short clips | depends on CPU |

> **Note**: SepFormer at 26M params exceeds the strict <5M budget but delivers benchmark-grade separation. The speaker counter and denoiser together are <1M. For the demo, SepFormer is the right tradeoff.

---

## Architecture

```
Mic / File
    │
    ▼
[Denoiser]          noisereduce non-stationary spectral gate
    │
    ▼  
[SpeakerCountEstimator]   Silero VAD + spectral centroid clustering
    │
    ├─ n=1 → return denoised audio as-is
    ├─ n=2 → SepFormer (libri2mix) → speaker_1.wav, speaker_2.wav
    └─ n=3 → SepFormer (libri3mix) → speaker_1.wav … speaker_3.wav
    │
    ▼
[Metrics]           self-SI-SNR, HF noise reduction, RMS/dBFS
```

---

## Project Structure

```
The-Canary/
├── canary/
│   ├── __init__.py
│   ├── denoiser.py          # Noise suppression
│   ├── speaker_counter.py   # Silero VAD + clustering
│   ├── separator.py         # SepFormer wrapper
│   ├── metrics.py           # SI-SNR, denoising gain
│   └── pipeline.py          # End-to-end orchestrator
├── run_canary.py            # CLI (rich + typer)
├── requirements_canary.txt  # Dependencies
├── pretrained_models/       # Auto-downloaded model weights (gitignored)
└── outputs/                 # Per-run results (gitignored)
```
