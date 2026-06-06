# 02 — Stage 0: The Passive Idle Gate
### The Canary | Wake-Word Detection + Silero VAD → 3-bit Output

> **This stage is the most important piece you will build.** If Stage 0 is wrong, everything downstream is garbage. Spend 60% of your debugging time here.

---

## 0. What Stage 0 Actually Does (In Plain English)

Your built-in mic runs continuously at 16kHz. Every 32ms (512 samples), Stage 0 gets a chunk and answers exactly **one question**:

> *"Is this audio worth spending ANY compute on?"*

The answer is the **3-bit word**:
```
┌──────────────────────────────────────────────────────────────────┐
│  Sb  (Speech Binary)  →  0 = no speech  |  1 = speech detected  │
│  Pw  (Wake-word Prob) →  float [0.0–1.0], how likely wake-word   │
│  Nf  (Noise Floor)    →  float [0.0–1.0], 0=clean, 1=very noisy  │
└──────────────────────────────────────────────────────────────────┘

PASS = Sb AND (Pw > τ1) AND (Nf < τ3)
    τ1 = 0.5  (from config: wakeword_threshold)
    τ3 = 0.8  (from config: noise_floor_threshold)

If PASS: forward chunk + 3-bit word to Stage 1
If FAIL: discard chunk, reset VAD state if needed, stay idle
```

**Why this ordering?**
Silero VAD runs first because it is extremely fast (~2ms). There is no point running the wake-word CNN if there is no speech at all — that alone eliminates 80–90% of all audio events in a typical room.

---

## 1. Component 1: Audio Capture (`audio_capture.py`)

This module owns the microphone. Nothing else touches the mic directly.

### Design decisions:

**Ring buffer over simple queue**  
A `collections.deque` with `maxlen=N` acts as a ring buffer. Audio chunks are added in the RT callback and consumed by Stage 0 — if Stage 0 is slow, old chunks are automatically dropped from the front. This prevents memory growth under load.

**Callback design**  
The sounddevice callback must be zero-allocation. Do not create new arrays inside it. Pre-allocate and copy.

```python
# stage0/audio_capture.py
import numpy as np
import sounddevice as sd
import queue
import threading
from collections import deque
from dataclasses import dataclass


@dataclass
class AudioChunk:
    """One chunk of audio data with metadata."""
    samples: np.ndarray   # shape: (512,), dtype float32, range [-1, 1]
    timestamp: float      # time.monotonic() at capture
    chunk_id: int         # monotonically increasing


class AudioCapture:
    """
    Owns the microphone stream.
    Delivers AudioChunk objects to Stage 0 via a thread-safe queue.
    
    Threading model:
      - sounddevice callback fires on CoreAudio RT thread (priority: real-time)
      - _callback ONLY enqueues — no inference, no numpy ops, no GIL-holding calls
      - Stage 0 thread calls get_chunk() which blocks with timeout
    """

    def __init__(self, config: dict):
        self.sample_rate = config['audio']['sample_rate']       # 16000
        self.chunk_size  = config['audio']['chunk_size']         # 512
        self.channels    = config['audio']['channels']           # 1
        self.dtype       = config['audio']['dtype']              # 'float32'
        self.device_id   = config['audio'].get('mic_device_id')  # None = default

        # Thread-safe FIFO — maxsize prevents memory explosion if Stage 0 is slow
        self._queue = queue.Queue(maxsize=32)

        self._chunk_id  = 0
        self._stream    = None
        self._running   = False

        # Pre-allocate a scratch buffer to avoid allocation in RT callback
        # (In Python this is less critical than C++ but still good practice)
        self._scratch   = np.zeros(self.chunk_size, dtype=np.float32)

    def _callback(self, indata: np.ndarray, frames: int,
                  time_info, status) -> None:
        """
        Called by CoreAudio RT thread every 32ms.
        MUST NOT: call any model, do heavy numpy, or block.
        MUST: copy data and enqueue quickly.
        """
        if status:
            # Log status flags but do not crash: buffer over/underflow
            # status.input_overflow means we missed some audio — log it
            pass

        # indata shape: (512, 1) — squeeze to 1D
        chunk = AudioChunk(
            samples=indata[:, 0].copy(),   # copy is critical — indata is reused
            timestamp=time_info.inputBufferAdcTime,
            chunk_id=self._chunk_id
        )
        self._chunk_id += 1

        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            # Drop oldest chunk — ring buffer semantics
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except queue.Empty:
                pass

    def start(self) -> None:
        """Open the mic stream and start capturing."""
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.chunk_size,
            device=self.device_id,
            callback=self._callback,
            # CoreAudio-specific: maximum conversion quality
            extra_settings=sd.CoreAudioSettings(
                change_device_parameters=False,
                fail_if_conversion_required=False,
                conversion_quality='max'
            )
        )
        self._stream.start()
        self._running = True

    def stop(self) -> None:
        """Close the mic stream cleanly."""
        if self._stream and self._running:
            self._stream.stop()
            self._stream.close()
            self._running = False

    def get_chunk(self, timeout: float = 0.1) -> AudioChunk | None:
        """
        Blocking call with timeout. Returns None if no audio arrives.
        Called by Stage 0 processing thread.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def is_running(self) -> bool:
        return self._running
```

