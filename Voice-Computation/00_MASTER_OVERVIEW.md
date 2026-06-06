# 🐤 The Canary — Master Implementation Plan
### Real-Time Multi-User Smart Assistant | Stage 0 → Stage 1 → Dynamic Resource Scaler

> **Author**: Hemang Seth, GadaElectronics | IIIT-Bangalore  
> **Scope of this doc-set**: Microphone input → 3-bit gate output → Acoustic Scene Intelligence → Scene Complexity Score → Mode A / B / C routing  
> **Platform**: macOS M3 Apple Silicon, built-in microphone  
> **Languages**: Python 3.12 (primary), C++ snippets for latency-critical paths  

---

## Table of Contents

| File | What It Covers |
|------|---------------|
| `00_MASTER_OVERVIEW.md` | This file — Architecture philosophy, signal flow, why each decision was made |
| `01_ENVIRONMENT_SETUP.md` | Conda env, Python 3.12, MPS, ONNX Runtime, sounddevice, all libraries |
| `02_STAGE0_PASSIVE_IDLE.md` | Silero VAD v5, openWakeWord, the 3-bit output, threading model |
| `03_STAGE1_ACOUSTIC_INTELLIGENCE.md` | Pre-processing, speaker count, overlap detection, directed speech |
| `04_DYNAMIC_RESOURCE_SCALER.md` | SCS formula, weight tuning, Mode A / B / C routing, queue design |

---

## 1. The Core Philosophy (Read This First)

The **entire reason Canary exists** is summarised in one line from your proposal:

> *"Every sound must first earn its compute."*

This means the pipeline is not a flat processing chain. It is a **compute gate** — each stage has a hard `PASS/FAIL` before the next stage sees a single CPU cycle. This is your fundamental design principle and everything below must honour it.

```
Microphone (raw PCM)
        │
        ▼
┌───────────────────────┐  FAIL (silence / noise)
│  STAGE 0              │──────────────────────────► IDLE (no compute)
│  Passive Idle Gate    │
│  Silero VAD  +        │  PASS (3-bit word: Sb|Pw|Nf)
│  Wake-Word CNN        │──────────────────────────────────────────┐
└───────────────────────┘                                          │
                                                                   ▼
                                              ┌─────────────────────────────────┐
                                              │  STAGE 1                        │
                                              │  Acoustic Scene Intelligence    │
                                              │  Pre-processing → Feature Ext.  │
                                              │  Speaker Count Estimation       │
                                              │  Overlap Probability (P_overlap)│
                                              │  Directed Speech Score (Ds)     │
                                              └─────────────────────────────────┘
                                                                   │
                                                     SCS Score (weighted sum)
                                                                   │
                                              ┌────────────────────▼──────────────┐
                                              │  DYNAMIC RESOURCE SCALER          │
                                              │  SCS < 0.25 → MODE A (Minimal)    │
                                              │  SCS 0.25–0.65 → MODE B (Assisted)│
                                              │  SCS > 0.65 → MODE C (Full Sep.)  │
                                              └───────────────────────────────────┘
```

---

## 2. What Went Wrong With The Direct Agent Approach

This is important — understand WHY it failed so you do not repeat it.

### Problem 1: No gate between stages
When you jumped directly to implementation, every audio chunk went through every model. The speaker count estimation was firing on silence, on noise, on TV audio — everything. There was no `PASS/FAIL` checkpoint. The fix: **Stage 0 must be a hard binary gate**. Nothing downstream executes unless the 3-bit word clears.

### Problem 2: Speaker count estimation without preprocessing
Raw microphone audio from a Mac M3 built-in mic is **not clean**. The mic captures room reflections, fan noise, and electrical interference. Running speaker count estimation on raw PCM is meaningless. The fix: **Always pre-process** (resample → normalise → apply high-pass filter → noise gate) before any feature extraction.

### Problem 3: Treating all features as independent
SCS (Scene Complexity Score) is not a threshold on a single feature. It is a **weighted composite** of multiple features. Each feature alone is unreliable; together they vote. The fix: Compute all features in Stage 1, combine them via the SCS formula, then route.

### Problem 4: Thread contention
VAD, feature extraction, and model inference running on the same thread causes buffer overflows in the audio callback. On Mac, the CoreAudio callback thread is **real-time priority** — any blocking call there crashes the stream. The fix: Dedicated thread architecture (see Stage 0 doc).

