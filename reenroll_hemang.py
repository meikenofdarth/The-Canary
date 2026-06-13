#!/usr/bin/env python3
"""
reenroll_hemang.py
==================
Re-enroll Hemang Seth using:
  1. Existing Voices/Hemang Seth/recordings/  samples
  2. Confirmed-Hemang speaker_1.wav files from outputs/ where ASR transcript
     is clean English speech (not noise/hallucinations)

Also rebuilds Deepkumar and Sanchit profiles from their existing recordings.

Run once:
    python3 reenroll_hemang.py
"""

import sys, shutil, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT        = Path(__file__).parent
VOICES_ROOT = ROOT / "Voices"
OUTPUTS     = ROOT / "outputs"

# ── 1. Collect confirmed-Hemang output sessions ─────────────────────────────
# These are output sessions where the transcript is confirmed Hemang's voice
# (English, clean, meaningful speech — reviewed by the user)
CONFIRMED_HEMANG_SESSIONS = [
    "20260613_015906",  # "Hey Hari Ram Krishna..."
    "20260613_020016",  # "Hey city, how are you?"
    "20260613_020505",  # "Hi Canary, how are you? How was your day?"
    "20260611_233034",  # "Canary my day was so bad..."  speaker_1
]

hemang_dir  = VOICES_ROOT / "Hemang Seth"
rec_dir     = hemang_dir / "recordings"
rec_dir.mkdir(parents=True, exist_ok=True)

# Count existing samples
existing = sorted(rec_dir.glob("sample_*.wav"))
next_idx = len(existing) + 1

print(f"\n[re-enroll] Hemang Seth — {len(existing)} existing sample(s)")
print("[re-enroll] Collecting confirmed output recordings ...\n")

added = 0
for session in CONFIRMED_HEMANG_SESSIONS:
    src = OUTPUTS / session / "speaker_1.wav"
    if not src.exists():
        print(f"  ⚠  {session}/speaker_1.wav not found — skipping")
        continue

    # Check we haven't already copied it (by size match)
    already = False
    for ex in existing:
        if ex.stat().st_size == src.stat().st_size:
            already = True
            break

    if already:
        print(f"  ✓  {session}/speaker_1.wav already enrolled — skip")
        continue

    dst = rec_dir / f"sample_{next_idx}.wav"
    shutil.copy2(str(src), str(dst))
    print(f"  +  {session}/speaker_1.wav  →  {dst.name}")
    next_idx += 1
    added += 1

print(f"\n[re-enroll] Added {added} new recording(s).")

# ── 2. Re-enroll Hemang Seth ─────────────────────────────────────────────────
print("\n[re-enroll] Re-building Hemang Seth profile ...")
from voice_computation.enroll import enroll_speaker, rebuild_all_profiles

# audio_paths=[] → enroll from existing recordings/ folder
enroll_speaker("Hemang Seth", [])

# ── 3. Rebuild other profiles so they stay consistent ────────────────────────
print("\n[re-enroll] Rebuilding Deepkumar profile ...")
enroll_speaker("Deepkumar", [])

print("\n[re-enroll] Rebuilding Sanchit profile ...")
enroll_speaker("Sanchit", [])

print("\n✅  All profiles rebuilt.  Run python3 run_canary.py to test.\n")
