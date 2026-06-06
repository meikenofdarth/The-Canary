import numpy as np
from dataclasses import dataclass
from collections import deque


@dataclass
class SpeakerCountResult:
    count: int
    confidence: float
    uncertainty: float
    method: str = "fusion"


class SpeakerCountEstimator:

    def __init__(self, config: dict):
        stage1_cfg = config['stage1']
        self._min_corr = stage1_cfg.get('speaker_count_min_correlation', 0.3)
        self._max_speakers = stage1_cfg.get('max_speaker_count', 3)
        self._n_mfcc = stage1_cfg.get('speaker_count_mfcc_bins', 13)
        self._history: deque[SpeakerCountResult] = deque(maxlen=10)

    def estimate(self, features: np.ndarray, samples: np.ndarray) -> SpeakerCountResult:
        min_samples = 1600
        max_samples = 48000
        if len(samples) < min_samples:
            samples = np.pad(samples, (0, max(0, min_samples - len(samples))), 'constant')
        samples = samples[:min(len(samples), max_samples)]

        pitch_count, pitch_conf = self._estimate_by_pitch(samples)
        mfcc_count, mfcc_conf = self._estimate_by_mfcc(samples)
        energy_count, energy_conf = self._estimate_by_energy_contour(samples)
        spectral_count, spectral_conf = self._estimate_by_spectral_contrast(samples)

        counts = np.array([pitch_count, mfcc_count, energy_count, spectral_count])
        confs = np.array([pitch_conf, mfcc_conf, energy_conf, spectral_conf])

        moderate_conf = confs > 0.35
        high_conf = confs > 0.6

        if mfcc_count == 1 and np.any(counts[moderate_conf] > 1) and mfcc_conf < 0.9:
            mfcc_count = int(round(np.median(counts[moderate_conf])))
            mfcc_conf = 0.4

        if np.sum(high_conf) >= 2:
            weighted = np.average(counts[high_conf], weights=confs[high_conf])
            count = int(round(weighted))
        elif np.sum(moderate_conf) >= 2:
            weighted = np.average(counts[moderate_conf], weights=confs[moderate_conf])
            count = int(round(weighted))
        elif np.sum(moderate_conf) == 1:
            count = int(counts[moderate_conf][0])
        else:
            count = int(round(np.median(counts)))

        count = max(1, min(count, self._max_speakers))

        count = max(1, min(count, self._max_speakers))
        confidence = float(np.clip(np.mean(confs), 0.0, 1.0))
        uncertainty = 1.0 - confidence

        result = SpeakerCountResult(count=count, confidence=confidence,
                                    uncertainty=uncertainty, method="fusion")
        self._history.append(result)
        return result

    def _estimate_by_pitch(self, samples: np.ndarray) -> tuple[int, float]:
        auto = np.correlate(samples, samples, mode='full')
        auto = auto[len(auto) // 2:]
        auto = auto / (auto[0] + 1e-12)

        min_lag, max_lag = 40, 320
        if len(auto) <= max_lag:
            max_lag = len(auto) - 1
        if min_lag >= max_lag:
            return 1, 0.3

        segment = auto[min_lag:max_lag]

        peak_idxs = []
        for i in range(1, len(segment) - 1):
            if (segment[i] > segment[i-1] and segment[i] > segment[i+1]
                    and segment[i] > 0.2):
                peak_idxs.append(i)

        if not peak_idxs:
            return 1, 0.3

        candidates = [(p + min_lag, float(segment[p])) for p in peak_idxs]
        candidates.sort(key=lambda x: -x[1])

        f0_lag = candidates[0][0]
        distinct = [f0_lag]

        for lag, val in candidates[1:]:
            if len(distinct) >= self._max_speakers:
                break

            is_harmonic = False
            for dl in distinct:
                big, small = max(lag, dl), min(lag, dl)
                ratio = big / small
                if abs(ratio - round(ratio)) < 0.1:
                    is_harmonic = True
                    break

            if not is_harmonic:
                distinct.append(lag)

        n = len(distinct)
        peak_ratio = candidates[0][1] / (candidates[1][1] + 1e-12) if len(candidates) > 1 else 0.5

        if n == 1:
            count = 1
            conf = 0.6 + 0.3 * min(candidates[0][1] / 0.7, 1.0)
        else:
            if peak_ratio > 3.0:
                count = 1
                conf = 0.5
            elif peak_ratio > 1.5:
                count = n - 1
                conf = 0.5 * min(1.0 / peak_ratio * 3, 1.0)
            else:
                count = n
                conf = 0.5 + 0.3 * min(n / 3.0, 1.0)

        return max(1, min(count, self._max_speakers)), float(np.clip(conf, 0.0, 1.0))

    def _estimate_by_mfcc(self, samples: np.ndarray) -> tuple[int, float]:
        try:
            import librosa
            n_fft = 512
            hop = 128
            mfcc = librosa.feature.mfcc(
                y=samples, sr=16000, n_mfcc=self._n_mfcc,
                n_fft=n_fft, hop_length=hop
            )
            if mfcc.shape[1] < 5:
                return 1, 0.3

            delta = librosa.feature.delta(mfcc, width=5)
            delta2 = librosa.feature.delta(mfcc, order=2, width=5)

            features = np.vstack([mfcc[:6], delta[:6], delta2[:6]]).T

            n_frames = features.shape[0]
            if n_frames < 4:
                return 1, 0.4

            intra_cluster = []
            max_k = min(3, n_frames - 1)
            for k in range(1, max_k + 1):
                centroids, labels = self._kmeans(features, k)
                distortion = 0.0
                for j in range(k):
                    cluster_pts = features[labels == j]
                    if len(cluster_pts) > 0:
                        distortion += float(np.sum((cluster_pts - centroids[j]) ** 2))
                intra_cluster.append(distortion / n_frames)

            if len(intra_cluster) < 2:
                return 1, 0.4

            distortions = np.array(intra_cluster) + 1e-10
            ratios = [distortions[k] / distortions[k + 1] for k in range(len(distortions) - 1)]

            best_k = int(np.argmax(ratios) + 1)
            elbow = float(ratios[best_k - 1] if best_k <= len(ratios) else 1.0)
            elbow = float(np.clip((elbow - 1.1) / 1.5, 0.0, 1.0))

            if best_k == 1 and elbow > 0.2:
                return 1, elbow
            if best_k >= 2 and elbow > 0.4:
                return min(best_k, self._max_speakers), elbow

            return 1, 0.3

        except ImportError:
            return 1, 0.3

    def _kmeans(self, data: np.ndarray, k: int, max_iters: int = 20):
        n = data.shape[0]
        if k >= n:
            k = max(1, n - 1)
        idx = np.random.choice(n, k, replace=False)
        centroids = data[idx].copy()
        for _ in range(max_iters):
            dists = np.zeros((n, k))
            for j in range(k):
                diff = data - centroids[j]
                dists[:, j] = np.sum(diff ** 2, axis=1)
            labels = np.argmin(dists, axis=1)
            new_centroids = np.zeros_like(centroids)
            for j in range(k):
                cluster_pts = data[labels == j]
                if len(cluster_pts) > 0:
                    new_centroids[j] = np.mean(cluster_pts, axis=0)
                else:
                    new_centroids[j] = centroids[j]
            if np.allclose(centroids, new_centroids):
                break
            centroids = new_centroids
        return centroids, labels

    def _estimate_by_energy_contour(self, samples: np.ndarray) -> tuple[int, float]:
        frame_len = 160
        hop = 80
        n_frames = max(1, (len(samples) - frame_len) // hop + 1)

        energies = []
        for i in range(n_frames):
            start = i * hop
            frame = samples[start:start + frame_len] if start + frame_len <= len(samples) else samples[start:]
            if len(frame) < frame_len:
                frame = np.pad(frame, (0, frame_len - len(frame)), 'constant')
            energy = float(np.sqrt(np.mean(frame ** 2) + 1e-12))
            energies.append(energy)

        energies = np.array(energies)
        if len(energies) < 4:
            return 1, 0.3

        energy_mean = float(np.mean(energies))
        energy_std = float(np.std(energies))
        cv = energy_std / (energy_mean + 1e-12)

        if cv > 0.7:
            return 2, float(np.clip(cv, 0.3, 1.0))
        return 1, 0.3

    def _estimate_by_spectral_contrast(self, samples: np.ndarray) -> tuple[int, float]:
        try:
            import librosa
            S = np.abs(librosa.stft(samples, n_fft=512))
            if S.shape[0] < 8:
                return 1, 0.3

            n_bands = 6
            band_edges = np.linspace(0, S.shape[0], n_bands + 1).astype(int)
            contrasts = []
            for b in range(n_bands):
                band = S[band_edges[b]:band_edges[b+1], :]
                if band.size == 0:
                    continue
                peak = float(np.max(band, axis=0).mean())
                valley = float(np.min(band, axis=0).mean())
                contrasts.append(peak / (valley + 1e-12))

            if len(contrasts) < 3:
                return 1, 0.3

            c = np.array(contrasts)
            c_mean = float(np.mean(c))
            c_std = float(np.std(c))
            cv = c_std / (c_mean + 1e-12)

            n_high_contrast = int(np.sum(c > c_mean * 1.5))
            n_low_contrast = int(np.sum(c < c_mean * 0.5))

            ratio = n_high_contrast / (max(n_low_contrast, 1))

            if ratio > 2.5 and cv > 0.5:
                return 3, float(np.clip(cv, 0.4, 1.0))
            elif ratio > 1.5 and cv > 0.3:
                return 2, float(np.clip(cv, 0.3, 1.0))
            return 1, max(0.2, float(np.clip(1.0 - cv * 2, 0.0, 0.5)))

        except ImportError:
            return 1, 0.3
