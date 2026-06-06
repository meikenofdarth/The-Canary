# 04 — Dynamic Resource Scaler
### The Canary | SCS Formula → Mode A / B / C → PipelineOutput JSON

> **Entry condition**: Receives `(AcousticSceneOutput, ThreeBitWord)` tuple from Stage 1.  
> **Exit contract**: Emits a `PipelineOutput` object — serialised to `.json` — conforming to Sanchit's pipeline contract. This is the handoff point between your pipeline and the ASR / Arbitration backend.

---

## 0. What the Dynamic Resource Scaler Is (And Is Not)

The DRS is NOT a neural network. It is NOT a classifier. It is a **deterministic function** with six responsibilities:

1. **Compute SCS** — weighted sum of the three Stage 1 scores
2. **Apply hysteresis** — prevent rapid mode-switching
3. **Apply mode hold** — minimum time in any mode before switching
4. **Select mode** — MODE_A, MODE_B, or MODE_C
5. **Assemble PipelineOutput** — the structured object Sanchit's code consumes
6. **Emit JSON** — write `pipeline_output.json` on each event (and/or push to queue)

The formula:

```
SCS = w1 * P_overlap + w2 * N_norm + w3 * U_speaker
      Σ(w_i) = 1

Recommended starting weights:
  w1 = 0.45  (P_overlap — strongest signal)
  w2 = 0.35  (N_norm — second strongest)
  w3 = 0.20  (U_speaker — tiebreaker)

Mode routing:
  SCS < 0.25           → MODE_A  (Minimal Inference Path)
  0.25 ≤ SCS ≤ 0.65   → MODE_B  (Assisted Path)
  SCS > 0.65           → MODE_C  (High-Complexity Recovery Path)
```

---

## 1. The Output Contract — PipelineOutput

This is the **exact object** Sanchit's backend expects. Do not deviate from field names or types.

```python
# pipeline_contract.py  ← put this in the project root, imported by both sides
from dataclasses import dataclass, field
from enum import Enum
import numpy as np


class PipelineMode(str, Enum):
    MODE_A = "A"   # Clean single speaker
    MODE_B = "B"   # Single speaker + noise  
    MODE_C = "C"   # Overlapping speakers


@dataclass
class AudioStream:
    stream_id: int
    audio: np.ndarray          # float32, 16kHz, mono — the mixed or separated stream
    sample_rate: int = 16000
    speaker_id: str = "unknown"       # Stage 2 fills this; DRS outputs "unknown"
    speaker_confidence: float = 0.0   # Stage 2 fills this; DRS outputs 0.0
    duration_seconds: float = 0.0


@dataclass
class PipelineOutput:
    mode: PipelineMode
    timestamp: float                   # time.monotonic() at DRS emit
    audio_streams: list[AudioStream]   # 1 stream (DRS); Stage 2 may split into 2+
    scene_complexity_score: float = 0.0
    vad_confidence: float = 0.0        # Sb (speech probability) from Stage 0 VAD
    wakeword_confidence: float = 0.0   # Pw from Stage 0 wake-word CNN
    overlap_probability: float = 0.0   # P_overlap from Stage 1
    noise_floor_db: float = -40.0      # Nf converted to dB scale
```

### What DRS fills vs what Stage 2 fills

| Field | Filled by | Value at DRS output |
|-------|-----------|-------------------|
| `mode` | DRS | MODE_A / B / C |
| `timestamp` | DRS | current monotonic time |
| `audio_streams[0].audio` | DRS | raw mixed audio from Stage 1 |
| `audio_streams[0].stream_id` | DRS | always 0 |
| `audio_streams[0].duration_seconds` | DRS | `len(audio) / 16000` |
| `audio_streams[0].speaker_id` | **Stage 2** | "unknown" at DRS |
| `audio_streams[0].speaker_confidence` | **Stage 2** | 0.0 at DRS |
| `scene_complexity_score` | DRS | smoothed SCS |
| `vad_confidence` | DRS | `three_bit.Sb` (float from VAD) |
| `wakeword_confidence` | DRS | `three_bit.Pw` |
| `overlap_probability` | DRS | `scene.P_overlap` |
| `noise_floor_db` | DRS | `Nf_to_dB(three_bit.Nf)` |

