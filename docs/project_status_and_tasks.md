# The Canary — Project Status & Task Assignments

**Last Updated**: May 27, 2026  
**Deadline**: June 22, 2026, 2:00 PM IST  
**Days Remaining**: ~26

---

## 🚦 Current Project Status

| Area | Status | Notes |
|------|--------|-------|
| Architecture Design | ✅ Done | Sequential Gated Modular Pipeline finalized |
| Implementation Plan | ✅ Done | See `docs/implementation_plan.md` |
| Repo + Scaffold | ✅ Done | All skeleton modules created |
| Integration Contract | ✅ Defined | `PipelineOutput` schema frozen (see below) |
| Engineer A (Hemang) Code | 🔴 Not Started | Stage 0, 1, 2 |
| Engineer B (Sanchit) Code | 🟡 Skeleton Only | Stage 3, 4 — scaffolded, needs implementation |
| Integration Testing | 🔴 Not Started | Target: Day 10-11 |
| Demo / Video | 🔴 Not Started | Target: Day 18-21 |

---

## 🏗️ Architecture Recap

```
Mic → [Stage 0] → [Stage 1] → [Stage 2] → [Stage 3] → [Stage 4] → Response
       HEMANG       HEMANG       HEMANG       SANCHIT     SANCHIT
```

| Stage | Name | Owner | Core Tech |
|-------|------|-------|-----------|
| 0 | Passive Idle Gate | **Hemang** | Silero VAD + microWakeWord |
| 1 | Acoustic Scene Intelligence | **Hemang** | MatchboxNet intent + SCS Router |
| 2 | Speaker Separation + Biometrics | **Hemang** | TIGER + CAM++ + FAISS enrollment |
| 3 | Localized ASR | **Sanchit** | sherpa-onnx + SenseVoiceSmall |
| 4 | Agentic Orchestration | **Sanchit** | Arbitration + FastMCP + Ollama/Qwen |

---

## 👤 HEMANG — Exact Task List (Engineer A)

**Your domain**: Everything from microphone input to separated, speaker-tagged audio streams.

### Stage 0: Passive Idle Gate
- [ ] Set up audio capture via `sounddevice` (16kHz, mono, float32)
- [ ] Implement circular audio buffer (30ms chunks, ~3-5 second window)
- [ ] Integrate **Silero VAD** (ONNX) — detect when someone is speaking
- [ ] Integrate **microWakeWord** (TFLite) — detect wake word ("Hey Canary" or chosen trigger)
- [ ] Gate logic: Only pass audio downstream when VAD + wake-word both fire
- [ ] **Files**: `src/stage0/vad.py`, `src/stage0/wakeword.py`, `src/stage0/gate.py`

### Stage 1: Acoustic Scene Intelligence
- [ ] Integrate **MatchboxNet** (pre-trained or adapt) for Device-Directed Speech Detection (DDSD)
  - Binary classifier: Is this spoken TO the device, or just background chatter?
  - If custom training is too risky → use simple energy/pitch heuristic as fallback
- [ ] Implement **Scene Complexity Score (SCS)** calculation:
  - Compute from: energy variance, spectral flux, zero-crossing rate, overlap estimate
  - Output: float 0.0 → 1.0
- [ ] Implement **SCS Router**:
  - SCS < 0.3 → **Mode A** (clean single speaker, skip separation)
  - SCS 0.3-0.6 → **Mode B** (noisy single speaker, light denoising)
  - SCS > 0.6 → **Mode C** (overlapping speakers, full TIGER separation)
- [ ] **Files**: `src/stage1/ddsd.py`, `src/stage1/scs.py`, `src/stage1/router.py`

### Stage 2: Speaker Separation + Biometrics
- [ ] Integrate **TIGER** separation model (0.8M params)
  - Load pre-trained safetensor weights
  - Convert to ONNX Runtime for inference (or run via PyTorch if ONNX export is problematic)
  - Input: mixed audio (float32, 16kHz) → Output: 2 separated streams (float32, 16kHz)
  - Profile latency — MUST be < 0.5 xRT on CPU
- [ ] Integrate **CAM++ B0** speaker verification (1.1M params, ONNX)
  - Extract 192-dim speaker embeddings from each separated stream
  - Compare against enrolled embeddings (pre-computed .npy files) using FAISS or cosine similarity
  - Output: `speaker_id` ("hemang", "sanchit", "unknown") + `speaker_confidence` (0.0-1.0)
- [ ] Pre-compute enrollment embeddings:
  - Record 5-10 utterances per person
  - Extract CAM++ embeddings, average them
  - Save as `models/speaker_embeddings/hemang.npy` and `models/speaker_embeddings/sanchit.npy`
- [ ] **Files**: `src/stage2/tiger.py`, `src/stage2/speaker_verify.py`, `src/stage2/enrollment.py`

