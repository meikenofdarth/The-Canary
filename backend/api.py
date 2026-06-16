"""
backend/api.py
===============
FastAPI REST wrapper around The Canary pipeline.

Endpoints:
    POST /api/command         — Full audio → response pipeline
    POST /api/enroll          — Enroll a new speaker
    POST /api/change-wakeword — Change the active wakeword
    GET  /api/users           — List enrolled users
    GET  /api/status          — System status
"""

from __future__ import annotations

import sys
import json
import tempfile
import difflib
import warnings
from pathlib import Path
from collections import Counter
from typing import Optional

import numpy as np
import soundfile as sf

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# ── Ensure project root is importable ─────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Imports from the existing pipeline ────────────────────────────────────────
from computation.audio.transcribe import transcribe_and_save, pre_screen, transcribe
from computation.audio.speaker_counter import SpeakerCountEstimator
from computation.voice.ranker import identify_speakers
from computation.intelligence.context_builder import build_context
from computation.intelligence.wakeword_detector import detect_wakeword, get_active_wakeword
from computation.intelligence.intent_engine import analyze_intent
from backend.mcp_server import execute_intent
from backend.queue import load_user_profiles
from database.canary_db import (
    get_preferences, get_all_users, get_user_count, upsert_user, get_db_path, init_db,
)

# Audio processing helpers from run_canary.py
from run_canary import (
    detect_and_separate, detect_and_separate_3spk,
    enhance_single, enhance_stream, _reduce_crosstalk,
    _speech_band_rms, _temporal_overlap, drs_shadow, si_snr,
)

SAMPLE_RATE = 16000

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="The Canary API",
    description="REST wrapper for The Canary voice assistant pipeline.",
    version="1.0.0",
)


