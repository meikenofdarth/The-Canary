from dataclasses import dataclass
from collections import deque
import numpy as np
from ..stage1.acoustic_intelligence import AcousticSceneOutput


@dataclass
class SCSResult:
    scs: float
    P_overlap: float
    N_norm: float
    U_speaker: float
    w1: float
    w2: float
    w3: float
    smoothed_scs: float
    window_id: int


class SCSCalculator:
    EMA_ALPHA = 0.30

    def __init__(self, config: dict):
        drs_cfg = config['dynamic_resource_scaler']
        self.w1 = drs_cfg['weight_overlap']
        self.w2 = drs_cfg['weight_noise']
        self.w3 = drs_cfg['weight_speaker_uncertainty']
        assert abs(self.w1 + self.w2 + self.w3 - 1.0) < 1e-6
        self._smoothed_scs = 0.0
        self._first_call = True
        self._history: deque[SCSResult] = deque(maxlen=100)

    def compute(self, scene: AcousticSceneOutput) -> SCSResult:
        raw_scs = float(np.clip(
            self.w1 * scene.P_overlap
          + self.w2 * scene.N_norm
          + self.w3 * scene.U_speaker,
            0.0, 1.0
        ))
        if self._first_call:
            self._smoothed_scs = raw_scs
            self._first_call = False
        else:
            self._smoothed_scs = (self.EMA_ALPHA * raw_scs
                                  + (1 - self.EMA_ALPHA) * self._smoothed_scs)
        result = SCSResult(
            scs=raw_scs, P_overlap=scene.P_overlap, N_norm=scene.N_norm,
            U_speaker=scene.U_speaker, w1=self.w1, w2=self.w2, w3=self.w3,
            smoothed_scs=self._smoothed_scs, window_id=scene.window_id,
        )
        self._history.append(result)
        return result

    def get_recent_stats(self) -> str:
        if not self._history:
            return "No SCS results yet"
        recent = list(self._history)[-10:]
        avg_scs = np.mean([r.scs for r in recent])
        return f"Recent SCS (last {len(recent)}): avg={avg_scs:.3f}, total_events={len(self._history)}"
