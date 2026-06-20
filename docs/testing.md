# How to Run & Test Everything

All commands are from the repository root with the project venv active
(`source .venv/bin/activate`, or prefix with `.venv/bin/`).

## 1. One-time setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# macOS mic support: brew install portaudio
```

Model weights (ConvTasNet, Whisper-tiny, ECAPA, Silero) auto-download on first
use. The MiniLibriMix eval set (~640 MB, only needed for SI-SNR/WER) downloads
once:

```bash
curl -L -o models/MiniLibriMix.zip \
  "https://zenodo.org/records/3871592/files/MiniLibriMix.zip"
cd models && unzip -q MiniLibriMix.zip && cd ..
```

## 2. Run the system

```bash
# REST API + web UI (warms the separation model at startup)
python -m backend.server                 # http://localhost:8000

# Web frontend (separate terminal)
cd frontend/web && pnpm install && pnpm dev   # http://localhost:3000

# CLI pipeline (interactive mic)
python run_canary.py
```

Try a command:
```bash
curl -F "audio=@data/test_audio/mix.wav" http://localhost:8000/api/command
curl http://localhost:8000/api/status
```

## 3. Test everything

### Unit / regression suite (fast, no downloads)
```bash
pytest tests/ -v
```
Expected: **18 passed, 1 xfailed**. Coverage:

| Test file | What it verifies |
|---|---|
| `test_budget.py` | separation model parameter budget (ConvTasNet xfail: 5.067M ~1.3% over 5.0M) |
| `test_phonetic_matcher.py` | Lisp Matrix phonetic edit-distance + per-user confusion matrices |
| `test_intent_phonetic.py` | Lisp Matrix wired into the intent engine (garbled keyword recovery) |
| `test_acoustic_rag.py` | DTW command matching, time-warp invariance, open-set no-op safety |
| `test_adaptive_vad.py` | disfluency-aware VAD (stutter block not split) |

### Parameter audit (the <5M proof)
```bash
python param_audit.py --target
```

### KPI reproduction
```bash
python tests/build_fixtures.py          # quick synthetic fixture
python tests/kpi_report.py              # xRT (warm/cold) + sanity SI-SNR + speaker-ID
python tests/eval_separation.py --n 40 --mix mix_clean   # SI-SNR/SI-SNRi (real)
python tests/eval_separation.py --n 40 --mix mix_both    # noisy SI-SNRi
python tests/eval_wer.py --mode librimix --n 10          # WER (real speech, no extra download)
```

## 4. Headline results

| KPI | Result | Notes |
|---|---|---|
| Separation params | 5.067M | ConvTasNet, real-time on CPU |
| xRT (warm) | ~0.11 | target < 0.5 |
| SI-SNR clean / SI-SNRi noisy | 14.97 / 12.75 dB | MiniLibriMix |
| WER (2-spk, real speech) | 27.2% | vs 70.8% raw mixture (separation cuts WER 2.6×) |

## 5. Accessibility features (manual demo)

- **Lisp Matrix** — `analyze_intent("tell me the newth", phonetic_profile="lisp")` → NEWS.
- **Acoustic RAG** — enroll anchor commands per user (`AcousticRAG.enroll`); a
  confident DTW match on `/api/command` fires the intent and bypasses ASR.
- **Adaptive VAD** — `get_vad_segments(audio, sr, profile="stutter")` tolerates
  mid-utterance blocks.
