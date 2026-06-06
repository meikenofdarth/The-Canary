import time
from enum import Enum
from .scs_calculator import SCSResult


class ProcessingMode(Enum):
    MODE_A = "A"
    MODE_B = "B"
    MODE_C = "C"


class ModeRouter:
    def __init__(self, config: dict):
        drs_cfg = config['dynamic_resource_scaler']
        self._a_thresh  = drs_cfg['mode_a_threshold']
        self._c_thresh  = drs_cfg['mode_c_threshold']
        self._hyst      = drs_cfg['hysteresis_margin']
        self._hold_ms   = drs_cfg['mode_hold_ms']
        self._current   = ProcessingMode.MODE_A
        self._held_since = time.monotonic()

    def route(self, scs: SCSResult) -> ProcessingMode:
        val = scs.smoothed_scs
        now = time.monotonic()
        held_long_enough = (now - self._held_since) * 1000 >= self._hold_ms

        if not held_long_enough:
            return self._current

        if self._current == ProcessingMode.MODE_A:
            if val >= self._a_thresh + self._hyst:
                self._transition(ProcessingMode.MODE_B if val < self._c_thresh else ProcessingMode.MODE_C, now)
        elif self._current == ProcessingMode.MODE_B:
            if val < self._a_thresh - self._hyst:
                self._transition(ProcessingMode.MODE_A, now)
            elif val > self._c_thresh + self._hyst:
                self._transition(ProcessingMode.MODE_C, now)
        elif self._current == ProcessingMode.MODE_C:
            if val <= self._c_thresh - self._hyst:
                self._transition(ProcessingMode.MODE_B, now)

        return self._current

    def _transition(self, new_mode, now):
        self._current = new_mode
        self._held_since = now
