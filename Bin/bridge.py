"""Bridge: ScalerDecision → PipelineOutput.

This is the HANDOFF ADAPTER between Hemang's Voice-Computation pipeline
and Sanchit's CanaryPipeline (src/pipeline.py).

CONTEXT (from team discussion):
    Hemang's pipeline outputs ScalerDecision — a single cleaned audio
    array with mode routing metadata. Sanchit's pipeline expects
    PipelineOutput — a list of AudioStream objects (post-separation).

    This bridge handles the conversion per mode:
    ┌─────────┬─────────────────────────────────────────────────────┐
    │ Mode A  │ 1 AudioStream — clean, speaker_id="unknown"         │
    │         │ Sanchit: skip TIGER, run CAM++ + ASR directly       │
    ├─────────┼─────────────────────────────────────────────────────┤
    │ Mode B  │ 1 AudioStream — denoised, speaker_id="unknown"      │
    │         │ Sanchit: skip TIGER, run CAM++ for ID, then ASR     │
    ├─────────┼─────────────────────────────────────────────────────┤
    │ Mode C  │ N local fallback streams when pitch evidence exists │
    │         │ otherwise mixed audio remains TIGER-ready           │
    └─────────┴─────────────────────────────────────────────────────┘

USAGE:
    from Voice_Computation.bridge import scaler_to_pipeline_output
    from Voice_Computation.pipeline import VoiceComputationPipeline

    vc_pipeline = VoiceComputationPipeline()
    decision = vc_pipeline.process(audio)

    if decision is not None:
        pipeline_output = scaler_to_pipeline_output(decision)
        # Hand off to Sanchit's CanaryPipeline
        result = canary_pipeline.process(pipeline_output)
"""

import time
from typing import Optional

import numpy as np

from .models import ScalerDecision
from .config import PipelineMode

# ── Import PipelineOutput from the shared contract ──────────────────────────
# The frozen integration contract lives in src/common/models.py.
# We import defensively so this module works standalone (e.g. in tests)
# even if the src package is not on the path.
try:
    import sys
    import os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from src.common.models import PipelineOutput, AudioStream
    _CONTRACT_AVAILABLE = True
except ImportError:
    _CONTRACT_AVAILABLE = False
    # Fallback dataclass definitions so the bridge can still be imported
    # and tested without the full src tree present.
    from dataclasses import dataclass, field
    from enum import Enum

    @dataclass
    class AudioStream:          # type: ignore[no-redef]
        stream_id: int
        audio: np.ndarray
        sample_rate: int = 16000
        speaker_id: str = "unknown"
        speaker_confidence: float = 0.0
        duration_seconds: float = 0.0

    @dataclass
    class PipelineOutput:       # type: ignore[no-redef]
        mode: object
        timestamp: float
        audio_streams: list
        scene_complexity_score: float = 0.0
        vad_confidence: float = 0.0
        wakeword_confidence: float = 0.0
        overlap_probability: float = 0.0
        noise_floor_db: float = -40.0


