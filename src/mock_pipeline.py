"""Mock Pipeline Output Generator.

Generates fake PipelineOutput data for development and testing.
Use this until Engineer A's code is ready for integration.
"""
import numpy as np
import time
import os
from src.common.models import PipelineOutput, PipelineMode, AudioStream


def generate_mock_output(
    mode: str = "C",
    duration: float = 3.0
) -> PipelineOutput:
    """Generate a mock PipelineOutput with synthetic audio.
    
    Args:
        mode: Pipeline mode (A, B, or C)
        duration: Audio duration in seconds
    """
    sr = 16000
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    
    streams = []
    if mode in ["A", "B"]:
        streams = [
            AudioStream(
                stream_id=0,
                audio=np.sin(2 * np.pi * 440 * t).astype(np.float32),
                sample_rate=sr,
                speaker_id="hemang",
                speaker_confidence=0.95,
                duration_seconds=duration
            )
        ]
    elif mode == "C":
        streams = [
            AudioStream(
                stream_id=0,
                audio=np.sin(2 * np.pi * 440 * t).astype(np.float32),
                sample_rate=sr,
                speaker_id="hemang",
                speaker_confidence=0.92,
                duration_seconds=duration
            ),
            AudioStream(
                stream_id=1,
                audio=np.sin(2 * np.pi * 880 * t).astype(np.float32),
                sample_rate=sr,
                speaker_id="sanchit",
                speaker_confidence=0.87,
                duration_seconds=duration
            )
        ]
    
    return PipelineOutput(
        mode=PipelineMode(mode),
        timestamp=time.time(),
        audio_streams=streams,
        scene_complexity_score=0.78 if mode == "C" else 0.2,
        vad_confidence=0.95,
        wakeword_confidence=0.88,
        overlap_probability=0.72 if mode == "C" else 0.05,
        noise_floor_db=-35.2
    )


def generate_from_wav(wav_file_1: str, wav_file_2: str = None) -> PipelineOutput:
    """Generate mock output from real .wav files.
    
    Args:
        wav_file_1: Path to first speaker's audio
        wav_file_2: Optional path to second speaker's audio
    """
    try:
        import soundfile as sf
    except ImportError:
        raise ImportError("Install soundfile: pip install soundfile")
    
    audio_1, sr = sf.read(wav_file_1, dtype='float32')
    streams = [
        AudioStream(
            stream_id=0,
            audio=audio_1,
            sample_rate=sr,
            speaker_id="hemang",
            speaker_confidence=0.95,
            duration_seconds=len(audio_1) / sr
        )
    ]
    
    mode = PipelineMode.MODE_A
    if wav_file_2 and os.path.exists(wav_file_2):
        audio_2, _ = sf.read(wav_file_2, dtype='float32')
        streams.append(
            AudioStream(
                stream_id=1,
                audio=audio_2,
                sample_rate=sr,
                speaker_id="sanchit",
                speaker_confidence=0.87,
                duration_seconds=len(audio_2) / sr
            )
        )
        mode = PipelineMode.MODE_C
    
    return PipelineOutput(
        mode=mode,
        timestamp=time.time(),
        audio_streams=streams,
        scene_complexity_score=0.78 if mode == PipelineMode.MODE_C else 0.2,
        vad_confidence=0.95,
        wakeword_confidence=0.88,
        overlap_probability=0.72 if mode == PipelineMode.MODE_C else 0.05,
        noise_floor_db=-35.2
    )


if __name__ == "__main__":
    # Quick test
    output = generate_mock_output(mode="C")
    print(f"Mode: {output.mode}")
    print(f"Streams: {len(output.audio_streams)}")
    for s in output.audio_streams:
        print(f"  Speaker: {s.speaker_id}, Duration: {s.duration_seconds}s, Shape: {s.audio.shape}")
