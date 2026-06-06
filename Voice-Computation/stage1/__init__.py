import numpy as np
import queue
import threading
from .preprocessor import AudioPreprocessor
from .feature_extractor import FeatureExtractor
from .acoustic_intelligence import AcousticIntelligence


class Stage1Runner:
    WINDOW_SIZE = 1600
    CHUNK_SIZE = 512

    def __init__(self, config, input_queue, output_queue):
        self._config = config
        self._in_q = input_queue
        self._out_q = output_queue
        self._stop = threading.Event()
        self._thread = None
        self._preprocessor = AudioPreprocessor(config)
        self._extractor = FeatureExtractor(config)
        self._intelligence = AcousticIntelligence(config)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._window_id = 0
        self._last_three_bit = None

    def _processing_loop(self):
        print("[Stage1] Processing thread started.")
        while not self._stop.is_set():
            try:
                item = self._in_q.get(timeout=0.1)
            except queue.Empty:
                continue

            three_bit, chunk_audio = item
            self._last_three_bit = three_bit

            self._intelligence.accumulate_raw_chunk(chunk_audio)

            self._buffer = np.concatenate([self._buffer, chunk_audio])

            while len(self._buffer) >= self.WINDOW_SIZE:
                window = self._buffer[:self.WINDOW_SIZE]
                self._buffer = self._buffer[self.WINDOW_SIZE:]
                self._process_window(window, three_bit)

    def _process_window(self, window, three_bit):
        processed = self._preprocessor.process(window, self._window_id)
        features = self._extractor.extract(processed.samples, self._window_id)
        scene = self._intelligence.process(features)

        if scene is None:
            self._window_id += 1
            return

        blended_N = float(np.clip(0.5 * scene.N_norm + 0.5 * three_bit.Nf, 0, 1))

        from dataclasses import replace
        final = replace(scene, N_norm=blended_N, window_id=self._window_id)

        payload = (final, three_bit)

        self._window_id += 1
        try:
            self._out_q.put_nowait(payload)
        except queue.Full:
            pass

    def start(self):
        self._thread = threading.Thread(target=self._processing_loop,
                                        name="Stage1-Thread", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
