import numpy as np
import sounddevice as sd
import queue
from collections import deque
from dataclasses import dataclass


@dataclass
class AudioChunk:
    samples: np.ndarray
    timestamp: float
    chunk_id: int


class AudioCapture:

    def __init__(self, config: dict):
        self.sample_rate = config['audio']['sample_rate']
        self.chunk_size  = config['audio']['chunk_size']
        self.channels    = config['audio']['channels']
        self.dtype       = config['audio']['dtype']
        self.device_id   = config['audio'].get('mic_device_id')

        self._queue = queue.Queue(maxsize=32)
        self._chunk_id  = 0
        self._stream    = None
        self._running   = False
        self._scratch   = np.zeros(self.chunk_size, dtype=np.float32)

    def _callback(self, indata: np.ndarray, frames: int,
                  time_info, status) -> None:
        if status:
            pass
        chunk = AudioChunk(
            samples=indata[:, 0].copy(),
            timestamp=time_info.inputBufferAdcTime,
            chunk_id=self._chunk_id
        )
        self._chunk_id += 1
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except queue.Empty:
                pass

    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            blocksize=self.chunk_size,
            device=self.device_id,
            callback=self._callback,
            extra_settings=sd.CoreAudioSettings(
                change_device_parameters=False,
                fail_if_conversion_required=False,
                conversion_quality='max'
            )
        )
        self._stream.start()
        self._running = True

    def stop(self) -> None:
        if self._stream and self._running:
            self._stream.stop()
            self._stream.close()
            self._running = False

    def get_chunk(self, timeout: float = 0.1) -> AudioChunk | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def is_running(self) -> bool:
        return self._running