> **For MODE_C**: DRS still outputs 1 stream (the mixed audio). Stage 2 (TFPSNet) will receive this `PipelineOutput`, run separation, and replace `audio_streams` with 2+ separated streams before passing to Stage 3. DRS does not run TFPSNet — that is out of scope for your deliverable.

---

## 2. Noise Floor dB Conversion

Sanchit's contract uses `noise_floor_db` (float, negative dB). Stage 0 outputs `Nf` (normalised 0–1 where 1=noisy). Convert:

```python
def nf_to_db(nf: float) -> float:
    """
    Convert Stage 0 normalised noise floor to approximate dBFS.
    Nf=0.0 (clean) → -60 dBFS
    Nf=1.0 (very noisy) → -10 dBFS
    Linear interpolation in dB space.
    """
    nf = float(np.clip(nf, 1e-6, 1.0))
    db = -60.0 + (nf * 50.0)   # maps [0,1] → [-60, -10] dBFS
    return round(db, 2)
```

---

## 3. SCS Calculator (`drs/scs_calculator.py`)

Unchanged from original design. Computes raw SCS, applies EMA smoothing.

```python
# drs/scs_calculator.py
from dataclasses import dataclass
from collections import deque
import numpy as np
from stage1.acoustic_intelligence import AcousticSceneOutput


@dataclass
class SCSResult:
    scs: float
    P_overlap: float
    N_norm: float
    U_speaker: float
    w1: float
    w2: float
    w3: float
    smoothed_scs: float
    window_id: int


class SCSCalculator:
    EMA_ALPHA = 0.30

    def __init__(self, config: dict):
        drs_cfg = config['dynamic_resource_scaler']
        self.w1 = drs_cfg['weight_overlap']
        self.w2 = drs_cfg['weight_noise']
        self.w3 = drs_cfg['weight_speaker_uncertainty']
        assert abs(self.w1 + self.w2 + self.w3 - 1.0) < 1e-6
        self._smoothed_scs = 0.0
        self._first_call = True
        self._history: deque[SCSResult] = deque(maxlen=100)

    def compute(self, scene: AcousticSceneOutput) -> SCSResult:
        raw_scs = float(np.clip(
            self.w1 * scene.P_overlap
          + self.w2 * scene.N_norm
          + self.w3 * scene.U_speaker,
            0.0, 1.0
        ))
        if self._first_call:
            self._smoothed_scs = raw_scs
            self._first_call = False
        else:
            self._smoothed_scs = (self.EMA_ALPHA * raw_scs
                                  + (1 - self.EMA_ALPHA) * self._smoothed_scs)
        result = SCSResult(
            scs=raw_scs, P_overlap=scene.P_overlap, N_norm=scene.N_norm,
            U_speaker=scene.U_speaker, w1=self.w1, w2=self.w2, w3=self.w3,
            smoothed_scs=self._smoothed_scs, window_id=scene.window_id,
        )
        self._history.append(result)
        return result
```

---

## 4. Mode Router (`drs/mode_router.py`)

Applies hysteresis and mode hold. Returns `ProcessingMode` enum.