def scaler_to_pipeline_output(decision: ScalerDecision) -> "PipelineOutput":
    """Convert a ScalerDecision into a PipelineOutput for Sanchit's pipeline.

    This function is the single point of truth for the Hemang → Sanchit
    handoff. It wraps the single mixed/cleaned audio array into the
    AudioStream list structure that CanaryPipeline.process() expects.

    Args:
        decision: Output from DynamicResourceScaler (Hemang's last stage).

    Returns:
        PipelineOutput conforming to src/common/models.py frozen contract.
    """
    audio = decision.audio
    sr = 16000
    duration_s = len(audio) / sr

    # Helper pitch-based speaker ID heuristic for the demo/fallback
    def identify_by_pitch(pitch_hz: float) -> tuple[str, float]:
        if 75.0 <= pitch_hz < 155.0:
            return "hemang", 0.92  # Admin
        elif 155.0 <= pitch_hz <= 420.0:
            return "sanchit", 0.88  # Guest
        return "unknown", 0.0

    if decision.separated_audio:
        streams = []
        for index, stream in enumerate(decision.separated_audio):
            speaker_id = "unknown"
            confidence = 0.0
            
            # Map using the analyzed speaker profiles
            if index < len(decision.speaker_profiles):
                profile = decision.speaker_profiles[index]
                speaker_id, confidence = identify_by_pitch(profile.get("pitch_hz", 0.0))
            
            if speaker_id == "unknown":
                speaker_id = "speaker_profile_{}".format(index + 1)
                
            streams.append(
                AudioStream(
                    stream_id=index,
                    audio=stream,
                    sample_rate=sr,
                    speaker_id=speaker_id,
                    speaker_confidence=confidence,
                    duration_seconds=len(stream) / sr,
                )
            )

    elif decision.mode == PipelineMode.MODE_A:
        # ── Mode A: Clean, single speaker ────────────────────────────────
        speaker_id = "unknown"
        confidence = 0.0
        if decision.speaker_profiles:
            speaker_id, confidence = identify_by_pitch(decision.speaker_profiles[0].get("pitch_hz", 0.0))
            
        streams = [
            AudioStream(
                stream_id=0,
                audio=audio,
                sample_rate=sr,
                speaker_id=speaker_id,
                speaker_confidence=confidence,
                duration_seconds=duration_s,
            )
        ]

    elif decision.mode == PipelineMode.MODE_B:
        # ── Mode B: Single speaker + background noise ─────────────────────
        speaker_id = "unknown"
        confidence = 0.0
        if decision.speaker_profiles:
            speaker_id, confidence = identify_by_pitch(decision.speaker_profiles[0].get("pitch_hz", 0.0))
            
        streams = [
            AudioStream(
                stream_id=0,
                audio=audio,
                sample_rate=sr,
                speaker_id=speaker_id,
                speaker_confidence=confidence,
                duration_seconds=duration_s,
            )
        ]

    else:
        # ── Mode C: Overlapping speakers — pass mixed audio to TIGER ─────
        streams = [
            AudioStream(
                stream_id=0,
                audio=audio,
                sample_rate=sr,
                speaker_id="mixed",        # Indicates TIGER must be run
                speaker_confidence=0.0,
                duration_seconds=duration_s,
            )
        ]

    return PipelineOutput(
        mode=decision.mode,
        timestamp=decision.timestamp,
        audio_streams=streams,
        scene_complexity_score=decision.scene_complexity_score,
        vad_confidence=decision.vad_confidence,
        wakeword_confidence=decision.wakeword_confidence,
        overlap_probability=decision.overlap_probability,
        noise_floor_db=decision.noise_floor_db,
    )


def pipeline_output_summary(output: "PipelineOutput") -> str:
    """Return a human-readable summary of a PipelineOutput for logging.

    Useful in Sanchit's pipeline for quick status prints.
    """
    mode_names = {"A": "CLEAN/SINGLE", "B": "NOISY/SINGLE", "C": "OVERLAP/MIXED"}
    mode_val = output.mode.value if hasattr(output.mode, "value") else str(output.mode)
    mode_name = mode_names.get(mode_val, mode_val)

    streams_summary = ", ".join(
        f"[stream {s.stream_id}: {s.speaker_id} {s.duration_seconds:.2f}s]"
        for s in output.audio_streams
    )

    return (
        f"PipelineOutput("
        f"mode={mode_val} ({mode_name}), "
        f"streams={streams_summary}, "
        f"SCS={output.scene_complexity_score:.3f}, "
        f"VAD={output.vad_confidence:.3f}, "
        f"WW={output.wakeword_confidence:.3f}, "
        f"overlap={output.overlap_probability:.3f}, "
        f"noise={output.noise_floor_db:.1f}dB"
        f")"
    )


# ── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    print("=== Bridge Self-Test ===\n")
    print(f"src/common/models.py contract available: {_CONTRACT_AVAILABLE}\n")

    sr = 16000
    audio_1s = np.random.randn(sr).astype(np.float32) * 0.3

    for mode, scs, ww_conf, overlap in [
        (PipelineMode.MODE_A, 0.10, 0.92, 0.00),
        (PipelineMode.MODE_B, 0.28, 0.65, 0.05),
        (PipelineMode.MODE_C, 0.55, 0.30, 0.72),
    ]:
        decision = ScalerDecision(
            mode=mode,
            audio=audio_1s,
            timestamp=time.time(),
            vad_confidence=0.93,
            wakeword_confidence=ww_conf,
            scene_complexity_score=scs,
            estimated_speaker_count=1 if mode != PipelineMode.MODE_C else 2,
            overlap_probability=overlap,
            noise_floor_db=-45.0,
            snr_estimate_db=25.0,
            is_directed_speech=True,
        )
        output = scaler_to_pipeline_output(decision)
        print(pipeline_output_summary(output))
        assert len(output.audio_streams) == 1
        assert output.audio_streams[0].audio.shape == (sr,)
        if mode == PipelineMode.MODE_C:
            assert output.audio_streams[0].speaker_id == "mixed"
        else:
            assert output.audio_streams[0].speaker_id == "unknown"

    print("\nBridge self-test passed!")
    print("\nHemang → Sanchit handoff format verified.")