---

## 3. Data Flow — What Each Stage Produces and Consumes

### Stage 0 Outputs: The 3-bit Word
This is the contract between Stage 0 and everything downstream.

```
┌─────────────────────────────────────────────────────┐
│                  3-BIT OUTPUT WORD                  │
├─────────────────┬──────────────┬────────────────────┤
│  Bit 0: Sb      │  Bit 1: Pw   │  Bit 2: Nf         │
│  Speech Binary  │  Wake-Word   │  Noise Floor        │
│  0 = no speech  │  Probability │  (normalised 0–1)   │
│  1 = speech     │  (float)     │  0=clean, 1=noisy   │
│  (from VAD)     │  (from CNN)  │  (from VAD energy)  │
├─────────────────┴──────────────┴────────────────────┤
│  PASS condition:                                    │
│  Sb == 1 AND Pw > τ1 AND Nf < τ3                   │
│  Only then: forward chunk to Stage 1                │
└─────────────────────────────────────────────────────┘
```

### Stage 1 Outputs: Feature Vector → SCS
```
┌──────────────────────────────────────────────────────────────┐
│               STAGE 1 FEATURE OUTPUT                         │
├──────────────────────┬───────────────────────────────────────┤
│  P_overlap (float)   │  Probability of overlapping speech    │
│                      │  (0 = 1 speaker, 1 = heavy overlap)   │
├──────────────────────┼───────────────────────────────────────┤
│  N_norm (float)      │  Normalised noise level (0–1)         │
│                      │  From SNR estimation                   │
├──────────────────────┼───────────────────────────────────────┤
│  U_speaker (float)   │  Speaker uncertainty score (0–1)      │
│                      │  From speaker count confidence         │
├──────────────────────┼───────────────────────────────────────┤
│  SCS (float)         │  w1*P_overlap + w2*N_norm + w3*U_spkr │
│                      │  Σw_i = 1                              │
└──────────────────────┴───────────────────────────────────────┘
```

### Dynamic Resource Scaler Output: Mode Signal
```python
# Exactly one of these is true at any time:
MODE_A = SCS < 0.25          # clean audio, known speaker → lightweight DSP
MODE_B = 0.25 <= SCS <= 0.65 # moderate noise/overlap → adaptive DSP + verification
MODE_C = SCS > 0.65          # heavy overlap, noisy → full speaker separation
```

---

## 4. Audio Parameters — The Non-Negotiables

These parameters are fixed for the entire pipeline. Do NOT change them mid-pipeline.

| Parameter | Value | Why |
|-----------|-------|-----|
| Sample Rate | **16,000 Hz** | Silero VAD, openWakeWord, MatchboxNet all require 16 kHz |
| Bit Depth | **float32** | Native numpy/torch format, no conversion needed |
| Channels | **1 (mono)** | Mac built-in mic is mono; do not attempt stereo |
| VAD Chunk Size | **512 samples** (32ms) | Silero v5 optimal chunk; also openWakeWord chunk |
| Stage 1 Window | **1600 samples** (100ms) | Feature extraction window (multiple of 512) |
| SCS Window | **4800 samples** (300ms) | Rolling window for SCS calculation |
| Audio Buffer | **Ring buffer, 8 × window** | Prevents blocking; allows lookback |

---

## 5. Threading Architecture (Critical for Mac M3)

macOS CoreAudio uses a **real-time callback thread**. You cannot call PyTorch inference, numpy FFT, or Python GIL-holding code from this thread. The architecture must be:

```
CoreAudio RT Thread
(sounddevice callback)
        │
        │ — enqueue raw PCM chunk (lock-free)
        ▼
   [Ring Buffer]
        │
        │ — dequeue (non-blocking)
        ▼
Stage 0 Thread (normal priority)
  Silero VAD + Wake-Word inference
        │
        │ — if PASS: enqueue chunk + 3-bit word
        ▼
   [Queue 0→1]
        │
Stage 1 Thread (normal priority)
  Pre-process + Feature Extraction
        │
        │ — emit SCS + mode signal
        ▼
   [Queue 1→DRS]
        │
Dynamic Resource Scaler Thread
  Mode Selection + Dispatch
        │
        └──► Mode A handler / Mode B handler / Mode C handler
```