```python
# drs/mode_router.py
import time
from enum import Enum
from dataclasses import dataclass
from .scs_calculator import SCSResult


class ProcessingMode(Enum):
    MODE_A = "A"
    MODE_B = "B"
    MODE_C = "C"


class ModeRouter:
    def __init__(self, config: dict):
        drs_cfg = config['dynamic_resource_scaler']
        self._a_thresh  = drs_cfg['mode_a_threshold']   # 0.25
        self._c_thresh  = drs_cfg['mode_c_threshold']   # 0.65
        self._hyst      = drs_cfg['hysteresis_margin']  # 0.05
        self._hold_ms   = drs_cfg['mode_hold_ms']        # 500
        self._current   = ProcessingMode.MODE_A
        self._held_since = time.monotonic()

    def route(self, scs: SCSResult) -> ProcessingMode:
        val = scs.smoothed_scs
        now = time.monotonic()
        held_long_enough = (now - self._held_since) * 1000 >= self._hold_ms

        if not held_long_enough:
            return self._current

        if self._current == ProcessingMode.MODE_A:
            if val >= self._a_thresh + self._hyst:
                self._transition(ProcessingMode.MODE_B if val < self._c_thresh else ProcessingMode.MODE_C, now)
        elif self._current == ProcessingMode.MODE_B:
            if val < self._a_thresh - self._hyst:
                self._transition(ProcessingMode.MODE_A, now)
            elif val > self._c_thresh + self._hyst:
                self._transition(ProcessingMode.MODE_C, now)
        elif self._current == ProcessingMode.MODE_C:
            if val <= self._c_thresh - self._hyst:
                self._transition(ProcessingMode.MODE_B, now)

        return self._current

    def _transition(self, new_mode, now):
        print(f"[DRS] Mode {self._current.value} → {new_mode.value}")
        self._current = new_mode
        self._held_since = now
```

---

## 5. PipelineOutput Assembler (`drs/output_assembler.py`)

### ⚠️ NEW MODULE — Core deliverable

This is the new module that replaces mode-specific "handlers" from the original design. Instead of dispatching to a Mode A/B/C handler that does further processing, the DRS assembles and emits the `PipelineOutput` object that satisfies Sanchit's contract.

```python
# drs/output_assembler.py
import time
import json
import numpy as np
from pathlib import Path
from dataclasses import dataclass, asdict
from pipeline_contract import PipelineOutput, PipelineMode, AudioStream
from .mode_router import ProcessingMode
from .scs_calculator import SCSResult
from stage1.acoustic_intelligence import AcousticSceneOutput
from stage0.passive_gate import ThreeBitWord


def nf_to_db(nf: float) -> float:
    nf = float(np.clip(nf, 1e-6, 1.0))
    return round(-60.0 + (nf * 50.0), 2)


def mode_to_pipeline_mode(m: ProcessingMode) -> PipelineMode:
    return {
        ProcessingMode.MODE_A: PipelineMode.MODE_A,
        ProcessingMode.MODE_B: PipelineMode.MODE_B,
        ProcessingMode.MODE_C: PipelineMode.MODE_C,
    }[m]


class PipelineOutputAssembler:
    """
    Converts DRS routing decision + Stage 1 scene + Stage 0 metadata
    into the PipelineOutput object.
    
    IMPORTANT: speaker_id and speaker_confidence are set to "unknown" / 0.0.
    Stage 2 (CAM++) will overwrite these fields after speaker verification.
    
    The audio passed is the RAW MIXED audio from stage1.raw_audio.
    It is NOT separated — separation is Stage 2's job.
    """

    def __init__(self, config: dict, output_dir: str = "outputs"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._event_count = 0

    def assemble(
        self,
        mode: ProcessingMode,
        scs_result: SCSResult,
        scene: AcousticSceneOutput,
        three_bit: ThreeBitWord,
    ) -> PipelineOutput:
        """
        Build the PipelineOutput object for one pipeline event.
        
        The audio_streams list always contains exactly ONE stream at this stage:
        the full mixed audio. Stage 2 replaces this with 2+ streams for MODE_C.
        """
        raw_audio = scene.raw_audio  # float32, 16kHz, mono

        stream = AudioStream(
            stream_id=0,
            audio=raw_audio,
            sample_rate=16000,
            speaker_id="unknown",         # Stage 2 fills this
            speaker_confidence=0.0,       # Stage 2 fills this
            duration_seconds=len(raw_audio) / 16000.0,
        )

        output = PipelineOutput(
            mode=mode_to_pipeline_mode(mode),
            timestamp=time.monotonic(),
            audio_streams=[stream],
            scene_complexity_score=round(scs_result.smoothed_scs, 4),
            vad_confidence=round(float(three_bit.Sb), 4),       # speech prob from Silero
            wakeword_confidence=round(float(three_bit.Pw), 4),  # wake-word prob from CNN
            overlap_probability=round(scene.P_overlap, 4),
            noise_floor_db=nf_to_db(three_bit.Nf),
        )

        self._event_count += 1
        return output

    def to_json(self, output: PipelineOutput, include_audio: bool = False) -> dict:
        """
        Serialise PipelineOutput to a JSON-compatible dict.
        
        include_audio=True: embed audio as base64 (large, for transfer to Sanchit)
        include_audio=False: embed audio shape/stats only (for logging/debugging)
        
        Sanchit's pipeline reads this from disk or receives it over queue.
        """
        import base64

        streams_serialised = []
        for s in output.audio_streams:
            entry = {
                "stream_id": s.stream_id,
                "sample_rate": s.sample_rate,
                "speaker_id": s.speaker_id,
                "speaker_confidence": s.speaker_confidence,
                "duration_seconds": round(s.duration_seconds, 4),
                "num_samples": len(s.audio),
            }
            if include_audio:
                # Base64-encode raw bytes for JSON transport
                entry["audio_b64"] = base64.b64encode(
                    s.audio.astype(np.float32).tobytes()
                ).decode("utf-8")
            else:
                # Stats only (for logging)
                entry["audio_rms"] = round(float(np.sqrt(np.mean(s.audio**2))), 6)
                entry["audio_peak"] = round(float(np.max(np.abs(s.audio))), 6)
            streams_serialised.append(entry)

        return {
            "mode": output.mode.value,
            "timestamp": round(output.timestamp, 6),
            "scene_complexity_score": output.scene_complexity_score,
            "vad_confidence": output.vad_confidence,
            "wakeword_confidence": output.wakeword_confidence,
            "overlap_probability": output.overlap_probability,
            "noise_floor_db": output.noise_floor_db,
            "audio_streams": streams_serialised,
        }

    def write_json(
        self,
        output: PipelineOutput,
        filename: str = "pipeline_output.json",
        include_audio: bool = True,
    ) -> Path:
        """
        Write PipelineOutput to a JSON file.
        Default: always overwrite pipeline_output.json (latest event).
        For archival: use filename=f"event_{self._event_count:04d}.json"
        """
        data = self.to_json(output, include_audio=include_audio)
        path = self._output_dir / filename
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path
```