---

## 2. Component 2: Silero VAD Engine (`vad_engine.py`)

Silero VAD v5 is a stateful model. It maintains internal state between chunks — this is what enables it to detect speech onset/offset across chunk boundaries. You MUST reset state at the right times.

### How Silero VAD v5 works internally:
1. Input: 512 samples of float32 audio at 16kHz
2. Internal state: LSTM hidden state (h, c) — persists across calls
3. Output: speech probability (0.0–1.0) for that 512-sample window
4. The model runs ONNX inference under the hood

### Critical Silero VAD parameters:

| Parameter | Recommended Value | Effect |
|-----------|-------------------|--------|
| `threshold` | 0.5 | Probability above which speech is declared |
| `min_speech_duration_ms` | 250 | Filters clicks/pops (shorter speech = false positive) |
| `min_silence_duration_ms` | 100 | Gap needed to close a speech segment |
| `speech_pad_ms` | 30 | Padding added to both ends of detected speech |

```python
# stage0/vad_engine.py
import numpy as np
import torch
from silero_vad import load_silero_vad
from dataclasses import dataclass
from collections import deque
import time


@dataclass
class VADResult:
    """Output from one VAD call on one chunk."""
    is_speech: bool           # hard binary decision
    speech_prob: float        # raw probability from model [0–1]
    noise_floor: float        # estimated noise floor [0–1, 0=clean]
    chunk_id: int


class SileroVADEngine:
    """
    Wraps Silero VAD v5 for streaming chunk-by-chunk inference.
    
    Threading: must be called from a single thread only.
    The LSTM state (h, c) is NOT thread-safe.
    
    Mac M3 note:
      - We use the PyTorch version, NOT ONNX, because silero_vad's
        PyTorch wrapper handles state management automatically.
      - Device is CPU — the model is too small to benefit from MPS,
        and MPS adds ~5ms overhead per call.
    """

    def __init__(self, config: dict):
        stage0_cfg = config['stage0']
        self.threshold  = stage0_cfg['vad_threshold']           # 0.5
        self.nf_thresh  = stage0_cfg['noise_floor_threshold']   # 0.8
        self.nf_window  = stage0_cfg['noise_floor_window_chunks']  # 10

        # Force CPU — VAD is fast enough on M3 CPU, MPS overhead not worth it
        self._device = torch.device('cpu')
        torch.set_num_threads(1)   # prevents NumPy/PyTorch thread contention

        # Load Silero VAD (downloads ~1.8MB on first run, cached afterwards)
        self._model = load_silero_vad()
        self._model.to(self._device)

        # Silero maintains its own state — this call resets h and c vectors
        self._reset_state()

        # Rolling buffer for noise floor estimation
        # Store RMS energy of last N chunks (both speech and silence)
        self._energy_history: deque[float] = deque(maxlen=self.nf_window * 5)
        # Separate buffer for frames Silero says are SILENT (better noise estimate)
        self._silence_energy: deque[float] = deque(maxlen=self.nf_window)

        # Hysteresis state for speech detection
        self._consecutive_speech = 0    # chunks in a row with prob > threshold
        self._consecutive_silence = 0   # chunks in a row with prob < threshold
        self._in_speech = False         # current speech state (hysteresis applied)

    def _reset_state(self):
        """Reset VAD LSTM state. Call at start of session or after long silence."""
        self._model.reset_states()

    def _estimate_noise_floor(self, chunk: np.ndarray, is_speech: bool) -> float:
        """
        Estimates noise floor as a normalised value [0–1].
        
        Method:
        - Track RMS energy of frames Silero marks as silence
        - These frames are your noise reference
        - Normalise against a pre-calibrated maximum (or self-calibrate)
        
        Returns: 0.0 = clean, 1.0 = very noisy
        """
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        self._energy_history.append(rms)

        if not is_speech:
            # Silence frames are our noise reference
            self._silence_energy.append(rms)

        if len(self._silence_energy) < 3:
            # Not enough reference yet — assume moderate noise
            return 0.3

        # Noise floor = average of silence frame energies
        noise_rms = float(np.mean(list(self._silence_energy)))

        # Normalise: typical mic noise floor is around 0.001–0.005 RMS
        # A noisy room pushes this to 0.02–0.05 RMS
        # Map 0.0 → 0.05 to 0 → 1 (clipped)
        noise_floor_normalised = float(np.clip(noise_rms / 0.05, 0.0, 1.0))
        return noise_floor_normalised

    def process_chunk(self, chunk: np.ndarray, chunk_id: int) -> VADResult:
        """
        Run Silero VAD on one 512-sample chunk.
        
        Args:
            chunk: float32 array of shape (512,), range [-1, 1]
            chunk_id: monotonic integer for tracking
            
        Returns:
            VADResult with speech decision and metadata
        """
        assert chunk.shape == (512,), f"Expected 512 samples, got {chunk.shape}"
        assert chunk.dtype == np.float32, f"Expected float32, got {chunk.dtype}"

        # Convert to torch tensor (CPU, no gradient)
        tensor = torch.from_numpy(chunk).unsqueeze(0)   # shape: (1, 512)

        # Run Silero inference — returns scalar probability
        with torch.no_grad():
            speech_prob = float(self._model(tensor, 16000).item())

        # Hysteresis: require multiple consecutive chunks to change state
        # This prevents rapid 0/1 toggling on borderline audio
        if speech_prob >= self.threshold:
            self._consecutive_speech += 1
            self._consecutive_silence = 0
        else:
            self._consecutive_silence += 1
            self._consecutive_speech = 0

        # State machine: speech onset requires 3 consecutive speech chunks
        #                speech offset requires 4 consecutive silence chunks
        if not self._in_speech and self._consecutive_speech >= 3:
            self._in_speech = True
        elif self._in_speech and self._consecutive_silence >= 4:
            self._in_speech = False
            # Optional: reset LSTM state after long silence
            if self._consecutive_silence > 50:   # >1.6s silence
                self._reset_state()

        # Estimate noise floor
        noise_floor = self._estimate_noise_floor(chunk, self._in_speech)

        return VADResult(
            is_speech=self._in_speech,
            speech_prob=speech_prob,
            noise_floor=noise_floor,
            chunk_id=chunk_id
        )

    def reset(self):
        """Public reset — call when starting a new session."""
        self._reset_state()
        self._energy_history.clear()
        self._silence_energy.clear()
        self._in_speech = False
        self._consecutive_speech = 0
        self._consecutive_silence = 0
```

