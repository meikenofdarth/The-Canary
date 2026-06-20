# The Canary - Speaker Separation, Denoising, and Intent Routing Pipeline

This project is a multi-speaker audio intelligence pipeline designed for smart assistants operating in noisy, dynamic environments. It captures audio, suppresses background noise, estimates the speaker count, separates individual voices, transcribes them using speech-to-text, evaluates scene complexity, and routes commands based on speaker intents and potential conflicts.

The entire documentation suite (including README.md, plan.md, and implementation.md) has been designed with clean structure and no emojis for readability by both human developers and Large Language Models (LLMs).

---

## What We Did (Key Optimizations)

To adapt the assistant pipeline to noisy household environments, the following optimizations were implemented:

1. Stop-on-Silence Recording
- Problem: The original implementation recorded for a fixed duration, capturing unnecessary silence or room noise.
- Solution: Integrated a dynamic recording mechanism using Silero Voice Activity Detection (VAD). It streams microphone audio and automatically stops recording after 1.8 seconds of silence once speech is detected, or at a maximum duration of 15 seconds.

2. Whisper Tiny Integration
- Problem: The default model (Whisper base) was slow on local CPUs.
- Solution: Transitioned ASR transcription to the Whisper tiny configuration, significantly speeding up transcription time while maintaining high accuracy for commands.

3. Speech-Band Filtering for 3-Speaker Mode
- Problem: Evaluating 3-speaker mixtures often created ghost streams containing only artifacts.
- Solution: Modified the 3-speaker mode to run the high-accuracy 2-speaker ConvTasNet (Libri2Mix) model internally. It filters output streams based on their speech-band RMS energy (300 Hz to 3400 Hz), discarding streams that fall below 25% of the loudest stream. If only one real speaker stream remains, the pipeline automatically down-routes to the single-speaker path.

4. Voiced Segment Extraction for Voice ID
- Problem: Running similarity matching on entire files contaminated voice profiles with silent gaps and room noise.
- Solution: Added a voiced segment extraction helper in the ranking module. It computes RMS energy of 30ms frames, estimates a local noise floor (10th percentile), and keeps only active speech frames (RMS greater than noise_floor * 2.5). These frames are concatenated together before performing speaker feature and embedding comparison.

5. Rejection Gating and Scaling Relaxation
- Problem: Valid speakers were frequently marked as UNKNOWN due to quality-based gates or confidence score compression.
- Solution: Disabled the quality rejection gates (speech ratio, SI-SNR, and RMS limits) in the voice ranker. The quality score scaling multiplier is fixed to 1.0, ensuring that raw match confidence is preserved. Diagnostic data (q_info) continues to be calculated and saved for shadow analysis.

6. Permissive Decision Thresholds
- Problem: Noise and separation artifacts compressed similarity scores, leading to false rejections.
- Solution: Lowered the multi-speaker decision confidence floor to 0.05. This allows the system to identify enrolled users under low signal-to-noise ratios.

7. Expanded DRS Mode B Range
- Problem: The Dynamic Resource Scaler (DRS) frequently flipped between Mode A and Mode C, bypassing Mode B.
- Solution: Adjusted the heuristics so Mode C is only forced if overlap exceeds 0.90 AND noise level exceeds 0.40. Fallback complexity thresholds were updated to classify complexity scores below 0.70 as Mode B (Moderate Interference), allowing a smoother progression across all three modes.

8. Template Wake Word Configuration
- Problem: Users running the system without building the C++ custom wake word engine had config loading failures.
- Solution: Renamed the default template configuration in the root directory to default_wakeword_config.json. If a user runs the change_wakeword.py script, a new custom configuration is generated and placed in the wakeword/ subdirectory.

---

## Project Structure

The project is structured into three core modules, an orchestrating CLI entrypoint, and data directories:

