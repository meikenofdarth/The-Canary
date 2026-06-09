# The Canary - Speaker Separation, Denoising, and Intent Routing Pipeline

This project is a multi-speaker audio intelligence pipeline designed for smart assistants operating in noisy, dynamic environments. It captures audio, suppresses background noise, estimates the speaker count, separates individual voices, transcribes them using speech-to-text, evaluates scene complexity, and routes commands based on speaker intents and potential conflicts.

---

## What It Does

The Canary processes mixed audio through a sequential pipeline of signal processing, machine learning models, and rule-based logic:

1. **Audio Capture**: Records mono audio from the system microphone (16000 Hz) or loads an audio file.
2. **Speaker Count Estimation**: Analyzes acoustic features of sliding windows to estimate if 1, 2, or 3 speakers are active.
3. **Blind Source Separation**: Applies pretrained SepFormer neural networks to separate overlapping voices into independent audio streams.
4. **Crosstalk Suppression**: Orthogonalizes streams using Gram-Schmidt projection to eliminate bleeding between channels.
5. **Speech Enhancement**: Applies high-pass filtering, spectral noise suppression, presence boosting, dynamic range compression, and loudness normalization to make each voice clear and intelligible.
6. **ASR Quality Gating**: Filters out silence, noise, and transcript hallucinations before and after running Whisper speech-to-text.
7. **Context & Wake Word Analysis**: Identifies wake word expressions (including fuzzy phonetic variants) and classifies speaker intents.
8. **Routing & Conflict Resolution**: Evaluates commands to detect conflicting operations (like play versus stop) and determines whether to execute, ignore, clarify, or multi-execute instructions.
9. **Dynamic Resource Scaling**: Computes scene complexity using noise level, speaker count, and speech overlap to output recommended processing modes.

---

## Project Structure

The project is structured into three core modules, an orchestrating CLI entrypoint, and data directories:

```
The-Canary/
├── run_canary.py            # CLI entrypoint and pipeline orchestrator
├── requirements_canary.txt  # Project dependencies list
├── separation-filtering/    # Core audio separation and DSP module
│   ├── __init__.py          # Module initialization
│   ├── denoiser.py          # Non-stationary spectral noise reduction
│   ├── speaker_counter.py   # Sliding-window acoustic feature clustering
│   ├── separator.py         # SepFormer source separation wrapper
│   ├── metrics.py           # Audio metrics (SI-SNR, RMS, SNR, leakage)
│   └── pipeline.py          # Core orchestrator class
├── asr/                     # Speech-to-text module
│   ├── __init__.py          # Module initialization
│   └── transcribe.py        # Whisper wrapper with pre/post-transcription gates
├── context_engine/          # Context parsing and routing engine
│   ├── __init__.py          # Module initialization
│   ├── context_builder.py   # context.json generator and router
│   ├── wakeword_detector.py # String matching and phonetic fuzzy wake word detector
│   ├── utterance_analyzer.py# Rules-based utterance classifier
│   └── conflict_detector.py # Action-antonym command conflict detector
├── pretrained_models/       # Cache directory for model checkpoints (gitignored)
└── outputs/                 # Run outputs containing audio and context JSON (gitignored)
```

---

## Detailed Component Walkthrough

### 1. Separation and Filtering Core (separation-filtering/)

*   **Denoiser (denoiser.py)**: Wraps the `noisereduce` library. It estimates noise profiles dynamically and applies spectral gating under a non-stationary assumption. This removes environmental noises (such as fans, HVAC hum, and room reverb) while preserving speech. It automatically scales and caps signal peaks to 0.98 to prevent clipping.
*   **Speaker Count Estimator (speaker_counter.py)**: Slides a 500ms window (50% overlap) across the audio signal. It extracts a 6-dimensional acoustic feature vector (log energy, zero-crossing rate, spectral centroid, spectral bandwidth, spectral rolloff, log flatness) for each voiced frame. These features are standardized and clustered using a greedy agglomerative clustering method across multiple distance thresholds. The median number of clusters represents the estimated speaker count (1 to 3).
*   **Speaker Separator (separator.py)**: Integrates SpeechBrain's pretrained SepFormer model. When 2 speakers are estimated, it loads `speechbrain/sepformer-libri2mix`. For 3 speakers, it loads `speechbrain/sepformer-libri3mix`. The models downsample the audio to 8000 Hz, execute blind source separation, upsample the separated streams back to 16000 Hz, and pad/trim them to align with the original input duration. In 3-speaker mode, it automatically discards any stream whose speech-band RMS is less than 25% of the loudest stream to filter out neural artifacts (ghost speakers).
*   **Metrics (metrics.py)**: Provides evaluation algorithms:
    *   **SI-SNR (Scale-Invariant Signal-to-Noise Ratio)**: Evaluates separation quality.
    *   **SNR**: Computes classical Signal-to-Noise Ratio.
    *   **RMS DB**: Computes Root Mean Square amplitude in dBFS.
    *   **Self-SI-SNR**: Computes cross-talk leakage by checking each separated stream against the sum of all other streams.
    *   **Denoising Gain**: Reports overall RMS change and high-frequency noise floor reduction.