### Your Final Output — The Handoff

Once Stages 0-2 are done, your code must produce a **`PipelineOutput`** dict and pass it to Sanchit's code. The exact schema is defined below in the Integration Contract section.

```python
# Your main function should look like this:
from src.common.models import PipelineOutput, PipelineMode, AudioStream

def process_audio(raw_audio: np.ndarray) -> PipelineOutput:
    """Full Stage 0-2 pipeline."""
    # 1. VAD + WakeWord check → if not triggered, return None
    # 2. MatchboxNet DDSD → if not device-directed, return None
    # 3. Compute SCS → determine Mode A/B/C
    # 4. If Mode C: run TIGER separation + CAM++ speaker ID
    # 5. Build and return PipelineOutput
    ...
```

### Key Constraints for Hemang
- ⚠️ All audio MUST be **16kHz, float32, mono** — Sanchit's ASR requires this exactly
- ⚠️ Speaker ID MUST be resolved before handoff — ASR doesn't do speaker identification
- ⚠️ Max audio clip duration: **10 seconds** — SenseVoice is optimized for ≤10s
- ⚠️ Total core frontend parameter budget: **< 5 million** (TIGER 0.8M + CAM++ 1.1M + others ≈ 2.7M total, well within budget)

---

## 👤 SANCHIT — Exact Task List (Engineer B)

**Your domain**: Everything from receiving separated audio to final command execution.

### Stage 3: ASR Engine
- [ ] Install `sherpa-onnx`, download SenseVoiceSmall INT8 ONNX model
- [ ] Implement `ASREngine.transcribe()` — single stream → text
- [ ] Implement `ASREngine.transcribe_parallel()` — 2 streams concurrently (use `multiprocessing`)
- [ ] Test on pre-recorded `.wav` files of your own voice
- [ ] Record 10+ test `.wav` files (both voices, various commands)
- [ ] **File**: `src/asr/engine.py` (skeleton exists, needs implementation)

### Stage 4: Arbitration + Agentic Orchestration

#### Arbitration Engine (Rule-Based — PRIMARY)
- [ ] Complete the `ArbitrationEngine` conflict detection and resolution logic
- [ ] Test all 6 rules with mock data:
  1. Single command, high confidence → EXECUTE
  2. Single command, low confidence → CLARIFY
  3. Two non-conflicting commands → EXECUTE_BOTH
  4. Two conflicting, different privilege → EXECUTE_HIGHER (Admin wins)
  5. Two conflicting, same privilege → CLARIFY
  6. Unknown speaker → REJECT
- [ ] **File**: `src/arbitration/engine.py` (skeleton exists, core logic written)

#### MCP Server + Smart Home Tools
- [ ] Install `fastmcp`
- [ ] Wire up MCP tool decorators for: `toggle_lights`, `set_thermostat`, `play_music`, `set_timer`, `get_weather`, `request_clarification`
- [ ] **File**: `src/agent/mcp_server.py` (skeleton exists, functions written, needs MCP wiring)

#### SLM Integration (SECONDARY — bonus)
- [ ] Install Ollama, pull `qwen2.5:1.5b`
- [ ] Implement `SLMClient.reason()` — send transcription context, get decision
- [ ] Craft system prompt for conflict resolution
- [ ] **File**: `src/agent/slm.py` (skeleton exists)

### Infrastructure

#### Redis State Store
- [ ] Install Redis locally (`brew install redis`)
- [ ] Test `StateStore` class — profiles, sessions, command history, metrics
- [ ] **File**: `src/execution/state_store.py` (skeleton exists, code written)

#### FAISS Speaker Index
- [ ] Install `faiss-cpu`
- [ ] Test `SpeakerIndex` with dummy embeddings
- [ ] **File**: `src/execution/speaker_index.py` (skeleton exists, code written)

#### Demo UI
- [ ] Install `rich`
- [ ] Build terminal UI showing: pipeline status, speaker transcriptions, conflict resolution, tool execution
- [ ] **File**: `src/ui/` (empty, needs implementation)

### Pipeline Orchestrator
- [ ] Wire all modules together in `src/pipeline.py` (skeleton exists)
- [ ] Build `IntegrationBridge` to validate Hemang's output format
- [ ] End-to-end test with mock data first, then real data

### Documentation & Deliverables
- [ ] Fill in `docs/ax.md` (required for submission)
- [ ] Write final `README.md`
- [ ] Record demo video
- [ ] Record setup/reproducibility video

---

## 🤝 INTEGRATION CONTRACT (FROZEN)

This is the **exact data format** that Hemang's code (Stage 2) must output, and Sanchit's code (Stage 3) will consume. **Do NOT modify without both agreeing.**

