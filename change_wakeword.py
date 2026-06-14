#!/usr/bin/env python3
"""
change_wakeword.py  –  The Canary Wakeword Configuration CLI
=============================================================
Records a new wake word 2–3 times, transcribes each with Whisper,
picks the majority-vote word, then calls the C++ Weighted Phonetic
Engine to build a full phonetic variant table and saves it as
wakeword/wakeword_config.json.

From that point on, wakeword_detector.py will use the new word instead
of "Canary". Run --reset to revert to Canary at any time.

Usage
-----
  python3 change_wakeword.py               # interactive: record + enroll
  python3 change_wakeword.py --reset       # delete config → back to Canary
  python3 change_wakeword.py --show        # show currently active wakeword
  python3 change_wakeword.py --build-only <word>  # skip recording, build table for <word>
  python3 change_wakeword.py --threshold 0.80     # custom similarity threshold

Architecture
------------
  1.  VAD-based recording (same _record_smart as add_voicer.py, 1.8s silence)
  2.  3 recordings → Whisper base → 3 transcriptions
  3.  Majority vote on single-word extraction
  4.  C++ binary: ./wakeword/build/wakeword_matcher --build-table <word>
  5.  Writes: wakeword/wakeword_config.json
  6.  wakeword_detector.py loads it on next import (zero run_canary.py changes)
"""

import os
import sys
import time
import json
import threading
import argparse
import warnings
import logging
import subprocess
from pathlib import Path
from collections import Counter

import numpy as np
import sounddevice as sd
import soundfile as sf

# ── Silence noisy loggers ────────────────────────────────────────────────────
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

# ── Paths ────────────────────────────────────────────────────────────────────
_ROOT        = Path(__file__).parent
_WAKEWORD_DIR = _ROOT / "computation" / "wakeword"
_BINARY      = _WAKEWORD_DIR / "build" / "wakeword_matcher"
_CONFIG_PATH = _WAKEWORD_DIR / "wakeword_config.json"

SAMPLE_RATE = 16_000

# ─────────────────────────────────────────────────────────────────────────────
#  Recording constants (identical to add_voicer.py)
# ─────────────────────────────────────────────────────────────────────────────
_CALIBRATION_SEC = 0.8
_SILENCE_TO_STOP = 1.8
_MIN_SPEECH_SEC  = 1.0   # shorter for a single word
_MAX_DURATION    = 15.0
_FRAME_LEN       = int(SAMPLE_RATE * 0.030)


# ─────────────────────────────────────────────────────────────────────────────
#  Terminal styling
# ─────────────────────────────────────────────────────────────────────────────
def _cls():
    os.system("cls" if os.name == "nt" else "clear")

def _banner():
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║     The Canary — Wake Word Configuration Studio    ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()

def _rule():
    print("  " + "─" * 54)

def _ok(t):   print(f"  ✓  {t}")
def _warn(t): print(f"  ⚠  {t}")
def _err(t):  print(f"  ✗  {t}")
def _h(t):    print(f"\n  ▶  {t}")


