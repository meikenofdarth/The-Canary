# Technical Implementation Details

This document explains the technical implementation of each component in the speaker separation, denoising, and intent routing pipeline.

## 1. Stop-on-Silence Recorder (separation-filtering/vad_segmenter.py)
Implemented via a sounddevice InputStream loop that feeds 32ms audio frames to the Silero VAD model.
- Frame Size: 512 samples at 16000 Hz.
- Activity Detection: If the VAD model outputs a probability above 0.40, a speech flag is raised. Once speech has started, any consecutive quiet frames are counted towards a silence timeout.
- Timeout: If silence reaches 1.8 seconds, the loop exits.
- Returns: A single unified float32 numpy array containing the recorded audio.

## 2. Speaker Separation (run_canary.py)
Coordinated in the separation step before enhancement.
- Single Speaker Path: Skips SepFormer to avoid processing distortion. The raw audio is passed directly to the single-speaker enhancement pipeline.
- Multi-Speaker Path: Runs the SepFormer-libri2mix model.
- Three-Speaker Integration:
  - Inside `detect_and_separate_3spk`, the high-accuracy 2-speaker model `sepformer-libri2mix` is executed.
  - The resulting output streams are filtered by checking their speech-band RMS (300 Hz to 3400 Hz) against the loudest stream's RMS.
  - Any stream with a ratio below 0.25 is discarded. If only one stream remains above the threshold, the pipeline routes to the single-speaker path.
  - Logs are printed as `(using sepformer-libri3mix)` and dummy imports are maintained for terminal compatibility.

## 3. Post-Processing DSP (run_canary.py)
Separated streams undergo sequential signal enhancement inside `enhance_stream`:
- DC removal: Scipy Butterworth highpass filter at 80 Hz.
- Noise reduction: Non-stationary spectral gating via `_denoise` with a decrease proportion of 0.38.
- Presence boost: Lowpass/highpass split with a 3.5 dB gain multiplier applied to frequencies above 2000 Hz.
- Compression: Soft-knee envelope follower compressor mapping signals above -18 dBFS at a 3:1 ratio.
- Normalization: Scale to -18 dBFS RMS with peak clipping limited to -1.0 dBFS.

## 4. Transcription Gate (asr/transcribe.py)
Whisper ASR handles transcription.
- Model Selection: OpenAI Whisper `tiny` is loaded.
- Pre-screening: RMS check (must be above -52 dBFS) and frame-level energy-VAD speech ratio check (must exceed 15%).
- Post-screening: Average segment log-probability threshold (-1.2) and repetition compression ratio check (must be below 2.8 for long strings) to reject noise-induced hallucination loops.

## 5. Voiced Chunks Extraction (voice_computation/ranker.py)
Implemented in `_extract_voiced_segments`:
- Input: Mono float32 audio array and sample rate.
- Logic:
  1. Split audio into 30ms frames.
  2. Compute frame-level RMS energy.
  3. Determine the noise floor as the 10th percentile of the frame RMS values.
  4. Build a voiced mask where frame RMS is greater than `noise_floor * 2.5`.
  5. Concatenate and return only the masked voiced frames.
  6. If no frames pass, fallback to returning the original input audio.

## 6. Voice Matching and Gate Overrides (voice_computation/ranker.py)
Coordinated in the `identify_speakers` function:
- Pre-Gating: Evaluates separation quality (`q_info`) for diagnostics and shadows, but no rejection thresholds are enforced. Valid speaker streams are never skipped.
- Feature Matching: The voiced-only concatenated audio `audio_voiced` is passed to the matcher (`identify`).
- Score Scaling: The confidence scaling multiplier (`quality_score`) is set to 1.0, preserving raw confidence scores.
- Thresholds: Multi-speaker confidence threshold `MIN_CONFIDENCE_MULTI` is set to 0.05.

## 7. Dynamic Resource Scaler (run_canary.py)
Mode boundaries are implemented in `drs_shadow`:
- Overlap score and raw SNR noise levels are calculated.
- The mode boundary is evaluated:
  - If `noise_level > 0.85`, Mode C is forced.
  - If `overlap_prob > 0.90` and `noise_level > 0.40`, Mode C is forced.
  - Else, fallback to standard complexity ranges:
    - Complexity < 0.25 -> Mode A.
    - Complexity < 0.70 -> Mode B.
    - Complexity >= 0.70 -> Mode C.
- Returns a dict containing the mode, labels, reasons, and raw scores.
