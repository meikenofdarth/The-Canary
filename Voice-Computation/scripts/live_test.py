#!/usr/bin/env python3
import sys
import time
import yaml
import signal
import queue
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Voice_Computation import CanaryPipeline


def main():
    config_path = Path(__file__).resolve().parent.parent / "config" / "pipeline_config.yaml"
    pipeline = CanaryPipeline(config_path=str(config_path))

    output_queue = pipeline.run_online()

    def shutdown(sig, frame):
        print("\nShutting down...")
        pipeline.stop_online()
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)

    print("Starting The Canary pipeline (live)...")
    print("Say the wake word followed by a command.")
    print("Output written to outputs/pipeline_output.json")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            try:
                out = output_queue.get(timeout=0.5)
                print(f"[Pipeline] Mode={out.mode.value} SCS={out.scene_complexity_score:.3f}")
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