---

## 3. Component 3: Wake-Word Engine (`wakeword_engine.py`)

openWakeWord works by accumulating 512-sample chunks in a **1-second sliding window** (16 chunks × 512 = 8192 samples). It returns a probability for each trained wake-word model.

### Important: Wake-word accumulation vs per-chunk VAD

Silero VAD works per 512-sample chunk (32ms). openWakeWord needs **1280ms of audio** to make a stable detection (it processes a 1280ms context window). This means:

- VAD fires every 32ms → fast gate
- Wake-word probability updates every 32ms BUT uses a 1280ms rolling window
- The Pw value you output is the peak probability over the last 1280ms

```python
# stage0/wakeword_engine.py
import numpy as np
from collections import deque
import openwakeword
from openwakeword.model import Model as OWWModel
from dataclasses import dataclass


@dataclass
class WakeWordResult:
    """Output from one wake-word check."""
    max_probability: float   # highest probability across recent window
    is_activated: bool       # probability exceeded threshold
    model_name: str          # which wake-word model triggered (or 'none')


class WakeWordEngine:
    """
    Wraps openWakeWord for streaming wake-word detection.
    
    How it works:
    - Maintains a rolling 1280ms audio buffer (20 chunks × 512 samples)
    - After each new chunk, runs OWW inference on the full buffer
    - Returns the peak probability from the last N chunks
    
    Threading: single-threaded only. State includes the audio buffer and model state.
    
    Mac M3 note:
    - Force ONNX inference backend (tflite can be unstable on ARM macOS)
    - Model runs on CPU — fast enough for 32ms chunks
    """

    # OWW context window: 1280ms = 20480 samples at 16kHz
    # It processes this internally as mel-spectrogram features
    OWW_CONTEXT_SAMPLES = 20480

    def __init__(self, config: dict):
        stage0_cfg = config['stage0']
        self.model_name     = stage0_cfg['wakeword_model']       # e.g. "hey_jarvis"
        self.threshold      = stage0_cfg['wakeword_threshold']   # 0.5
        self.window_ms      = stage0_cfg['wakeword_window_ms']   # 1000ms
        self.require_ww     = stage0_cfg['require_wakeword']     # True

        # Number of chunks to compute peak probability over
        self.peak_window_chunks = int(self.window_ms / 32)  # 1000/32 ≈ 31 chunks

        # Load openWakeWord model with ONNX backend
        # First call downloads model if not cached
        self._model = OWWModel(
            wakeword_models=[self.model_name],
            inference_framework='onnx'    # Force ONNX — avoids tflite ARM issues
        )

        # Rolling probability history for peak detection
        self._prob_history: deque[float] = deque(maxlen=self.peak_window_chunks)

        # Audio accumulation buffer: OWW needs audio context
        # sounddevice gives us float32 in [-1, 1]
        # OWW expects int16 OR float32 depending on version
        # Safe: use float32 and let OWW handle conversion
        self._audio_buffer: deque[np.ndarray] = deque(maxlen=40)  # ~1.3s buffer

    def process_chunk(self, chunk: np.ndarray, vad_active: bool) -> WakeWordResult:
        """
        Process one 512-sample chunk.
        
        Args:
            chunk: float32 array of shape (512,), range [-1, 1]
            vad_active: whether Silero VAD detected speech in this chunk
            
        Returns:
            WakeWordResult with probability and activation status
            
        Optimization: if VAD says no speech and wake-word history is 0,
        skip OWW inference entirely (saves ~3ms per chunk)
        """
        # Early exit: no speech and recent history is clean → skip OWW
        recent_max = max(self._prob_history, default=0.0)
        if not vad_active and recent_max < 0.1:
            self._prob_history.append(0.0)
            return WakeWordResult(
                max_probability=0.0,
                is_activated=False,
                model_name='none'
            )

        # Accumulate chunk into buffer
        self._audio_buffer.append(chunk)

        # OWW processes the full buffer each call
        # Convert to continuous array for prediction
        audio_context = np.concatenate(list(self._audio_buffer))  # (N*512,)

        # Run OWW prediction
        # Returns dict: {model_name: probability_array}
        predictions = self._model.predict(audio_context)

        # Extract probability for our target model
        if self.model_name in predictions:
            prob_array = predictions[self.model_name]
            # prob_array is a float array — take the most recent value
            current_prob = float(prob_array[-1]) if hasattr(prob_array, '__len__') \
                           else float(prob_array)
        else:
            current_prob = 0.0

        self._prob_history.append(current_prob)

        # Peak probability over the window
        peak_prob = max(self._prob_history)

        is_activated = peak_prob >= self.threshold

        return WakeWordResult(
            max_probability=peak_prob,
            is_activated=is_activated,
            model_name=self.model_name if is_activated else 'none'
        )

    def reset(self):
        """Reset after a false trigger or session end."""
        self._prob_history.clear()
        self._audio_buffer.clear()
```

