import numpy as np
from dataclasses import dataclass
from .vad_engine import VADResult
from .wakeword_engine import WakeWordResult


@dataclass
class ThreeBitWord:
    Sb: bool
    Pw: float
    Nf: float
    PASS: bool
    chunk_id: int
    timestamp: float

    def __str__(self):
        status = "PASS \u2705" if self.PASS else "FAIL \U0001f507"
        return (f"[Chunk {self.chunk_id}] {status} | "
                f"Sb={int(self.Sb)} Pw={self.Pw:.3f} Nf={self.Nf:.3f}")


class PassiveGate:

    def __init__(self, config: dict):
        stage0_cfg = config['stage0']
        self.wakeword_threshold    = stage0_cfg['wakeword_threshold']
        self.noise_floor_threshold = stage0_cfg['noise_floor_threshold']
        self.require_wakeword      = stage0_cfg['require_wakeword']

        self._total_chunks  = 0
        self._pass_chunks   = 0
        self._fail_reasons  = {'no_speech': 0, 'no_wakeword': 0, 'too_noisy': 0}

    def evaluate(self, vad: VADResult, ww: WakeWordResult,
                 timestamp: float,
                 asr_wake_word_detected: bool = False) -> ThreeBitWord:
        self._total_chunks += 1

        Sb = vad.is_speech
        Pw = 1.0 if asr_wake_word_detected else ww.max_probability
        Nf = vad.noise_floor

        if not Sb:
            self._fail_reasons['no_speech'] += 1
            gate_pass = False
        elif self.require_wakeword and Pw < self.wakeword_threshold:
            self._fail_reasons['no_wakeword'] += 1
            gate_pass = False
        elif Nf >= self.noise_floor_threshold:
            self._fail_reasons['too_noisy'] += 1
            gate_pass = False
        else:
            gate_pass = True
            self._pass_chunks += 1

        return ThreeBitWord(
            Sb=Sb, Pw=Pw, Nf=Nf,
            PASS=gate_pass,
            chunk_id=vad.chunk_id,
            timestamp=timestamp
        )

    @property
    def pass_rate(self) -> float:
        if self._total_chunks == 0:
            return 0.0
        return self._pass_chunks / self._total_chunks

    def print_stats(self):
        total = self._total_chunks
        print(f"\n=== Passive Gate Statistics ===")
        print(f"Total chunks evaluated: {total}")
        print(f"PASS chunks: {self._pass_chunks} ({self.pass_rate*100:.1f}%)")
        print(f"Fail \u2014 no speech: {self._fail_reasons['no_speech']}")
        print(f"Fail \u2014 no wake word: {self._fail_reasons['no_wakeword']}")
        print(f"Fail \u2014 too noisy: {self._fail_reasons['too_noisy']}")
