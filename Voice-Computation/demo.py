"""Demo runner for the Voice-Computation pipeline.

USAGE:
    python -m Voice-Computation                    # mic, 7 s
    python -m Voice-Computation --input file.wav   # from WAV file
    python -m Voice-Computation --live             # continuous
    python -m Voice-Computation --bypass-wakeword  # skip wake-word gate
    python -m Voice-Computation -v                 # verbose logging
"""

import argparse
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from .config import VoiceConfig
from .models import ScalerDecision
from .pipeline import VoiceComputationPipeline

logger = logging.getLogger(__name__)

# ── Terminal helpers ───────────────────────────────────────────────────────────

_SEP = "-" * 52
_SEP2 = "=" * 52


def _line(label: str, value: str, width: int = 24) -> str:
    return f"  {label:<{width}}: {value}"


def print_banner():
    print(_SEP2)
    print("  THE CANARY  —  Voice Computation Module")
    print("  Stage 0  : VAD  +  Wake-Word")
    print("  Routing  : LIGHT (A)  /  MEDIUM (B)  /  HEAVY (C)")
    print(_SEP2)
    print()


def print_result(
    decision: Optional[ScalerDecision],
    wakeword_detected: bool,
    wakeword_conf: float,
    wakeword_keyword: str,
    ww_transcript: str = "",
    vad_prob: float = 0.0,
    audio_duration_s: float = 0.0,
    pipeline: Optional["VoiceComputationPipeline"] = None,
    saved_path: str = "",
):
    """Print the clean, emoji-free result to the terminal."""

    print(_SEP)
    print("  DETECTION RESULT")
    print(_SEP)

    # --- Wake-word ---
    if wakeword_detected:
        ww_status = "YES  —  keyword: '{}'  (conf={:.3f})".format(
            wakeword_keyword, wakeword_conf
        )
    else:
        ww_status = "NO"
    print(_line("Speech detected", "YES  (prob={:.3f})".format(vad_prob)))
    print(_line("Wake word detected", ww_status))
    print()

    # --- Mode routing ---
    if decision is None:
        print(_line("Routing decision", "DROPPED"))
        print(_line("Reason", "No speech / wake word not heard"))
        print(_line("Tip", "Use --bypass-wakeword to process all speech"))
    else:
        mode_val = decision.mode.value
        mode_name = {"A": "LIGHT", "B": "MEDIUM", "C": "HEAVY"}.get(mode_val, mode_val)
        mode_desc = {
            "A": "Clean audio, single speaker  ->  direct ASR",
            "B": "Moderate noise / mild overlap  ->  adaptive DSP",
            "C": "Heavy overlap / noisy  ->  full TIGER separation",
        }.get(mode_val, "")

        scs_bar_len = 20
        scs = decision.scene_complexity_score
        filled = int(scs * scs_bar_len)
        scs_bar = "[" + "#" * filled + "." * (scs_bar_len - filled) + "]"

        print(_line("Mode", "{} ({})".format(mode_name, mode_val)))
        print(_line("Description", mode_desc))
        print()
        print("  METRICS")
        print(_SEP)
        print(_line("VAD confidence", "{:.3f}".format(decision.vad_confidence)))
        print(_line("Wake-word conf", "{:.3f}".format(decision.wakeword_confidence)))
        print(_line("Scene complexity", "{:.3f}  {}".format(scs, scs_bar)))
        cfg = pipeline.config if pipeline else VoiceConfig()
        print(_line("  -> thresholds", "A < {:.2f}  |  {:.2f} <= B < {:.2f}  |  C >= {:.2f}".format(
            cfg.scs_threshold_a, cfg.scs_threshold_a, cfg.scs_threshold_b, cfg.scs_threshold_b
        )))
        print(_line("Speaker count", str(decision.estimated_speaker_count)))
        print(_line("Overlap prob", "{:.3f}".format(decision.overlap_probability)))
        print(_line("Noise floor", "{:.1f} dB".format(decision.noise_floor_db)))
        print(_line("SNR estimate", "{:.1f} dB".format(decision.snr_estimate_db)))
        print(_line("Directed speech", str(decision.is_directed_speech)))
        print(_line("Audio duration", "{:.2f} s".format(audio_duration_s)))

    print()
    stats = pipeline.stats
    print("  PIPELINE STATS")
    print(_SEP)
    print(_line("Total processed", str(stats["total_chunks"])))
    print(_line("Activations", str(stats["total_activations"])))
    print(_line("Dropped", str(stats["total_drops"])))
    drop_pct = stats["drop_rate"] * 100
    print(_line("Drop rate", "{:.1f}%".format(drop_pct)))
    print(_SEP2)
    print()


# ── Run modes ─────────────────────────────────────────────────────────────────


def _save_recording(audio: np.ndarray, sample_rate: int) -> str:
    """Save audio to a WAV file in Voice-Computation/audio/recordings/.

    Returns the saved file path as a string.
    """
    from datetime import datetime

    import soundfile as sf

    rec_dir = Path(__file__).parent / "audio" / "recordings"
    rec_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = rec_dir / "recording_{}.wav".format(ts)
    sf.write(str(path), audio, sample_rate, subtype="PCM_16")
    return str(path)


