import time
import json
import numpy as np
from pathlib import Path
from ..pipeline_contract import PipelineOutput, PipelineMode, AudioStream
from .mode_router import ProcessingMode
from .scs_calculator import SCSResult
from ..stage1.acoustic_intelligence import AcousticSceneOutput
from ..stage0.passive_gate import ThreeBitWord


def nf_to_db(nf: float) -> float:
    nf = float(np.clip(nf, 1e-6, 1.0))
    return round(-60.0 + (nf * 50.0), 2)


def mode_to_pipeline_mode(m: ProcessingMode) -> PipelineMode:
    return {
        ProcessingMode.MODE_A: PipelineMode.MODE_A,
        ProcessingMode.MODE_B: PipelineMode.MODE_B,
        ProcessingMode.MODE_C: PipelineMode.MODE_C,
    }[m]


class PipelineOutputAssembler:

    def __init__(self, config: dict, output_dir: str = "outputs",
                 transcript: str | None = None,
                 asr_wake_word_detected: bool = False):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._event_count = 0
        self._transcript = transcript or ""
        self._asr_wake_word_detected = asr_wake_word_detected

    def assemble(
        self,
        mode: ProcessingMode,
        scs_result: SCSResult,
        scene: AcousticSceneOutput,
        three_bit: ThreeBitWord,
    ) -> PipelineOutput:
        raw_audio = scene.raw_audio

        stream = AudioStream(
            stream_id=0,
            audio=raw_audio,
            sample_rate=16000,
            speaker_id="unknown",
            speaker_confidence=0.0,
            duration_seconds=len(raw_audio) / 16000.0,
        )

        output = PipelineOutput(
            mode=mode_to_pipeline_mode(mode),
            timestamp=time.monotonic(),
            audio_streams=[stream],
            scene_complexity_score=round(scs_result.smoothed_scs, 4),
            vad_confidence=round(float(three_bit.Sb), 4),
            wakeword_confidence=round(float(three_bit.Pw), 4),
            overlap_probability=round(scene.P_overlap, 4),
            noise_floor_db=nf_to_db(three_bit.Nf),
            speaker_count_estimate=scene.speaker_count_estimate,
        )

        self._event_count += 1
        return output

    def to_json(self, output: PipelineOutput, include_audio: bool = False) -> dict:
        import base64

        streams_serialised = []
        for s in output.audio_streams:
            entry = {
                "stream_id": s.stream_id,
                "sample_rate": s.sample_rate,
                "speaker_id": s.speaker_id,
                "speaker_confidence": s.speaker_confidence,
                "duration_seconds": round(s.duration_seconds, 4),
                "num_samples": len(s.audio),
            }
            if include_audio:
                entry["audio_b64"] = base64.b64encode(
                    s.audio.astype(np.float32).tobytes()
                ).decode("utf-8")
            else:
                entry["audio_rms"] = round(float(np.sqrt(np.mean(s.audio**2))), 6)
                entry["audio_peak"] = round(float(np.max(np.abs(s.audio))), 6)
            streams_serialised.append(entry)

        ww_conf = 1.0 if self._asr_wake_word_detected else output.wakeword_confidence
        result = {
            "mode": output.mode.value,
            "timestamp": round(output.timestamp, 6),
            "scene_complexity_score": output.scene_complexity_score,
            "vad_confidence": output.vad_confidence,
            "wakeword_confidence": ww_conf,
            "overlap_probability": output.overlap_probability,
            "noise_floor_db": output.noise_floor_db,
            "speaker_count_estimate": output.speaker_count_estimate,
            "transcript": self._transcript,
            "audio_streams": streams_serialised,
        }
        return result

    def write_json(
        self,
        output: PipelineOutput,
        filename: str = "pipeline_output.json",
        include_audio: bool = True,
    ) -> Path:
        data = self.to_json(output, include_audio=include_audio)
        path = self._output_dir / filename
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path
