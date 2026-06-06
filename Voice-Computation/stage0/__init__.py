import threading
import queue
import time
from .audio_capture import AudioCapture, AudioChunk
from .vad_engine import SileroVADEngine
from .wakeword_engine import WakeWordEngine
from .passive_gate import PassiveGate, ThreeBitWord


class Stage0Runner:

    def __init__(self, config: dict, output_queue: queue.Queue):
        self._config = config
        self._output_queue = output_queue
        self._thread = None
        self._stop_event = threading.Event()

        self.capture  = AudioCapture(config)
        self.vad      = SileroVADEngine(config)
        self.ww       = WakeWordEngine(config)
        self.gate     = PassiveGate(config)

    def _processing_loop(self):
        print("[Stage0] Processing thread started.")
        self.capture.start()

        while not self._stop_event.is_set():
            chunk: AudioChunk | None = self.capture.get_chunk(timeout=0.05)

            if chunk is None:
                continue

            now = time.monotonic()

            vad_result = self.vad.process_chunk(chunk.samples, chunk.chunk_id)

            ww_result = self.ww.process_chunk(chunk.samples, vad_result.is_speech)

            three_bit = self.gate.evaluate(vad_result, ww_result, now)

            if three_bit.PASS:
                try:
                    payload = (three_bit, chunk.samples)
                    self._output_queue.put_nowait(payload)
                except queue.Full:
                    pass

        self.capture.stop()
        print("[Stage0] Processing thread stopped.")

    def start(self):
        self._thread = threading.Thread(target=self._processing_loop,
                                        name="Stage0-Thread", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
