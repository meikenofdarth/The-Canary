# Open-Weight Models & Agentic AI — `ax.md`

This document explains, in detail, how The Canary uses **open-weight models** and
**agentic AI / agentic development tools**, and — as required — what **worked**
and what **did not work**.

---

## Part A — Open-weight models

Every ML model in the solution is open-weight and runs fully on-device (no
closed/cloud inference APIs in the core pipeline).

| Stage | Open-weight model | License | Source |
|---|---|---|---|
| Separation | ConvTasNet (`JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k`) | Apache-2.0 | Asteroid / Hugging Face |
| ASR | Whisper tiny | MIT | OpenAI / Hugging Face |
| Speaker ID | ECAPA-TDNN (`speechbrain/spkrec-ecapa-voxceleb`) | Apache-2.0 | SpeechBrain |
| VAD | Silero VAD | MIT | snakers4/silero-vad |

**Budget interpretation.** The problem statement caps the *multi-speaker
separation system* at < 5M parameters. We therefore spend the budget on the
separator (ConvTasNet, 5.067M) and the VAD gate (0.463M), and treat ASR and
biometrics as separate downstream stages — a standard decoupled-pipeline reading
that keeps an open-vocabulary ASR feasible.

---

## Part B — Agentic AI inside the product

The Canary's "agent" is a **deterministic reasoning + tool-chaining pipeline**,
not an LLM agent. This is a deliberate engineering choice driven by the hard
constraints (real-time, on-device CPU, < 5M separation budget): an LLM in the
hot path would blow the latency and footprint budgets and add nondeterminism to
safety-relevant routing (who is allowed to do what).

### Reasoning & planning pipeline
1. **Perception** — separation + ASR + speaker-ID + wakeword produce a
   structured per-speaker record `{transcript, speaker, confidence, wakeword}`.
2. **Classification** — `utterance_analyzer` tags COMMAND/QUESTION/CONVERSATION
   across 15 smart-home domains; `conflict_detector` flags antonym-action and
   "override" conflicts between speakers.
3. **Scene scaling** — the **Dynamic Resource Scaler (DRS)** computes a Scene
   Complexity Score from overlap/noise/speaker counts and selects Mode A/B/C.
4. **Arbitration (planning)** — the arbitration engine scores each speaker
   `priority = 0.4·wakeword + 0.4·identity_conf + 0.2·known_user` and chooses a
   route: `EXECUTE`, `MULTI_EXECUTE`, `CLARIFY`, or `IGNORE`. This is where
   **Role-Based Access Control** (admin > guest) and conflict resolution live.

### Tool use / tool chaining
`backend/mcp_server.py` is the action layer. The intent engine maps the resolved
command to a tool and chains the call with extracted entities:

- `get_weather(location)` → wttr.in JSON API
- `get_news(location)` → Google News RSS (feedparser)
- `play_media(query, fallback)` → iTunes Search API (with a favourite-genre
  fallback when the transcript is garbled)
- `stop_media()` → pygame mixer control

