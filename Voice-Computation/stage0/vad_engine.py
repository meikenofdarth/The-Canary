import numpy as np
import torch
from silero_vad import load_silero_vad
from dataclasses import dataclass
from collections import deque


@dataclass
class VADResult:
    is_speech: bool
    speech_prob: float
    noise_floor: float
    chunk_id: int


class SileroVADEngine:

    def __init__(self, config: dict):
        stage0_cfg = config['stage0']
        self.threshold  = stage0_cfg['vad_threshold']
        self.nf_thresh  = stage0_cfg['noise_floor_threshold']
        self.nf_window  = stage0_cfg['noise_floor_window_chunks']

        self._device = torch.device('cpu')
        torch.set_num_threads(1)

        self._model = load_silero_vad()
        self._model.to(self._device)
        self._reset_state()

        self._energy_history: deque[float] = deque(maxlen=self.nf_window * 5)
        self._silence_energy: deque[float] = deque(maxlen=self.nf_window)

        self._consecutive_speech = 0
        self._consecutive_silence = 0
        self._in_speech = False

    def _reset_state(self):
        self._model.reset_states()

    def _estimate_noise_floor(self, chunk: np.ndarray, is_speech: bool) -> float:
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        self._energy_history.append(rms)

        if not is_speech:
            self._silence_energy.append(rms)

        if len(self._silence_energy) < 3:
            return 0.3

        noise_rms = float(np.mean(list(self._silence_energy)))
        noise_floor_normalised = float(np.clip(noise_rms / 0.05, 0.0, 1.0))
        return noise_floor_normalised

    def process_chunk(self, chunk: np.ndarray, chunk_id: int) -> VADResult:
        assert chunk.shape == (512,), f"Expected 512 samples, got {chunk.shape}"
        assert chunk.dtype == np.float32, f"Expected float32, got {chunk.dtype}"

        tensor = torch.from_numpy(chunk).unsqueeze(0)

        with torch.no_grad():
            speech_prob = float(self._model(tensor, 16000).item())

        if speech_prob >= self.threshold:
            self._consecutive_speech += 1
            self._consecutive_silence = 0
        else:
            self._consecutive_silence += 1
            self._consecutive_speech = 0

        if not self._in_speech and self._consecutive_speech >= 3:
            self._in_speech = True
        elif self._in_speech and self._consecutive_silence >= 4:
            self._in_speech = False
            if self._consecutive_silence > 50:
                self._reset_state()

        noise_floor = self._estimate_noise_floor(chunk, self._in_speech)

        return VADResult(
            is_speech=self._in_speech,
            speech_prob=speech_prob,
            noise_floor=noise_floor,
            chunk_id=chunk_id
        )

    def reset(self):
        self._reset_state()
        self._energy_history.clear()
        self._silence_energy.clear()
        self._in_speech = False
        self._consecutive_speech = 0
        self._consecutive_silence = 0