```python
from src.common.models import PipelineOutput, PipelineMode, AudioStream

# Hemang produces this:
output = PipelineOutput(
    mode=PipelineMode.MODE_C,          # "A", "B", or "C"
    timestamp=1748350000.0,            # time.time()
    audio_streams=[
        AudioStream(
            stream_id=0,
            audio=np.ndarray,          # MUST be float32, 16kHz, mono
            sample_rate=16000,         # MUST be 16000
            speaker_id="hemang",       # "hemang", "sanchit", or "unknown"
            speaker_confidence=0.92,   # 0.0 to 1.0
            duration_seconds=3.5       # length of clip
        ),
        AudioStream(
            stream_id=1,
            audio=np.ndarray,
            sample_rate=16000,
            speaker_id="sanchit",
            speaker_confidence=0.87,
            duration_seconds=3.2
        )
    ],
    scene_complexity_score=0.78,       # 0.0 to 1.0
    vad_confidence=0.95,
    wakeword_confidence=0.88,
    overlap_probability=0.72,
    noise_floor_db=-35.2
)

# Sanchit consumes it via:
from src.pipeline import CanaryPipeline
result = pipeline.process(output)
```

### Rules:
| Rule | Detail |
|------|--------|
| Audio format | `np.ndarray`, `dtype=float32`, 16kHz sample rate, mono channel |
| Mode A/B | 1 stream in `audio_streams` |
| Mode C | 2 streams in `audio_streams` |
| Speaker ID | Must be resolved by CAM++ BEFORE handoff |
| Max duration | 10 seconds per clip |
| Completeness | Output must be fully populated — no partial/incremental sends |

---

## 📅 Timeline & Milestones

```
Week 1 (Days 1-7):    PARALLEL DEVELOPMENT — Zero dependency
  Hemang: Audio buffer → VAD → WakeWord → MatchboxNet
  Sanchit: ASR standalone → MCP tools → SLM setup → Redis/FAISS

Week 2 (Days 8-14):   INTEGRATION PHASE
  Hemang: TIGER → CAM++ → Pipeline assembly
  Sanchit: Arbitration → RBAC → Integration bridge → UI
  📌 Day 10-11: CRITICAL — First integration test

Week 3 (Days 15-21):  POLISH + DEMO
  Both: Integration testing → Debug → Polish → Demo recording
  📌 Day 18: Demo dry-run
  📌 Day 20-21: Final video recording
```

### Checkpoints

| Day | What | Who |
|-----|------|-----|
| **Day 2** | Freeze `PipelineOutput` schema | Both |
| **Day 7** | Independent modules working | Both |
| **Day 10-11** | **First real integration** — Hemang passes TIGER output → Sanchit's ASR → text | Both |
| **Day 14** | Full end-to-end pipeline working | Both |
| **Day 18** | Demo dry-run | Both |
| **Day 20-21** | Final video recording + submission prep | Both |

---

## 🏠 Project Structure

```
The-Canary/
├── src/
│   ├── common/           # Shared: data models, config
│   │   ├── models.py     # PipelineOutput, TranscriptionResult, ArbitrationDecision
│   │   └── config.py     # Central configuration
│   ├── stage0/           # 👤 HEMANG: VAD, WakeWord
│   ├── stage1/           # 👤 HEMANG: MatchboxNet, SCS Router
│   ├── stage2/           # 👤 HEMANG: TIGER, CAM++
│   ├── asr/              # 👤 SANCHIT: ASR Engine (sherpa-onnx)
│   ├── arbitration/      # 👤 SANCHIT: Conflict resolution, RBAC
│   ├── agent/            # 👤 SANCHIT: MCP Server, SLM (Ollama)
│   ├── execution/        # 👤 SANCHIT: Redis state store, FAISS, queue
│   ├── ui/               # 👤 SANCHIT: Demo terminal UI
│   ├── pipeline.py       # Main orchestrator (both contribute)
│   └── mock_pipeline.py  # Mock data generator (for parallel dev)
├── models/               # Model weights (downloaded, not committed)
├── data/test_audio/      # Test .wav files (not committed)
├── tests/                # Integration tests
├── docs/
│   ├── implementation_plan.md   # Full technical plan
│   ├── project_status_and_tasks.md  # THIS FILE
│   └── ax.md             # Agentic AI docs (required for submission)
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

---

## ⚠️ Critical Reminders

1. **Parameter budget**: Total core frontend < 5M params. We're at ~2.7M — well within budget.
2. **No cloud APIs**: Everything runs locally. No Google/OpenAI/AWS calls.
3. **Open source only**: All components MIT/Apache 2.0/BSD licensed.
4. **Demo must show 3 scenarios**:
   - Conflicting commands → RBAC resolves
   - Parallel non-conflicting commands → both execute
   - Background chatter rejection → system ignores ambient speech
5. **Pre-record fallback audio**: In case live mic demo fails.
6. **Git history matters**: Judges check commit history — make meaningful commits, not one giant push.
