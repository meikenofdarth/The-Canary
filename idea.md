# The Canary Idea Notes

This file is the working map for the current state of the repository, with a focus on the `Voice-Computation` stack and the handoff into the broader `src/` pipeline.

It records:
- What each major file does
- How the audio pipeline moves from mic input to routed output
- The thresholds and metrics used at each step
- The separation fallback we added for overlapping speech
- The actual verification results we observed on recordings
- The limitations that still remain

## Big Picture

The Canary is a multi-stage voice pipeline that tries to answer one question very quickly and consistently:

**Is this speech worth routing, and if so, how heavy should the downstream processing be?**

The acoustic side is responsible for:
- Capturing audio
- Detecting speech
- Detecting the wake word
- Estimating scene complexity
- Estimating speaker count and overlap
- Cleaning audio
- Producing final audio artifacts and metadata

The downstream side in `src/` is responsible for:
- ASR
- Speaker verification
- Arbitration
- Command execution
- Session/state management

The handoff between the two is `ScalerDecision` in `Voice-Computation/models.py` and `PipelineOutput` in `src/common/models.py`.

## Current Routing Policy

Final thresholds now used by the acoustic routing layer:

- `MODE_A` if `SCS < 0.22`
- `MODE_B` if `0.22 <= SCS < 0.40`
- `MODE_C` if `SCS >= 0.40`

Interpretation:
- Mode A: clean single-speaker input
- Mode B: noisy but still mostly single-speaker input
- Mode C: heavy overlap or noisy enough that a separation path is useful

## Why Noise Floor Is Negative

`noise_floor_db` is now treated as `dBFS`, which means decibels relative to digital full scale.

That scale works like this:
- `0 dBFS` = maximum possible digital amplitude, basically clipping
- Negative values = below full scale, which is normal

So:
- `-67.9 dBFS` means very quiet background
- `-24 dBFS` means loud background or music
- `-17 dBFS` means very loud background

This is not a bug. It is the correct scale for digital audio.

## Acoustic Pipeline

### 1. `Voice-Computation/audio/capture.py`

Responsibilities:
- Capture microphone input with `sounddevice`
- Maintain a ring buffer
- Support direct file loading through `FileAudioSource`

Key behavior:
- Mic captures mono, 16 kHz audio
- The ring buffer stores rolling audio so the pipeline can request windows
- File input is resampled to 16 kHz if needed

### 2. `Voice-Computation/audio/ring_buffer.py`

Responsibilities:
- Thread-safe storage of captured audio
- Return the most recent chunk or full available audio

This is the bridge between the PortAudio callback and the processing pipeline.

### 3. `Voice-Computation/vad/silero_vad.py`

Responsibilities:
- Run Silero VAD through ONNX Runtime
- Apply energy pre-gating
- Smooth probabilities
- Apply spike suppression
- Track speech boundary state

Important implementation details:
- We fixed the ONNX wrapper to include the 64-sample context required by the model
- We now pass a scalar sample rate tensor as expected
- `process_audio()` scans an entire utterance from a clean temporary state, then restores the streaming state
- Noise floor is estimated from the quietest frames and returned as dBFS

Important metrics:
- `vad_threshold = 0.5`
- `vad_energy_threshold = 0.003`
- `vad_consecutive_required = 2`
- `vad_min_speech_ms = 250`
- `vad_min_silence_ms = 300`

What this means:
- Speech is not accepted on one noisy spike
- Very quiet frames are skipped early
- Long utterances are scored by max speech probability and speech fraction

### 4. `Voice-Computation/wakeword/detector.py`

Responsibilities:
- Transcribe audio through STT
- Search transcript for wake-word variants
- Debounce wake detections

Wake-word variants considered:
- `canary`
- `hey canary`
- `ok canary`
- `hi canary`
- `hello canary`

Wake-word confidence policy:
- Full keyword variants score `1.0`
- Bare `canary` scores `0.9`
- Confidence must meet `wakeword_threshold`

Fallback behavior:
- If STT is unavailable, acoustic fallback can still allow VAD-based activation when configured

### 5. `Voice-Computation/preprocessing/normalizer.py`

Responsibilities:
- Remove DC offset
- Apply optional soft-limiting on clipped input
- Add tiny dither
- Apply pre-emphasis
- RMS-normalize audio
- Estimate SNR

Why this matters:
- Wake-word and routing both depend on consistent amplitude behavior
- Pre-emphasis helps speech features but can exaggerate harmonics, which is why speaker analysis is done on a raw DC-centered waveform instead of the pre-emphasized waveform

### 6. `Voice-Computation/preprocessing/noise_estimator.py`

Responsibilities:
- Estimate background noise spectrum from non-speech audio
- Perform spectral subtraction

The noise estimator is used as a denoising aid, not as the source of the final routing decision.

### 7. `Voice-Computation/preprocessing/features.py`

Responsibilities:
- Compute mel spectrogram
- Compute MFCCs
- Compute energy
- Compute ZCR
- Compute spectral centroid
- Compute spectral flatness
- Compute spectral rolloff
- Estimate pitch

This file is the core feature source for scene analysis.

