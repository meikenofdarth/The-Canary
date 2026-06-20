# The Canary — Technical Documentation

Real-time, multi-user smart assistant for dynamic and noisy smart environments.
It separates up to three overlapping speakers from mono/stereo audio,
distinguishes commands from ambient chatter, identifies the speaker, resolves
multi-user conflicts, and returns a personalized spoken response — on commodity
CPU hardware.

## Documentation index

| Document | Contents |
|---|---|
| [`architecture.md`](architecture.md) | End-to-end pipeline, stage-by-stage detail, service topology, design decisions |
| [`tech_stack.md`](tech_stack.md) | Technical stack, OSS libraries (with links), models & datasets used |
| [`installation.md`](installation.md) | Install steps, user guide, and full KPI reproduction commands |
| [`ax.md`](ax.md) | **Open-weight models + agentic AI**: in-product agent, tool chaining, dev workflow, what worked / what didn't |
| [`lisp_matrix.md`](lisp_matrix.md) | **Lisp Matrix** — dynamic phonetic intent matching (accessibility/innovation feature) |
| [`acoustic_rag.md`](acoustic_rag.md) | **Acoustic RAG** — DTW command matching that bypasses ASR for severe speech (accessibility/innovation) |
| [`adaptive_vad.md`](adaptive_vad.md) | **Adaptive VAD** — per-speaker disfluency-aware silence thresholds (accessibility) |
| [`testing.md`](testing.md) | **How to run & test everything** — setup, run, full test suite, KPI reproduction |
| [`separation_results.md`](separation_results.md) | Measured KPIs + the model-selection benchmark/decision log |
| [`findings.md`](findings.md) | **Consolidated findings & decision log** — everything tried, measured, and decided across the project |
| [`implementation.md`](implementation.md), [`plan.md`](plan.md), [`walkthrough.md`](walkthrough.md) | Earlier design/implementation notes |

## Salient features

- **Sub-5M real-time separation** — Asteroid ConvTasNet (5.067M params), cached
  and warmed; warm-call **xRT ≈ 0.11** (target < 0.5).
- **Evidence-based model selection** — DPRNNTasNet and TIGER fit the param
  budget but were rejected on measured CPU latency; full log in
  `separation_results.md`.
- **Credible evaluation** — SI-SNR/SI-SNRi on real MiniLibriMix mixtures
  (14.97 dB clean / 12.75 dB SI-SNRi noisy), not a synthetic toy fixture.
- **Up-to-3-speaker handling** with speech-band ghost-stream rejection and
  Gram-Schmidt cross-talk suppression.
- **Personalized, identity-aware routing** — ECAPA-TDNN + classical feature
  fusion for speaker ID, with Role-Based Access Control in the arbitration
  engine.
- **Robust gating** — Silero VAD + energy pre-screen + phonetic (weighted-
  Levenshtein) wakeword matching to reject ambient chatter and STT errors.
- **Deterministic agentic tool layer** — weather / news / music tools chained
  from resolved intent, with spoken (gTTS) responses.
- **Lisp Matrix** — dynamic phonetic intent matching with per-user confusion
  matrices, so atypical speech (e.g. a lisp) is understood even when ASR fails
  (`docs/lisp_matrix.md`).
- **Acoustic RAG** — DTW-based command matching that bypasses ASR entirely for
  speech too atypical to transcribe; time-warp invariant; wired as a live
  first-chance in `/api/command` (`docs/acoustic_rag.md`).
- **Adaptive VAD** — per-speaker disfluency profiles so a stuttering block isn't
  truncated into a fragment (`docs/adaptive_vad.md`).
- **Reproducibility-first tooling** — `param_audit.py`, `tests/eval_separation.py`,
  `tests/kpi_report.py`, and a budget regression test (`tests/test_budget.py`).

## Reproduce the headline KPIs

```bash
python param_audit.py                              # separation system < 5M
python tests/kpi_report.py                         # xRT + sanity SI-SNR
python tests/eval_separation.py --n 40 --mix mix_clean   # SI-SNR on MiniLibriMix
pytest tests/test_budget.py -v                     # budget regression gate
```

## Attribution

The Canary is an original implementation. It builds on the following upstream
open-source projects and **open-weight pretrained models** (all credited in
[`tech_stack.md`](tech_stack.md)):

- Pretrained models: Asteroid ConvTasNet, OpenAI Whisper, SpeechBrain
  ECAPA-TDNN, Silero VAD (used as-is; no fine-tuning).
- Toolkits/libraries: Asteroid, SpeechBrain, PyTorch/torchaudio, librosa,
  noisereduce, FastAPI, Next.js, React Native, and others listed in the stack.
- Evaluation dataset: MiniLibriMix (derived from LibriSpeech, CC BY 4.0).

> If any part of this repository derives from another open-source project
> template, that source and the list of newly developed features should be
> stated here before submission.
