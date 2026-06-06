import numpy as np
from scipy import signal
from dataclasses import dataclass


@dataclass
class ProcessedWindow:
    samples: np.ndarray
    rms_before: float
    rms_after: float
    clipping_detected: bool
    window_id: int


class AudioPreprocessor:

    TARGET_RMS = 0.1
    PREEMPHASIS_COEFF = 0.97
    HIGHPASS_CUTOFF = 80
    HIGHPASS_ORDER = 4

    def __init__(self, config: dict):
        stage1_cfg = config['stage1']
        sample_rate = config['audio']['sample_rate']
        cutoff = stage1_cfg.get('highpass_cutoff_hz', 80)
        order = stage1_cfg.get('highpass_order', 4)
        self._target_rms = 0.1

        sos = signal.butter(order, cutoff, btype='high',
                            fs=sample_rate, output='sos')
        self._sos = sos
        self._filter_zi = signal.sosfilt_zi(self._sos)
        self._filter_state_valid = False

    def process(self, samples: np.ndarray, window_id: int) -> ProcessedWindow:
        assert samples.shape == (1600,), f"Expected 1600 samples, got {samples.shape}"
        x = samples.copy()
        clipping = bool(np.any(np.abs(x) > 0.999))
        x -= np.mean(x)

        if self._filter_state_valid:
            x, self._filter_zi = signal.sosfilt(self._sos, x, zi=self._filter_zi)
        else:
            zi_init = self._filter_zi * x[0]
            x, self._filter_zi = signal.sosfilt(self._sos, x, zi=zi_init)
            self._filter_state_valid = True

        rms_before = float(np.sqrt(np.mean(x ** 2)) + 1e-10)
        x = x * (self._target_rms / rms_before)
        x = np.clip(x, -1.0, 1.0)
        rms_after = float(np.sqrt(np.mean(x ** 2)))
        x = signal.lfilter([1.0, -0.97], [1.0], x)

        return ProcessedWindow(
            samples=x.astype(np.float32),
            rms_before=rms_before,
            rms_after=rms_after,
            clipping_detected=clipping,
            window_id=window_id
        )