### 2. Speech-to-Text (asr/)

*   **Transcription Engine (transcribe.py)**: Integrates OpenAI's Whisper speech-to-text model (defaulting to the `base` model). To ensure high-quality transcripts and avoid processing noise, it implements two gating mechanisms:
    *   **Pre-Screening Gate**: Checks audio before running Whisper. It rejects streams if the overall RMS energy is below -52 dBFS (silent stream) or if the voiced frame ratio is less than 15% (energy-based Voice Activity Detection).
    *   **Post-Transcription Quality Gate**: Analyzes Whisper outputs. It rejects transcripts if the average segment log probability (`avg_logprob`) is below -1.2 (gibberish/noise), if the transcript exhibits repetitive patterns, or if the text compression ratio exceeds 2.8 for long strings (Whisper hallucination loops).
    *   Streams that fail these gates are marked as `REJECTED` in their metadata, and their transcripts are discarded. Streams that pass are flagged as `READY`.

### 3. Context Engine (context_engine/)

*   **Wake Word Detector (wakeword_detector.py)**: Performs string-matching against standard wake words (such as "Canary", "Hey Canary", "Hello Canary"). To compensate for phonetic errors in transcription, it incorporates a fuzzy mapping table of over 40 common Whisper mis-transcriptions (like "cannery", "qanary", "anari", "canarie", "canary's") with predefined confidence weights (0.55 to 0.80).
*   **Utterance Analyzer (utterance_analyzer.py)**: A rules-based regex classifier mapping sentences across 15 smart home domains (Media, Lighting, Climate, Security, Appliances, Entertainment, Communication, Shopping, Timers, Navigation, Routines, Search/Information, Volume, Open/Close, Health). It classifies utterances into:
    *   `COMMAND`: An imperative request directed at the assistant.
    *   `QUESTION`: An interrogative request.
    *   `CONVERSATION`: Social or ambient speech not addressed to the assistant.
    *   `UNKNOWN`: Too short or ambiguous to classify.
*   **Conflict Detector (conflict_detector.py)**: Scans commands from different speakers to check for conflicts. A conflict is identified if the action verbs used are antonyms (such as "play" versus "stop", "turn on" versus "turn off", "open" versus "close", "warmer" versus "cooler"). It also checks for override command phrases where one speaker tells the assistant to redirect attention (e.g., "listen to me", "ignore him", "focus on me"), resulting in an intentional override conflict.
*   **Context Builder (context_builder.py)**: Aggregates transcripts, wake word indicators, and intent categories into a unified JSON structure. It applies routing rules based on the active command counts and conflict flags to produce a system routing decision.

### 4. CLI Entrypoint (run_canary.py)

*   **Audio Capture**: Records a fixed duration (default 7 seconds) using `sounddevice` or handles file-based inputs.
*   **Smart Routing Heuristics**: If only 1 speaker is detected, it skips SepFormer entirely to avoid artificial distortion, passing the raw signal directly to a high-fidelity single-speaker enhancement pipeline. If 2 or 3 speakers are detected, it invokes SepFormer and then runs stream-specific enhancement.
*   **Gram-Schmidt Crosstalk Suppression**: Applies Gram-Schmidt orthogonalization between separated streams. This minimizes bleeding (cross-talk) between streams and orders the streams by speech-band energy, ensuring `speaker_1.wav` contains the dominant voice.
*   **Post-Processing DSP**: Each stream is processed by a high-pass filter (80 Hz), non-stationary noise reduction, a presence shelf boost (+3.5 dB above 2000 Hz) to restore high-frequency detail, a soft-knee dynamic compressor (attack 5ms, release 150ms, threshold -18 dB, ratio 3:1), and peak-limited loudness normalization.
*   **Dynamic Resource Scaler (DRS)**: Analyzes the mixture in shadow mode. It calculates a complexity score based on:
    *   **Noise Level**: In-band SNR calculation of the raw mixture.
    *   **Overlap Probability**: Temporal overlap percentage of voiced frames between speaker streams.
    *   **Speaker Score**: Scaled speaker count.
    *   Complexity Score formula: `0.5 * Overlap_Probability + 0.3 * Noise_Level + 0.2 * Speaker_Score`.
    *   It assigns a complexity mode:
        *   **Mode A (Clean Scene)**: Score below 0.25 (1 speaker, low noise, sequential turn-taking).
        *   **Mode B (Moderate Interference)**: Score 0.25 to 0.55 (2 speakers, mild noise, minor overlaps).
        *   **Mode C (High Interference / Heavy Noise)**: Score 0.55 and above (3+ speakers, heavy noise, or critical overlap). Hard rules immediately force Mode C if the noise level exceeds 0.8, the overlap probability exceeds 0.7, or 3+ speakers are present.