---

## 4. Component 4: The Passive Gate (`passive_gate.py`)

This is the **decision node** of Stage 0. It takes VAD result + Wake-word result and produces the 3-bit word.

```python
# stage0/passive_gate.py
import numpy as np
from dataclasses import dataclass
from .vad_engine import VADResult
from .wakeword_engine import WakeWordResult


@dataclass
class ThreeBitWord:
    """
    The Stage 0 output contract.
    
    Everything downstream consumes only this struct — not raw VAD or OWW results.
    This is the API boundary between Stage 0 and Stage 1.
    """
    Sb: bool    # Speech Binary — True = speech detected
    Pw: float   # Wake-word probability [0.0–1.0]
    Nf: float   # Noise floor [0.0–1.0]
    
    # Derived gate decision (not a "bit" but included for convenience)
    PASS: bool  # True = forward to Stage 1
    
    # Metadata
    chunk_id: int
    timestamp: float

    def __str__(self):
        status = "PASS ✅" if self.PASS else "FAIL 🔇"
        return (f"[Chunk {self.chunk_id}] {status} | "
                f"Sb={int(self.Sb)} Pw={self.Pw:.3f} Nf={self.Nf:.3f}")


class PassiveGate:
    """
    Combines VAD + WakeWord results into the 3-bit output.
    
    PASS formula (from your thesis):
        PASS = Sb AND (Pw > τ1) AND (Nf < τ3)
    
    If require_wakeword=False (testing mode), PASS = Sb AND (Nf < τ3)
    This is useful during development to test Stage 1 without needing
    to speak the wake word every time.
    """

    def __init__(self, config: dict):
        stage0_cfg = config['stage0']
        self.wakeword_threshold    = stage0_cfg['wakeword_threshold']     # τ1 = 0.5
        self.noise_floor_threshold = stage0_cfg['noise_floor_threshold']  # τ3 = 0.8
        self.require_wakeword      = stage0_cfg['require_wakeword']       # True

        # Statistics for debugging / tuning
        self._total_chunks  = 0
        self._pass_chunks   = 0
        self._fail_reasons  = {'no_speech': 0, 'no_wakeword': 0, 'too_noisy': 0}

    def evaluate(self, vad: VADResult, ww: WakeWordResult,
                 timestamp: float) -> ThreeBitWord:
        """
        Evaluate PASS/FAIL for one chunk.
        
        Args:
            vad: result from SileroVADEngine.process_chunk()
            ww:  result from WakeWordEngine.process_chunk()
            timestamp: time.monotonic() at chunk capture
            
        Returns:
            ThreeBitWord with PASS flag
        """
        self._total_chunks += 1

        Sb = vad.is_speech
        Pw = ww.max_probability
        Nf = vad.noise_floor

        # Gate evaluation
        if not Sb:
            self._fail_reasons['no_speech'] += 1
            gate_pass = False

        elif self.require_wakeword and Pw < self.wakeword_threshold:
            self._fail_reasons['no_wakeword'] += 1
            gate_pass = False

        elif Nf >= self.noise_floor_threshold:
            self._fail_reasons['too_noisy'] += 1
            gate_pass = False

        else:
            gate_pass = True
            self._pass_chunks += 1

        return ThreeBitWord(
            Sb=Sb, Pw=Pw, Nf=Nf,
            PASS=gate_pass,
            chunk_id=vad.chunk_id,
            timestamp=timestamp
        )

    @property
    def pass_rate(self) -> float:
        """Fraction of chunks that PASS the gate. Should be low (< 5%) in normal use."""
        if self._total_chunks == 0:
            return 0.0
        return self._pass_chunks / self._total_chunks

    def print_stats(self):
        total = self._total_chunks
        print(f"\n=== Passive Gate Statistics ===")
        print(f"Total chunks evaluated: {total}")
        print(f"PASS chunks: {self._pass_chunks} ({self.pass_rate*100:.1f}%)")
        print(f"Fail — no speech: {self._fail_reasons['no_speech']}")
        print(f"Fail — no wake word: {self._fail_reasons['no_wakeword']}")
        print(f"Fail — too noisy: {self._fail_reasons['too_noisy']}")
```

