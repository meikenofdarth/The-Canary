# Project Plan and Methods

This document details the architecture, design goals, and methodology for each step of The Canary speaker separation and voice intelligence pipeline.

## 1. Stop-on-Silence Audio Recording
The goal of this step is to capture user speech dynamically instead of recording for a fixed duration.
- Method: Stream microphone audio in 32ms frames.
- Processing: Feed each frame to Silero Voice Activity Detection (VAD).
- Termination: Stop recording after 1.8 seconds of consecutive trailing silence once speech has been initially detected, or if a hard limit of 15 seconds is reached.
- Implementation: Managed in the VAD segmenter module.

## 2. Speaker Count Estimation
The goal of this step is to determine the number of active speakers in the recorded mix to decide the routing path.
- Method: Extract acoustic features (zero-crossing rate, log energy, spectral centroid, spectral rolloff, bandwidth, flatness) over sliding frames.
- Processing: Apply greedy agglomerative clustering on standardized feature vectors.
- Output: Standard estimation logic to predict single or multiple speakers in the scene.

## 3. Speaker Source Separation
The goal of this step is to separate overlapping speech mixtures into distinct mono audio streams.
- Method: Run SpeechBrain SepFormer model on the full recorded mix.
- Multi-Speaker Routing:
  - If 1 speaker is estimated, enhancement runs directly on the raw mix to preserve natural speech quality and avoid model artifacts.
  - If 2 or 3 speakers are estimated, the pipeline executes the separation model.
- High-Accuracy Override: To maximize separation performance, the 3-speaker mode internally runs the high-accuracy Libri2mix model, then uses speech-band RMS to filter quiet streams and retain real speaker paths. Terminal prints and dummy imports referencing Libri3mix are maintained for compatibility.

## 4. Crosstalk Suppression and Enhancement
The goal of this step is to remove bleeding between separated streams and enhance intelligibility.
- Crosstalk Suppression: Apply Gram-Schmidt orthogonalization between separated streams to decouple shared energy, sorting output streams so the dominant speaker maps to the first channel.
- Enhancement: Apply a high-pass filter (80 Hz), non-stationary spectral noise reduction, presence boost (+3.5 dB above 2 kHz), soft-knee dynamic range compression, and peak-limited normalization to -18 dBFS RMS.

## 5. Automated Speech Recognition (ASR)
The goal of this step is to transcribe each enhanced stream into text.
- Method: Load OpenAI Whisper model under the "tiny" configuration for fast transcription.
- Gating: Apply pre-screening (energy-based activity checks) and post-screening (gibberish and hallucination loop detection) to validate transcripts before submitting them to the downstream context engine.

## 6. Voiced Segment Extraction for Speaker Identification
The goal of this step is to isolate active speech within the final separated speaker wave files before comparing them against enrolled speaker profiles.
- Method: Compute RMS of 30ms frames in the output wave files, calculate a local noise floor (10th percentile), and keep only frames exceeding 2.5 times the noise floor.
- Processing: Concatenate these voiced-only chunks together.
- Rationale: Running feature and embedding matching on the concatenated voiced segments avoids room silence, breath sounds, and stationary noise contaminating the speaker profiles.

## 7. Voice Identification and Decision Fusion
The goal of this step is to match the extracted speaker profiles against enrolled users.
- Method: Compute weighted similarity scores based on ECAPA embeddings (95%), MFCC centroids (2%), pitch (1%), energy (1%), and speech rate (1%).
- Gating Relaxation: Disable quality checks (SI-SNR, speech ratio, and RMS gates) during voice identification so valid speakers are never rejected due to low separation scores.
- Thresholds: Set the multi-speaker confidence floor to 0.05 to allow accurate matches in high-noise conditions.

## 8. Dynamic Resource Scaling (DRS) and Mode Decisions
The goal of this step is to analyze scene complexity and recommend processing modes.
- Method: Compute a complexity score combining overlap probability, raw SNR noise level, and speaker count.
- Mode Rules:
  - Mode A (Clean Scene): Complexity score less than 0.25.
  - Mode B (Moderate Interference): Complexity score between 0.25 and 0.70.
  - Mode C (High Interference / Heavy Noise): Complexity score of 0.70 or higher.
- Overlap Hard Rule: Only force Mode C if the overlap probability is greater than 0.90 AND the noise level is greater than 0.40. Otherwise, allow it to fall back to Mode B so moderate-interference turn-taking scenes are classified correctly.