```
The-Canary/
├── run_canary.py                # CLI entrypoint and pipeline orchestrator
├── requirements_canary.txt      # Project dependencies list
├── plan.md                      # Project plan and methods
├── implementation.md            # Technical implementation details
├── README.md                    # General overview and points completed
├── default_wakeword_config.json # Template phonetic lookup table for "canary"
├── separation-filtering/        # Core audio separation and DSP module
│   ├── __init__.py              # Module initialization
│   ├── denoiser.py              # Non-stationary spectral noise reduction
│   ├── speaker_counter.py       # Sliding-window clustering feature extractor
│   ├── separator.py             # ConvTasNet source separation wrapper
│   ├── metrics.py               # Audio metrics (SI-SNR, RMS, SNR, leakage)
│   └── pipeline.py              # Core orchestrator class
├── asr/                         # Speech-to-text module
│   ├── __init__.py              # Module initialization
│   └── transcribe.py            # Whisper wrapper with pre/post-transcription gates
├── context_engine/              # Context parsing and routing engine
│   ├── __init__.py              # Module initialization
│   ├── context_builder.py       # context.json generator and router
│   ├── wakeword_detector.py     # Phonetic fuzzy wake word detector
│   ├── utterance_analyzer.py    # Rules-based utterance classifier
│   └── conflict_detector.py     # Action-antonym command conflict detector
├── pretrained_models/           # Cache directory for model checkpoints (gitignored)
└── outputs/                     # Run outputs containing audio and context JSON (gitignored)
```

---

## Detailed Component Walkthrough

### 1. Separation and Filtering Core (separation-filtering/)

* Denoiser (denoiser.py): Wraps the noisereduce library. It estimates noise profiles dynamically and applies spectral gating under a non-stationary assumption. This removes environmental noises (such as fans, HVAC hum, and room reverb) while preserving speech. It automatically scales and caps signal peaks to 0.98 to prevent clipping.
* Speaker Count Estimator (speaker_counter.py): Slides a 500ms window (50% overlap) across the audio signal. It extracts a 6-dimensional acoustic feature vector (log energy, zero-crossing rate, spectral centroid, spectral bandwidth, spectral rolloff, log flatness) for each voiced frame. These features are standardized and clustered using a greedy agglomerative clustering method across multiple distance thresholds. The median number of clusters represents the estimated speaker count (1 to 3).
* Speaker Separator (separator.py): Integrates Asteroid's pretrained ConvTasNet model (JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k, ~5.07M params). It runs at 16000 Hz, executes blind source separation, and pads/trims the separated streams to align with the original input duration. In 3-speaker mode, it automatically discards any stream whose speech-band RMS is less than 25% of the loudest stream to filter out neural artifacts (ghost speakers).
* Metrics (metrics.py): Provides evaluation algorithms:
    * SI-SNR (Scale-Invariant Signal-to-Noise Ratio): Evaluates separation quality.
    * SNR: Computes classical Signal-to-Noise Ratio.
    * RMS DB: Computes Root Mean Square amplitude in dBFS.
    * Self-SI-SNR: Computes cross-talk leakage by checking each separated stream against the sum of all other streams.
    * Denoising Gain: Reports overall RMS change and high-frequency noise floor reduction.

### 2. Speech-to-Text (asr/)

* Transcription Engine (transcribe.py): Integrates OpenAI's Whisper speech-to-text model (defaulting to the tiny model). To ensure high-quality transcripts and avoid processing noise, it implements two gating mechanisms:
    * Pre-Screening Gate: Checks audio before running Whisper. It rejects streams if the overall RMS energy is below -52 dBFS (silent stream) or if the voiced frame ratio is less than 15% (energy-based Voice Activity Detection).
    * Post-Transcription Quality Gate: Analyzes Whisper outputs. It rejects transcripts if the average segment log probability (avg_logprob) is below -1.2 (gibberish/noise), if the transcript exhibits repetitive patterns, or if the text compression ratio exceeds 2.8 for long strings (Whisper hallucination loops).
    * Streams that fail these gates are marked as REJECTED in their metadata, and their transcripts are discarded. Streams that pass are flagged as READY.