---

## 5. The Stage 0 Processing Thread

Putting it all together — the actual processing loop:

```python
# stage0/__init__.py  (or  stage0/stage0_runner.py)
import threading
import queue
import time
from .audio_capture import AudioCapture, AudioChunk
from .vad_engine import SileroVADEngine
from .wakeword_engine import WakeWordEngine
from .passive_gate import PassiveGate, ThreeBitWord


class Stage0Runner:
    """
    Runs Stage 0 in a dedicated thread.
    Receives raw audio from AudioCapture, produces ThreeBitWord objects.
    
    Usage:
        output_queue = queue.Queue()
        runner = Stage0Runner(config, output_queue)
        runner.start()
        # In Stage 1 thread:
        word = output_queue.get(timeout=0.5)
    """

    def __init__(self, config: dict, output_queue: queue.Queue):
        self._config = config
        self._output_queue = output_queue
        self._thread = None
        self._stop_event = threading.Event()

        # Sub-components
        self.capture  = AudioCapture(config)
        self.vad      = SileroVADEngine(config)
        self.ww       = WakeWordEngine(config)
        self.gate     = PassiveGate(config)

    def _processing_loop(self):
        """Main loop running on Stage 0 thread."""
        print("[Stage0] Processing thread started.")
        self.capture.start()

        while not self._stop_event.is_set():
            chunk: AudioChunk | None = self.capture.get_chunk(timeout=0.05)

            if chunk is None:
                continue   # timeout, keep looping

            now = time.monotonic()

            # Step 1: VAD (fast, ~2ms)
            vad_result = self.vad.process_chunk(chunk.samples, chunk.chunk_id)

            # Step 2: Wake-word (fast if skipped, ~3ms if running)
            ww_result = self.ww.process_chunk(chunk.samples, vad_result.is_speech)

            # Step 3: Gate decision
            three_bit = self.gate.evaluate(vad_result, ww_result, now)

            # Only forward PASS chunks — this is the gate
            if three_bit.PASS:
                try:
                    # Attach the raw audio samples for Stage 1 to process
                    # (Stage 1 needs the audio, not just the metadata)
                    payload = (three_bit, chunk.samples)
                    self._output_queue.put_nowait(payload)
                except queue.Full:
                    # If Stage 1 is too slow, drop this chunk
                    # This is acceptable — better than blocking the RT pipeline
                    pass

        self.capture.stop()
        print("[Stage0] Processing thread stopped.")

    def start(self):
        self._thread = threading.Thread(target=self._processing_loop,
                                        name="Stage0-Thread", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
```

