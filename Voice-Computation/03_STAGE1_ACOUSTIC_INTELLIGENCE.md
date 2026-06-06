# 03 — Stage 1: Acoustic Scene Intelligence
### The Canary | Pre-Processing → Feature Extraction → P_overlap · N_norm · U_speaker

> **Entry condition**: This module only receives chunks that passed Stage 0's gate (PASS=True).  
> **Exit contract**: Outputs `AcousticSceneOutput` (P_overlap, N_norm, U_speaker, + accumulated raw audio) — for the Dynamic Resource Scaler.

---

## 0. Why Stage 1 Fails When Rushed

The failure mode you hit when going directly to implementation was almost certainly this:

1. Raw 512-sample chunks arrived from Stage 0
2. You tried to estimate speaker count on each individual chunk
3. 512 samples = 32ms — not enough context for any reliable estimation
4. You got random, noisy outputs that looked like bugs but were actually an **insufficient analysis window** problem

The fix is the **accumulation window**. Stage 1 does not process 512-sample chunks directly. It accumulates chunks until it has a **1600-sample (100ms) window**, then extracts features from that window. The SCS is then computed over a **4800-sample (300ms) rolling average** of those features.

```
Stage 0 → Stage 1 boundary:
  Input:  one 512-sample chunk (32ms) → arrives every 32ms

Stage 1 internal:
  Accumulate → 1600-sample window → extract features every 100ms
  Rolling average → 4800 samples of features → SCS every 300ms

Stage 1 → DRS boundary:
  Output: (P_overlap, N_norm, U_speaker) + accumulated_audio → updated every 300ms
```

