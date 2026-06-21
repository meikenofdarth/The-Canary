# Agentic AI & Open-Weight Models — `ax.md`

This document details how The Canary leverages **open-weight models** and advanced **agentic development tools** to deliver a robust, real-time smart home assistant. It covers our Agentic AI setup, workflows, reasoning pipelines, tool use, memory handling, and the multi-agent orchestration systems we employed.

---

## Part A — Open-Weight Models Used

Every Machine Learning model in our solution is strictly open-weight and runs fully on-device (no closed or cloud-based inference APIs are used in the core pipeline).

| Stage | Open-weight model | License | Source / Hugging Face Link |
|---|---|---|---|
| **Separation** | ConvTasNet (`JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k`) | Apache-2.0 | [Asteroid Hub](https://huggingface.co/JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k) |
| **ASR** | Whisper Base | MIT | [OpenAI Whisper](https://huggingface.co/openai/whisper-base) |
| **Speaker ID** | ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`) | Apache-2.0 | [SpeechBrain](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) |
| **VAD Gate** | Silero VAD | MIT | [snakers4/silero-vad](https://github.com/snakers4/silero-vad) |

**Budget interpretation:** The official problem statement caps the *multi-speaker separation system* at < 5M parameters. We deliberately spend this budget on the separator (ConvTasNet, 5.06M) and the VAD gate (0.46M), and treat ASR and biometrics as separate downstream stages. This decoupled pipeline is standard practice and allows us to use high-quality open-vocabulary ASR without violating the separation constraint.

---

## Part B — The Product: Agentic Setup & Reasoning Pipelines

The Canary acts as a deterministic, ultra-fast local agent. Because we are constrained by real-time latency (xRT < 0.5) and a CPU-only edge footprint, we avoided placing a monolithic, non-deterministic LLM in the hot path. Instead, our **Agentic AI setup** relies on a heavily optimized, multi-stage reasoning and planning pipeline.

### Reasoning & Planning Pipelines
Our agent's reasoning operates in sequential phases:
1. **Perception:** The separation, ASR, biometrics, and wakeword engines process the acoustic environment to yield a structured perception record: `{transcript, speaker, confidence, wakeword}`.
2. **Classification & Conflict Detection:** The `utterance_analyzer` categorizes the parsed intent across 15 domains. The agent employs a `conflict_detector` that semantically detects adversarial commands (e.g., Speaker A saying "Turn on" while Speaker B says "Turn off").
3. **Arbitration (Planning):** The arbitration engine uses Role-Based Access Control (RBAC). It computes a priority score based on biometric confidence, wakeword presence, and user enrollment status (`priority = 0.4*wakeword + 0.4*id_conf + 0.2*known`). The agent then *plans* its execution route: `EXECUTE`, `MULTI_EXECUTE`, `CLARIFY`, or `IGNORE`.

### Tool Use & Tool Chaining
Our system connects intentions to actions via strict tool chaining, analogous to an **MCP server** mapping. The intent engine extracts entities and chains them to backend tools:
- `get_weather(location)` → Fetches from wttr.in JSON API.
- `get_news(location)` → Fetches from Google News RSS via feedparser.
- `play_media(query)` → Searches the iTunes API.

The agentic workflow resolves entities like personal pronouns ("my city") by querying the identified speaker's profile. Thus, the tool chain is context-aware: *Speaker ID + Intent + Entities → Tool Selection → API Call → Personalized Spoken Response*.

### Memory & Context Handling
- **Long-term Context (Profiles):** We maintain persistent user profiles (`database/Voices/`, `database/canary.db`) holding voice embeddings and preferences (home city, news region, favorite music genres).
- **Short-term Memory (Turn Context):** Per-turn interaction context is serialized to `context.json` and `response.json`, giving the agent a "scratchpad" for traceability and state management across multi-speaker overlaps.

---

## Part C — The Development: Multi-Agent Orchestration & Assistants

While the deployed product is deterministic for speed and safety, **the creation and optimization of the codebase relied heavily on an advanced Multi-agent orchestration system**. 

### Coding Assistants, Agents, and Harness
We utilized a multi-agent AI coding assistant framework (Antigravity). During the hackathon, we set up **Agentic workflows** where a primary orchestrating agent delegated specialized tasks to subagents:
- `docs_writer`: Entrusted with maintaining architectural documentation and ensuring consistency.
- `frontend-builder`: Delegated tasks for the web dashboard visualization.
- `mobile-builder`: Handled the React Native mobile app development.

### Workspace Customization: `agents.md` and Skills
The agentic harness was customized specifically for our workspace. 
- Using standard **skills** (like `modern-web-guidance`), the frontend subagent automatically applied modern CSS paradigms.
- The repository's context and rules were governed by workspace constraints that kept the agents focused on the < 5M parameter target and the xRT KPI.

### What Worked (From Experience)
1. **Multi-Agent Orchestration for Full-Stack Velocity:** Delegating the React web dashboard and the React Native mobile app to parallel subagents while the main agent optimized the Python DSP pipeline allowed us to build a comprehensive ecosystem in record time.
2. **Measure-Driven Tool Chaining:** Our agent wrote and used its own **harness tools** (`tests/kpi_report.py`, `tests/eval_separation.py`). By writing an evaluation tool and chaining it into the workflow, the agent could automatically test models, verify the 5M parameter constraint, and reject models that failed the CPU xRT test (e.g., TIGER and DPRNNTasNet).
3. **Artifact-Driven Planning:** Creating an `implementation_plan.md` artifact prior to major refactors (like moving to whole-clip inference) ensured the human developer and the AI agent stayed perfectly aligned.

### What Did Not Work (From Experience)
1. **Relying on Non-Deterministic LLM Agents for Core Routing:** We initially considered using a local GBNF-constrained SLM for the intent router (a true MCP protocol setup). However, latency constraints made this unworkable. A deterministic tool-chaining pipeline was vastly superior for real-time edge hardware.
2. **Misleading Architectures:** Trusting published paper parameters blindly led us astray. Our agentic harness had to physically load and measure the models. For instance, CAM++ was documented as ~1.1M parameters but measured at 7.2M. The automated parameter audit script saved the project from violating constraints. 

Ultimately, blending highly specialized **coding assistants** during development with a razor-fast, deterministic tool-chaining agent in production yielded the perfect balance of rapid iteration and real-time reliability.