---

## 6. JSON Output Format

Every pipeline event produces a JSON file. Example for a MODE_B event:

```json
{
  "mode": "B",
  "timestamp": 12483.291847,
  "scene_complexity_score": 0.4123,
  "vad_confidence": 0.8721,
  "wakeword_confidence": 0.7340,
  "overlap_probability": 0.3812,
  "noise_floor_db": -41.5,
  "audio_streams": [
    {
      "stream_id": 0,
      "sample_rate": 16000,
      "speaker_id": "unknown",
      "speaker_confidence": 0.0,
      "duration_seconds": 0.3,
      "num_samples": 4800,
      "audio_b64": "<base64-encoded float32 PCM>"
    }
  ]
}
```

> **Sanchit reads this by**: loading `audio_b64` → `base64.decode` → `np.frombuffer(..., dtype=np.float32)` → float32 numpy array at 16kHz.

---

## 7. DRS Runner (`drs/drs_runner.py`)

### ⚠️ UPDATED — Replaces handler-dispatch with PipelineOutput emit

```python
# drs/drs_runner.py
import queue
import threading
import time
from pathlib import Path
from .scs_calculator import SCSCalculator
from .mode_router import ModeRouter
from .output_assembler import PipelineOutputAssembler
from stage1.acoustic_intelligence import AcousticSceneOutput
from stage0.passive_gate import ThreeBitWord


class DRSRunner:
    """
    Dynamic Resource Scaler thread.
    
    Input:  (AcousticSceneOutput, ThreeBitWord) tuples from Stage 1 queue
    Output: PipelineOutput written to JSON + placed on output queue
    
    The output queue (pipeline_output_queue) is what Sanchit's code reads from
    if running in the same process. JSON file is the inter-process contract.
    """

    def __init__(self, config: dict, input_queue: queue.Queue,
                 pipeline_output_queue: queue.Queue | None = None,
                 output_dir: str = "outputs"):
        self._config  = config
        self._in_q    = input_queue
        self._out_q   = pipeline_output_queue   # optional — Sanchit's queue if co-process
        self._stop    = threading.Event()

        self._scs_calc  = SCSCalculator(config)
        self._router    = ModeRouter(config)
        self._assembler = PipelineOutputAssembler(config, output_dir=output_dir)

        self._event_count = 0

    def _processing_loop(self):
        print("[DRS] Processing thread started.")
        while not self._stop.is_set():
            try:
                item = self._in_q.get(timeout=0.2)
            except queue.Empty:
                continue

            scene: AcousticSceneOutput
            three_bit: ThreeBitWord
            scene, three_bit = item

            # Step 1: Compute SCS
            scs_result = self._scs_calc.compute(scene)

            # Step 2: Route to mode
            mode = self._router.route(scs_result)

            # Step 3: Assemble PipelineOutput
            pipeline_out = self._assembler.assemble(
                mode=mode,
                scs_result=scs_result,
                scene=scene,
                three_bit=three_bit,
            )

            # Step 4: Write JSON (always — Sanchit polls this file OR reads the queue)
            json_path = self._assembler.write_json(
                pipeline_out,
                filename="pipeline_output.json",
                include_audio=True,
            )

            # Step 5: Push to inter-process queue if provided
            if self._out_q is not None:
                try:
                    self._out_q.put_nowait(pipeline_out)
                except queue.Full:
                    pass

            self._event_count += 1
            print(f"[DRS] Event {self._event_count:04d} | "
                  f"Mode={mode.value} | SCS={scs_result.smoothed_scs:.3f} | "
                  f"P_ov={scene.P_overlap:.3f} | "
                  f"audio={len(scene.raw_audio)/16000:.2f}s → {json_path}")

    def start(self):
        self._thread = threading.Thread(target=self._processing_loop,
                                        name="DRS-Thread", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        print(f"\n[DRS] Total events emitted: {self._event_count}")
        print(self._scs_calc.get_recent_stats())
```

