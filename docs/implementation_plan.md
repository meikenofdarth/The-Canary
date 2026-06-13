# Canary Architecture Unification & Execution Integration

Hemang has successfully refactored the core acoustic pipeline! He introduced a much more robust approach:
1. **Segment-Level Separation:** Instead of passing the full 7s recording to SepFormer (which caused artifacts), he now chunks the audio using VAD and only runs separation on segments that contain overlapping speech.
2. **ECAPA-TDNN Speaker Tracking:** Instead of using the generic CAM++ model on dirty audio, he uses `speechbrain/spkrec-ecapa-voxceleb` to extract embeddings from clean segments, then clusters them and merges them into per-speaker audio tracks.
3. **C++ WakeWord Engine:** A highly optimized C++ engine for fuzzy wakeword matching.
4. **Context & Arbitration Engine:** A pure Python arbitration engine that calculates priority scores (wakeword confidence, identity confidence, enrolled user bonus) to decide whether to EXECUTE, CLARIFY, SEQUENTIAL, or IGNORE.

## The Gap

Because Hemang branched off from an older version of the repository, **all of our LLM Execution Engine code (the SLM Agent, FastMCP Tools, State Store, and Execution Queue) is missing from this branch.** Hemang's pipeline ends at the `arbitration_engine` — it prints out decisions like `EXECUTE` but doesn't actually call any tools.

As requested, I have completely overwritten the `main` branch with Hemang's branch. No old code was kept. 

## Proposed Changes

To complete the project and make The Canary fully functional end-to-end, we must build a new Execution Layer that natively plugs into Hemang's arbitration output.

### 1. Build the Execution Layer (`execution/`)
Create a new execution module that takes Hemang's arbitration decisions and executes them:
- **`execution/mcp_server.py`**: A FastMCP server containing the SmartHome tools (lights, thermostat, media, locks) and Calendar tools.
- **`execution/slm_agent.py`**: A lightweight local agent (e.g. using a small language model or structured tool calling) that takes the speaker's intent and executes the corresponding MCP tool.
- **`execution/queue.py`**: A queue manager to handle `SEQUENTIAL` executions (when multiple users issue valid, non-conflicting commands simultaneously) and `CLARIFY` routes.

### 2. Integrate with `run_canary.py`
Update Hemang's `run_canary.py` to pipe the output of `arbitration_engine.arbitrate()` directly into the Execution Layer.

#### [MODIFY] [run_canary.py](file:///Users/sanchitkumardogra/kaam/Samsung%20Ennovatex%20/run_canary.py)
- Import the new `ExecutionQueue`.
- After `context_engine` finishes, pass the `context.json` payload into the execution queue.

#### [NEW] [execution/__init__.py](file:///Users/sanchitkumardogra/kaam/Samsung%20Ennovatex%20/execution/__init__.py)
#### [NEW] [execution/mcp_server.py](file:///Users/sanchitkumardogra/kaam/Samsung%20Ennovatex%20/execution/mcp_server.py)
#### [NEW] [execution/slm_agent.py](file:///Users/sanchitkumardogra/kaam/Samsung%20Ennovatex%20/execution/slm_agent.py)
#### [NEW] [execution/queue.py](file:///Users/sanchitkumardogra/kaam/Samsung%20Ennovatex%20/execution/queue.py)

## Verification Plan
1. **Unit Tests**: Write tests for the `ExecutionQueue` to ensure it handles `EXECUTE`, `SEQUENTIAL`, and `CLARIFY` routes properly.
2. **End-to-End Test**: Record a dual-speaker overlapping audio file (e.g. "Turn on lights" and "Turn off thermostat"). Verify that Hemang's acoustic engine separates them, assigns them to profiles, and the Execution Layer successfully invokes both SmartHome tools.

> [!IMPORTANT]
> Since we completely discarded the old `main` branch as requested, I will rewrite the execution engine from scratch tailored specifically to Hemang's new arbitration output format. Please approve this plan so we can begin coding the final execution piece!