### 8. `Voice-Computation/scene/analyzer.py`

Responsibilities:
- Compute scene complexity score
- Estimate speaker count
- Estimate overlap probability
- Normalize noise
- Determine whether speech is directed

Current SCS weighting:
- `overlap`: `0.35`
- `noise`: `0.50`
- `wakeword`: `0.15`

Why the weights changed:
- Acoustic conditions should dominate routing
- Wake-word confidence should not artificially make a scene look “complex”

What happens now:
- Speaker count and overlap can be supplied directly by the dedicated acoustic analyzer
- If present, those values take precedence over older heuristics

### 9. `Voice-Computation/separation/speaker_analyzer.py`

This is the new dedicated speaker-analysis module.

Responsibilities:
- Look at pitch candidates
- Look at frame intensity in dBFS
- Look at frequency centroid
- Estimate overlap density
- Build speaker profiles

What it produces:
- `estimated_speaker_count`
- `profiles`
- `active_frame_ratio`
- `multi_pitch_frame_ratio`
- `overlap_probability`
- `mean_intensity_dbfs`
- `spectral_centroid_hz`

Design notes:
- It is a fallback acoustic analysis module, not a biometric speaker ID system
- It rejects likely octave/harmonic duplicates so one speaker does not become two fake speakers
- It needs a minimum amount of active evidence before it claims a second speaker

Thresholds:
- `speaker_frame_rms_threshold = 0.004`
- `speaker_min_profile_frames = 8`
- `speaker_pitch_min_hz = 75`
- `speaker_pitch_max_hz = 420`
- `speaker_pitch_cluster_min_gap_hz = 42`
- `speaker_multi_pitch_ratio_threshold = 0.55`

### 10. `Voice-Computation/separation/spectral_separator.py`

This is the local separation fallback.

Responsibilities:
- Perform STFT-based noise gating
- Build pitch-guided soft masks
- Export one processed mix and optional per-speaker stems

What it does:
- `processed_audio`: cleaned output mix
- `speaker_streams`: separated stems when analysis supports at least two speakers
- `method`: currently `pitch-guided-soft-mask`

Important limitation:
- This is not a trained TIGER model
- It is a practical local fallback that gives useful diagnostic stems
- Strong overlap still means imperfect separation

Verification result:
- Synthetic two-voice audio produced 2 stems
- Noisy overlap recording produced 2 stems
- Clean speech recordings were suppressed back to 1 speaker with no stems

### 11. `Voice-Computation/scaler/resource_scaler.py`

Responsibilities:
- Convert scene analysis into mode A/B/C
- Apply mode-specific DSP
- Package the final `ScalerDecision`

Mode logic:
- Mode A: high-pass + peak normalize
- Mode B: 4-band Wiener filtering + peak normalize
- Mode C: use the processed separation fallback mix if available, then peak normalize

What gets carried into `ScalerDecision` now:
- Final audio
- VAD confidence
- Wake-word confidence
- Scene complexity score
- Estimated speaker count
- Overlap probability
- Noise floor
- SNR estimate
- Whether speech is directed
- Mel spectrogram
- Energy profile
- Separated audio stems
- Separation method
- Speaker profile metadata

### 12. `Voice-Computation/pipeline.py`

Responsibilities:
- Orchestrate the whole acoustic pipeline
- Manage the wake-word override path
- Apply normalization and denoising
- Run feature extraction
- Run speaker analysis and local separation
- Run scene analysis
- Run the resource scaler

Important flow:
1. VAD on raw audio
2. Wake-word check
3. Normalize audio
4. Denoise if noise estimate exists
5. Extract features
6. Analyze speakers on raw DC-centered waveform
7. Produce local separated stems if needed
8. Compute scene complexity
9. Build final scaled output

Why speaker analysis uses the raw DC-centered waveform:
- Pre-emphasis boosted harmonics enough to create fake multi-speaker evidence
- Using the raw centered waveform makes speaker counting more stable

### 13. `Voice-Computation/bridge.py`

Responsibilities:
- Convert `ScalerDecision` into `PipelineOutput`
- Bridge the acoustic side to the `src/` side

Current behavior:
- Mode A and B become one stream named `unknown`
- Mode C becomes:
  - local fallback streams if `decision.separated_audio` exists
  - otherwise a single mixed stream named `mixed`

This keeps the handoff compatible with a future trained TIGER implementation.

### 14. `Voice-Computation/demo.py`

Responsibilities:
- Provide CLI demo for mic or file input
- Print the human-readable result
- Save artifacts to disk

Saved artifacts now include:
- Raw `.wav`
- Processed `.wav`
- Optional `speaker_1.wav`, `speaker_2.wav`, etc.
- `.json` metadata
- `.txt` transcript
- `.pkl` decision object

The JSON metadata includes:
- `mode`
- `vad_confidence`
- `wakeword_confidence`
- `scene_complexity_score`
- `estimated_speaker_count`
- `overlap_probability`
- `noise_floor_db`
- `snr_estimate_db`
- `is_directed_speech`
- `separation_method`
- `separated_stream_count`
- `speaker_profiles`
- `processed_audio_files`
- `speech_detected`
- `speech_detection_source`