# ─────────────────────────────────────────────────────────────────────────────
#  Smart VAD recording  (verbatim from add_voicer.py)
# ─────────────────────────────────────────────────────────────────────────────
def _record_smart(label: str) -> np.ndarray:
    """
    VAD-driven smart recording with ENTER-to-stop fallback.
    Identical mechanism to add_voicer.py — 1.8 s silence auto-stop.
    """
    print()
    for i in (3, 2, 1):
        print(f"    {i} ...", end="\r", flush=True)
        time.sleep(1)
    print("                        ", end="\r", flush=True)

    frames      = []
    frames_lock = threading.Lock()
    stop_event  = threading.Event()

    def _audio_cb(indata, nf, ti, status):
        with frames_lock:
            frames.append(indata.copy())

    def _keyboard_watcher():
        try:
            if os.name == "nt":
                sys.stdin.readline()
                stop_event.set()
            else:
                import select
                while not stop_event.is_set():
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if rlist:
                        sys.stdin.readline()
                        stop_event.set()
                        break
        except Exception:
            pass

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32",
        blocksize=_FRAME_LEN, callback=_audio_cb,
    )
    stream.start()
    kb_thread = threading.Thread(target=_keyboard_watcher, daemon=True)
    kb_thread.start()

    # Calibrate noise floor
    print("  👂  Calibrating ...                                  ",
          end="\r", flush=True)
    time.sleep(_CALIBRATION_SEC)

    with frames_lock:
        cal_buf = np.concatenate(frames).squeeze() if frames else np.zeros(_FRAME_LEN)
    cal_n = len(cal_buf) // _FRAME_LEN
    if cal_n > 0:
        cal_rms = [
            float(np.sqrt(np.mean(cal_buf[i*_FRAME_LEN:(i+1)*_FRAME_LEN] ** 2)))
            for i in range(cal_n)
        ]
        noise_floor = max(float(np.percentile(cal_rms, 50)), 0.001)
    else:
        noise_floor = 0.004

    speech_thresh  = noise_floor * 3.0
    adapt_deadline = time.time() + 5.0

    print("  🎙  Say the wake word  —  auto-stops after silence  [ENTER to finish]  ",
          end="\r", flush=True)

    loop_start     = time.time()
    had_speech     = False
    speech_start   = None
    speech_seconds = 0.0
    silence_start  = None
    last_frame_idx = 0

    while not stop_event.is_set():
        elapsed = time.time() - loop_start
        if elapsed >= _MAX_DURATION:
            print(f"\n  ⏹  Max duration ({_MAX_DURATION:.0f}s) reached.             ")
            break

        if not had_speech and time.time() > adapt_deadline:
            speech_thresh *= 0.5
            adapt_deadline = time.time() + 5.0

        with frames_lock:
            n_now = len(frames)

        if n_now > last_frame_idx:
            with frames_lock:
                recent_slices = frames[max(0, n_now - 5):n_now]
            recent = np.concatenate(recent_slices).squeeze()
            rms    = float(np.sqrt(np.mean(recent ** 2)))
            last_frame_idx = n_now
            is_speech = rms > speech_thresh

            if is_speech:
                if not had_speech:
                    had_speech   = True
                    speech_start = time.time()
                silence_start  = None
                speech_seconds = time.time() - speech_start
                bar = "█" * min(int(speech_seconds * 4), 26)
                print(f"  🔴 {speech_seconds:4.1f}s  {bar:<26}  [ENTER to stop]  ",
                      end="\r", flush=True)

            elif had_speech:
                if silence_start is None:
                    silence_start = time.time()
                silence_dur = time.time() - silence_start

                if speech_seconds < _MIN_SPEECH_SEC:
                    bar = "▒" * min(int(speech_seconds * 4), 26)
                    print(f"  🔴 {speech_seconds:4.1f}s  {bar:<26}  (keep going ...)  ",
                          end="\r", flush=True)
                elif silence_dur >= _SILENCE_TO_STOP:
                    print(f"\n  ⏹  Done — auto-stopped.                              ")
                    break
                else:
                    countdown = _SILENCE_TO_STOP - silence_dur
                    bar = "█" * min(int(speech_seconds * 4), 26)
                    print(f"  ⏸  {speech_seconds:4.1f}s  {bar:<26}  stopping in {countdown:.1f}s  ",
                          end="\r", flush=True)
            else:
                dots = "." * (int(elapsed * 2) % 4)
                print(f"  👂  Waiting for speech {dots:<4}  [ENTER to finish early]  ",
                      end="\r", flush=True)

        time.sleep(0.04)

    if stop_event.is_set():
        print(f"\n  ⏹  Stopped by ENTER.                              ")

    stop_event.set()  # Signal keyboard watcher thread to exit if VAD auto-stopped
    stream.stop()
    stream.close()

    with frames_lock:
        if not frames:
            return np.zeros(SAMPLE_RATE, dtype=np.float32)
        return np.concatenate(frames).squeeze().astype(np.float32)