@app.on_event("startup")
async def _startup_banner():
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║   THE CANARY API  —  v2 (dedupe + outputs/)     ║")
    print("  ║   /api/command saves to outputs/<timestamp>/    ║")
    print("  ║   single-speaker dedupe + faint-stream gate ON  ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Serve the voice interface (wave.html) at the root URL
# ─────────────────────────────────────────────────────────────────────────────
_INTERFACE_DIR = _PROJECT_ROOT / "frontend" / "interface"


@app.get("/")
async def root():
    """Serve wave.html at http://localhost:8000/"""
    wave = _INTERFACE_DIR / "wave.html"
    if wave.exists():
        return FileResponse(str(wave), media_type="text/html")
    raise HTTPException(status_code=404, detail="wave.html not found")


# Serve any other files in frontend/interface (CSS, JS, images if added later)
if _INTERFACE_DIR.exists():
    app.mount(
        "/interface",
        StaticFiles(directory=str(_INTERFACE_DIR), html=True),
        name="interface",
    )


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_to_wav(src: Path, dst: Path) -> None:
    """Convert any audio file (webm/opus/mp3/m4a/etc.) to mono 16 kHz PCM WAV via ffmpeg."""
    import shutil as _shutil
    import subprocess

    if src.stat().st_size < 1000:
        raise RuntimeError(f"Audio file too small ({src.stat().st_size} bytes) — likely empty recording.")

    ffmpeg = _shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not Path(ffmpeg).exists():
        raise RuntimeError("ffmpeg not found on PATH. Install with: brew install ffmpeg")

    # -y overwrite, -i input, -ac 1 mono, -ar 16000 Hz, -acodec pcm_s16le 16-bit PCM, -f wav
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", str(src),
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        "-acodec", "pcm_s16le",
        "-f", "wav",
        str(dst),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {proc.stderr.strip()}")


def _load_audio_as_float32(path: Path) -> np.ndarray:
    """Load any audio file as mono float32 @ 16kHz.

    Tries soundfile first (fast, handles WAV/FLAC/OGG-Vorbis).
    Falls back to ffmpeg subprocess for everything else (WebM/Opus/MP3/M4A/etc.).
    """
    import torch, torchaudio

    # Path 1: soundfile direct (fastest for WAV)
    try:
        audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
        if isinstance(audio, np.ndarray) and audio.ndim == 2:
            audio = audio.mean(axis=1)
        audio = audio.astype(np.float32)
        if sr != SAMPLE_RATE:
            waveform_t = torch.from_numpy(audio).unsqueeze(0)
            audio = torchaudio.functional.resample(
                waveform_t, sr, SAMPLE_RATE
            ).squeeze(0).numpy()
        return audio.astype(np.float32)
    except Exception:
        pass

    # Path 2: ffmpeg → temp WAV → soundfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = Path(tmp.name)
    try:
        _ffmpeg_to_wav(path, tmp_wav)
        audio, sr = sf.read(str(tmp_wav), dtype="float32", always_2d=False)
        if isinstance(audio, np.ndarray) and audio.ndim == 2:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)
    finally:
        try:
            tmp_wav.unlink()
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/command
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/command")
async def command_endpoint(audio: UploadFile = File(...)):
    """
    Full pipeline: audio blob → separation → ASR → voice ID → context → execution.
    Returns unified JSON response.
    """
    # Validate file
    if not audio.filename:
        raise HTTPException(status_code=400, detail="No audio file provided.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="canary_api_"))

    # Also persist to outputs/<timestamp>/ just like run_canary.py
    import datetime as _dt
    _ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _PROJECT_ROOT / "outputs" / _ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  [api] /api/command  →  outputs/{_ts}/")

    try:
        # 1. Save uploaded audio to temp file
        raw_path = tmp_dir / "raw_input.wav"
        content = await audio.read()
        raw_path.write_bytes(content)

        # 2. Load as numpy float32 @ 16kHz
        try:
            raw = _load_audio_as_float32(raw_path)
        except Exception as audio_err:
            raise HTTPException(status_code=422, detail=f"Could not decode audio: {audio_err}")

        # Re-save as proper WAV (in case input was WebM or other format)
        sf.write(str(raw_path), raw, SAMPLE_RATE, subtype="PCM_16")

        # Silence gate
        raw_rms_db = 20.0 * np.log10(np.sqrt(np.mean(raw ** 2)) + 1e-10)
        if raw_rms_db < -55.0:
            return {
                "route": "IGNORE",
                "transcript": "",
                "speaker": "UNKNOWN",
                "domain": "UNKNOWN",
                "entities": {},
                "execution_result": None,
                "drs_mode": "A",
                "detail": "No audio detected — signal too quiet.",
            }

        # 3. Speaker count estimation
        try:
            estimator = SpeakerCountEstimator(sample_rate=SAMPLE_RATE, max_speakers=3)
            est_spk = estimator.estimate(raw)
        except Exception:
            est_spk = 1  # default to single speaker — never force separation on one voice

        # 4. Separation
        if est_spk >= 3:
            n_spk, streams = detect_and_separate_3spk(raw, SAMPLE_RATE)
        else:
            n_spk, streams = detect_and_separate(raw, SAMPLE_RATE)

        # Cross-talk reduction
        overlap_prob = 0.0
        if n_spk >= 2 and len(streams) >= 2:
            streams = _reduce_crosstalk(streams)
            streams = sorted(streams,
                             key=lambda s: _speech_band_rms(s, SAMPLE_RATE), reverse=True)

            # ── Energy-ratio gate: drop streams that are likely SepFormer artifacts ──
            top_rms = _speech_band_rms(streams[0], SAMPLE_RATE)
            kept = [streams[0]]
            for s in streams[1:]:
                ratio = _speech_band_rms(s, SAMPLE_RATE) / (top_rms + 1e-10)
                if ratio >= 0.30:   # only keep streams ≥30% of dominant
                    kept.append(s)
            if len(kept) < len(streams):
                print(f"  [api] dropped {len(streams)-len(kept)} faint stream(s) (likely artifact)")
            streams = kept
            n_spk   = len(streams)

            if len(streams) >= 2:
                overlap_prob = _temporal_overlap(streams[0], streams[1], SAMPLE_RATE)

        # 5. Enhancement + save WAVs
        saved = []
        if n_spk == 1:
            enhanced = enhance_single(raw, SAMPLE_RATE)
            fname = "speaker_1.wav"
            sf.write(str(tmp_dir / fname), enhanced, SAMPLE_RATE, subtype="PCM_16")
            saved.append(fname)
        else:
            for i, s in enumerate(streams, 1):
                enhanced = enhance_stream(s, SAMPLE_RATE)
                fname = f"speaker_{i}.wav"
                sf.write(str(tmp_dir / fname), enhanced, SAMPLE_RATE, subtype="PCM_16")
                saved.append(fname)

        # 6. Transcription (pre_screen + transcribe_and_save)
        ready_speakers = []
        for fname in saved:
            wav_p = tmp_dir / fname
            screen = pre_screen(wav_p)
            if screen["verdict"] == "REJECTED":
                transcribe_and_save(wav_p, model_name="tiny")
            else:
                text, status = transcribe_and_save(wav_p, model_name="tiny")
                if status == "SPEECH":
                    ready_speakers.append(fname)

        # 7. Voice identification
        voice_ids = {}
        try:
            voice_ids = identify_speakers(saved, tmp_dir, raw_mix=raw,
                                          sr=SAMPLE_RATE, overlap=overlap_prob)
        except Exception:
            pass

        # 7b. DEDUPLICATE — if SepFormer split one voice into multiple streams that
        # all identify as the same enrolled speaker, keep only the highest-confidence one.
        if voice_ids and len(saved) >= 2:
            by_name = {}
            for fname in saved:
                r = voice_ids.get(fname, {})
                name = r.get("speaker", "UNKNOWN")
                conf = float(r.get("confidence", 0.0))
                if name == "UNKNOWN":
                    continue
                if name not in by_name or conf > by_name[name]["conf"]:
                    by_name[name] = {"fname": fname, "conf": conf}

            keep = {e["fname"] for e in by_name.values()}
            # keep UNKNOWN streams too (they might be real other speakers)
            keep.update(f for f in saved if voice_ids.get(f, {}).get("speaker") == "UNKNOWN")

            if len(keep) < len(saved):
                dropped = [f for f in saved if f not in keep]
                print(f"  [dedupe] same-speaker duplicates dropped: {dropped}")
                saved     = [f for f in saved if f in keep]
                voice_ids = {f: voice_ids[f] for f in saved if f in voice_ids}
                # Also trim streams list to match
                if streams and len(streams) > len(saved):
                    streams = streams[:len(saved)]
                n_spk = len(saved)

        # 8. DRS shadow
        drs = drs_shadow(raw, SAMPLE_RATE, n_spk, streams)

        # ── Persist to outputs/<timestamp>/ (mirrors run_canary.py behaviour) ──
        import shutil as _shutil
        try:
            # raw input
            _shutil.copy2(str(tmp_dir / "raw_input.wav"), str(out_dir / "raw_input.wav"))
            # speaker wavs + txt
            for fname in saved:
                src_wav = tmp_dir / fname
                if src_wav.exists():
                    _shutil.copy2(str(src_wav), str(out_dir / fname))
                src_txt = tmp_dir / fname.replace(".wav", ".txt")
                if src_txt.exists():
                    _shutil.copy2(str(src_txt), str(out_dir / fname.replace(".wav", ".txt")))
        except Exception as _cp_err:
            print(f"  [outputs] copy failed (non-fatal): {_cp_err}")

        # 9. Context engine (builds context.json + response.json)
        try:
            context = build_context(tmp_dir, drs, n_spk, voice_ids=voice_ids)
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"Context engine failed: {e}")

        # 10. Read response.json (written by build_context to project root)
        response_path = _PROJECT_ROOT / "response.json"
        if not response_path.exists():
            # Fallback: check tmp_dir
            alt = tmp_dir / "response.json"
            if alt.exists():
                response_path = alt

        response_payload = {"route": "IGNORE"}
        if response_path.exists():
            try:
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
            except Exception as _rj_err:
                print(f"  [api] response.json parse failed: {_rj_err}")

            # Persist response.json + context.json to outputs/
            try:
                import shutil as _shutil2
                _shutil2.copy2(str(response_path), str(out_dir / "response.json"))
                ctx_src = tmp_dir / "context.json"
                if ctx_src.exists():
                    _shutil2.copy2(str(ctx_src), str(out_dir / "context.json"))
            except Exception as _cp2_err:
                print(f"  [api] outputs/ copy failed: {_cp2_err}")

        route = response_payload.get("route", "IGNORE")
        active_command = response_payload.get("active_command") or {}

        # Extract key fields from response
        transcript = active_command.get("transcript", "")
        speaker    = active_command.get("identity", "UNKNOWN")
        domain     = active_command.get("domain", "UNKNOWN")
        entities   = active_command.get("entities", {})
        polarity   = active_command.get("polarity", "POSITIVE")
        known_user = active_command.get("known_user", False)

        # 11. Execute intent if route != IGNORE
        execution_result = None
        if route not in ("IGNORE", "CLARIFY"):
            profiles = load_user_profiles()
            profile = profiles.get(speaker) if known_user else None

            # For SEQUENTIAL, execute all queued commands
            if route == "SEQUENTIAL" or route == "MULTI_EXECUTE":
                seq_queue = response_payload.get("sequential_queue", [])
                execution_results = []
                for cmd in seq_queue:
                    cmd_identity = cmd.get("identity", "Unknown")
                    cmd_domain = cmd.get("domain", "UNKNOWN")
                    cmd_text = cmd.get("transcript", "")
                    cmd_entities = cmd.get("entities", {})
                    cmd_polarity = cmd.get("polarity", "POSITIVE")
                    cmd_known = cmd.get("known_user", False)
                    cmd_profile = profiles.get(cmd_identity) if cmd_known else None
                    try:
                        res = execute_intent(cmd_domain, cmd_text, cmd_profile,
                                             cmd_entities, cmd_polarity)
                        execution_results.append(res)
                    except Exception as ex:
                        execution_results.append({"status": "error", "message": str(ex)})
                execution_result = execution_results
            else:
                # Single EXECUTE
                try:
                    execution_result = execute_intent(domain, transcript, profile,
                                                     entities, polarity)
                except Exception as ex:
                    execution_result = {"status": "error", "message": str(ex)}

        return {
            "route": route,
            "transcript": transcript,
            "speaker": speaker,
            "domain": domain,
            "entities": entities,
            "execution_result": execution_result,
            "drs_mode": drs.get("mode", "?"),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"\n  [api] PIPELINE ERROR:\n{tb}\n")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {type(e).__name__}: {e}")
    finally:
        # Cleanup temp directory
        import shutil
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/enroll
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/enroll")
async def enroll_endpoint(
    name: str = Form(...),
    audio_files: list[UploadFile] = File(...),
    city: str = Form("Bengaluru"),
    news_country: str = Form("India"),
    favorite_genre: str = Form("Pop"),
):
    """
    Enroll a new speaker: save audio, extract voice features, store in DB.
    Requires exactly 3 audio files.
    """
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")

    name = name.strip()

    if len(audio_files) < 3:
        raise HTTPException(status_code=400, detail="Exactly 3 audio files required.")

    # Check user limit
    if get_user_count() >= 5:
        from database.canary_db import get_user
        if get_user(name) is None:
            raise HTTPException(status_code=409,
                                detail="Maximum of 5 users reached. Delete a user first.")

    # Save audio files to database/Voices/{name}/recordings/
    voices_dir = _PROJECT_ROOT / "database" / "Voices" / name / "recordings"
    voices_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for idx, f in enumerate(audio_files[:3], start=1):
        dest = voices_dir / f"sample_{idx}.wav"
        content = await f.read()

        # Detect actual format from the upload filename / content-type
        # Browser MediaRecorder sends audio/webm (Opus) regardless of file extension.
        # We write to a temp file with the correct extension so torchaudio / ffmpeg
        # can decode it, then re-encode as proper 16-bit PCM WAV at 16 kHz.
        original_ext = ".webm"
        if f.filename:
            original_ext = Path(f.filename).suffix or ".webm"
        elif f.content_type:
            ct = f.content_type.lower()
            if "ogg" in ct:
                original_ext = ".ogg"
            elif "mp3" in ct or "mpeg" in ct:
                original_ext = ".mp3"
            elif "wav" in ct:
                original_ext = ".wav"

        tmp_raw = dest.with_suffix(original_ext)
        tmp_raw.write_bytes(content)

        try:
            audio_data = _load_audio_as_float32(tmp_raw)
            sf.write(str(dest), audio_data, SAMPLE_RATE, subtype="PCM_16")
            # Remove the temp raw file once we have the WAV
            if tmp_raw != dest:
                try:
                    tmp_raw.unlink()
                except OSError:
                    pass
        except Exception as conv_err:
            # If decode failed, try one more time treating it as raw WAV bytes
            try:
                dest.write_bytes(content)
                audio_data = _load_audio_as_float32(dest)
                sf.write(str(dest), audio_data, SAMPLE_RATE, subtype="PCM_16")
            except Exception:
                raise HTTPException(
                    status_code=422,
                    detail=f"Could not decode audio file {idx}: {conv_err}. "
                           "Please upload a supported format (WAV, WebM, MP3, OGG)."
                )

        saved_paths.append(str(dest))

    # Run enrollment
    try:
        from computation.voice.enroll import enroll_speaker
        profile = enroll_speaker(name, saved_paths)
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Voice enrollment failed: {e}")

    # Store in database with preferences
    preferences = {
        "city": city,
        "news_country": news_country,
        "favorite_genre": favorite_genre,
    }

    try:
        speaker_id = upsert_user(name, profile, preferences)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Database error: {e}")

    return {
        "speaker_id": speaker_id,
        "name": name,
        "city": city,
        "news_country": news_country,
        "favorite_genre": favorite_genre,
        "recording_count": profile.get("recording_count", 3),
        "status": "enrolled",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/change-wakeword
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/change-wakeword")
async def change_wakeword_endpoint(
    audio_files: list[UploadFile] = File(...),
):
    """
    Change the active wakeword.
    Accepts 3 audio recordings of the new wakeword.
    Transcribes each, majority-votes the word, builds lookup table.
    """
    if len(audio_files) < 3:
        raise HTTPException(status_code=400,
                            detail="Exactly 3 audio recordings required.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="canary_wakeword_"))
    transcriptions: list[str] = []

    try:
        import re as _re

        for idx, f in enumerate(audio_files[:3], start=1):
            # Save to temp
            # Save to temp — detect real format from upload metadata
            original_ext = ".webm"
            if f.filename:
                original_ext = Path(f.filename).suffix or ".webm"
            elif f.content_type:
                ct = f.content_type.lower()
                if "ogg" in ct:
                    original_ext = ".ogg"
                elif "mp3" in ct or "mpeg" in ct:
                    original_ext = ".mp3"
                elif "wav" in ct:
                    original_ext = ".wav"

            tmp_raw = tmp_dir / f"ww_{idx}{original_ext}"
            tmp_path = tmp_dir / f"ww_{idx}.wav"
            content = await f.read()
            tmp_raw.write_bytes(content)

            # Convert browser audio (WebM/Opus/MP3) → 16 kHz mono PCM WAV
            try:
                audio_data = _load_audio_as_float32(tmp_raw)
                sf.write(str(tmp_path), audio_data, SAMPLE_RATE, subtype="PCM_16")
                if tmp_raw != tmp_path:
                    try:
                        tmp_raw.unlink()
                    except OSError:
                        pass
            except Exception as conv_err:
                print(f"    [wakeword] Audio conversion error for file {idx}: {conv_err}")
                continue  # skip this recording rather than crashing

            # Transcribe with Whisper
            try:
                result = transcribe(tmp_path, model_name="base")
                raw_text = result.get("text", "").strip()
                if raw_text:
                    # Extract clean single word
                    words = _re.findall(r"[a-zA-Z']+", raw_text.lower())
                    fillers = {"hey", "hi", "ok", "okay", "oh", "um", "uh",
                               "the", "a", "and"}
                    clean = [w for w in words if w not in fillers and len(w) >= 2]
                    if not clean:
                        clean = words
                    if clean:
                        transcriptions.append(clean[0])
            except Exception:
                continue

        if not transcriptions:
            raise HTTPException(status_code=422,
                                detail="Could not transcribe any recordings.")

        # Majority vote
        counts = Counter(transcriptions)
        winner = counts.most_common(1)[0][0]

        # Build lookup table
        wakeword_dir = _PROJECT_ROOT / "computation" / "wakeword"
        config_path = wakeword_dir / "wakeword_config.json"
        binary_path = wakeword_dir / "build" / "wakeword_matcher"

        variants_count = 0

        if binary_path.exists():
            # Use C++ binary
            import subprocess
            try:
                result = subprocess.run(
                    [
                        str(binary_path),
                        "--build-table", winner,
                        "--threshold", "0.70",
                        "--output", str(config_path),
                    ],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    variants_count = data.get("variants_generated", 0)
                else:
                    # Fall through to Python fallback
                    raise Exception(result.stderr)
            except Exception:
                # Python fallback below
                pass

        if variants_count == 0:
            # Python fallback: build lookup table with difflib
            lookup_table = {}
            # Generate character variants
            chars = "abcdefghijklmnopqrstuvwxyz"
            candidates = set()

            # Single char substitutions
            for i in range(len(winner)):
                for c in chars:
                    variant = winner[:i] + c + winner[i+1:]
                    candidates.add(variant)

            # Single char insertions
            for i in range(len(winner) + 1):
                for c in chars:
                    variant = winner[:i] + c + winner[i:]
                    candidates.add(variant)

            # Single char deletions
            for i in range(len(winner)):
                variant = winner[:i] + winner[i+1:]
                if len(variant) >= 2:
                    candidates.add(variant)

            # Transpositions
            for i in range(len(winner) - 1):
                variant = winner[:i] + winner[i+1] + winner[i] + winner[i+2:]
                candidates.add(variant)

            # Score each candidate
            for candidate in candidates:
                score = difflib.SequenceMatcher(None, winner, candidate).ratio()
                if score >= 0.70:
                    lookup_table[candidate] = round(score, 4)

            # Always include exact match
            lookup_table[winner] = 1.0

            config = {
                "word": winner,
                "threshold": 0.70,
                "lookup_table": lookup_table,
            }
            config_path.write_text(
                json.dumps(config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            variants_count = len(lookup_table)

        return {
            "word": winner,
            "variants_generated": variants_count,
            "transcriptions": transcriptions,
            "status": "success",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Wakeword change failed: {e}")
    finally:
        import shutil
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
#  GET /api/users
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/users")
async def users_endpoint():
    """Return all enrolled users with preferences (stripped of large fields)."""
    try:
        users = get_all_users()
        # Strip large blob fields
        for u in users:
            u.pop("embedding_centroid", None)
            u.pop("mfcc_mean", None)
        return {"users": users, "count": len(users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE /api/users/{name}
# ─────────────────────────────────────────────────────────────────────────────

@app.delete("/api/users/{name}")
async def delete_user_endpoint(name: str):
    """
    Delete an enrolled speaker by name.
    Removes the DB row, recordings table entries, and the on-disk Voices/<name>/ folder.
    """
    from database.canary_db import delete_user, get_user
    import shutil

    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")

    name = name.strip()

    # Verify user exists before any destructive work
    user = get_user(name)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{name}' not found.")

    # Remove from DB (also clears recordings table due to FK)
    try:
        ok = delete_user(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not ok:
        raise HTTPException(status_code=404, detail=f"User '{name}' not found.")

    # Remove on-disk voice profile folder (best-effort)
    voices_dir = _PROJECT_ROOT / "database" / "Voices" / name
    try:
        if voices_dir.exists():
            shutil.rmtree(voices_dir, ignore_errors=True)
    except Exception:
        pass  # filesystem cleanup is best-effort

    return {"name": name, "status": "deleted"}


# ─────────────────────────────────────────────────────────────────────────────
#  GET /api/status
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status_endpoint():
    """Return system status: active wakeword, enrolled users, DB path."""
    try:
        wakeword = get_active_wakeword()
    except Exception:
        wakeword = "canary"

    try:
        user_count = get_user_count()
    except Exception:
        user_count = 0

    db_path = get_db_path()

    return {
        "active_wakeword": wakeword,
        "enrolled_users": user_count,
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "status": "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/run   &   GET /api/run/result
#  Trigger run_canary.py as a subprocess and poll for the result.
# ─────────────────────────────────────────────────────────────────────────────
import subprocess as _subprocess
import threading as _threading

_run_lock   = _threading.Lock()
_run_state  = {"status": "idle", "result": None, "error": None, "proc": None}


def _launch_run_canary():
    """Runs run_canary.py in the background, updates _run_state when done."""
    global _run_state
    python  = sys.executable
    script  = str(_PROJECT_ROOT / "run_canary.py")
    resp_p  = _PROJECT_ROOT / "response.json"

    # Clear previous result
    with _run_lock:
        _run_state["status"] = "running"
        _run_state["result"] = None
        _run_state["error"]  = None

    try:
        proc = _subprocess.Popen(
            [python, script],
            cwd=str(_PROJECT_ROOT),
            stdout=_subprocess.PIPE,
            stderr=_subprocess.STDOUT,
            text=True,
        )
        with _run_lock:
            _run_state["proc"] = proc

        stdout, _ = proc.communicate(timeout=60)

        if proc.returncode != 0:
            with _run_lock:
                _run_state["status"] = "error"
                _run_state["error"]  = f"run_canary exited {proc.returncode}"
            return

        # Read response.json written by the pipeline
        result = {}
        if resp_p.exists():
            try:
                result = json.loads(resp_p.read_text(encoding="utf-8"))
            except Exception:
                result = {}

        with _run_lock:
            _run_state["status"] = "done"
            _run_state["result"] = result
            _run_state["proc"]   = None

    except _subprocess.TimeoutExpired:
        proc.kill()
        with _run_lock:
            _run_state["status"] = "error"
            _run_state["error"]  = "timeout (>60 s)"
            _run_state["proc"]   = None
    except Exception as e:
        with _run_lock:
            _run_state["status"] = "error"
            _run_state["error"]  = str(e)
            _run_state["proc"]   = None


@app.post("/api/run")
async def run_endpoint():
    """
    Launch run_canary.py (records from local mic, runs full pipeline).
    Returns immediately; poll GET /api/run/result for completion.
    """
    with _run_lock:
        if _run_state["status"] == "running":
            return {"started": False, "reason": "already running"}
        _run_state["status"] = "running"
        _run_state["result"] = None
        _run_state["error"]  = None

    t = _threading.Thread(target=_launch_run_canary, daemon=True)
    t.start()
    return {"started": True}


@app.post("/api/run/stop")
async def run_stop_endpoint():
    """Send SIGTERM to the running run_canary.py process."""
    import signal as _signal
    with _run_lock:
        proc = _run_state.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.send_signal(_signal.SIGTERM)
            except Exception:
                pass
            _run_state["status"] = "idle"
            _run_state["proc"]   = None
            return {"stopped": True}
    return {"stopped": False, "reason": "not running"}


@app.get("/api/run/result")
async def run_result_endpoint():
    """Poll this until status == 'done' or 'error'."""
    with _run_lock:
        return {
            "status": _run_state["status"],
            "result": _run_state["result"],
            "error":  _run_state["error"],
        }