### 15. `Voice-Computation/models.py`

Responsibilities:
- Define the contracts between modules

Important dataclasses:
- `VADResult`
- `WakeWordResult`
- `PreProcessedAudio`
- `AudioFeatures`
- `SceneAnalysis`
- `ScalerDecision`

New fields added to `ScalerDecision`:
- `separated_audio`
- `separation_method`
- `speaker_profiles`

## File Map

### Voice-Computation

- [Voice-Computation/config.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/config.py)
- [Voice-Computation/models.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/models.py)
- [Voice-Computation/pipeline.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/pipeline.py)
- [Voice-Computation/scene/analyzer.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/scene/analyzer.py)
- [Voice-Computation/scaler/resource_scaler.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/scaler/resource_scaler.py)
- [Voice-Computation/vad/silero_vad.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/vad/silero_vad.py)
- [Voice-Computation/wakeword/detector.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/wakeword/detector.py)
- [Voice-Computation/preprocessing/normalizer.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/preprocessing/normalizer.py)
- [Voice-Computation/preprocessing/noise_estimator.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/preprocessing/noise_estimator.py)
- [Voice-Computation/preprocessing/features.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/preprocessing/features.py)
- [Voice-Computation/audio/capture.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/audio/capture.py)
- [Voice-Computation/audio/ring_buffer.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/audio/ring_buffer.py)
- [Voice-Computation/demo.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/demo.py)
- [Voice-Computation/bridge.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/bridge.py)
- [Voice-Computation/separation/speaker_analyzer.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/separation/speaker_analyzer.py)
- [Voice-Computation/separation/spectral_separator.py](/Users/knight_striker/Desktop/The-Canary/Voice-Computation/separation/spectral_separator.py)

### src

- `src/common/models.py`: shared contracts for `PipelineOutput`, `AudioStream`, `TranscriptionResult`, `ArbitrationDecision`
- `src/common/config.py`: runtime config for the downstream pipeline
- `src/asr/engine.py`: ASR engine
- `src/arbitration/engine.py`: command arbitration
- `src/execution/queue.py`: execution queue
- `src/execution/state_store.py`: stored roles and state
- `src/execution/speaker_index.py`: speaker embedding index
- `src/pipeline.py`: top-level downstream pipeline
- `src/mock_pipeline.py`: mock integration path
- `src/demo/full_demo.py`: end-to-end demo
- `src/demo/ui.py`: UI helpers
- `src/agent/*`: agent and MCP logic

## Verified Runs

### Wake-word sample

Input:
- `wake-word.mp3`

Result after fixes:
- VAD probability: `1.000`
- Speaker count: `1`
- Overlap probability: `0.000`
- Scene complexity: `0.000`
- Mode: `A`
- Noise floor: `-67.9 dBFS`

### Overlap sample

Input:
- `Voice-Computation/audio/recordings/recording_20260602_225640.wav`

Result:
- VAD probability: `1.000`
- Speaker count: `2`
- Overlap probability: `0.756`
- Scene complexity: `0.779`
- Mode: `C`
- Noise floor: `-17.3 dBFS`
- Separated stems exported: `2`
- Separation method: `pitch-guided-soft-mask`

Exported files:
- raw wav
- processed wav
- speaker 1 wav
- speaker 2 wav
- json metadata
- pkl decision
- txt transcript

### Synthetic separation test

We also tested synthetic dual-voice audio:
- estimated speaker count: `2`
- separated stems: `2`

That confirmed the analyzer and soft-mask separation path are wired together correctly.

## What We Learned

1. A raw Silero ONNX call without the required context produced near-zero VAD confidence.
2. Negative noise floor values are expected and meaningful on the dBFS scale.
3. Pre-emphasis can make a single voice look like two speakers if we analyze the wrong waveform.
4. A pitch-only heuristic can overcount harmonics unless octave relationships are rejected.
5. Audio recordings written in the same second need microsecond timestamps to avoid filename collisions.
6. Rereading a shared cache inside scene analysis can create stale metrics when runs happen close together.
7. Mono soft separation is useful, but it is not a replacement for a trained separation model.

## Limitations

- The local separation path is a fallback, not true source separation quality
- Strong overlap still benefits from a trained TIGER model
- Speaker profiles are acoustic clusters, not identity verification
- `pytest` is not installed in the current venv, so test discovery via pytest could not be run directly here

## Current Output Contract

The acoustic side now produces:
- a cleaned routed audio buffer
- optional per-speaker stems
- a final mode decision
- metadata rich enough for the downstream pipeline to consume or inspect

The downstream side receives:
- `PipelineOutput`
- one or more `AudioStream` objects
- speaker profile labels where available
- mixed-mode handoff when separation is not available

## Practical Summary

If the input is clean and one person is speaking:
- Mode A
- direct ASR path

If the input is noisy but basically one person:
- Mode B
- adaptive DSP path

If the input is loud, overlapped, or crowded:
- Mode C
- local separation fallback creates stems
- `PipelineOutput` carries the stems forward
- a trained TIGER stage can replace the fallback later

That is the current shape of the system.
