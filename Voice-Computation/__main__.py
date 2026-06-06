#!/usr/bin/env python3
import sys
import time
import argparse
import json
from pathlib import Path
import numpy as np


def record_audio(duration: float = 7.0, sample_rate: int = 16000,
                 chunk_size: int = 512, device_id: int | None = None) -> np.ndarray:
    import sounddevice as sd
    print(f"\n  \U0001f3a4 Recording {duration}s of audio... (speak now!)")
    print(f"  Press Ctrl+C to stop early.\n")
    recorded = []

    def callback(indata, frames, time_info, status):
        if status:
            print(f"  Status: {status}")
        recorded.append(indata[:, 0].copy())

    stream = sd.InputStream(
        samplerate=sample_rate, channels=1, dtype='float32',
        blocksize=chunk_size, device=device_id, callback=callback,
    )
    stream.start()
    start_time = time.monotonic()
    try:
        while time.monotonic() - start_time < duration:
            remaining = duration - (time.monotonic() - start_time)
            bar_len = 30
            progress = 1.0 - (remaining / duration)
            filled = int(bar_len * progress)
            bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
            sys.stdout.write(f"\r  [{bar}] {progress*100:3.0f}%  ({remaining:.1f}s left)")
            sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n  Recording stopped early.")
    finally:
        stream.stop()
        stream.close()
    print("\n")
    if not recorded:
        raise RuntimeError("No audio captured. Check microphone permissions.")
    return np.concatenate(recorded)


def _load_file(path: str) -> np.ndarray:
    import soundfile as sf
    audio, sr = sf.read(path)
    if audio.ndim > 1:
        audio = audio[:, 0]
    audio = audio.astype(np.float32)
    if sr != 16000:
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
    return audio


def save_wav(path: Path, audio: np.ndarray, sample_rate: int = 16000):
    try:
        import soundfile as sf
        sf.write(str(path), audio, sample_rate, subtype='FLOAT')
    except ImportError:
        import scipy.io.wavfile as wav
        audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        wav.write(str(path), sample_rate, audio_int16)


def print_summary(results, audio, recording_path, output_dir, transcript=None,
                  wake_word_result=None, speaker_count=None,
                  transcript_path=None):
    print("\n" + "=" * 64)
    print("  \U0001f426 THE CANARY - PIPELINE SUMMARY")
    print("=" * 64)
    print(f"  Recording     : {recording_path.name}")
    print(f"  Duration      : {len(audio)/16000:.2f}s")
    print(f"  Samples       : {len(audio)}")

    if transcript:
        text = transcript.get("text", "")
        suffix = "..." if len(text) > 80 else ""
        print(f"  Transcription : \"{text[:80]}{suffix}\"")
        print(f"  ASR confidence: {transcript.get('confidence', 0):.3f}")
        print(f"  Language      : {transcript.get('language', '?')}")

    if wake_word_result:
        ww = wake_word_result
        status = "\u2705 DETECTED" if ww["detected"] else "\u274c NOT FOUND"
        print(f"  Wake word     : \"{ww['wake_word']}\" {status}")

    if speaker_count is not None:
        print(f"  Speakers est. : {speaker_count}")

    print(f"  Output dir    : {output_dir}")
    print()

    if not results:
        print("  \u26a0\ufe0f  No pipeline events emitted.")
        print("  The audio did not pass Stage 0 gate (no speech or wake word detected).")
        print("  Try: require_wakeword=False, or speak more clearly.")
        return

    r = results[-1]
    print(f"  Mode          : {r.mode.value} "
          f"({'Minimal' if r.mode.value=='A' else 'Assisted' if r.mode.value=='B' else 'Full Sep.'})")
    print(f"  SCS           : {r.scene_complexity_score:.4f}")
    print(f"  P_overlap     : {r.overlap_probability:.4f}")
    print(f"  N_norm (dB)   : {r.noise_floor_db:.1f} dBFS")
    print(f"  VAD conf      : {r.vad_confidence:.4f}")
    print(f"  Wake-word conf: {r.wakeword_confidence:.4f}")
    print(f"  Speakers      : {r.speaker_count_estimate}")
    print()

    print(f"  \U0001f4c4 Output files:")
    print(f"    {output_dir / 'pipeline_results.json'}")
    print(f"    {output_dir / 'pipeline_data.pkl'}")
    print(f"    {recording_path}")
    if transcript_path and transcript_path.exists():
        print(f"    {transcript_path}")
    print("=" * 64)


def main():
    parser = argparse.ArgumentParser(
        description="The Canary - Voice-Computation Pipeline"
    )
    parser.add_argument("--duration", type=float, default=7.0,
                        help="Recording duration in seconds (default: 7)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (default: Voice-Computation/outputs/)")
    parser.add_argument("--file", type=str, default=None,
                        help="Process existing WAV file instead of recording")
    parser.add_argument("--require-wakeword", action="store_true",
                        help="Require wake word for Stage 0 gate")
    parser.add_argument("--device", type=int, default=None,
                        help="Microphone device ID")
    parser.add_argument("--no-asr", action="store_true",
                        help="Skip ASR transcription")
    args = parser.parse_args()

    base_dir = Path(__file__).parent
    output_dir = Path(args.output) if args.output else (base_dir / "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    from . import CanaryPipeline
    pipeline = CanaryPipeline(config_path=str(base_dir / "config" / "pipeline_config.yaml"))

    if args.file:
        audio = _load_file(args.file)
        recording_path = Path(args.file)
    else:
        audio = record_audio(duration=args.duration, sample_rate=16000, device_id=args.device)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        recording_path = output_dir / f"recording_{timestamp}.wav"
        save_wav(recording_path, audio)

    transcript = None
    wake_word_result = None
    transcript_txt_path = None

    if not args.no_asr:
        from .transcriber import Transcriber, detect_wake_word, save_transcript
        asr = Transcriber(model_name="base")
        transcript_txt_path = output_dir / "transcript.txt"
        try:
            transcript = asr.transcribe(audio)
            save_transcript(transcript, transcript_txt_path)
            wake_word_result = detect_wake_word(transcript, wake_word="canary")
            if wake_word_result["detected"] and not args.require_wakeword:
                args.require_wakeword = False
        except Exception:
            pass

    transcript_text = (transcript or {}).get('text', '') if transcript else ''
    asr_detected = bool(wake_word_result and wake_word_result["detected"])
    try:
        results = pipeline.run_offline(
            audio=audio, output_dir=str(output_dir),
            require_wakeword=args.require_wakeword,
            transcript=transcript_text, asr_wake_word_detected=asr_detected,
        )
    except Exception as e:
        print(f"\n  \u274c Pipeline error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    speaker_count = results[-1].speaker_count_estimate if results else None
    print_summary(results, audio, recording_path, output_dir,
                  transcript=transcript, wake_word_result=wake_word_result,
                  speaker_count=speaker_count, transcript_path=transcript_txt_path)

if __name__ == "__main__":
    main()