---

## 6. Threshold Tuning Strategy

This is where most people fail. Do NOT use default thresholds in production. Tune them for your actual room.

### Step 1: Calibrate the noise floor threshold (τ3)

```
1. Start the pipeline in a QUIET room (no TV, no fan, nothing)
2. Log Nf values for 5 minutes of ambient silence
3. Your quiet-room Nf average is your baseline — say 0.15
4. Set τ3 = 0.15 × 4 = 0.60 (4× baseline gives headroom)
5. Now play TV audio at typical volume, log Nf → say 0.45
6. Your τ3 should be above 0.45 to ignore TV → set to 0.65-0.70
7. Now speak normally → Nf during your speech is ~0.20 (lower than TV)
8. Confirm: Nf for your voice < τ3 ✓
```

### Step 2: Calibrate the wake-word threshold (τ1)

```
1. Speak the wake word 50 times at different distances (0.5m, 1m, 2m)
2. Log all Pw values for true positives → median should be ~0.7–0.9
3. Speak random sentences without the wake word → log Pw → should be < 0.2
4. Set τ1 between the two clusters, closer to the false-positive side
5. Typical good value: τ1 = 0.5
6. If you get too many false triggers: raise τ1 to 0.6–0.7
7. If you get too many misses (you say the wake word and nothing happens): lower to 0.4
```

