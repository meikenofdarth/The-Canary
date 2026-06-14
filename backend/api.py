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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _load_audio_as_float32(path: Path) -> np.ndarray:
    """Load any audio file as mono float32 @ 16kHz."""
    audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        import torchaudio
        import torch
        audio = torchaudio.functional.resample(
            torch.from_numpy(audio).unsqueeze(0), sr, SAMPLE_RATE
        ).squeeze(0).numpy()
    return audio.astype(np.float32)


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

    try:
        # 1. Save uploaded audio to temp file
        raw_path = tmp_dir / "raw_input.wav"
        content = await audio.read()
        raw_path.write_bytes(content)

        # 2. Load as numpy float32 @ 16kHz
        raw = _load_audio_as_float32(raw_path)

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
            est_spk = 2

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

        # 8. DRS shadow
        drs = drs_shadow(raw, SAMPLE_RATE, n_spk, streams)

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

        if response_path.exists():
            response_payload = json.loads(response_path.read_text(encoding="utf-8"))
        else:
            response_payload = {"route": "IGNORE"}

        route = response_payload.get("route", "IGNORE")
        active_command = response_payload.get("active_command", {})

        # Extract key fields from response
        transcript = active_command.get("transcript", "")
        speaker = active_command.get("identity", "UNKNOWN")
        domain = active_command.get("domain", "UNKNOWN")
        entities = active_command.get("entities", {})
        polarity = active_command.get("polarity", "POSITIVE")
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
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")
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

        # Write raw bytes first
        dest.write_bytes(content)

        # Convert to proper WAV if needed
        try:
            audio_data = _load_audio_as_float32(dest)
            sf.write(str(dest), audio_data, SAMPLE_RATE, subtype="PCM_16")
        except Exception:
            pass  # If it's already a valid WAV, fine

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
            tmp_path = tmp_dir / f"ww_{idx}.wav"
            content = await f.read()
            tmp_path.write_bytes(content)

            # Convert to proper WAV
            try:
                audio_data = _load_audio_as_float32(tmp_path)
                sf.write(str(tmp_path), audio_data, SAMPLE_RATE, subtype="PCM_16")
            except Exception:
                pass

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