---

## 8. Full Pipeline Entry Point (`scripts/live_test.py`)

```python
#!/usr/bin/env python3
"""
live_test.py — End-to-end pipeline.
Runs Stage 0 → Stage 1 → DRS → writes pipeline_output.json each event.

Usage:
    python scripts/live_test.py

Press Ctrl+C to stop.
"""
import queue, time, yaml, signal, sys


def main():
    with open("config/pipeline_config.yaml") as f:
        config = yaml.safe_load(f)

    q_s0_s1  = queue.Queue(maxsize=16)
    q_s1_drs = queue.Queue(maxsize=8)
    q_output = queue.Queue(maxsize=32)   # PipelineOutput objects

    from stage0 import Stage0Runner
    from stage1 import Stage1Runner
    from drs import DRSRunner

    stage0 = Stage0Runner(config, q_s0_s1)
    stage1 = Stage1Runner(config, q_s0_s1, q_s1_drs)
    drs    = DRSRunner(config, q_s1_drs,
                       pipeline_output_queue=q_output,
                       output_dir="outputs")

    def shutdown(sig, frame):
        print("\nShutting down...")
        drs.stop(); stage1.stop(); stage0.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)

    print("Starting The Canary pipeline...")
    print(f"Wake word: '{config['stage0']['wakeword_model']}'")
    print("Say the wake word followed by a command.")
    print("Output written to outputs/pipeline_output.json\n")
    print("Press Ctrl+C to stop.\n")

    stage0.start(); stage1.start(); drs.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
```

---

## 9. Directory Structure (Updated)