def _process_and_print(
    audio: np.ndarray,
    config: VoiceConfig,
    pipeline: VoiceComputationPipeline,
    saved_path: str = "",
):
    """Run the pipeline and print the clean result."""
    t0 = time.time()
    decision = pipeline.process(audio)
    elapsed = time.time() - t0

    duration_s = len(audio) / config.sample_rate

    # Read detection results from the pipeline's internal state
    vad_result = pipeline.vad.process_audio(audio)
    ww_result = pipeline.wakeword.process_audio(audio)

    ww_detected = decision is not None or ww_result.detected
    ww_conf = ww_result.confidence if ww_result else 0.0
    ww_keyword = ww_result.keyword if ww_result else ""
    vad_prob = vad_result.speech_probability if vad_result else 0.0

    if ww_keyword == "bypass":
        ww_keyword = "(bypass mode)"
        ww_detected = vad_result.is_speech

    print_result(
        decision=decision,
        wakeword_detected=ww_detected,
        wakeword_conf=ww_conf,
        wakeword_keyword=ww_keyword,
        vad_prob=vad_prob,
        audio_duration_s=duration_s,
        pipeline=pipeline,
        saved_path=saved_path,
    )

    xrt = elapsed / duration_s if duration_s > 0 else 0
    print("  Processing time : {:.1f} ms  (xRT = {:.3f})".format(elapsed * 1000, xrt))
    print()

    # Ensure no cache file is left behind
    from .wakeword.detector import _cache_delete
    _cache_delete()


def run_from_file(filepath: str, config: VoiceConfig):
    from .audio.capture import FileAudioSource

    print("Loading : {}".format(filepath))
    source = FileAudioSource(filepath, config)
    audio = source.get_audio()
    print(
        "Duration: {:.2f} s  |  Peak: {:.4f}".format(
            len(audio) / config.sample_rate, float(np.abs(audio).max())
        )
    )
    print()

    # For a single file there is only one utterance — don't require 2 consecutive hits
    config.wakeword_consecutive_hits = 1

    print("Loading pipeline...")
    pipeline = VoiceComputationPipeline(config)
    print("Pipeline ready.")
    print()

    _process_and_print(audio, config, pipeline, saved_path=filepath)


def run_from_mic(config: VoiceConfig, duration_s: float = 7.0):
    from .audio.capture import AudioCapture

    # Single recording = single shot — don't require 2 consecutive hits
    config.wakeword_consecutive_hits = 1

    print("Loading pipeline (VAD model downloads on first run)...")
    pipeline = VoiceComputationPipeline(config)
    print("Pipeline ready.")
    print()

    print("Recording {:.0f} s from microphone...".format(duration_s))
    if config.wakeword_threshold > 0:
        print("  Say 'Canary' or 'Hey Canary' clearly.")
    else:
        print("  Wake-word bypass ON — all speech will be processed.")
    print()

    capture = AudioCapture(config)
    capture.start()

    for remaining in range(int(duration_s), 0, -1):
        print("\r  Recording... {}s  ".format(remaining), end="", flush=True)
        time.sleep(1)
    print("\r  Recording complete.          ")
    print()

    audio = capture.get_audio(duration_s=duration_s)
    capture.stop()

    print(
        "Captured : {:.2f} s  |  Peak: {:.4f}".format(
            len(audio) / config.sample_rate, float(np.abs(audio).max())
        )
    )
    print()

    # Save the recording as a WAV file
    saved_path = _save_recording(audio, config.sample_rate)

    _process_and_print(audio, config, pipeline, saved_path=saved_path)


def run_live(config: VoiceConfig, duration_s: float = 30.0):
    print("LIVE MODE — listening for {:.0f} s  (Ctrl+C to stop)".format(duration_s))
    print("  Say 'Hey Canary' to activate.")
    print()

    pipeline = VoiceComputationPipeline(config)

    def on_decision(decision: ScalerDecision):
        mode_val = decision.mode.value
        mode_name = {"A": "LIGHT", "B": "MEDIUM", "C": "HEAVY"}.get(mode_val, mode_val)
        print(_SEP)
        print("  ACTIVATED  ->  Mode: {} ({})".format(mode_name, mode_val))
        print(_line("Confidence", "{:.3f}".format(decision.vad_confidence)))
        print(_line("SCS", "{:.3f}".format(decision.scene_complexity_score)))
        print(_line("Speakers", str(decision.estimated_speaker_count)))
        print(_SEP)
        print()

    pipeline.run_live(callback=on_decision, duration_s=duration_s)

    stats = pipeline.stats
    print(_SEP)
    print("  FINAL STATS")
    print(_SEP)
    print(_line("Total processed", str(stats["total_chunks"])))
    print(_line("Activations", str(stats["total_activations"])))
    print(_line("Drop rate", "{:.1f}%".format(stats["drop_rate"] * 100)))
    print(_SEP2)


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="The Canary — Voice-Computation Pipeline"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help="Path to a WAV file (default: microphone)",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=7.0,
        help="Recording duration in seconds (default: 7)",
    )
    parser.add_argument(
        "--live", "-l", action="store_true", help="Continuous live mode"
    )
    parser.add_argument(
        "--bypass-wakeword",
        "-b",
        action="store_true",
        help="Skip wake-word gate — process all speech",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Logging — INFO by default, suppress noisy third-party libs
    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    # Always show our own pipeline logs at INFO when verbose
    if args.verbose:
        for name in ("Voice_Computation", "__main__"):
            logging.getLogger(name).setLevel(logging.DEBUG)

    config = VoiceConfig()
    print_banner()

    if args.bypass_wakeword:
        config.wakeword_threshold = 0.0
        print("  Note: wake-word bypass enabled — all speech will be processed.")
        print()

    if args.input:
        run_from_file(args.input, config)
    elif args.live:
        run_live(config, args.duration)
    else:
        run_from_mic(config, args.duration)


if __name__ == "__main__":
    main()
