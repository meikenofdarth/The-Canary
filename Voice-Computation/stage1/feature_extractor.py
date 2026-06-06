import numpy as np
import librosa
from dataclasses import dataclass


@dataclass
class AudioFeatures:
    zcr_mean: float
    zcr_variance: float
    spectral_flatness: float
    mfcc_delta_variance: float
    corr_consistency: float
    energy_ratio: float
    window_id: int


class FeatureExtractor:

    N_MFCC = 13
    N_FRAMES = 8
    FRAME_LENGTH = 200
    HOP_LENGTH = 160

    def __init__(self, config: dict):
        stage1_cfg = config['stage1']

    def extract(self, samples: np.ndarray, window_id: int) -> AudioFeatures:
        assert samples.shape == (1600,), f"Expected 1600 samples, got {samples.shape}"

        zcr_mean, zcr_variance = self._compute_zcr(samples)

        spectral_flatness = self._compute_spectral_flatness(samples)

        mfcc_delta_variance = self._compute_mfcc_delta_variance(samples)

        corr_consistency = self._compute_autocorrelation_consistency(samples)

        energy_ratio = self._compute_energy_ratio(samples)

        return AudioFeatures(
            zcr_mean=zcr_mean,
            zcr_variance=zcr_variance,
            spectral_flatness=spectral_flatness,
            mfcc_delta_variance=mfcc_delta_variance,
            corr_consistency=corr_consistency,
            energy_ratio=energy_ratio,
            window_id=window_id,
        )

    def _compute_zcr(self, samples: np.ndarray) -> tuple[float, float]:
        frame_length = self.FRAME_LENGTH
        hop_length = self.HOP_LENGTH
        zcr = librosa.feature.zero_crossing_rate(
            samples, frame_length=frame_length, hop_length=hop_length
        )[0]
        return float(np.mean(zcr)), float(np.var(zcr))

    def _compute_spectral_flatness(self, samples: np.ndarray) -> float:
        D = np.abs(np.fft.rfft(samples))
        D = D[D > 1e-12]
        if len(D) < 2:
            return 0.5
        geometric = float(np.exp(np.mean(np.log(D))))
        arithmetic = float(np.mean(D))
        if arithmetic < 1e-12:
            return 0.5
        return float(np.clip(geometric / arithmetic, 0.0, 1.0))

    def _compute_mfcc_delta_variance(self, samples: np.ndarray) -> float:
        mfcc = librosa.feature.mfcc(
            y=samples, sr=16000, n_mfcc=self.N_MFCC,
            n_fft=self.FRAME_LENGTH, hop_length=self.HOP_LENGTH
        )
        if mfcc.shape[1] < 2:
            return 0.0
        delta = librosa.feature.delta(mfcc)
        delta_variance = float(np.mean(np.var(delta, axis=1)))
        return delta_variance

    def _compute_autocorrelation_consistency(self, samples: np.ndarray) -> float:
        autocorr = np.correlate(samples, samples, mode='full')
        autocorr = autocorr[len(autocorr) // 2:]

        autocorr = autocorr / (autocorr[0] + 1e-12)

        min_lag = 53
        max_lag = 267
        if len(autocorr) <= max_lag:
            max_lag = len(autocorr) - 1
        if min_lag >= max_lag:
            return 0.5

        segment = autocorr[min_lag:max_lag + 1]

        if len(segment) < 2:
            return 0.5

        peak_val = float(np.max(segment))
        peak_idx = int(np.argmax(segment))

        trough_val = float(np.min(segment))

        consistency = 1.0 - float(np.clip(peak_val - trough_val, 0.0, 1.0))

        if consistency < 0.1:
            return 0.1

        return consistency

    def _compute_energy_ratio(self, samples: np.ndarray) -> float:
        D = np.fft.rfft(samples)
        power = np.abs(D) ** 2
        freqs = np.fft.rfftfreq(1600, d=1.0 / 16000)

        speech_band = (freqs >= 300) & (freqs <= 3400)
        speech_energy = float(np.sum(power[speech_band]))
        total_energy = float(np.sum(power)) + 1e-12

        return float(np.clip(speech_energy / total_energy, 0.0, 1.0))