# ─────────────────────────────────────────────────────────────────────────────
#  ASR: transcribe a single word from audio
# ─────────────────────────────────────────────────────────────────────────────
def _transcribe_word(audio: np.ndarray) -> str | None:
    """
    Run Whisper 'base' on the audio and extract the first clean word.
    Returns None if transcription fails or is empty.
    """
    try:
        import whisper
        if not hasattr(whisper, "load_model"):
            raise ImportError("Wrong whisper package — run: pip install openai-whisper")
    except ImportError as e:
        _err(f"Whisper not available: {e}")
        return None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = whisper.load_model("base")
        result = model.transcribe(
            audio,
            language="en",
            fp16=False,
            word_timestamps=False,
        )

    raw = result.get("text", "").strip()
    if not raw:
        return None

    # Extract words — strip punctuation, lowercase, take first real word
    import re
    words = re.findall(r"[a-zA-Z']+", raw.lower())
    # Remove filler words
    fillers = {"hey", "hi", "ok", "okay", "oh", "um", "uh", "the", "a", "and"}
    clean = [w for w in words if w not in fillers and len(w) >= 2]
    if not clean:
        # If all were fillers, just take the first raw word
        clean = words

    return clean[0] if clean else None


# ─────────────────────────────────────────────────────────────────────────────
#  C++ binary: build the phonetic variant table
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_binary_built() -> bool:
    """Auto-build the C++ binary if it's not present."""
    if _BINARY.exists():
        return True

    _warn("C++ wakeword engine not built yet. Building now ...")
    makefile = _WAKEWORD_DIR / "Makefile"
    if not makefile.exists():
        _err("wakeword/Makefile not found. Cannot build engine.")
        return False

    try:
        result = subprocess.run(
            ["make"], cwd=str(_WAKEWORD_DIR),
            capture_output=False, timeout=60
        )
        if result.returncode != 0:
            _err("Build failed. See output above.")
            return False
        _ok("C++ engine built successfully.")
        return True
    except Exception as e:
        _err(f"Build error: {e}")
        return False


