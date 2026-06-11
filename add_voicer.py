#!/usr/bin/env python3
"""
add_voicer.py  –  The Canary Voice Enrollment CLI
==================================================
Run:  python3 add_voicer.py

Guides a user through recording 3 scripted utterances and enrolls their
voice profile into the Voice Identity Engine.

Completely independent from run_canary.py. Safe to run at any time.

Usage
-----
  python3 add_voicer.py                    # interactive mode
  python3 add_voicer.py --name "Hemang"   # skip name prompt
  python3 add_voicer.py --rebuild          # rebuild ALL profiles from existing recordings
  python3 add_voicer.py --list             # list enrolled speakers
"""

import os
import sys
import time
import threading
import argparse
import warnings
import logging
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))

# ── Suppress HuggingFace Hub rate-limit / unauthenticated-request warning ─────
# The model is cached locally after first download; the HF Hub is not contacted
# at runtime. This warning is a false alarm for offline usage.
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub.utils._headers").setLevel(logging.ERROR)
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

SAMPLE_RATE   = 16_000
SILENCE_GATE  = -50.0       # dBFS below which we consider it silence (quality gate)


# ─────────────────────────────────────────────────────────────────────────────
#  Terminal styling helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cls():
    """Clear the terminal."""
    import os
    os.system("cls" if os.name == "nt" else "clear")


def _banner():
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║        The Canary — Voice Enrollment Studio        ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()


def _rule():
    print("  " + "─" * 54)


def _h(text: str):
    print(f"\n  ▶  {text}")


def _ok(text: str):
    print(f"  ✓  {text}")


def _warn(text: str):
    print(f"  ⚠  {text}")


def _err(text: str):
    print(f"  ✗  {text}")


# ─────────────────────────────────────────────────────────────────────────────
#  Enrollment scripts
# ─────────────────────────────────────────────────────────────────────────────

SCRIPTS = [
    {
        "label": "Script 1 — Natural Speech",
        "instruction": "Speak clearly and naturally at your normal pace.",
        "text": (
            "Canary, my name is [your name]. Today I am recording my voice profile "
            "for speaker identification. I am speaking naturally and clearly so the "
            "system can learn the characteristics of my voice."
        ),
    },
    {
        "label": "Script 2 — Varied Pace",
        "instruction": "Start a little faster, then slow down — vary your rhythm.",
        "text": (
            "Canary, I would like to test different speaking styles. Sometimes I speak "
            "quickly, sometimes slowly, and sometimes with more excitement. This "
            "recording helps capture those variations."
        ),
    },
    {
        "label": "Script 3 — Questions & Commands",
        "instruction": "Use natural question and command intonation.",
        "text": (
            "Canary, can you tell me the weather today? "
            "Canary, please play some relaxing music. "
            "Canary, remind me about my meeting tomorrow morning."
        ),
    },
]


# ─────────────────────────────────────────────────────────────────────────────
#  Recording  —  VAD-based auto-stop
# ─────────────────────────────────────────────────────────────────────────────

# Smart recording constants
_CALIBRATION_SEC  = 0.8    # measure ambient noise floor from first N seconds
_SILENCE_TO_STOP  = 1.8    # seconds of silence after speech → auto-stop
_MIN_SPEECH_SEC   = 2.5    # must capture at least this much speech before stopping
_MAX_DURATION     = 30.0   # hard cap so the loop always terminates
_FRAME_LEN        = int(SAMPLE_RATE * 0.030)   # 30 ms VAD frame


