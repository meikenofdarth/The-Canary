import queue
import threading
from pathlib import Path
from .scs_calculator import SCSCalculator
from .mode_router import ModeRouter
from .output_assembler import PipelineOutputAssembler
from ..stage1.acoustic_intelligence import AcousticSceneOutput
from ..stage0.passive_gate import ThreeBitWord


class DRSRunner:

    def __init__(self, config: dict, input_queue: queue.Queue,
                 pipeline_output_queue: queue.Queue | None = None,
                 output_dir: str = "outputs"):
        self._config  = config
        self._in_q    = input_queue
        self._out_q   = pipeline_output_queue
        self._stop    = threading.Event()
        self._thread  = None

        self._scs_calc  = SCSCalculator(config)
        self._router    = ModeRouter(config)
        self._assembler = PipelineOutputAssembler(config, output_dir=output_dir)

        self._event_count = 0

    def process_one(self, scene: AcousticSceneOutput, three_bit: ThreeBitWord) -> tuple:
        scs_result = self._scs_calc.compute(scene)
        mode = self._router.route(scs_result)
        pipeline_out = self._assembler.assemble(
            mode=mode, scs_result=scs_result, scene=scene, three_bit=three_bit,
        )
        json_path = self._assembler.write_json(
            pipeline_out, filename="pipeline_output.json", include_audio=True,
        )
        if self._out_q is not None:
            try:
                self._out_q.put_nowait(pipeline_out)
            except queue.Full:
                pass
        self._event_count += 1
        return pipeline_out, json_path

    def _processing_loop(self):
        print("[DRS] Processing thread started.")
        while not self._stop.is_set():
            try:
                item = self._in_q.get(timeout=0.2)
            except queue.Empty:
                continue

            scene, three_bit = item
            pipeline_out, json_path = self.process_one(scene, three_bit)

            print(f"[DRS] Event {self._event_count:04d} | "
                  f"Mode={pipeline_out.mode.value} | "
                  f"SCS={pipeline_out.scene_complexity_score:.3f} | "
                  f"P_ov={scene.P_overlap:.3f} | "
                  f"audio={len(scene.raw_audio)/16000:.2f}s \u2192 {json_path}")

    def start(self):
        self._thread = threading.Thread(target=self._processing_loop,
                                        name="DRS-Thread", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        print(f"\n[DRS] Total events emitted: {self._event_count}")
        print(self._scs_calc.get_recent_stats())
