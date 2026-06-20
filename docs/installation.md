# Installation, User Guide & Reproducibility

## 1. Prerequisites

- Python 3.10+ (developed/tested on 3.12)
- `git`, and a C/C++ toolchain if you want to rebuild the wakeword matcher
- System audio library for microphone capture:
  - macOS: `brew install portaudio`
  - Linux: `sudo apt-get install portaudio19-dev`
- Node.js 18+ and `pnpm` (or `npm`) for the web frontend
- Internet access on first run (models auto-download from Hugging Face)

## 2. Backend / ML setup

```bash
# from the repository root
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The first separation / ASR / speaker-ID call downloads the pretrained weights
into `pretrained_models/` and the Hugging Face cache automatically.

## 3. Running the system

### CLI pipeline (interactive microphone)
```bash
python run_canary.py
```
Speak when prompted; recording auto-stops on ~1.8 s of trailing silence. Outputs
land in `outputs/<timestamp>/` (`raw_input.wav`, `speaker_N.wav`,
`speaker_N.txt`, `context.json`, `response.json`).

### REST API + web UI
```bash
# terminal 1 — backend (serves API on :8000; warms the separation model on start)
python -m backend.server

# terminal 2 — web frontend
cd frontend/web
pnpm install        # or: npm install
pnpm dev            # http://localhost:3000
```

Key endpoints (`backend/api.py`):

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/command` | POST (audio file) | Full pipeline: separate → ID → transcribe → route → respond |
| `/api/enroll` | POST (name + audio) | Enroll a voice profile |
| `/api/change-wakeword` | POST (3 recordings) | Change the active wakeword |
| `/api/users` | GET | List enrolled users |
| `/api/status` | GET | Active wakeword, enrolled count, DB path |
| `/api/run`, `/api/run/result` | POST/GET | Trigger & poll a CLI-style run |

Example:
```bash
curl -F "audio=@data/test_audio/mix.wav" http://localhost:8000/api/command
curl http://localhost:8000/api/status
```

## 4. User guide (typical flow)

1. **Enroll users** via `/api/enroll` (or `add_voicer.py`) so the assistant can
   personalize and apply Role-Based Access Control.
2. (Optional) **Set the wakeword** with `change_wakeword.py` / `/api/change-wakeword`.
3. **Speak a command**, e.g. *"Hey Jarvis, what's the weather in Delhi?"*. The
   system separates speakers, identifies the speaker, checks the wakeword,
   classifies intent, resolves conflicts, and speaks a personalized answer.
4. **Conflict demo**: two speakers issuing opposing commands → route `CLARIFY`.
   Admin vs guest → admin wins via arbitration priority. Background chatter that
   contains the wakeword → rejected by the gating/intent layer.

## 5. Reproducing the KPIs

### Parameter budget (separation system < 5M)
```bash
python param_audit.py            # prints per-stage parameter table + verdict
```

### Real-time factor (xRT) and separation sanity
```bash
python tests/build_fixtures.py   # builds a quick 2-speaker fixture
python tests/kpi_report.py       # SI-SNR + warm/cold xRT + speaker-ID
```

### SI-SNR / SI-SNRi on a real benchmark (MiniLibriMix)
```bash
# one-time dataset download (~640 MB) into models/MiniLibriMix/
curl -L -o models/MiniLibriMix.zip \
  "https://zenodo.org/records/3871592/files/MiniLibriMix.zip"
cd models && unzip -q MiniLibriMix.zip && cd ..

# evaluate (clean and noisy), with post-processing A/B
python tests/eval_separation.py --n 40 --mix mix_clean
python tests/eval_separation.py --n 40 --mix mix_both
```

### Full test suite
```bash
pytest tests/ -v        # expect: 18 passed, 1 xfailed
```
Covers the budget gate (ConvTasNet xfail), Lisp Matrix (matcher + intent
wiring), Acoustic RAG (DTW + open-set), and Adaptive VAD. A WER number on real
speech (no extra download):
```bash
python tests/eval_wer.py --mode librimix --n 10
```

> See `docs/testing.md` for the complete, consolidated run & test guide.

## 6. Measured results (summary)

| KPI | Result | Target |
|---|---|---|
| Separation parameters | 5.067M | < 5M (separation system) |
| xRT (warm, separation) | ~0.11 | < 0.5 |
| SI-SNR (clean, MiniLibriMix) | 14.97 dB | >25 dB* |
| SI-SNRi (noisy, MiniLibriMix) | 12.75 dB | — |
| WER (2-spk separated, real speech) | 27.2% | <5% clean single-spk* |

\* The >25 dB clean SI-SNR and <5% single-speaker WER targets are above the
ceiling of any real-time sub-5M model; separation cuts WER 70.8%→27.2% (2.6×) on
2-speaker audio. See `docs/separation_results.md` for the full analysis and the
DPRNN/TIGER rejection log.

## 6b. Accessibility features (phenotypic-inclusive)

- **Lisp Matrix** — phonetic intent recovery for garbled ASR (`docs/lisp_matrix.md`).
- **Acoustic RAG** — DTW command matching that bypasses ASR (`docs/acoustic_rag.md`).
- **Adaptive VAD** — per-speaker disfluency silence tolerance (`docs/adaptive_vad.md`).

## 7. Notes / troubleshooting

- **First request is slow?** It isn't — the backend warms the separation model
  at startup (`warmup_separation()`); the `[SEP] ... loaded & cached` banner
  prints once, then `cached (no reload)` on every call.
- **Whisper package conflict:** if you see a whisper import error, run
  `pip uninstall -y whisper && pip install openai-whisper`.
- `models/`, `pretrained_models/`, and `outputs/` are git-ignored (weights and
  per-run artifacts).

> _Screenshots: add web-UI and terminal screenshots here for the final
> submission (placeholder)._
