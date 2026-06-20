# Technical Stack, OSS Libraries, Models & Datasets

## Technical stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 (backend / ML), TypeScript (frontend) |
| API server | FastAPI + Uvicorn |
| Web frontend | Next.js 16 + React 19 + Tailwind CSS (`frontend/web`) |
| Mobile frontend | React Native (`frontend/mobile`) |
| ML runtime | PyTorch, torchaudio, ONNX Runtime |
| Audio DSP | librosa, scipy, soundfile, sounddevice, noisereduce |
| Separation | Asteroid (ConvTasNet) |
| ASR | OpenAI Whisper (tiny) |
| Speaker ID | SpeechBrain (ECAPA-TDNN) |
| VAD | Silero VAD |
| Wakeword | Custom C++ weighted-Levenshtein phonetic matcher |
| Accessibility | Lisp Matrix (Double Metaphone + Needleman-Wunsch), Acoustic RAG (MFCC + FastDTW), Adaptive VAD |
| TTS | gTTS + pygame playback |
| Tool/agent layer | Python tool functions over public APIs (wttr.in, Google News RSS, iTunes) |
| Persistence | SQLite (`database/canary.db`), per-speaker profiles in `database/Voices/` |

## Open-source libraries / projects used

| Library | Purpose | Link |
|---|---|---|
| Asteroid | Source-separation toolkit; ConvTasNet model + `from_pretrained` | https://github.com/asteroid-team/asteroid |
| SpeechBrain | ECAPA-TDNN speaker embeddings | https://github.com/speechbrain/speechbrain |
| OpenAI Whisper | Automatic speech recognition | https://github.com/openai/whisper |
| Silero VAD | Voice activity detection | https://github.com/snakers4/silero-vad |
| noisereduce | Spectral-gating denoiser | https://github.com/timsainb/noisereduce |
| PyTorch | Deep-learning runtime | https://github.com/pytorch/pytorch |
| torchaudio | Audio I/O & resampling | https://github.com/pytorch/audio |
| librosa | Audio feature extraction (MFCC, pitch, STFT) | https://github.com/librosa/librosa |
| SciPy / NumPy | DSP & numerics | https://scipy.org / https://numpy.org |
| soundfile / sounddevice | WAV I/O & microphone capture | https://github.com/bastibe/python-soundfile |
| FastAPI | REST API framework | https://github.com/fastapi/fastapi |
| Uvicorn | ASGI server | https://github.com/encode/uvicorn |
| gTTS | Text-to-speech | https://github.com/pndurette/gTTS |
| pygame | Cross-platform audio playback | https://github.com/pygame/pygame |
| feedparser | Google News RSS parsing | https://github.com/kurtmckee/feedparser |
| metaphone | Double Metaphone phonetic encoding (Lisp Matrix) | https://github.com/oubiwann/metaphone |
| fastdtw | Approximate Dynamic Time Warping (Acoustic RAG) | https://github.com/slaypni/fastdtw |
| ONNX / ONNX Runtime | Parameter audit + ONNX inference | https://github.com/onnx/onnx |
| sherpa-onnx | On-device speech toolkit (evaluated for ASR/speaker) | https://github.com/k2-fsa/sherpa-onnx |
| Next.js | Web UI framework | https://github.com/vercel/next.js |
| React Native | Mobile UI framework | https://github.com/facebook/react-native |

## Models used (all open-weight)

| Model | Role | Params | License | Link |
|---|---|---|---|---|
| `JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k` | **Multi-speaker separation (shipped)** | **5.067M** | Apache-2.0 | https://huggingface.co/JorisCos/ConvTasNet_Libri2Mix_sepnoisy_16k |
| `openai/whisper` (tiny) | ASR | 37.2M | MIT | https://huggingface.co/openai/whisper-tiny |
| `speechbrain/spkrec-ecapa-voxceleb` | Speaker embedding | 22.2M | Apache-2.0 | https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb |
| Silero VAD | Voice activity detection | 0.463M | MIT | https://github.com/snakers4/silero-vad |

### Models evaluated but **not** shipped (see `docs/separation_results.md`)
| Model | Params | Why rejected | Link |
|---|---|---|---|
| `mpariente/DPRNNTasNet-ks2_WHAM_sepclean` | 3.65M | Warm xRT 0.85 — fails <0.5 real-time on CPU | https://huggingface.co/mpariente/DPRNNTasNet-ks2_WHAM_sepclean |
| `JusperLee/TIGER-speech` | 0.82M | Warm xRT 8.03 — fails real-time on CPU | https://huggingface.co/JusperLee/TIGER-speech |

> Per the problem statement, the **< 5M parameter limit applies to the
> multi-speaker separation system**. The shipped separator (ConvTasNet) is
> 5.067M; ASR and speaker-ID are separate downstream stages outside that limit.

## Datasets used

| Dataset | Use | License | Link |
|---|---|---|---|
| MiniLibriMix | SI-SNR / SI-SNRi evaluation (real 2-speaker mixtures with ground-truth sources) | CC BY 4.0 (derived from LibriSpeech) | https://zenodo.org/records/3871592 |
| LibriSpeech (via LibriMix) | Source corpus for the mixtures | CC BY 4.0 | https://www.openslr.org/12 |
| WHAM! / WSJ0-2mix (via pretrained weights) | Training corpus of the evaluated DPRNN/separation models | — | https://wham.whisper.ai |

## Models / datasets published

None published as of this submission. The separation model is used as-is from
Asteroid's pretrained zoo; no fine-tuning or new weights were produced.