**Why threads and not asyncio?**  
Audio callbacks are not coroutines. The CoreAudio RT thread fires at hardware interrupt level. Python's asyncio event loop runs in a single thread and cannot pre-empt the GIL. Use `threading.Thread` + `queue.Queue` (thread-safe, blocking with timeout). For the audio callback itself, use the `sounddevice` callback API which handles the RT thread.

---

## 6. Model Summary — What You Are Actually Running

| Stage | Model | Parameters | Format | Runtime |
|-------|-------|-----------|--------|---------|
| 0 — VAD | Silero VAD v5 | ~0.5M | ONNX (.onnx) | ONNX Runtime (CPU) |
| 0 — Wake Word | openWakeWord | ~0.4M | ONNX / tflite | ONNX Runtime (CPU) |
| 1 — Noise/Overlap | Custom DSP features | 0 (no model) | numpy | CPU |
| 1 — Speaker Count | Correlation + MFCC heuristic | 0 (no model) | numpy | CPU |
| DRS — SCS | Weighted formula | 0 (no model) | Python | CPU |

**Key insight**: Stage 0 and Stage 1 (in your scope) use **no GPU**. MPS/CoreML is only needed if you later add Samsung TFPSNet (Mode C) or CAM++ (speaker verification). For Stages 0, 1, and DRS: CPU-only via ONNX Runtime is optimal — it avoids Metal/MPS overhead for small models and keeps latency predictable.

---

## 7. Latency Budget

Your target is `xRT < 0.5`, meaning processing one second of audio must take less than 0.5 seconds.

| Stage | Expected Latency | Notes |
|-------|----------------|-------|
| Stage 0 VAD (512 samples) | **~2ms** | ONNX on M3 CPU |
| Stage 0 Wake Word (512 samples) | **~3ms** | ONNX on M3 CPU |
| Stage 1 Pre-processing | **~1ms** | numpy FFT |
| Stage 1 Feature extraction | **~5ms** | ZCR, MFCC, spectral flatness |
| SCS computation | **<0.1ms** | Pure Python arithmetic |
| Mode dispatch | **<0.1ms** | if/else |
| **TOTAL per chunk (512 samp)** | **~11ms** | Well within 32ms chunk budget |

Since you process 512 samples at 16 kHz = **32ms real-time** and the entire pipeline takes ~11ms, you have ~21ms headroom. This is more than sufficient for Mode A. Mode C (full separation) will be the challenge — that is for future scope.

---

## 8. Recommended Reading Order

1. **Start here** → `01_ENVIRONMENT_SETUP.md` — install everything correctly for M3
2. **Build Stage 0** → `02_STAGE0_PASSIVE_IDLE.md` — get the 3-bit output working first
3. **Test Stage 0 alone** — point mic at room noise, TV audio, your own voice with and without wake word
4. **Build Stage 1** → `03_STAGE1_ACOUSTIC_INTELLIGENCE.md` — only after Stage 0 is stable
5. **Build DRS** → `04_DYNAMIC_RESOURCE_SCALER.md` — only after Stage 1 is outputting stable features

**Do not parallelize development across stages.** The interdependence is strong. A broken Stage 0 will produce garbage features in Stage 1.

---

## 9. Key Research References Used In This Plan

| Reference | Used For |
|-----------|----------|
| Silero VAD v5 (snakers4/silero-vad) | Stage 0 VAD core |
| openWakeWord (dscripka/openWakeWord) | Stage 0 wake-word detection |
| MatchboxNet (arxiv: 2004.08531) | Stage 1 noise/command classification backbone |
| pyannote overlapped-speech-detection | Stage 1 overlap estimation design |
| ONNX Runtime (Microsoft) | Cross-platform inference engine |
| sounddevice + CoreAudio | Mac M3 real-time audio capture |
| librosa feature extraction | ZCR, spectral flatness, MFCC implementation |
| Conditional Computation (Bengio et al. arxiv: 1511.06297) | Dynamic Resource Scaler design |
| PyTorch MPS (Apple Silicon) | GPU acceleration for future heavy models |

---

*Next → Read `01_ENVIRONMENT_SETUP.md`*