def _record_smart(label: str) -> np.ndarray:
    """
    VAD-driven smart recording with ENTER-to-stop fallback.

    Phases
    ------
    1. 3-2-1 countdown  (no audio captured yet).
    2. Calibrate: 0.8 s of ambient audio → estimate noise floor.
    3. Listen / Record: show live RMS bar while speech is detected.
    4. Trailing: 1.8 s post-speech silence countdown; speech resumes → cancel.
    5. Auto-stop OR user presses ENTER.

    Adaptive threshold: if no speech is detected for 5 s, halve the threshold
    automatically (handles mics with very low gain or quiet speakers).

    Hard cap: 30 s total.
    Returns float32 mono ndarray at SAMPLE_RATE.
    """
    # ── 3-2-1 countdown (no stream yet) ──────────────────────────────────
    print()
    for i in (3, 2, 1):
        print(f"    {i} ...", end="\r", flush=True)
        time.sleep(1)
    print("                        ", end="\r", flush=True)

    # ── Shared state ──────────────────────────────────────────────────────
    frames      = []
    frames_lock = threading.Lock()
    stop_event  = threading.Event()   # set by keyboard thread or VAD

    def _audio_cb(indata, nf, ti, status):
        with frames_lock:
            frames.append(indata.copy())

    def _keyboard_watcher():
        """Daemon thread: pressing ENTER sets stop_event."""
        try:
            sys.stdin.readline()
            stop_event.set()
        except Exception:
            pass

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="float32",
        blocksize=_FRAME_LEN, callback=_audio_cb,
    )
    stream.start()

    kb_thread = threading.Thread(target=_keyboard_watcher, daemon=True)
    kb_thread.start()

    # ── Phase 1: calibrate noise floor ────────────────────────────────────
    #
    # Use the 50th-percentile (median) of 30-ms frame RMS values, then ×3.0.
    # Median is robust to transient sounds during calibration.
    # A minimum floor of 0.001 prevents the threshold being set to zero in
    # an anechoically quiet room.
    #
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

    speech_thresh   = noise_floor * 3.0
    adapt_deadline  = time.time() + 5.0   # halve threshold if no speech by then

    # ── Phase 2-5: VAD loop ───────────────────────────────────────────────
    print("  🎙  Speak now  —  auto-stops after silence  [ENTER to finish]  ",
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

        # Adaptive threshold: if quiet mic / quiet speaker, lower the bar
        if not had_speech and time.time() > adapt_deadline:
            speech_thresh *= 0.5
            adapt_deadline = time.time() + 5.0   # allow another 5 s before next halving

        with frames_lock:
            n_now = len(frames)

        if n_now > last_frame_idx:
            # Analyse the 5 most recent 30-ms frames (~150 ms window)
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
                bar = "█" * min(int(speech_seconds * 2), 26)
                print(f"  🔴 {speech_seconds:4.1f}s  {bar:<26}  [ENTER to stop]  ",
                      end="\r", flush=True)

            elif had_speech:
                if silence_start is None:
                    silence_start = time.time()
                silence_dur = time.time() - silence_start

                if speech_seconds < _MIN_SPEECH_SEC:
                    bar = "▒" * min(int(speech_seconds * 2), 26)
                    print(f"  🔴 {speech_seconds:4.1f}s  {bar:<26}  (keep going ...)  ",
                          end="\r", flush=True)
                elif silence_dur >= _SILENCE_TO_STOP:
                    print(f"\n  ⏹  Done — auto-stopped.                              ")
                    break
                else:
                    countdown = _SILENCE_TO_STOP - silence_dur
                    bar = "█" * min(int(speech_seconds * 2), 26)
                    print(f"  ⏸  {speech_seconds:4.1f}s  {bar:<26}  stopping in {countdown:.1f}s  ",
                          end="\r", flush=True)

            else:
                dots = "." * (int(elapsed * 2) % 4)
                print(f"  👂  Waiting for speech {dots:<4}  [ENTER to finish early]  ",
                      end="\r", flush=True)

        time.sleep(0.04)   # ~25 Hz polling

    if stop_event.is_set():
        print(f"\n  ⏹  Stopped by ENTER.                              ")

    stream.stop()
    stream.close()

    with frames_lock:
        if not frames:
            return np.zeros(SAMPLE_RATE, dtype=np.float32)
        audio = np.concatenate(frames).squeeze().astype(np.float32)

    return audio


def _check_quality(audio: np.ndarray) -> tuple:
    """
    Quick quality gate.
    Returns (ok: bool, reason: str).
    """
    rms_db = 20.0 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-10)
    if rms_db < SILENCE_GATE:
        return False, f"Recording too quiet ({rms_db:.0f} dBFS). Please speak louder."

    # Check that at least 20% of frames are voiced
    frame_len = int(SAMPLE_RATE * 0.030)
    n_frames  = len(audio) // frame_len
    if n_frames == 0:
        return False, "Recording too short."

    rms_vals   = np.array([
        np.sqrt(np.mean(audio[i * frame_len:(i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    noise_floor = float(np.percentile(rms_vals, 10)) + 1e-10
    voiced_frac = float(np.mean(rms_vals > noise_floor * 3.0))

    if voiced_frac < 0.20:
        return False, f"Only {voiced_frac:.0%} of the recording contains speech. Please speak more."

    return True, f"OK  (RMS: {rms_db:.0f} dBFS, voiced: {voiced_frac:.0%})"


# ─────────────────────────────────────────────────────────────────────────────
#  Main enrollment flow
# ─────────────────────────────────────────────────────────────────────────────

def run_enrollment(name: str) -> None:
    """Interactively record 3 scripts and enroll the speaker."""
    from voice_computation.enroll import enroll_speaker, get_profile, list_enrolled

    _cls()
    _banner()
    print(f"  Enrolling speaker:  {name}")
    _rule()

    # Check if already enrolled
    existing = get_profile(name)
    if existing:
        n_recs = existing.get("recording_count", 0)
        _warn(f"'{name}' already has {n_recs} recording(s) enrolled.")
        print()
        print("  Options:")
        print("    [r] Re-enroll (replace existing profile)")
        print("    [a] Add more recordings to existing profile")
        print("    [q] Quit")
        print()
        choice = input("  Your choice: ").strip().lower()
        if choice == "q":
            print("\n  Exiting.\n")
            sys.exit(0)
        elif choice == "a":
            # Will append to existing recordings
            _run_recording_flow(name, mode="append")
            return
        else:
            print("  Re-enrolling — existing profile will be replaced.")

    _run_recording_flow(name, mode="replace")


def _run_recording_flow(name: str, mode: str = "replace") -> None:
    """Record 3 scripts, save them, then call enroll_speaker."""
    from voice_computation.enroll import enroll_speaker, _recordings_dir, _speaker_dir

    voices_root = Path(__file__).parent / "Voices"
    spk_dir     = voices_root / name
    spk_dir.mkdir(parents=True, exist_ok=True)
    rec_dir = spk_dir / "recordings"
    rec_dir.mkdir(exist_ok=True)

    # Determine starting index for recordings
    if mode == "append":
        existing = sorted(rec_dir.glob("sample_*.wav"))
        start_idx = len(existing) + 1
    else:
        # Replace mode: clear existing recordings
        for f in rec_dir.glob("sample_*.wav"):
            f.unlink()
        start_idx = 1

    saved_paths = []

    for script_idx, script in enumerate(SCRIPTS, start=1):
        _rule()
        print(f"\n  📋  {script['label']}")
        print()
        print(f"  💡  {script['instruction']}")
        print()
        print("  ┌─────────────────────────────────────────────────────┐")
        # Word-wrap the script text at ~55 chars
        words  = script["text"].split()
        line   = ""
        for word in words:
            if len(line) + len(word) + 1 > 55:
                print(f"  │  {line}")
                line = word
            else:
                line = line + " " + word if line else word
        if line:
            print(f"  │  {line}")
        print("  └─────────────────────────────────────────────────────┘")

        while True:
            print()
            print("  Press  ENTER  to start recording  "
                  "(press ENTER again anytime to stop early) ...")
            input("  → ")

            audio = _record_smart(script["label"])
            ok, reason = _check_quality(audio)

            if ok:
                _ok(f"Quality check passed — {reason}")
                # Save to disk
                sample_num = start_idx + script_idx - 1
                dest       = rec_dir / f"sample_{sample_num}.wav"
                sf.write(str(dest), audio, SAMPLE_RATE, subtype="PCM_16")
                saved_paths.append(dest)
                _ok(f"Saved → {dest.relative_to(Path(__file__).parent)}")
                break
            else:
                _warn(f"Quality check failed — {reason}")
                retry = input("  Try again? [y/n]: ").strip().lower()
                if retry != "y":
                    _warn("Skipping this recording.")
                    break

    if not saved_paths:
        _err("No recordings were saved. Enrollment aborted.")
        sys.exit(1)

    _rule()
    print(f"\n  Building voice profile for '{name}' ...")
    print("  (This will take ~30–60 seconds while models compute features)\n")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # Pass empty list — enroll_speaker will pick up recordings/ automatically
        profile = enroll_speaker(name, [])

    _rule()
    _ok(f"Enrollment complete for '{name}'!")
    print()
    print(f"  Recordings  : {profile['recording_count']}")
    print(f"  Mean pitch  : {profile['pitch']['mean']:.1f} Hz")
    print(f"  Speech rate : {profile['speech_rate']:.2f} syl/sec")
    print(f"  Profile     : Voices/{name}/profile.json")
    print()
    print("  Run  python3 run_canary.py  to use speaker identification.")
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="The Canary — Voice Enrollment CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 add_voicer.py                   # interactive mode
  python3 add_voicer.py --name Hemang     # skip name prompt
  python3 add_voicer.py --list            # show enrolled speakers
  python3 add_voicer.py --rebuild         # rebuild all profiles
        """,
    )
    parser.add_argument("--name",    type=str, default=None,
                        help="Speaker name (skip interactive prompt)")
    parser.add_argument("--list",    action="store_true",
                        help="List all enrolled speakers and exit")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild ALL profiles from existing recordings")

    args = parser.parse_args()

    # ── List mode ─────────────────────────────────────────────────────────
    if args.list:
        from voice_computation.enroll import list_enrolled, get_profile
        _banner()
        enrolled = list_enrolled()
        if not enrolled:
            print("  No speakers enrolled yet.")
            print("  Run  python3 add_voicer.py  to enroll the first speaker.")
        else:
            print(f"  Enrolled speakers ({len(enrolled)}):")
            print()
            for name in enrolled:
                p = get_profile(name)
                n_recs = p.get("recording_count", "?") if p else "?"
                pitch  = p["pitch"]["mean"] if p else 0
                rate   = p.get("speech_rate", 0) if p else 0
                print(f"    • {name:<14}  {n_recs} recording(s)  "
                      f"pitch: {pitch:.0f} Hz  rate: {rate:.2f} syl/s")
        print()
        sys.exit(0)

    # ── Rebuild mode ──────────────────────────────────────────────────────
    if args.rebuild:
        from voice_computation.enroll import rebuild_all_profiles
        _banner()
        print("  Rebuilding all speaker profiles from existing recordings ...\n")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rebuild_all_profiles()
        print("\n  Done.\n")
        sys.exit(0)

    # ── Interactive / named enrollment ────────────────────────────────────
    # NOTE: run_enrollment() calls _cls() + _banner() itself.
    # Do NOT call _banner() here — it would print twice.

    if args.name:
        name = args.name.strip()
    else:
        _banner()
        print("  Enter the speaker's name:")
        name = input("  Name: ").strip()
        if not name:
            _err("No name provided. Exiting.")
            sys.exit(1)

    # Capitalise each word so multi-word names look right
    # e.g. "mother dear" → "Mother Dear",  "hemang" → "Hemang"
    name = " ".join(w[0].upper() + w[1:] for w in name.split() if w)

    run_enrollment(name)


if __name__ == "__main__":
    main()
