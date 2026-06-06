import numpy as np
from collections import deque
from openwakeword.model import Model as OWWModel
from dataclasses import dataclass


@dataclass
class WakeWordResult:
    max_probability: float
    is_activated: bool
    model_name: str


class WakeWordEngine:

    OWW_CONTEXT_SAMPLES = 20480

    def __init__(self, config: dict):
        stage0_cfg = config['stage0']
        self.model_name     = stage0_cfg['wakeword_model']
        self.threshold      = stage0_cfg['wakeword_threshold']
        self.window_ms      = stage0_cfg['wakeword_window_ms']
        self.require_ww     = stage0_cfg['require_wakeword']

        self.peak_window_chunks = int(self.window_ms / 32)

        self._model = OWWModel(
            wakeword_models=[self.model_name],
            inference_framework='onnx'
        )

        self._prob_history: deque[float] = deque(maxlen=self.peak_window_chunks)
        self._audio_buffer: deque[np.ndarray] = deque(maxlen=40)

    def process_chunk(self, chunk: np.ndarray, vad_active: bool) -> WakeWordResult:
        recent_max = max(self._prob_history, default=0.0)
        if not vad_active and recent_max < 0.1:
            self._prob_history.append(0.0)
            return WakeWordResult(
                max_probability=0.0,
                is_activated=False,
                model_name='none'
            )

        self._audio_buffer.append(chunk)
        audio_context = np.concatenate(list(self._audio_buffer))

        predictions = self._model.predict(audio_context)

        if self.model_name in predictions:
            prob_array = predictions[self.model_name]
            current_prob = float(prob_array[-1]) if hasattr(prob_array, '__len__') else float(prob_array)
        else:
            current_prob = 0.0

        self._prob_history.append(current_prob)
        peak_prob = max(self._prob_history)
        is_activated = peak_prob >= self.threshold

        return WakeWordResult(
            max_probability=peak_prob,
            is_activated=is_activated,
            model_name=self.model_name if is_activated else 'none'
        )

    def reset(self):
        self._prob_history.clear()
        self._audio_buffer.clear()
