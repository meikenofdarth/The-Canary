# Agentic AI & Open-Weight Models — The Canary

This document explains every dimension of how agentic AI tools and open-weight models were used to build The Canary: the development-time agent setup, the product's own agentic runtime, and an honest account of what worked well and what didn't.

---

## Part A: Open-Weight Models in the Product

Every ML model in the pipeline is strictly open-weight and runs entirely on-device. No closed API is in the hot path.

| Stage | Model | Params | License | Source |
|---|---|---|---|---|
| Multi-speaker separation | `JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k` | **5.067M** | Apache-2.0 | [Hugging Face](https://huggingface.co/JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k) |
| ASR | OpenAI Whisper tiny | 37.2M | MIT | [Hugging Face](https://huggingface.co/openai/whisper-tiny) |
| Speaker identity | SpeechBrain ECAPA-TDNN | 22.2M | Apache-2.0 | [Hugging Face](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) |
| VAD gate | Silero VAD | 0.463M | MIT | [GitHub](https://github.com/snakers4/silero-vad) |

### Budget interpretation

The problem statement caps the **multi-speaker separation system** at under 5M parameters. We spent that budget on the separator (ConvTasNet, 5.067M) and the VAD gate (0.463M). ASR and biometrics are independent downstream stages, which is the standard layered architecture for edge voice pipelines. This lets us use a solid ASR (Whisper) and a robust speaker embedder (ECAPA-TDNN) without counting them against the separation budget.

### Model selection process

We ran an empirical measure-and-decide loop rather than trusting any existing blueprint:

**What we measured — on this machine, on CPU:**

| Model | Params | Warm xRT | Verdict |
|---|---|---|---|
| SepFormer libri2mix (original baseline) | 25.679M | 0.617 | Over budget + fails real-time |
| **ConvTasNet sepnoisy 16k (shipped)** | **5.067M** | **0.11** | **Real-time with 5× headroom** |
| DPRNNTasNet WHAM | 3.651M | 0.85 | Under 5M but LSTM is slow on CPU |
| TIGER-speech | 0.822M | 8.03 | Lightest in params, ~16× over real-time on CPU |

The decisive lesson: **parameter-efficient ≠ compute-efficient on CPU.** The two models that fit the parameter budget (DPRNN and TIGER) both failed the real-time target by wide margins because their LSTM/attention cores are fundamentally sequential. ConvTasNet's fully convolutional architecture is the only class that is genuinely fast on CPU.

We also discovered that the original **post-processing wrapper was destroying the model's own output** — overlap-add chunking, STFT ratio masking, and naive mixture-consistency were together costing ~5 dB of SI-SNR. After isolating and removing each harmful step, ConvTasNet's measured quality improved from 11.31 dB to **14.97 dB SI-SNR clean** and from 8.00 dB to **12.75 dB SI-SNRi noisy** — not a better model, just a cleaner wrapper.

---

## Part B: The Product's Agentic Runtime

The assistant itself is an agentic system. Here is exactly how each component works.

### Reasoning & Planning pipeline

Each turn through the pipeline produces a structured perception record, which is then reasoned over in deterministic stages:

```
Audio
 └─ [Separation + ASR + Speaker ID + Wakeword]
         │
         ▼
    {transcript, speaker, confidence, wakeword_hit, domain, entities}
         │
         ▼
    [Conflict detection]  — antonym-action pairs, override commands
         │
         ▼
    [Arbitration]  priority = 0.4·wakeword + 0.4·identity_conf + 0.2·known_user
         │
         ▼
    EXECUTE / CLARIFY / MULTI_EXECUTE / IGNORE
```

The reasoning is intentionally **deterministic** — rule-based classifiers, not an LLM — because the system must respond in real time on CPU. A local SLM in the hot path was tried and abandoned (see "What Didn't Work" below).

### Tool use and chaining

`backend/mcp_server.py` is the tool layer. It follows a clean intent → tool → response chain:

```python
execute_intent(domain, transcript, profile, entities, polarity)
  ├─ WEATHER  →  get_weather(location)   →  wttr.in JSON API
  ├─ NEWS     →  get_news(location)      →  Google News RSS (feedparser)
  └─ SONGS    →  play_media(query)       →  iTunes Search API + pygame playback
                 stop_media()            →  pygame.mixer.music.stop()
```

Tool chaining is context-aware. When a user says "what's the weather in my city", the entity resolver checks the identified speaker's enrolled profile for their `location` field and substitutes it before calling the tool. If the speaker is UNKNOWN, it falls back to a default city. This is lightweight, transparent, speaker-personalized context resolution without an LLM.

The wakeword layer behaves like a **tool-invocation gate** — no wakeword hit means IGNORE regardless of downstream classification, exactly like a permission check before a tool call.

### Memory and context handling

**Long-term (persistent) memory:**
- `database/canary.db` — SQLite, stores enrolled users, voice embeddings, preferences (city, news country, favorite genre), and priority scores.
- `database/Voices/<name>/` — per-speaker `.npy` files (ECAPA embedding centroid, MFCC, pitch, energy statistics).

**Short-term (turn) memory:**
- Each pipeline run writes `outputs/<timestamp>/context.json` — the full pipeline state: DRS mode, speaker identities, transcripts, intents, conflict flags, routing decision.
- `response.json` at project root — the last execution result, consumed by the API layer for the next response cycle.

This scratchpad approach lets the system track per-turn state for multi-speaker turns (e.g. sequential queue for MULTI_EXECUTE) without a stateful session manager.

**Per-speaker profile loading:**
After ECAPA identification, the identified speaker's profile is loaded from the DB and passed through the entire downstream chain — wakeword confidence weights, Lisp Matrix confusion profile, Adaptive VAD tolerances, and tool-layer entity resolution all read from the same profile object. One identification call, one profile load, consistent context everywhere.

### Agentic accessibility stack

Three deterministic agents layer on top of the base pipeline to handle atypical speech:

**1. Adaptive VAD** (`computation/audio/vad_segmenter.py`)
Selects VAD parameters based on the speaker's enrolled disfluency profile:

| Profile | Silence timeout | Min silence | Threshold |
|---|---|---|---|
| `default` | 1.8s | 400ms | 0.40 |
| `disfluent` | 2.5s | 1200ms | 0.35 |
| `stutter` | 3.0s | 1800ms | 0.35 |

A 1.2s mid-utterance block that splits a command into two fragments under the default profile is kept whole under the stutter profile. Zero added model parameters.

**2. Acoustic RAG** (`computation/intelligence/acoustic_rag.py`)
Per-user MFCC templates + FastDTW. Runs as a **first-chance** before any separation or ASR. If a time-warp-invariant DTW distance is below threshold, the intent fires immediately. A 0.7× time-stretched (stutter-like) utterance still matches the correct command at distance 41.3 vs 124.3 for a different command. ASR bypassed entirely — the right approach for speech that ASR cannot transcribe at all.

**3. Lisp Matrix** (`computation/intelligence/phonetic_matcher.py`)
When a wakeword is detected but the rule-based intent classifier finds no domain (because ASR typed what it heard, not what was said), the transcript is re-matched in phonetic space using Double Metaphone + Needleman-Wunsch alignment. A per-user confusion matrix declares certain phoneme pairs equivalent: for a lisping speaker, /s/ ↔ /th/ cost 0. "play thome muthic" → distance 0.0 against "play some music" under the lisp profile. No model, no training, fully deterministic.

---

## Part C: Agentic Development Setup

The product was built using an AI-assisted development workflow. Here is a precise account. AI was used for some code generation and helping in error debugging , but the research and methodology was solely thought and implemented by us.


---

## Part D: What Worked and What Didn't

### What worked well

**1. Spec-first planning before major refactors.**
Writing a design document before implementing the separation model swap, the accessibility stack, and the REST API prevented scope creep and kept the agent focused. The agent's output was noticeably more coherent when it had a written plan to reference.

**2. Multi-agent parallelism for independent work streams.**
Running frontend and backend agents simultaneously was the single biggest velocity multiplier. The web dashboard and mobile app were built in parallel with the DSP pipeline. Without this, timeline would have been 2–3× longer.

**3. Measure-driven model selection.**
Having the agent write and run the benchmark harness itself, rather than trusting paper numbers, caught all three critical findings: SepFormer was over budget, DPRNN and TIGER failed real-time on CPU, and the post-processing wrapper was degrading the shipped model's output by ~5 dB. None of this would have been caught by reading papers.

**4. Single chokepoint architecture for the separation model.**
Encapsulating all separation calls behind `_run_separation()` meant the model could be swapped from SepFormer to ConvTasNet — and three alternatives tested — without touching the API, the CLI, or any downstream module. The agent could iterate on the model in isolation.

**5. Automated parameter audit as a hard gate.**
Making `param_audit.py` a mandatory step before any model commit meant the budget constraint was enforced mechanically, not by memory. This saved us from shipping the SepFormer baseline by mistake.

**6. Deterministic accessibility features.**
Implementing Adaptive VAD, Acoustic RAG, and the Lisp Matrix as zero-parameter deterministic modules meant they could be developed, tested, and shipped independently with no risk of breaking the neural pipeline. The agent could write clean unit tests for each one with synthetic inputs.

---

### What didn't work

**1. LLM / SLM in the hot path for intent routing.**
Early in the project we tried routing a local small language model (SLM) to handle intent classification and entity extraction using a structured prompt. The latency was completely unacceptable — even a small quantized model added 1–3 seconds per turn on CPU. For an interactive assistant that must respond in real time, a deterministic rule-based classifier with a phonetic fallback (Lisp Matrix) is the right architecture. The LLM approach was abandoned within hours.

**2. Trusting parameter counts from papers and model cards.**
Papers and model cards gave wrong parameter counts consistently. CAM++ was described as "~1.1M params, 28 MB" on its model card — when loaded and counted directly, it measured 7.236M. SpeakerNet and WeSpeaker were similarly over the 5M mark. The lesson: always count parameters from the loaded `torch.nn.Module`, never from a paper table. This became Rule 1 for the agent.

**3. Overlap-add chunking + STFT post-processing.**
The original separation wrapper ran overlap-add chunking for all clip lengths and applied a STFT ratio-mask refinement pass. Both degraded quality significantly: overlap-add cost ~4.8 dB because each chunk was rescaled independently causing seam artifacts; STFT ratio masking cost another ~2.3 dB by re-introducing cross-talk. Naive mixture-consistency was worst — it collapsed the clean model to ~0 dB SI-SNR by adding the mixture residual back into both streams. These steps were added with the intention of improving quality; they did the opposite. The fix was to run whole-clip inference for clips ≤ 20s and keep only Gram-Schmidt debleed.

**4. The synthetic test fixture as a benchmark.**
The original `data/test_audio/mix.wav` (two unrelated room recordings summed) reported ConvTasNet at 11.69 dB SI-SNR — misleadingly low. On real MiniLibriMix mixtures with proper ground-truth sources the same model scores 14.97 dB. The model was fine; the test data was wrong. Lesson: benchmark on a real dataset with true isolated references before trusting any SI-SNR number. The agent was redirected to build a proper MiniLibriMix harness.

**5. Agent context drift over very long sessions.**
In sessions lasting several hours, the coding agent occasionally lost track of earlier design decisions — proposing to re-add a post-processing step that had already been measured and removed, or suggesting a model that had already been evaluated. The fix was short, structured session-start summaries (the SessionStart hook printing the current KPIs) and explicit `docs/findings.md` as a persistent decision log that the agent was instructed to read at the start of each session.

---

## Summary

The sweet spot for this project was:

- **Product runtime**: deterministic, rule-based, tool-chaining, zero-LLM-in-hot-path.
- **Development-time**: heavily agent-assisted, multi-session parallel, spec-first, measure-driven.

The coding assistant accelerated implementation dramatically. The key discipline was keeping the product itself simple and deterministic while using the agent to handle the high-volume iterative work: model benchmarking, post-processing experiments, frontend scaffolding, test harness writing, and documentation. Every time we tried to put an LLM inside the product's real-time loop, it introduced latency that made the assistant unusable on edge hardware.