> **New requirement (Sanchit's contract)**: Stage 1 must also forward the **raw accumulated audio** (float32, 16kHz) alongside the feature scores so the DRS can include it in the `PipelineOutput` handed to Stage 2/3. Stage 1 does NOT separate audio — it just passes the mixed stream through.

---

## 1. Pre-Processor (`preprocessor.py`)

Every accumulated window goes through this before feature extraction. No changes from original design.

### Operations (in order):

1. **DC Offset Removal** — Mac M3 mic can have small DC bias
2. **High-Pass Filter (80 Hz)** — removes room rumble, fan noise, low-frequency thumps
3. **Normalisation to Target Loudness** — normalise each window to fixed RMS target (-23 LUFS approx)
4. **Pre-emphasis Filter** — `y[n] = x[n] - 0.97 * x[n-1]`, boosts high-frequency formants

```python
# stage1/preprocessor.py
import numpy as np
from scipy import signal
from dataclasses import dataclass


@dataclass
class ProcessedWindow:
    """Clean audio ready for feature extraction."""
    samples: np.ndarray      # float32, shape (1600,), range [-1, 1]
    rms_before: float        # RMS before normalisation (real speech energy)
    rms_after: float         # RMS after (always near target)
    clipping_detected: bool  # True if input was clipped (mic saturation)
    window_id: int


class AudioPreprocessor:
    """
    Stateless audio pre-processor.
    All operations are deterministic given the input.
    No model, no state, no GPU.
    """

    TARGET_RMS = 0.1
    PREEMPHASIS_COEFF = 0.97
    HIGHPASS_CUTOFF = 80
    HIGHPASS_ORDER = 4

    def __init__(self, config: dict):
        stage1_cfg = config['stage1']
        sample_rate  = config['audio']['sample_rate']
        cutoff       = stage1_cfg.get('highpass_cutoff_hz', 80)
        order        = stage1_cfg.get('highpass_order', 4)
        self._target_rms = 0.1

        sos = signal.butter(order, cutoff, btype='high',
                            fs=sample_rate, output='sos')
        self._sos = sos
        self._filter_zi = signal.sosfilt_zi(self._sos)
        self._filter_state_valid = False

    def process(self, samples: np.ndarray, window_id: int) -> ProcessedWindow:
        assert samples.shape == (1600,), f"Expected 1600 samples, got {samples.shape}"
        x = samples.copy()
        clipping = bool(np.any(np.abs(x) > 0.999))
        x -= np.mean(x)

        if self._filter_state_valid:
            x, self._filter_zi = signal.sosfilt(self._sos, x, zi=self._filter_zi)
        else:
            zi_init = self._filter_zi * x[0]
            x, self._filter_zi = signal.sosfilt(self._sos, x, zi=zi_init)
            self._filter_state_valid = True

        rms_before = float(np.sqrt(np.mean(x ** 2)) + 1e-10)
        x = x * (self._target_rms / rms_before)
        x = np.clip(x, -1.0, 1.0)
        rms_after = float(np.sqrt(np.mean(x ** 2)))
        x = signal.lfilter([1.0, -0.97], [1.0], x)

        return ProcessedWindow(
            samples=x.astype(np.float32),
            rms_before=rms_before,
            rms_after=rms_after,
            clipping_detected=clipping,
            window_id=window_id
        )
```

---

## 2. Feature Extractor (`feature_extractor.py`)

Five features computed per 100ms window. No neural model — all DSP.

### Feature 1: Zero-Crossing Rate (ZCR)
Variance of ZCR across sub-frames rises during overlap. Single speaker: low variance. Two speakers: high variance. White noise: very high but stable.

### Feature 2: Spectral Flatness (Wiener Entropy)
Ratio of geometric mean to arithmetic mean of power spectrum. Low (0–0.3) = clean speech. High (0.6–1.0) = heavy noise or heavy overlap.

### Feature 3: MFCC Temporal Delta Variance
Rate of change of MFCC features frame-to-frame. Single speaker: slow, smooth. Two speakers overlapping: rapid, jerky changes.

### Feature 4: Autocorrelation Consistency
Measures whether the pitch period is stable. Single speaker has stable pitch peak. Two speakers create competing pitch peaks → lower consistency.

### Feature 5: Energy Ratio (Speech Band / Total)
Speech energy concentrated in 300–3400 Hz. Noise spreads outside this band. High ratio = clean speech. Low ratio = noise contamination.

```python
# stage1/feature_extractor.py
# (Unchanged from original design — see previous version for full implementation)
# Key output dataclass:

from dataclasses import dataclass
import numpy as np

@dataclass
class AudioFeatures:
    """Five-feature vector extracted from one 1600-sample window."""
    zcr_mean: float
    zcr_variance: float
    spectral_flatness: float
    mfcc_delta_variance: float
    corr_consistency: float
    energy_ratio: float
    window_id: int
```

---

## 3. Acoustic Intelligence (`acoustic_intelligence.py`)

### ⚠️ UPDATED OUTPUT CONTRACT

`AcousticSceneOutput` now carries a `raw_audio` field — the unprocessed mixed audio accumulated over the analysis window. This is what gets passed through to the DRS and ultimately into `PipelineOutput.audio_streams[0].audio`.

**Why raw, not processed?** Stage 2 (TFPSNet, CAM++) must receive the original microphone signal, not the pre-emphasised, normalised version used for feature extraction. Those transformations are for feature quality, not for downstream models.

```python
# stage1/acoustic_intelligence.py
from dataclasses import dataclass
import numpy as np
from collections import deque
from .feature_extractor import AudioFeatures


@dataclass
class AcousticSceneOutput:
    """
    Output from Stage 1 — forwarded to the Dynamic Resource Scaler.
    
    *** NEW: raw_audio field carries the mixed microphone audio ***
    This is the unmodified (but Stage 0-gated) PCM that DRS will
    include in PipelineOutput for Sanchit's pipeline contract.
    """
    P_overlap: float           # Overlap probability [0, 1]
    N_norm: float              # Normalised noise level [0, 1]
    U_speaker: float           # Speaker uncertainty score [0, 1]
    speaker_count_estimate: int  # Rough heuristic (1, 2, or 3)
    window_id: int

    # *** NEW FIELD ***
    raw_audio: np.ndarray      # float32, 16kHz, mono — accumulated mixed audio
    #                            shape: (N,) where N = chunks since last SCS update
    #                            This is passed through unchanged to PipelineOutput


class AcousticIntelligence:
    """
    Converts AudioFeatures → (P_overlap, N_norm, U_speaker).
    Also accumulates raw audio from Stage 0 chunks for passthrough.
    """

    SCS_WINDOW_SIZE = 3   # Number of 100ms windows per SCS update (= 300ms)

    def __init__(self, config: dict):
        self._history: deque[AudioFeatures] = deque(maxlen=self.SCS_WINDOW_SIZE)
        # Raw audio accumulator: holds chunks until SCS update fires
        self._raw_audio_buffer: list[np.ndarray] = []

    def accumulate_raw_chunk(self, chunk: np.ndarray) -> None:
        """
        Called by Stage1Runner for EVERY 512-sample chunk received from Stage 0.
        Stores original PCM so it can be bundled into AcousticSceneOutput.
        """
        self._raw_audio_buffer.append(chunk.copy())

    def process(self, features: AudioFeatures) -> AcousticSceneOutput | None:
        """
        Add one feature window to the rolling buffer.
        Returns AcousticSceneOutput when the 300ms SCS window is full, else None.
        The raw_audio field contains all PCM accumulated since the last output.
        """
        self._history.append(features)

        if len(self._history) < self.SCS_WINDOW_SIZE:
            return None   # not enough context yet

        # --- Compute P_overlap ---
        zcr_var_mean     = np.mean([f.zcr_variance for f in self._history])
        mfcc_dv_mean     = np.mean([f.mfcc_delta_variance for f in self._history])
        corr_mean        = np.mean([f.corr_consistency for f in self._history])
        sf_mean          = np.mean([f.spectral_flatness for f in self._history])

        p_ov_raw = (0.30 * min(zcr_var_mean / 0.20, 1.0)
                  + 0.30 * min(mfcc_dv_mean / 0.50, 1.0)
                  + 0.40 * corr_mean)
        P_overlap = float(np.clip(p_ov_raw, 0.0, 1.0))

        # --- Compute N_norm ---
        energy_r_mean = np.mean([f.energy_ratio for f in self._history])
        N_norm_raw = (0.50 * sf_mean
                    + 0.50 * max(0.0, 1.0 - energy_r_mean))
        N_norm = float(np.clip(N_norm_raw, 0.0, 1.0))

        # --- Compute U_speaker ---
        U_speaker = float(np.clip(
            0.60 * corr_mean + 0.40 * min(mfcc_dv_mean / 0.50, 1.0),
            0.0, 1.0
        ))

        # --- Speaker count heuristic ---
        combined = 0.5 * P_overlap + 0.5 * U_speaker
        if combined < 0.25:   spk = 1
        elif combined < 0.55: spk = 2
        else:                  spk = 3

        # --- Flush raw audio buffer ---
        if self._raw_audio_buffer:
            raw = np.concatenate(self._raw_audio_buffer)
            self._raw_audio_buffer = []   # reset for next window
        else:
            raw = np.zeros(0, dtype=np.float32)

        return AcousticSceneOutput(
            P_overlap=P_overlap,
            N_norm=N_norm,
            U_speaker=U_speaker,
            speaker_count_estimate=spk,
            window_id=features.window_id,
            raw_audio=raw,
        )
```

---

## 4. Stage 1 Window Accumulator and Runner (`stage1_runner.py`)

### ⚠️ UPDATED: Raw audio must be routed to `accumulate_raw_chunk`

```python
# stage1/stage1_runner.py
import numpy as np
import queue
import threading
from .preprocessor import AudioPreprocessor
from .feature_extractor import FeatureExtractor
from .acoustic_intelligence import AcousticIntelligence


class Stage1Runner:
    WINDOW_SIZE = 1600
    CHUNK_SIZE  = 512

    def __init__(self, config, input_queue, output_queue):
        self._config = config
        self._in_q  = input_queue
        self._out_q = output_queue
        self._stop  = threading.Event()
        self._preprocessor = AudioPreprocessor(config)
        self._extractor    = FeatureExtractor(config)
        self._intelligence = AcousticIntelligence(config)
        self._buffer   = np.zeros(0, dtype=np.float32)
        self._window_id = 0
        self._last_three_bit = None

    def _processing_loop(self):
        print("[Stage1] Processing thread started.")
        while not self._stop.is_set():
            try:
                item = self._in_q.get(timeout=0.1)
            except queue.Empty:
                continue

            three_bit, chunk_audio = item
            self._last_three_bit = three_bit

            # *** Feed raw chunk to intelligence for passthrough accumulation ***
            self._intelligence.accumulate_raw_chunk(chunk_audio)

            self._buffer = np.concatenate([self._buffer, chunk_audio])

            while len(self._buffer) >= self.WINDOW_SIZE:
                window = self._buffer[:self.WINDOW_SIZE]
                self._buffer = self._buffer[self.WINDOW_SIZE:]
                self._process_window(window, three_bit)

    def _process_window(self, window, three_bit):
        processed = self._preprocessor.process(window, self._window_id)
        features  = self._extractor.extract(processed.samples, self._window_id)
        scene     = self._intelligence.process(features)

        if scene is None:
            self._window_id += 1
            return   # waiting for 300ms of context

        # Blend noise estimate from Stage 0 VAD
        blended_N = float(np.clip(0.5 * scene.N_norm + 0.5 * three_bit.Nf, 0, 1))

        from dataclasses import replace
        final = replace(scene,
                        N_norm=blended_N,
                        window_id=self._window_id,
                        # raw_audio already set by AcousticIntelligence.process()
                        )

        # Attach Stage 0 metadata for DRS (pass as tuple)
        payload = (final, three_bit)

        self._window_id += 1
        try:
            self._out_q.put_nowait(payload)
        except queue.Full:
            pass

    def start(self):
        self._thread = threading.Thread(target=self._processing_loop,
                                        name="Stage1-Thread", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
```

---

## 5. Feature Tuning: Expected Value Ranges

| Feature | Silence | Clean 1 Speaker | 2 Speakers Overlapping | TV/Background Noise |
|---------|---------|-----------------|----------------------|---------------------|
| ZCR Mean | < 0.05 | 0.05–0.15 | 0.08–0.20 | 0.30–0.80 |
| ZCR Variance | < 0.01 | 0.01–0.05 | 0.05–0.20 | 0.01–0.10 |
| Spectral Flatness | 0.05–0.15 | 0.10–0.35 | 0.25–0.55 | 0.50–0.90 |
| MFCC Δ Variance | < 0.10 | 0.10–0.25 | 0.30–0.60 | 0.15–0.40 |
| Corr Consistency | < 0.10 | 0.10–0.25 | 0.45–0.80 | 0.20–0.50 |
| Energy Ratio | ~0.20 | 0.20–0.50 | 0.30–0.70 | 0.30–0.60 |
| **P_overlap** | < 0.15 | < 0.25 | **> 0.50** | 0.30–0.55 |
| **N_norm** | < 0.10 | < 0.25 | 0.20–0.45 | **> 0.55** |
| **U_speaker** | < 0.15 | < 0.20 | **> 0.50** | 0.25–0.50 |

---

## 6. Testing Stage 1 in Isolation

Before connecting to Stage 0, test with pre-recorded audio files.

**Test audio to prepare (record with QuickTime or similar):**
- `test_silence_30s.wav` — 30 seconds of ambient quiet
- `test_single_speaker.wav` — 30 seconds of you talking normally
- `test_overlap.wav` — two overlapping voices (play from phone)
- `test_tv_noise.wav` — 30 seconds of TV audio

**Test procedure:**

```python
# scripts/test_stage1_offline.py
import numpy as np
import librosa
import yaml

with open("config/pipeline_config.yaml") as f:
    config = yaml.safe_load(f)

y, sr = librosa.load("test_single_speaker.wav", sr=16000, mono=True)

from stage1.preprocessor import AudioPreprocessor
from stage1.feature_extractor import FeatureExtractor
from stage1.acoustic_intelligence import AcousticIntelligence

prep  = AudioPreprocessor(config)
feat  = FeatureExtractor(config)
intel = AcousticIntelligence(config)

window_size = 1600

for i in range(0, len(y) - window_size, window_size):
    window = y[i:i+window_size].astype(np.float32)
    intel.accumulate_raw_chunk(window)    # ← must call this too
    p = prep.process(window, i)
    f = feat.extract(p.samples, i)
    s = intel.process(f)
    if s:
        print(f"Window {i//window_size:3d}: "
              f"P_ov={s.P_overlap:.3f} N={s.N_norm:.3f} U={s.U_speaker:.3f} "
              f"spk={s.speaker_count_estimate} "
              f"raw_audio_len={len(s.raw_audio)}")
```

> **Verify raw_audio**: `len(s.raw_audio)` should equal approximately `3 × WINDOW_SIZE = 4800` samples (300ms). It may vary slightly near boundaries.

---

*Next → Read `04_DYNAMIC_RESOURCE_SCALER.md`*