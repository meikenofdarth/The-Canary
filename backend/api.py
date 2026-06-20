
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

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from computation.audio.transcribe import transcribe_and_save, pre_screen, transcribe
from computation.audio.speaker_counter import SpeakerCountEstimator
from computation.voice.ranker import identify_speakers
from computation.intelligence.context_builder import build_context
from computation.intelligence.wakeword_detector import detect_wakeword, get_active_wakeword
from computation.intelligence.intent_engine import analyze_intent
from backend.mcp_server import execute_intent
from backend.queue import load_user_profiles
from computation.intelligence.acoustic_rag import AcousticRAG
from database.canary_db import (
    get_preferences, get_all_users, get_user_count, upsert_user, get_db_path, init_db,
    update_priority,
)

from run_canary import (
    detect_and_separate, detect_and_separate_3spk,
    enhance_single, enhance_stream, _reduce_crosstalk,
    _speech_band_rms, _temporal_overlap, drs_shadow, si_snr,
    warmup_separation,
)

SAMPLE_RATE = 16000

app = FastAPI(
    title="The Canary API",
    description="REST wrapper for The Canary voice assistant pipeline.",
    version="1.0.0",
)


@app.on_event("startup")
async def _startup_banner():
    print("\n  The Canary API — ready on http://localhost:8000\n")
    try:
        warmup_separation()
    except Exception as e:
        print(f"  [startup] separation warm-up skipped: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_INTERFACE_DIR = _PROJECT_ROOT / "frontend" / "interface"


@app.get("/")
async def root():
    wave = _INTERFACE_DIR / "wave.html"
    if wave.exists():
        return FileResponse(str(wave), media_type="text/html")
    raise HTTPException(status_code=404, detail="wave.html not found")


if _INTERFACE_DIR.exists():
    app.mount(
        "/interface",
        StaticFiles(directory=str(_INTERFACE_DIR), html=True),
        name="interface",
    )


def _ffmpeg_to_wav(src: Path, dst: Path) -> None:
    import shutil as _shutil
    import subprocess

    if src.stat().st_size < 1000:
        raise RuntimeError(f"Audio file too small ({src.stat().st_size} bytes) — likely empty recording.")

    ffmpeg = _shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not Path(ffmpeg).exists():
        raise RuntimeError("ffmpeg not found on PATH. Install with: brew install ffmpeg")

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
    import torch, torchaudio

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


@app.post("/api/command")
async def command_endpoint(audio: UploadFile = File(...)):
    if not audio.filename:
        raise HTTPException(status_code=400, detail="No audio file provided.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="canary_api_"))

    import datetime as _dt
    _ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _PROJECT_ROOT / "outputs" / _ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  ── Command · {_ts} ──────────────────────────────")

    try:
        raw_path = tmp_dir / "raw_input.wav"
        content = await audio.read()
        raw_path.write_bytes(content)

        try:
            raw = _load_audio_as_float32(raw_path)
        except Exception as audio_err:
            raise HTTPException(status_code=422, detail=f"Could not decode audio: {audio_err}")

        sf.write(str(raw_path), raw, SAMPLE_RATE, subtype="PCM_16")

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

        try:
            estimator = SpeakerCountEstimator(sample_rate=SAMPLE_RATE, max_speakers=3)
            est_spk = estimator.estimate(raw)
        except Exception:
            est_spk = 1

        try:
            _dtw = AcousticRAG(store_dir=str(_PROJECT_ROOT / "database" / "acoustic_rag"))
            dtw_hit = _dtw.open_set_match(raw, SAMPLE_RATE)
        except Exception:
            dtw_hit = {"matched": False}

        if dtw_hit.get("matched"):
            intent = dtw_hit["intent"]
            domain = intent if intent in ("WEATHER", "NEWS", "SONGS") else "COMMAND"
            print(f"  [api] Acoustic RAG matched '{dtw_hit['label']}' "
                  f"(user={dtw_hit['user']}, d={dtw_hit['distance']}) — bypassing ASR")
            exec_result = None
            if domain in ("WEATHER", "NEWS", "SONGS"):
                try:
                    profile = (load_user_profiles() or {}).get(dtw_hit["user"], {})
                    exec_result = execute_intent(domain, "", profile=profile)
                except Exception:
                    exec_result = None
            return {
                "route": "EXECUTE",
                "transcript": f"(matched acoustic template: {dtw_hit['label']})",
                "speaker": dtw_hit["user"],
                "domain": domain,
                "entities": {},
                "execution_result": exec_result,
                "drs_mode": "A",
                "detail": f"Acoustic RAG / DTW match (d={dtw_hit['distance']}) — ASR bypassed.",
            }

        if est_spk >= 3:
            n_spk, streams = detect_and_separate_3spk(raw, SAMPLE_RATE)
        else:
            n_spk, streams = detect_and_separate(raw, SAMPLE_RATE)

        overlap_prob = 0.0
        if n_spk >= 2 and len(streams) >= 2:
            streams = _reduce_crosstalk(streams)
            streams = sorted(streams,
                             key=lambda s: _speech_band_rms(s, SAMPLE_RATE), reverse=True)

            top_rms = _speech_band_rms(streams[0], SAMPLE_RATE)
            kept = [streams[0]]
            for s in streams[1:]:
                ratio = _speech_band_rms(s, SAMPLE_RATE) / (top_rms + 1e-10)
                if ratio >= 0.30:
                    kept.append(s)
            if len(kept) < len(streams):
                print(f"  [api] dropped {len(streams)-len(kept)} faint stream(s) (likely artifact)")
            streams = kept
            n_spk   = len(streams)

            if len(streams) >= 2:
                overlap_prob = _temporal_overlap(streams[0], streams[1], SAMPLE_RATE)

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

        ready_speakers = []
        for fname in saved:
            wav_p = tmp_dir / fname
            screen = pre_screen(wav_p)
            if screen["verdict"] == "REJECTED":
                transcribe_and_save(wav_p)
            else:
                text, status = transcribe_and_save(wav_p)
                if status == "SPEECH":
                    ready_speakers.append(fname)

        voice_ids = {}
        try:
            voice_ids = identify_speakers(saved, tmp_dir, raw_mix=raw,
                                          sr=SAMPLE_RATE, overlap=overlap_prob)
        except Exception:
            pass

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
            keep.update(f for f in saved if voice_ids.get(f, {}).get("speaker") == "UNKNOWN")

            if len(keep) < len(saved):
                dropped = [f for f in saved if f not in keep]
                print(f"  [dedupe] same-speaker duplicates dropped: {dropped}")
                saved     = [f for f in saved if f in keep]
                voice_ids = {f: voice_ids[f] for f in saved if f in voice_ids}
                if streams and len(streams) > len(saved):
                    streams = streams[:len(saved)]
                n_spk = len(saved)

        drs = drs_shadow(raw, SAMPLE_RATE, n_spk, streams)

        import shutil as _shutil
        try:
            _shutil.copy2(str(tmp_dir / "raw_input.wav"), str(out_dir / "raw_input.wav"))
            for fname in saved:
                src_wav = tmp_dir / fname
                if src_wav.exists():
                    _shutil.copy2(str(src_wav), str(out_dir / fname))
                src_txt = tmp_dir / fname.replace(".wav", ".txt")
                if src_txt.exists():
                    _shutil.copy2(str(src_txt), str(out_dir / fname.replace(".wav", ".txt")))
        except Exception as _cp_err:
            print(f"  [outputs] copy failed (non-fatal): {_cp_err}")

        try:
            context = build_context(tmp_dir, drs, n_spk, voice_ids=voice_ids)
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"Context engine failed: {e}")

        response_path = _PROJECT_ROOT / "response.json"
        if not response_path.exists():
            alt = tmp_dir / "response.json"
            if alt.exists():
                response_path = alt

        response_payload = {"route": "IGNORE"}
        if response_path.exists():
            try:
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
            except Exception as _rj_err:
                print(f"  [api] response.json parse failed: {_rj_err}")

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

        transcript = active_command.get("transcript", "")
        speaker    = active_command.get("identity", "UNKNOWN")
        domain     = active_command.get("domain", "UNKNOWN")
        entities   = active_command.get("entities", {})
        polarity   = active_command.get("polarity", "POSITIVE")
        known_user = active_command.get("known_user", False)

        execution_result = None
        if route not in ("IGNORE", "CLARIFY"):
            profiles = load_user_profiles()
            profile = profiles.get(speaker) if known_user else None

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
        import shutil
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


@app.post("/api/enroll")
async def enroll_endpoint(
    name: str = Form(...),
    audio_files: list[UploadFile] = File(...),
    city: str = Form("Bengaluru"),
    news_country: str = Form("India"),
    favorite_genre: str = Form("Pop"),
):
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")

    name = name.strip()

    if len(audio_files) < 3:
        raise HTTPException(status_code=400, detail="Exactly 3 audio files required.")

    if get_user_count() >= 5:
        from database.canary_db import get_user
        if get_user(name) is None:
            raise HTTPException(status_code=409,
                                detail="Maximum of 5 users reached. Delete a user first.")

    voices_dir = _PROJECT_ROOT / "database" / "Voices" / name / "recordings"
    voices_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for idx, f in enumerate(audio_files[:3], start=1):
        dest = voices_dir / f"sample_{idx}.wav"
        content = await f.read()

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
            if tmp_raw != dest:
                try:
                    tmp_raw.unlink()
                except OSError:
                    pass
        except Exception as conv_err:
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

    try:
        from computation.voice.enroll import enroll_speaker
        profile = enroll_speaker(name, saved_paths)
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Voice enrollment failed: {e}")

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


@app.post("/api/change-wakeword")
async def change_wakeword_endpoint(
    audio_files: list[UploadFile] = File(...),
):
    if len(audio_files) < 3:
        raise HTTPException(status_code=400,
                            detail="Exactly 3 audio recordings required.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="canary_wakeword_"))
    transcriptions: list[str] = []

    try:
        import re as _re

        for idx, f in enumerate(audio_files[:3], start=1):
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
                continue

            try:
                result = transcribe(tmp_path)
                raw_text = result.get("text", "").strip()
                if raw_text:
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

        counts = Counter(transcriptions)
        winner = counts.most_common(1)[0][0]

        wakeword_dir = _PROJECT_ROOT / "computation" / "wakeword"
        config_path = wakeword_dir / "wakeword_config.json"
        binary_path = wakeword_dir / "build" / "wakeword_matcher"

        variants_count = 0

        if binary_path.exists():
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
                    raise Exception(result.stderr)
            except Exception:
                pass

        if variants_count == 0:
            lookup_table = {}
            chars = "abcdefghijklmnopqrstuvwxyz"
            candidates = set()

            for i in range(len(winner)):
                for c in chars:
                    variant = winner[:i] + c + winner[i+1:]
                    candidates.add(variant)

            for i in range(len(winner) + 1):
                for c in chars:
                    variant = winner[:i] + c + winner[i:]
                    candidates.add(variant)

            for i in range(len(winner)):
                variant = winner[:i] + winner[i+1:]
                if len(variant) >= 2:
                    candidates.add(variant)

            for i in range(len(winner) - 1):
                variant = winner[:i] + winner[i+1] + winner[i] + winner[i+2:]
                candidates.add(variant)

            for candidate in candidates:
                score = difflib.SequenceMatcher(None, winner, candidate).ratio()
                if score >= 0.70:
                    lookup_table[candidate] = round(score, 4)

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

        from computation.intelligence.wakeword_detector import reload_config
        reload_config()

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


@app.get("/api/users")
async def users_endpoint():
    try:
        users = get_all_users()
        for u in users:
            u.pop("embedding_centroid", None)
            u.pop("mfcc_mean", None)
        return {"users": users, "count": len(users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@app.delete("/api/users/{name}")
async def delete_user_endpoint(name: str):
    from database.canary_db import delete_user, get_user
    import shutil

    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")

    name = name.strip()

    user = get_user(name)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{name}' not found.")

    try:
        ok = delete_user(name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not ok:
        raise HTTPException(status_code=404, detail=f"User '{name}' not found.")

    voices_dir = _PROJECT_ROOT / "database" / "Voices" / name
    try:
        if voices_dir.exists():
            shutil.rmtree(voices_dir, ignore_errors=True)
    except Exception:
        pass

    return {"name": name, "status": "deleted"}


from pydantic import BaseModel

class PriorityPayload(BaseModel):
    priority: int

@app.patch("/api/users/{name}/priority")
async def update_priority_endpoint(name: str, payload: PriorityPayload):
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")

    name = name.strip()

    if not (1 <= payload.priority <= 5):
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 5.")

    ok = update_priority(name, payload.priority)
    if not ok:
        raise HTTPException(status_code=404, detail=f"User '{name}' not found.")

    return {"name": name, "priority": payload.priority, "status": "updated"}


@app.get("/api/status")
async def status_endpoint():
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


import subprocess as _subprocess
import threading as _threading

_run_lock   = _threading.Lock()
_run_state  = {"status": "idle", "result": None, "error": None, "proc": None}


def _launch_run_canary():
    global _run_state
    python  = sys.executable
    script  = str(_PROJECT_ROOT / "run_canary.py")
    resp_p  = _PROJECT_ROOT / "response.json"

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
    with _run_lock:
        return {
            "status": _run_state["status"],
            "result": _run_state["result"],
            "error":  _run_state["error"],
        }
