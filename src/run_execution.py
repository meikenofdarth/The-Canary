#!/usr/bin/env python3

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))  # project root → finds database/

from backend.queue import process_arbitration


def get_latest_response():
    outputs_dir = Path("outputs")
    if not outputs_dir.exists():
        return None
    files = list(outputs_dir.rglob("response.json"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _load_and_run(path: Path) -> None:
    print(f"\n[Execution] Processing: {path}")
    try:
        with open(path, "r") as f:
            payload = json.load(f)
        process_arbitration(payload)
    except json.JSONDecodeError as e:
        print(f"[Execution] JSON parse error: {e}")
    except Exception as e:
        print(f"[Execution] Error: {e}")


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
                time.sleep(0.5)
                _load_and_run(latest)
                last_file  = latest
                last_mtime = mtime

        time.sleep(1)


def run_once(path: Path) -> None:
    if not path.exists():
        print(f"Error: File '{path}' not found.")
        sys.exit(1)
    _load_and_run(path)


def main():
    if len(sys.argv) > 1:
        run_once(Path(sys.argv[1]))
    else:
        try:
            watch()
        except KeyboardInterrupt:
            print("\n[Watcher] Stopped.")


if __name__ == "__main__":
    main()