def _build_table(word: str, threshold: float) -> bool:
    """
    Call the C++ binary to generate wakeword_config.json.
    Returns True on success.
    """
    if not _ensure_binary_built():
        return False

    print(f"\n  ⚙️  Building phonetic variant table for '{word}' ...")
    print("     (Weighted DP engine — may take 2–5 seconds) ...")

    try:
        result = subprocess.run(
            [
                str(_BINARY),
                "--build-table", word,
                "--threshold",   str(threshold),
                "--output",      str(_CONFIG_PATH),
            ],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            _err(f"Engine error: {result.stderr.strip()}")
            return False

        data = json.loads(result.stdout)
        n = data.get("variants_generated", "?")
        _ok(f"Table built: {n} phonetic variants generated.")
        _ok(f"Config saved → {_CONFIG_PATH.relative_to(_ROOT)}")
        return True

    except subprocess.TimeoutExpired:
        _err("C++ engine timed out (>30s). Try again.")
        return False
    except Exception as e:
        _err(f"Unexpected error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Main enrollment flow
# ─────────────────────────────────────────────────────────────────────────────
def run_wakeword_enrollment(n_recordings: int = 3,
                             threshold: float = 0.75) -> None:
    """
    Record the wake word 2–3 times, pick majority-vote transcription,
    build phonetic table, save config.
    """
    _cls()
    _banner()
    _h("Say your new wake word clearly when prompted.")
    print("     You will be asked to say it 3 times.")
    print("     The system uses majority vote to determine the word.")
    _rule()

    tmp_dir = _ROOT / "computation" / "wakeword" / "_recordings"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    transcriptions: list[str] = []

    for attempt in range(1, n_recordings + 1):
        print(f"\n  Recording {attempt} of {n_recordings}")
        print("  Press ENTER to start:")
        input("  → ")

        audio = _record_smart(f"Wake word recording {attempt}")

        # Quality check
        rms_db = 20.0 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-10)
        if rms_db < -50.0:
            _warn(f"Recording too quiet ({rms_db:.0f} dBFS). Try again.")
            attempt -= 1
            continue

        # Save temp file
        tmp_path = tmp_dir / f"ww_{attempt}.wav"
        sf.write(str(tmp_path), audio, SAMPLE_RATE, subtype="PCM_16")

        print(f"\n  🔍  Transcribing recording {attempt} ...", flush=True)
        word = _transcribe_word(audio)

        if word:
            _ok(f"Heard: '{word}'")
            transcriptions.append(word)
        else:
            _warn("Could not transcribe. Please try again.")
            # Retry this slot
            if attempt < n_recordings:
                continue

    if not transcriptions:
        _err("No successful recordings. Aborting.")
        return

    # ── Majority vote ─────────────────────────────────────────────────────
    counts  = Counter(transcriptions)
    winner  = counts.most_common(1)[0][0]
    count_w = counts[winner]

    _rule()
    print(f"\n  Transcription results:")
    for t, c in counts.items():
        marker = "  ◀ selected" if t == winner else ""
        print(f"    '{t}'  ({c}x){marker}")
    print()

    if count_w < 2 and len(transcriptions) >= 2:
        _warn("No majority agreement — using most common transcription.")
    elif count_w == 1 and len(transcriptions) == 1:
        _warn("Only one recording succeeded — using it directly.")

    print(f"  Selected wake word: '{winner}'")

    if winner.lower() == "canary":
        _warn("'canary' is already the default wake word.")
        print("  Tip: You can use --reset to clear any custom config.")
        return

    # ── Build phonetic table ──────────────────────────────────────────────
    ok = _build_table(winner, threshold)
    if not ok:
        _err("Failed to build phonetic table. Wake word NOT changed.")
        return

    _rule()
    _ok(f"Wake word changed to: '{winner}'")
    print()
    print("  The system will now recognise phonetic variants of this word.")
    print("  Run  python3 run_canary.py  to test the new wake word.")
    print()
    print("  To revert to Canary:  python3 change_wakeword.py --reset")
    print()

    # Cleanup temp recordings
    for f in tmp_dir.glob("ww_*.wav"):
        f.unlink()


# ─────────────────────────────────────────────────────────────────────────────
#  CLI: --show / --reset / --build-only
# ─────────────────────────────────────────────────────────────────────────────
def cmd_show() -> None:
    """Show the currently active wakeword configuration."""
    _banner()
    if not _CONFIG_PATH.exists():
        print("  Active wake word   : canary  (default)")
        print("  Config file        : not present (Canary mode)")
    else:
        try:
            cfg = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            word      = cfg.get("word", "?")
            threshold = cfg.get("threshold", 0.75)
            n_variants = len(cfg.get("lookup_table", {}))
            print(f"  Active wake word   : {word}")
            print(f"  Similarity threshold: {threshold}")
            print(f"  Phonetic variants  : {n_variants}")
            print(f"  Config file        : {_CONFIG_PATH.relative_to(_ROOT)}")
        except Exception as e:
            _err(f"Could not read config: {e}")
    print()


def cmd_reset() -> None:
    """Delete custom config → revert to Canary."""
    _banner()
    if _CONFIG_PATH.exists():
        _CONFIG_PATH.unlink()
        _ok("Custom wake word config deleted.")
        _ok("Active wake word is now: canary (default)")
    else:
        print("  No custom config present — already using Canary (default).")
    print()


def cmd_build_only(word: str, threshold: float) -> None:
    """Build phonetic table for a word without recording."""
    _banner()
    print(f"  Building table for: '{word}'")
    _rule()
    ok = _build_table(word, threshold)
    if ok:
        print()
        _ok(f"Wake word set to: '{word}'")
        print("  Run  python3 run_canary.py  to use the new wake word.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="The Canary — Wake Word Configuration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 change_wakeword.py                     # interactive: record + enroll
  python3 change_wakeword.py --show              # show current wake word
  python3 change_wakeword.py --reset             # revert to Canary
  python3 change_wakeword.py --build-only jarvis # skip recording
  python3 change_wakeword.py --threshold 0.80    # stricter matching
        """,
    )
    parser.add_argument("--show",        action="store_true",
                        help="Show currently active wake word and exit")
    parser.add_argument("--reset",       action="store_true",
                        help="Delete custom config — revert to Canary")
    parser.add_argument("--build-only",  type=str, default=None, metavar="WORD",
                        help="Build phonetic table for WORD without recording")
    parser.add_argument("--threshold",   type=float, default=0.75,
                        help="Similarity threshold [0.0–1.0] (default: 0.75)")
    parser.add_argument("--recordings",  type=int, default=3,
                        help="Number of recordings to take (default: 3, min: 2)")
    args = parser.parse_args()

    if args.show:
        cmd_show()
        return

    if args.reset:
        cmd_reset()
        return

    if args.build_only:
        cmd_build_only(args.build_only.strip().lower(), args.threshold)
        return

    n_recs = max(2, min(args.recordings, 5))
    run_wakeword_enrollment(n_recordings=n_recs, threshold=args.threshold)


if __name__ == "__main__":
    main()
