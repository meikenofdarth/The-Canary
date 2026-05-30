# The Canary — Technical Architecture

## System Overview

The Canary is a real-time multi-speaker voice assistant designed for smart home environments. It handles overlapping speech, speaker verification, and conflicting command arbitration — all running on-device with no cloud dependency.

## Pipeline Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Microphone  │────▶│    VAD +     │────▶│    TIGER     │
│  Input (16k) │     │  WakeWord    │     │  Separation  │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                     ┌──────────────┐     ┌───────▼───────┐
                     │   CAM++      │◀────│  SenseVoice   │
                     │  Speaker ID  │     │    ASR        │
                     └──────┬───────┘     └───────┬───────┘
                            │                     │
                     ┌──────▼─────────────────────▼───────┐
                     │       Arbitration Engine            │
                     │  (RBAC + Conflict Detection)       │
                     └──────────────┬──────────────────────┘
                                    │
                     ┌──────────────▼──────────────┐
                     │     MCP Tool Execution      │
                     │  (Smart Home Actions)       │
                     └──────────────┬──────────────┘
                                    │
                     ┌──────────────▼──────────────┐
                     │      Redis State Store      │
                     │  (Profiles, History, TTL)   │
                     └─────────────────────────────┘
```

## Module Inventory

| Module | File | Owner | Status |
|--------|------|-------|--------|
| VAD + WakeWord | `src/stage0/` | Hemang | In Progress |
| Scene Intelligence | `src/stage1/` | Hemang | In Progress |
| Source Separation | `src/stage2/` | Hemang | In Progress |
| ASR Engine | `src/asr/engine.py` | Sanchit | ✅ Complete |
| Arbitration | `src/arbitration/engine.py` | Sanchit | ✅ Complete |
| MCP Server | `src/agent/mcp_server.py` | Sanchit | ✅ Complete |
| SLM Agent | `src/agent/slm_agent.py` | Sanchit | ✅ Complete |
| State Store | `src/execution/state_store.py` | Sanchit | ✅ Complete |
| Speaker Index | `src/execution/speaker_index.py` | Sanchit | ✅ Complete |
| Execution Queue | `src/execution/queue.py` | Sanchit | ✅ Complete |
| Demo UI | `src/demo/` | Sanchit | ✅ Complete |
| Pipeline Orchestrator | `src/pipeline.py` | Shared | ✅ Complete |

## Data Flow Contract

The two engineers integrate through the `PipelineOutput` dataclass:

```python
@dataclass
class PipelineOutput:
    mode: PipelineMode          # A (clean), B (noisy), C (overlap)
    timestamp: float
    audio_streams: list[AudioStream]
    scene_complexity_score: float
    vad_confidence: float
    wakeword_confidence: float
    overlap_probability: float
    noise_floor_db: float
```

Engineer A produces this. Engineer B consumes it.

## Performance Targets

| Metric | Target | Achieved |
|--------|--------|----------|
| ASR Real-Time Factor | < 0.1 | 0.017-0.028 |
| SLM Inference | < 2s | 0.8-1.2s |
| E2E Latency (Mode A) | < 500ms | ~340ms |
| E2E Latency (Mode C) | < 2s | ~1.2s |
| Speaker Verification | > 0.9 cos sim | 0.994 |
| Memory (total) | < 2GB | ~1.5GB |

## Models Used

| Model | Task | Parameters | Format | Source |
|-------|------|-----------|--------|--------|
| SenseVoiceSmall | ASR | 234M | ONNX INT8 | [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) |
| Qwen2.5 1.5B | SLM Agent | 1.5B | Q4_K_M | [Ollama](https://ollama.com) |
| CAM++ B0 | Speaker Embedding | ~5M | ONNX | [3D-Speaker](https://github.com/alibaba-damo-academy/3D-Speaker) |
| MatchboxNet | Wake Word | ~75K | ONNX | [NeMo](https://github.com/NVIDIA/NeMo) |
| TIGER | Source Separation | ~2M | ONNX | [WeNet](https://github.com/wenet-e2e/wenet) |

Total parameter budget: < 5M (excluding SLM).
