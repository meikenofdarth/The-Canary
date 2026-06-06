import numpy as np
import yaml
import queue
import threading
import time
from pathlib import Path

from .pipeline_contract import PipelineOutput, PipelineMode, AudioStream
from .stage0 import Stage0Runner
from .stage1 import Stage1Runner
from .drs import DRSRunner


class CanaryPipeline:

    def __init__(self, config_path: str | None = None, config: dict | None = None):
        if config is not None:
            self.config = config
        else:
            path = config_path or Path(__file__).parent / "config" / "pipeline_config.yaml"
            with open(path) as f:
                self.config = yaml.safe_load(f)

        self._online_components = None

    def run_online(self, output_dir: str = "outputs") -> queue.Queue:
        q_s0_s1 = queue.Queue(maxsize=16)
        q_s1_drs = queue.Queue(maxsize=8)
        q_output = queue.Queue(maxsize=32)

        stage0 = Stage0Runner(self.config, q_s0_s1)
        stage1 = Stage1Runner(self.config, q_s0_s1, q_s1_drs)
        drs = DRSRunner(self.config, q_s1_drs,
                         pipeline_output_queue=q_output,
                         output_dir=output_dir)

        stage0.start()
        stage1.start()
        drs.start()

        self._online_components = {
            'stage0': stage0, 'stage1': stage1, 'drs': drs,
            'q_output': q_output,
        }

        return q_output

    def stop_online(self):
        if self._online_components:
            self._online_components['drs'].stop()
            self._online_components['stage1'].stop()
            self._online_components['stage0'].stop()
            self._online_components = None

    def run_offline(self, audio: np.ndarray, sample_rate: int = 16000,
                    output_dir: str | None = None,
                    require_wakeword: bool = False,
                    transcript: str | None = None,
                    asr_wake_word_detected: bool = False) -> list[PipelineOutput]:
        if output_dir is None:
            output_dir = Path(__file__).parent / "outputs"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        cfg = dict(self.config)
        if not require_wakeword:
            cfg['stage0'] = dict(cfg.get('stage0', {}))
            cfg['stage0']['require_wakeword'] = False

        from .stage0.vad_engine import SileroVADEngine
        from .stage0.wakeword_engine import WakeWordEngine, WakeWordResult as _WWR
        from .stage0.passive_gate import PassiveGate
        from .stage1.acoustic_intelligence import AcousticIntelligence
        from .drs.scs_calculator import SCSCalculator
        from .drs.mode_router import ModeRouter
        from .drs.output_assembler import PipelineOutputAssembler

        vad = SileroVADEngine(cfg)
        ww = WakeWordEngine(cfg)
        gate = PassiveGate(cfg)
        ai = AcousticIntelligence(cfg)
        scs_calc = SCSCalculator(cfg)
        router = ModeRouter(cfg)
        assembler = PipelineOutputAssembler(cfg, output_dir=str(output_dir),
                                            transcript=transcript,
                                            asr_wake_word_detected=asr_wake_word_detected)

        chunk_size = cfg['audio']['chunk_size']

        num_chunks = len(audio) // chunk_size

        passed_chunks = []
        last_three_bit = None

        for i in range(num_chunks):
            start = i * chunk_size
            chunk = audio[start:start + chunk_size].astype(np.float32)
            now = time.monotonic()

            vad_result = vad.process_chunk(chunk, i)
            if asr_wake_word_detected:
                ww_result = _WWR(max_probability=1.0, is_activated=True, model_name="asr")
            else:
                ww_result = ww.process_chunk(chunk, vad_result.is_speech)
            three_bit = gate.evaluate(vad_result, ww_result, now,
                                      asr_wake_word_detected=asr_wake_word_detected)

            if three_bit.PASS:
                passed_chunks.append(chunk)
                last_three_bit = three_bit

        if not passed_chunks:
            return []

        full_audio = np.concatenate(passed_chunks)

        scene = ai.analyze_full(full_audio, noise_floor=last_three_bit.Nf)
        scs_result = scs_calc.compute(scene)
        mode = router.route(scs_result)

        pipeline_out = assembler.assemble(
            mode=mode, scs_result=scs_result,
            scene=scene, three_bit=last_three_bit,
        )
        results = [pipeline_out]

        import json as _json
        streams = []
        for s in pipeline_out.audio_streams:
            streams.append({
                "stream_id": s.stream_id,
                "sample_rate": s.sample_rate,
                "speaker_id": s.speaker_id,
                "speaker_confidence": s.speaker_confidence,
                "duration_seconds": round(s.duration_seconds, 4),
                "num_samples": len(s.audio),
                "audio_rms": round(float(np.sqrt(np.mean(s.audio**2))), 6),
                "audio_peak": round(float(np.max(np.abs(s.audio))), 6),
            })
        event = {
            "mode": pipeline_out.mode.value,
            "timestamp": round(pipeline_out.timestamp, 6),
            "scene_complexity_score": pipeline_out.scene_complexity_score,
            "vad_confidence": pipeline_out.vad_confidence,
            "wakeword_confidence": pipeline_out.wakeword_confidence,
            "overlap_probability": pipeline_out.overlap_probability,
            "noise_floor_db": pipeline_out.noise_floor_db,
            "speaker_count_estimate": pipeline_out.speaker_count_estimate,
            "transcript": transcript or "",
            "audio_streams": streams,
        }
        out_path = Path(output_dir) / "pipeline_results.json"
        with open(out_path, "w") as f:
            _json.dump(event, f, indent=2)

        try:
            import pickle as _pickle
            pkl_path = Path(output_dir) / "pipeline_data.pkl"
            with open(pkl_path, "wb") as f:
                _pickle.dump(results, f)
        except Exception:
            pass

        return results
