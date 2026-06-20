#!/usr/bin/env python3

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

logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub.utils._headers").setLevel(logging.ERROR)
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

SAMPLE_RATE   = 16_000
SILENCE_GATE  = -50.0


def _cls():
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


_CALIBRATION_SEC  = 0.8
_SILENCE_TO_STOP  = 1.8
_MIN_SPEECH_SEC   = 2.5
_MAX_DURATION     = 30.0
_FRAME_LEN        = int(SAMPLE_RATE * 0.030)


def _record_smart(label: str) -> np.ndarray:
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
    adapt_deadline  = time.time() + 5.0

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

        time.sleep(0.04)

    if stop_event.is_set():
        print(f"\n  ⏹  Stopped by ENTER.                              ")

    stop_event.set()
    stream.stop()
    stream.close()

    with frames_lock:
        if not frames:
            return np.zeros(SAMPLE_RATE, dtype=np.float32)
        audio = np.concatenate(frames).squeeze().astype(np.float32)

    return audio


def _check_quality(audio: np.ndarray) -> tuple:
    rms_db = 20.0 * np.log10(np.sqrt(np.mean(audio ** 2)) + 1e-10)
    if rms_db < SILENCE_GATE:
        return False, f"Recording too quiet ({rms_db:.0f} dBFS). Please speak louder."

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


def run_enrollment(name: str) -> None:
    from computation.voice.enroll import enroll_speaker, get_profile, list_enrolled

    _cls()
    _banner()
    print(f"  Enrolling speaker:  {name}")
    _rule()

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
            _run_recording_flow(name, mode="append")
            return
        else:
            print("  Re-enrolling — existing profile will be replaced.")

    _run_recording_flow(name, mode="replace")


def _extract_hints_from_recordings(name: str) -> dict:
    import re
    hints: dict = {}

    rec_dir = Path(__file__).parent / "Voices" / name / "recordings"
    if not rec_dir.exists():
        return hints

    for txt_file in rec_dir.glob("*.txt"):
        try:
            text = txt_file.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue

        m = re.search(r"(?:my city is|i live in|i am from|from)\s+([A-Za-z\s]+?)(?:\.|,|$)", text)
        if m and "city" not in hints:
            hints["city"] = m.group(1).strip().title()

        m = re.search(r"i (?:like|love|enjoy|prefer)\s+([A-Za-z\-]+)\s+music", text)
        if m and "favorite_genre" not in hints:
            hints["favorite_genre"] = m.group(1).strip().title()

    return hints


def _ask_personalization(name: str, profile: dict) -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import canary_db

    hints = _extract_hints_from_recordings(name)

    _rule()
    print()
    print("  Almost done! A few quick personalization questions:")
    print()
    print("  ─────────────────────────────────────────────────────────────────")

    default_city = hints.get("city", "Bengaluru")
    city_input = input(
        f"  1. What city are you in? (used for weather & news)  [{default_city}]\n"
        "     > "
    ).strip()
    city = city_input if city_input else default_city

    default_news = "India"
    news_input = input(
        f"\n  2. What's your preferred news region? (e.g. India, US, UK, global)  [{default_news}]\n"
        "     > "
    ).strip()
    news_country = news_input if news_input else default_news

    default_genre = hints.get("favorite_genre", "Pop")
    genre_input = input(
        f"\n  3. What's your favourite music genre?  (e.g. Pop, Rock, Jazz, Hip-Hop, Classical)  [{default_genre}]\n"
        "     > "
    ).strip()
    favorite_genre = genre_input if genre_input else default_genre

    print("  ─────────────────────────────────────────────────────────────────")
    print()

    prefs = {
        "city":           city,
        "news_country":   news_country,
        "favorite_genre": favorite_genre,
    }

    try:
        from database.canary_db import update_preferences
        update_preferences(name, prefs)
        _ok(f"Preferences saved: city={city}, news={news_country}, genre={favorite_genre}")
    except Exception as e:
        _warn(f"Could not save preferences to DB: {e}")

    print()


def _run_recording_flow(name: str, mode: str = "replace") -> None:
    from computation.voice.enroll import enroll_speaker, _recordings_dir, _speaker_dir

    voices_root = Path(__file__).parent / "database" / "Voices"
    spk_dir     = voices_root / name
    spk_dir.mkdir(parents=True, exist_ok=True)
    rec_dir = spk_dir / "recordings"
    rec_dir.mkdir(exist_ok=True)

    if mode == "append":
        existing = sorted(rec_dir.glob("sample_*.wav"))
        start_idx = len(existing) + 1
    else:
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
        profile = enroll_speaker(name, [])

    _rule()
    _ok(f"Enrollment complete for '{name}'!")
    print()
    print(f"  Recordings  : {profile['recording_count']}")
    print(f"  Mean pitch  : {profile['pitch']['mean']:.1f} Hz")
    print(f"  Speech rate : {profile['speech_rate']:.2f} syl/sec")
    print(f"  Profile     : Voices/{name}/profile.json")
    print()

    _ask_personalization(name, profile)

    print("  Run  python3 run_canary.py  to use speaker identification.")
    print()


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

    if args.list:
        from computation.voice.enroll import list_enrolled, get_profile
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

    if args.rebuild:
        from computation.voice.enroll import rebuild_all_profiles
        _banner()
        print("  Rebuilding all speaker profiles from existing recordings ...\n")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rebuild_all_profiles()
        print("\n  Done.\n")
        sys.exit(0)


    if args.name:
        name = args.name.strip()
    else:
        _banner()
        print("  Enter the speaker's name:")
        name = input("  Name: ").strip()
        if not name:
            _err("No name provided. Exiting.")
            sys.exit(1)

    name = " ".join(w[0].upper() + w[1:] for w in name.split() if w)

    run_enrollment(name)


if __name__ == "__main__":
    main()