### 3. Context Engine (context_engine/)

* Wake Word Detector (wakeword_detector.py): Performs string-matching against standard wake words (such as "Canary", "Hey Canary", "Hello Canary"). To compensate for phonetic errors in transcription, it incorporates a fuzzy mapping table of over 40 common Whisper mis-transcriptions (like "cannery", "qanary", "anari", "canarie", "canary's") with predefined confidence weights (0.55 to 0.80).
* Utterance Analyzer (utterance_analyzer.py): A rules-based regex classifier mapping sentences across 15 smart home domains (Media, Lighting, Climate, Security, Appliances, Entertainment, Communication, Shopping, Timers, Navigation, Routines, Search/Information, Volume, Open/Close, Health). It classifies utterances into:
    * COMMAND: An imperative request directed at the assistant.
    * QUESTION: An interrogative request.
    * CONVERSATION: Social or ambient speech not addressed to the assistant.
    * UNKNOWN: Too short or ambiguous to classify.
* Conflict Detector (conflict_detector.py): Scans commands from different speakers to check for conflicts. A conflict is identified if the action verbs used are antonyms (such as "play" versus "stop", "turn on" versus "turn off", "open" versus "close", "warmer" versus "cooler"). It also checks for override command phrases where one speaker tells the assistant to redirect attention (e.g., "listen to me", "ignore him", "focus on me"), resulting in an intentional override conflict.
* Context Builder (context_builder.py): Aggregates transcripts, wake word indicators, and intent categories into a unified JSON structure. It applies routing rules based on the active command counts and conflict flags to produce a system routing decision.

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

Create and activate a virtual environment, then install the dependencies listed in requirements_canary.txt:

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
2. It records microphone audio until a 1.8-second silence timeout is hit, saving the buffer as raw_input.wav in a timestamped subdirectory under outputs/.
3. It estimates the speaker count.
4. If multiple speakers are detected, it separates the mixture using ConvTasNet, suppresses cross-talk, and saves individual files (speaker_1.wav, speaker_2.wav, etc.).
5. It runs the pre-screening quality checks. If passed, it loads Whisper and transcribes the audio to text, saving transcripts as .txt files.
6. It performs DRS shadow analysis and invokes the Context Engine.
7. The Context Engine evaluates wake words and intents, prints a structured ASCII summary to the terminal, and saves context.json.

---

## Output Specifications

Each execution generates a dedicated, timestamped folder under outputs/YYYYMMDD_HHMMSS/:

```
outputs/20260609_101530/
├── raw_input.wav       # Original recording before any processing
├── speaker_1.wav       # Enhanced audio stream for Speaker 1 (Dominant)
├── speaker_1.txt       # ASR Transcript and quality gate metadata for Speaker 1
├── speaker_2.wav       # Enhanced audio stream for Speaker 2 (if detected)
├── speaker_2.txt       # ASR Transcript and quality gate metadata for Speaker 2
└── context.json        # Compiled system state, metrics, and routing decision
```

---

## Routing Decision Logic

The routing engine routes commands based on the presence of the wake word, command classification, and conflicting instructions:

| Wake Word Command Count | Conflict Detected | Routing Result | System Behavior |
| :--- | :--- | :--- | :--- |
| 0 | No | IGNORE | All speech is classified as ambient conversation or noise. No actions are taken. |
| 1 | No | EXECUTE | A single speaker issued a command. The command is passed to execution. |
| >= 2 | Yes | CLARIFY | Opposing commands were issued (e.g. play versus stop) or an attention override was spoken. The system prompts for clarification. |
| >= 2 | No | MULTI_EXECUTE | Multiple speakers issued compatible, non-conflicting commands. The system executes them in sequence. |
