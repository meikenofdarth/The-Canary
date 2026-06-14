#!/usr/bin/env python3
"""
run_execution.py
================
The Canary — Execution Engine

Two modes:

  Watch mode (default — no arguments):
      Continuously watches the outputs/ directory for new response.json files
      produced by run_canary.py. When a new one appears, automatically
      triggers the execution engine. Runs forever until Ctrl+C.

      python3 run_execution.py

  One-shot mode (with a file path):
      Process a specific response.json once and exit.

      python3 run_execution.py outputs/20260614_170514/response.json
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.queue import process_arbitration


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_latest_response() -> Path | None:
    """Return the most-recently modified response.json under outputs/."""
    outputs_dir = Path("outputs")
    if not outputs_dir.exists():
        return None
    files = list(outputs_dir.rglob("response.json"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _load_and_run(path: Path) -> None:
    """Load a response.json and feed it to the execution engine."""
    print(f"\n[Execution] Processing: {path}")
    try:
        with open(path, "r") as f:
            payload = json.load(f)
        process_arbitration(payload)
    except json.JSONDecodeError as e:
        print(f"[Execution] JSON parse error: {e}")
    except Exception as e:
        print(f"[Execution] Error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  Watch mode — runs forever, processes new outputs as they arrive
# ─────────────────────────────────────────────────────────────────────────────

def watch() -> None:
    print("[Watcher] Watching outputs/ for new voice commands...  (Ctrl+C to stop)")

    last_file:  Path | None = None
    last_mtime: float       = 0.0

    while True:
        latest = get_latest_response()

        if latest:
            try:
                mtime = latest.stat().st_mtime
            except OSError:
                time.sleep(1)
                continue

            if latest != last_file or mtime > last_mtime:
                # Give run_canary.py a moment to finish writing the file
                time.sleep(0.5)
                _load_and_run(latest)
                last_file  = latest
                last_mtime = mtime

        time.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
#  One-shot mode
# ─────────────────────────────────────────────────────────────────────────────

def run_once(path: Path) -> None:
    if not path.exists():
        print(f"Error: File '{path}' not found.")
        sys.exit(1)
    _load_and_run(path)


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        # One-shot: process the given file and exit
        run_once(Path(sys.argv[1]))
    else:
        # Watch mode: loop forever
        try:
            watch()
        except KeyboardInterrupt:
            print("\n[Watcher] Stopped.")


if __name__ == "__main__":
    main()