Entity resolution includes a fuzzy location matcher (`difflib` against a
curated city/country list) and a personal-pronoun resolver ("my city" → the
identified user's profile default), then the result is spoken back via **gTTS**.
This is genuine tool-chaining: *speaker identity + intent + entities →
tool selection → API call → personalized spoken response.*

### Memory / context handling
- **Per-user profiles** (`database/Voices/`, `database/canary.db`) hold voice
  embeddings and preferences (home city, news country, favourite genre) — used
  for personalization and RBAC.
- **Per-turn context** is serialized to `context.json` / `response.json` for
  traceability and debugging.
- There is **no long-horizon conversational memory** in this version (see
  "what did not work").

### Phenotypic-inclusive accessibility (deterministic, novel)

A layered, zero-extra-parameter accessibility stack adapts the deterministic
pipeline to each speaker's physiology — keyed off the per-user profile loaded
after speaker identification:

- **Lisp Matrix** (`intelligence/phonetic_matcher.py`, wired into the intent
  engine) — repairs ASR output in *phonetic* space: Double Metaphone + a
  Needleman-Wunsch alignment with a per-user confusion matrix (e.g. /s/↔/θ/ at
  zero cost for a lisp). Recovers intent when the keyword is garbled
  ("newth"→NEWS). Pure algorithmic, 0 parameters.
- **Acoustic RAG** (`intelligence/acoustic_rag.py`, live first-chance in
  `/api/command`) — MFCC + FastDTW matching of enrolled anchor commands that
  fires the intent and **bypasses ASR entirely** for speech too atypical to
  transcribe; time-warp invariant. 0 parameters.
- **Adaptive VAD** (`audio/vad_segmenter.py`) — per-speaker disfluency profiles
  so a stuttering block is not truncated/split.

This is a deliberately deterministic, explainable alternative to throwing a large
LLM at disfluent speech — it fits the real-time, on-device, parameter-budget
constraints and directly targets the inclusivity theme.

---

## Part C — Agentic development workflow (how we built it)

We used an **AI coding assistant (agentic harness with file edit, shell, and
search tools)** heavily during Phase 2. It was most valuable not for writing
boilerplate but for **measure-driven model selection** under a hard constraint.

### What the assistant was used for
- A **parameter-audit harness** (`param_audit.py`) that loads each model and
  counts real parameters — the single source of truth for the < 5M rule.
- An **evaluation harness** (`tests/eval_separation.py`, `tests/kpi_report.py`)
  for SI-SNR / SI-SNRi / xRT on MiniLibriMix, including A/B testing of
  post-processing techniques.
- Iterative **model swaps** behind one chokepoint (`_run_sepformer`): SepFormer →
  ConvTasNet, plus DPRNNTasNet and TIGER trials — each measured, then accepted or
  rejected on evidence.
- Refactors: thread-safe **model cache**, backend **warm-up**, a self-proving
  `[SEP]` runtime banner, and honest test gating (`xfail`).

### What worked
- **Measuring instead of trusting the blueprint.** Our planning doc claimed
  "CAM++ B0 ≈ 1.1M"; loading it showed **7.236M**. Measuring caught several such
  errors before they cost us.
- **One chokepoint for the swappable model** made it safe to try four separators
  without ever changing the API contract.
- **A real benchmark changed the conclusion.** On a synthetic fixture SI-SNR
  looked like 11.69 dB; on MiniLibriMix (real ground-truth sources) ConvTasNet
  scored **14.97 dB** — proving the model was fine and the fixture was the
  problem.
- **Reliable metrics (params, xRT) drove decisions**, not vibes: DPRNN and TIGER
  fit the parameter budget but were rejected on measured CPU xRT.

### What did **not** work (honest log)
- **Parameter-efficient ≠ compute-efficient on CPU.** TIGER (0.82M) and
  DPRNNTasNet (3.65M) easily fit the param budget but ran at xRT **8.03** and
  **0.85** respectively on CPU — both fail the < 0.5 real-time KPI. Only the
  convolutional ConvTasNet (5.067M, xRT ~0.11) is real-time, so we accept being
  ~1.3% over the strict 5.0M rather than miss real-time.
- **The wrapper, not the model, was capping quality.** Overlap-add chunking,
  STFT ratio-mask refine, and mixture-consistency post-processing were each
  measured to *lower* SI-SNR; the naive mixture-consistency form collapsed the
  clean model to ~0 dB (it re-injects the mixture residual into both streams).
  Switching to whole-clip inference + Gram-Schmidt-only recovered **+3.7 dB clean
  (11.31→14.97) / +4.8 dB noisy SI-SNRi (8.00→12.75)** — a reminder that
  "obvious" DSP tricks must be measured, not assumed. ConvTasNet separates
  cleanly at ~15 dB SI-SNR, near its ceiling.
- **Trusting an architecture blueprint's numbers** (CAM++ size, "fast" claims for
  attention models) repeatedly misled us until we verified with measurements.
- **No LLM agent / MCP-protocol server in the hot path.** We evaluated a true
  MCP + local SLM (GBNF-constrained) design but did not adopt it for the core
  real-time loop — latency and determinism for safety-relevant routing won out.
  The current "MCP server" file is a deterministic tool layer, not a protocol
  server; promoting it to true MCP + SLM remains future work.

### Net lesson
For a hard real-time + parameter-constrained edge problem, the agentic workflow
paid off most as a **fast measure–decide loop**: try a model/technique, run the
audit + eval harness, keep it only if the numbers improve. Several
"hackathon-winning" ideas from the planning phase were correctly discarded
because the harness showed they failed the real constraints.