### Step 3: Validate the VAD threshold

```
1. Record 10 seconds of silence → VAD probability should stay < 0.3
2. Speak continuously for 10 seconds → VAD probability should stay > 0.7
3. The default τ = 0.5 is usually correct for Silero v5
4. If your mic has high self-noise: lower to 0.4
```

---

## 7. Testing Stage 0 in Isolation

**Test 1: Silence test**
```bash
python scripts/live_test.py --stage 0 --duration 30 --mode silence
```
Expected: 0 PASS events for 30 seconds of ambient silence.

**Test 2: Speech without wake word**
```bash
python scripts/live_test.py --stage 0 --duration 30 --mode no-wakeword
```
Expected: 0 PASS events (Sb=1 but Pw low → gate fails).

**Test 3: Speech with wake word**
```bash
python scripts/live_test.py --stage 0 --duration 30 --mode wakeword
```
Expected: PASS events each time you say the wake word.

**Test 4: TV audio stress test**
- Play YouTube video at normal volume
- Run stage 0
- Expected: 0 PASS events (TV doesn't say wake word or Nf too high)

**Test 5: TV + your voice + wake word**
- Play TV
- Say wake word clearly
- Expected: PASS events only for your wake word utterances

---

## 8. C++ Note (Performance Critical Path)

If you later find Stage 0 is still too slow (unlikely on M3, but possible if you add more models), here is the architecture for a C++ audio bridge:

```cpp
// AudioBridge.cpp — bare-bones CoreAudio callback to circular buffer
// This bypasses Python entirely for audio capture

#include <AudioToolbox/AudioToolbox.h>
#include <atomic>
#include <vector>

constexpr int SAMPLE_RATE  = 16000;
constexpr int CHUNK_FRAMES = 512;
constexpr int RING_SLOTS   = 64;

// Lock-free single-producer single-consumer ring buffer
struct RingBuffer {
    float data[RING_SLOTS][CHUNK_FRAMES];
    std::atomic<int> write_idx{0};
    std::atomic<int> read_idx{0};
    
    bool push(const float* chunk) {
        int w = write_idx.load(std::memory_order_relaxed);
        int next_w = (w + 1) % RING_SLOTS;
        if (next_w == read_idx.load(std::memory_order_acquire)) {
            return false;  // full — drop
        }
        memcpy(data[w], chunk, CHUNK_FRAMES * sizeof(float));
        write_idx.store(next_w, std::memory_order_release);
        return true;
    }
    
    bool pop(float* out) {
        int r = read_idx.load(std::memory_order_relaxed);
        if (r == write_idx.load(std::memory_order_acquire)) {
            return false;  // empty
        }
        memcpy(out, data[r], CHUNK_FRAMES * sizeof(float));
        read_idx.store((r + 1) % RING_SLOTS, std::memory_order_release);
        return true;
    }
};
```

However, on M3 with Python 3.12 and sounddevice, the Python implementation above is fast enough. C++ bridge is a future optimisation, not required now.

---

*Next → Read `03_STAGE1_ACOUSTIC_INTELLIGENCE.md`*