```
canary/
├── pipeline_contract.py          ← *** NEW: shared contract (both sides import this)
├── outputs/
│   ├── pipeline_output.json      ← *** latest event (overwritten each time)
│   └── event_0001.json           ← archived events (optional, set in DRSRunner)
├── stage0/ ...                   (unchanged)
├── stage1/
│   ├── acoustic_intelligence.py  ← UPDATED: raw_audio field added
│   └── stage1_runner.py          ← UPDATED: accumulate_raw_chunk call added
├── drs/
│   ├── scs_calculator.py         (unchanged)
│   ├── mode_router.py            (unchanged)
│   ├── output_assembler.py       ← *** NEW: replaces old mode handlers
│   └── drs_runner.py             ← UPDATED: emits PipelineOutput, not handler calls
└── ...
```

---

## 10. Why No Transcript In The JSON?

Sanchit's contract includes `speaker_id` but not a transcript field. ASR (Whisper or IndicVoices fine-tune) runs in **Sanchit's pipeline after Stage 2**, on the already-separated streams. Your deliverable ends at the DRS JSON output.

If the evaluation panel asks: you emit the mixed audio + metadata → Stage 2 separates → Stage 3 transcribes. The transcript is out of scope for your two stages.

---

## 11. Hysteresis and Weight Tuning

### Hysteresis reminder

```
Mode A → Mode B: SCS must exceed 0.25 + 0.05 = 0.30
Mode B → Mode A: SCS must drop below 0.25 − 0.05 = 0.20
Mode B → Mode C: SCS must exceed 0.65 + 0.05 = 0.70
Mode C → Mode B: SCS must drop below 0.65 − 0.05 = 0.60
```

### Weight tuning phases

**Phase 1** — Collect ground truth: record 5–10 min of each scenario (CLEAN_1SPK / NOISY_1SPK / 2SPK_CLEAN / 2SPK_NOISY / TV_ONLY) and manually label 300ms windows.

**Phase 2** — Run Stage 1 features on all recordings. Save (P_overlap, N_norm, U_speaker) per window.

**Phase 3** — Determine target mode per scenario:
- CLEAN_1SPK → MODE_A
- NOISY_1SPK → MODE_B
- 2SPK_CLEAN → MODE_B / MODE_C
- 2SPK_NOISY → MODE_C
- TV_ONLY → should never reach DRS (Stage 0 blocks it)

**Phase 4** — Adjust weights until routing accuracy satisfies targets.

---

## 12. Common Failure Modes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `raw_audio` in JSON is empty `[]` | `accumulate_raw_chunk` not called in Stage1Runner | Verify `_intelligence.accumulate_raw_chunk(chunk_audio)` is called before `_buffer` append |
| `audio_b64` decodes to wrong length | `raw_audio` from wrong accumulation window | Print `len(scene.raw_audio)` — expect ~4800 samples |
| Mode C fires constantly in quiet room | Spectral flatness too high (mic noise) | Lower `weight_noise` from 0.35 → 0.25; check highpass filter |
| Mode never leaves A during overlap | `corr_consistency` not capturing pitch variation | Verify autocorr lag range covers 53–267 samples (60–300 Hz at 16kHz) |
| Rapid mode flickering | SCS hovering at boundary | Increase hysteresis to 0.10, mode_hold_ms to 1000 |
| JSON file not written | `output_dir` path doesn't exist | DRSRunner creates it with `mkdir(parents=True)` — check write permissions |

---

## 13. Expected Performance on Mac M3

| Operation | Expected Latency |
|-----------|----------------|
| Audio capture callback | < 1ms |
| Stage 0 VAD (per chunk) | 1.5–3ms |
| Stage 0 WakeWord (per chunk) | 2–4ms |
| Stage 1 feature extraction (per window) | 3–7ms |
| SCS computation | < 0.5ms |
| Mode routing | < 0.5ms |
| PipelineOutput assembly + JSON write | < 2ms |
| **Total Stage 0–DRS per event** | **~15–17ms** |

Real-time factor: 17ms / 100ms window = **xRT ≈ 0.17** ✓  
Target: xRT < 0.5 ✓

---

*End of Dynamic Resource Scaler documentation.*  
*Your deliverable: Stage 0 → Stage 1 → DRS → `pipeline_output.json` with `PipelineOutput` contract.*  
*Sanchit's pipeline reads the JSON, loads audio from `audio_b64`, runs TFPSNet + CAM++ + ASR.*