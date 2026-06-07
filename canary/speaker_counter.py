"""
canary/speaker_counter.py
--------------------------
Windowed speaker count estimator.

Approach:
  - Slides a short window (500ms) across the audio with 50% overlap
  - For each window, extracts a 6-dim acoustic feature vector
  - Only keeps windows with sufficient energy (voiced)
  - Agglomerative threshold clustering on the features → speaker count

This approach handles the case of continuous overlapping speech where
VAD detects a single long segment.
"""

from __future__ import annotations

import numpy as np
import torch
from typing import List
import warnings


class SpeakerCountEstimator:
    """
    Estimates the number of distinct speakers using sliding-window
    spectral feature clustering.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate in Hz. Silero VAD requires 16000.
    max_speakers : int
        Cap on returned speaker count (default 3).
    window_sec : float
        Analysis window length in seconds (default 0.5s).
    hop_sec : float
        Hop between windows in seconds (default 0.25s).
    energy_threshold_db : float
        Windows below this RMS level (dBFS) are skipped (default -45 dBFS).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        max_speakers: int = 3,
        window_sec: float = 0.5,
        hop_sec: float = 0.25,
        energy_threshold_db: float = -45.0,
    ):
        self.sample_rate = sample_rate
        self.max_speakers = max_speakers
        self.window_size = int(window_sec * sample_rate)
        self.hop_size = int(hop_sec * sample_rate)
        self.energy_threshold_db = energy_threshold_db

    # ------------------------------------------------------------------
    def _extract_features(self, window: np.ndarray) -> np.ndarray:
        """
        Extract a 6-dim feature vector from one audio window.
        Features:
          0: log energy
          1: zero-crossing rate
          2: spectral centroid (Hz)
          3: spectral bandwidth
          4: spectral rolloff (85%)
          5: spectral flatness (log)
        """
        N = 1024
        w = window.astype(np.float64)
        if len(w) < N:
            w = np.pad(w, (0, N - len(w)))

        # Energy
        energy = float(np.mean(w ** 2))
        log_energy = float(np.log10(energy + 1e-10))

        # ZCR
        zcr = float(np.mean(np.abs(np.diff(np.sign(w)))) / 2.0)

        # Spectrum
        spec = np.abs(np.fft.rfft(w * np.hanning(len(w)), n=N))
        freqs = np.fft.rfftfreq(N, d=1.0 / self.sample_rate)
        spec_sum = spec.sum() + 1e-9

        # Centroid
        centroid = float(np.dot(freqs, spec) / spec_sum)

        # Bandwidth
        bandwidth = float(np.sqrt(np.dot((freqs - centroid) ** 2, spec) / spec_sum))

        # Rolloff
        cumspec = np.cumsum(spec)
        rolloff_idx = np.searchsorted(cumspec, 0.85 * spec_sum)
        rolloff = float(freqs[min(rolloff_idx, len(freqs) - 1)])

        # Flatness (geometric mean / arithmetic mean of spectrum)
        log_spec = np.log(spec + 1e-10)
        flatness = float(np.exp(log_spec.mean()) / (spec.mean() + 1e-9))
        log_flatness = float(np.log10(flatness + 1e-10))

        return np.array(
            [log_energy, zcr, centroid, bandwidth, rolloff, log_flatness],
            dtype=np.float32,
        )

    # ------------------------------------------------------------------
    def _cluster_features(
        self, features: np.ndarray, distance_threshold: float = 0.4
    ) -> int:
        """
        Greedy agglomerative clustering on L2-normalised features.
        Returns number of clusters (= estimated speaker count).
        """
        if len(features) == 0:
            return 1

        # Standardise features (z-score per dimension)
        mean = features.mean(axis=0)
        std = features.std(axis=0) + 1e-8
        normed = (features - mean) / std

        # Then L2-normalise each row
        row_norms = np.linalg.norm(normed, axis=1, keepdims=True) + 1e-9
        normed = normed / row_norms

        # Shuffle to reduce ordering bias
        np.random.seed(42)
        idx = np.random.permutation(len(normed))
        normed = normed[idx]

        centroids = [normed[0].copy()]
        counts = [1]

        for feat in normed[1:]:
            dists = [np.linalg.norm(feat - c) for c in centroids]
            min_dist = min(dists)
            min_idx = int(np.argmin(dists))

            if min_dist > distance_threshold and len(centroids) < self.max_speakers:
                centroids.append(feat.copy())
                counts.append(1)
            else:
                # Running average update
                n = counts[min_idx]
                centroids[min_idx] = (centroids[min_idx] * n + feat) / (n + 1)
                counts[min_idx] += 1

        return len(centroids)

    # ------------------------------------------------------------------
    def estimate(self, audio: np.ndarray) -> int:
        """
        Estimate number of distinct speakers in a 1-D float32 16kHz mono array.

        Returns an int ≥ 1.
        """
        features = []
        n = len(audio)

        for start in range(0, n - self.window_size, self.hop_size):
            window = audio[start : start + self.window_size]

            # Skip low-energy windows (silence/noise)
            rms = float(np.sqrt(np.mean(window ** 2)))
            rms_db = 20.0 * np.log10(rms + 1e-10)
            if rms_db < self.energy_threshold_db:
                continue

            features.append(self._extract_features(window))

        if not features:
            return 1

        feats = np.stack(features)

        # Try multiple thresholds and take the median result
        # (more robust than a single threshold)
        results = []
        for thresh in [0.3, 0.4, 0.5, 0.6]:
            results.append(self._cluster_features(feats.copy(), thresh))

        # Use the most common result
        from collections import Counter
        count = Counter(results)
        n_spk = count.most_common(1)[0][0]

        return max(1, min(n_spk, self.max_speakers))
