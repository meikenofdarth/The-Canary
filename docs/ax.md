# Agentic AI & Open-Weight Models

Here's a breakdown of how we approached the open-weight constraints and built our agentic workflows for The Canary.

## Part A: Open-Weight Models

We made sure every machine learning model in this project is strictly open-weight and runs locally on-device. There are no closed APIs or cloud dependencies in the core pipeline.

| Stage | Model Used | License | Source |
|---|---|---|---|
| **Separation** | ConvTasNet (`JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k`) | Apache-2.0 | [Asteroid Hub](https://huggingface.co/JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k) |
| **ASR** | Whisper Base | MIT | [OpenAI](https://huggingface.co/openai/whisper-base) |
| **Speaker ID** | ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`) | Apache-2.0 | [SpeechBrain](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) |
| **VAD Gate** | Silero VAD | MIT | [snakers4/silero-vad](https://github.com/snakers4/silero-vad) |

**Meeting the Budget:** The hackathon guidelines cap the multi-speaker separation system at under 5 million parameters. We spent this budget entirely on the separator itself (ConvTasNet is ~5.06M) and the VAD gate (0.46M). We treat the ASR and biometrics as independent downstream components, which is pretty standard for edge pipelines. This lets us use a solid ASR like Whisper without breaking the separation budget.

## Part B: Product Architecture & Reasoning

Since we're building for edge CPUs where real-time execution (xRT < 0.5) is critical, we couldn't just throw a massive, slow LLM in the hot path. Instead, we built a fast, deterministic reasoning pipeline.

### Reasoning & Planning
The system's reasoning happens in a few fast steps:
1. **Perception:** The separation, ASR, biometrics, and wakeword modules digest the audio and spit out a structured record: `{transcript, speaker, confidence, wakeword}`.
2. **Classification & Conflict Detection:** An `utterance_analyzer` categorizes the intent. We also built a `conflict_detector` that checks if speakers are giving contradictory commands (like Speaker A saying "Turn on" and Speaker B saying "Turn off").
3. **Arbitration (Planning):** The arbitration engine uses a basic Role-Based Access Control (RBAC) system. It calculates a priority score based on biometric confidence, wakeword usage, and whether the user is enrolled. Finally, it decides the execution route: `EXECUTE`, `MULTI_EXECUTE`, `CLARIFY`, or `IGNORE`.

### Tool Use & Chaining
We map intents to actions using strict tool chaining, similar to how an MCP server works. The intent engine parses entities and hands them off to backend tools:
- `get_weather(location)` -> hits the wttr.in API.
- `get_news(location)` -> parses Google News RSS.
- `play_media(query)` -> searches iTunes.

This chain is fully context-aware. It resolves things like "my city" by looking up the identified speaker's profile in the database.

### Memory & Context
- **Long-term Context:** We keep persistent profiles (`database/Voices/`, `database/canary.db`) that store voice embeddings and personal preferences (home city, favorite music, etc.).
- **Short-term Memory:** The context for each turn is dumped into `context.json` and `response.json`. This acts as a scratchpad so the system can keep track of state when handling multiple speakers at once.

## Part C: Development & Multi-Agent Orchestration

While the final product is highly deterministic, the actual *development* of this codebase relied heavily on multi-agent orchestration.

### Coding Assistants & Workflows
We used an AI coding assistant framework during the hackathon. We set up an orchestrating agent that passed specialized tasks to subagents:
- `docs_writer`: Handled keeping the technical documentation updated and consistent.
- `frontend-builder`: Took care of building the React web dashboard.
- `mobile-builder`: Worked on the React Native mobile app in parallel.

### Customizing the Workspace
We tuned the agentic harness specifically for this project. 
- We gave the frontend subagent skills (like `modern-web-guidance`) to automatically pull in modern CSS patterns.
- We set strict workspace rules that forced the agents to constantly check the < 5M parameter cap and the xRT performance targets.

### What Worked Well
1. **Multi-Agent Velocity:** Having separate agents tackle the web dashboard and mobile app while the main agent focused on the heavy Python DSP pipeline was huge. We got a full ecosystem running much faster than we normally would have.
2. **Measure-Driven Tooling:** We had the agent write its own evaluation tools (`kpi_report.py`, `eval_separation.py`). By hooking these tools directly into the workflow, the agent could automatically test models against the CPU constraints and reject ones that were too heavy.
3. **Artifact Planning:** Forcing the AI to write out an `implementation_plan.md` before doing major refactors kept everything on track and prevented messy rewrites.

### What Didn't Work
1. **LLM Agents for Core Routing:** Originally, we tried using a local SLM for the intent router to handle raw MCP protocol stuff. It was just too slow. For edge hardware, building a deterministic tool-chaining pipeline turned out to be way more practical.
2. **Trusting Paper Parameter Counts:** We quickly learned we couldn't trust the parameter sizes listed in research papers. For example, CAM++ was listed at ~1.1M but actually measured closer to 7.2M when we loaded it. Building an automated parameter audit script saved us from a disqualification.

Using coding assistants to write the software, but keeping the actual product deterministic and tool-based, ended up being the perfect sweet spot for this project.