---

## Setup and Installation

### 1. Prerequisites

The pipeline requires Python 3.8 or higher. You must install system-level audio dependencies.

On macOS (using Homebrew):
```bash
brew install portaudio
```

On Linux (Debian/Ubuntu):
```bash
sudo apt-get install portaudio19-dev python3-pyaudio
```

### 2. Virtual Environment Setup

Create and activate a virtual environment, then install the dependencies listed in `requirements_canary.txt`:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements_canary.txt
```

---

## How to Run

To run the pipeline in interactive recording mode:

```bash
python run_canary.py
```

### What happens during execution:
1. The script initializes the audio stream and prompts you to speak.
2. It records 7 seconds of audio from the default microphone and saves it as `raw_input.wav` in a timestamped subdirectory under `outputs/`.
3. It estimates the speaker count.
4. If multiple speakers are detected, it downloads the SpeechBrain SepFormer weights (if not already cached under `pretrained_models/`), separates the mixture, suppresses cross-talk, and saves individual files (`speaker_1.wav`, `speaker_2.wav`, etc.).
5. It runs the pre-screening quality checks. If passed, it loads Whisper and transcribes the audio to text, saving transcripts as `.txt` files.
6. It performs DRS shadow analysis and invokes the Context Engine.
7. The Context Engine evaluates wake words and intents, prints a structured ASCII summary to the terminal, and saves `context.json`.

---

## Output Specifications

Each execution generates a dedicated, timestamped folder under `outputs/YYYYMMDD_HHMMSS/`:

```
outputs/20260609_101530/
├── raw_input.wav       # Original recording before any processing
├── speaker_1.wav       # Enhanced audio stream for Speaker 1 (Dominant)
├── speaker_1.txt       # ASR Transcript and quality gate metadata for Speaker 1
├── speaker_2.wav       # Enhanced audio stream for Speaker 2 (if detected)
├── speaker_2.txt       # ASR Transcript and quality gate metadata for Speaker 2
└── context.json        # Compiled system state, metrics, and routing decision
```

### Transcript Text File Format

A speaker `.txt` file contains structured metadata followed by the transcript and segments:

```
[Language: en]
[Status: ✓  READY — meaningful speech detected]
[RMS: -18.0 dBFS | Speech ratio: 82%]

Hey Canary turn on the living room lights.

--- Segments ---
[0.00s → 4.50s] Hey Canary turn on the living room lights.
```

If a stream is rejected during pre-screening or post-transcription, the `.txt` file details the rejection reason:

```
[Status: ✗  REJECTED — failed pre-screening (insufficient speech)]
[Detail: Speech ratio 4% < 15% — mostly residual noise/artifacts]
[RMS: -42.1 dBFS | Speech ratio: 4%]

(stream flagged as noise — Whisper not invoked)
```

### Structured Context (context.json)

The `context.json` file contains the complete system context. Below is an example payload representing a multi-speaker command conflict:

```json
{
  "timestamp": "2026-06-09T10:15:35.123456",
  "session_dir": "outputs/20260609_101530",
  "drs_mode": "C",
  "scene": {
    "speaker_count": 2,
    "complexity": 0.612,
    "noise_level": 0.380,
    "simul_speech": 0.450
  },
  "speakers": [
    {
      "id": "speaker_1",
      "status": "READY",
      "transcript": "Hey Canary play some music",
      "wakeword": true,
      "wakeword_confidence": 1.0,
      "wakeword_phrase": "hey canary",
      "type": "COMMAND",
      "type_confidence": 0.95
    },
    {
      "id": "speaker_2",
      "status": "READY",
      "transcript": "Okay Canary stop the music",
      "wakeword": true,
      "wakeword_confidence": 1.0,
      "wakeword_phrase": "okay canary",
      "type": "COMMAND",
      "type_confidence": 0.95
    }
  ],
  "wakeword_count": 2,
  "command_count": 2,
  "conflict": true,
  "conflict_pair": [
    "play",
    "stop"
  ],
  "route": "CLARIFY"
}
```

---

## Routing Decision Logic

The routing engine routes commands based on the presence of the wake word, command classification, and conflicting instructions:

| Wake Word Command Count | Conflict Detected | Routing Result | System Behavior |
| :--- | :--- | :--- | :--- |
| 0 | No | `IGNORE` | All speech is classified as ambient conversation or noise. No actions are taken. |
| 1 | No | `EXECUTE` | A single speaker issued a command. The command is passed to execution. |
| >= 2 | Yes | `CLARIFY` | Opposing commands were issued (e.g. play versus stop) or an attention override was spoken. The system prompts for clarification. |
| >= 2 | No | `MULTI_EXECUTE` | Multiple speakers issued compatible, non-conflicting commands. The system executes them in sequence. |
