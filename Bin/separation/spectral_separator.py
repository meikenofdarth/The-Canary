"""Multi-pitch tracking and spatial/harmonic speech separation.

This module unmixes overlapping speech streams *before* speaker analysis.
It implements:
1. Spatial panning-based filtering for stereo signals.
2. Multi-pitch harmonic tracking and overtone-rejection for mono signals.
"""

from dataclasses import dataclass, field
import numpy as np
from scipy.signal import istft, stft
from ..config import VoiceConfig


@dataclass
class SeparationResult:
    """Filtered mix and separated speaker streams."""

    processed_audio: np.ndarray
    speaker_streams: list[np.ndarray] = field(default_factory=list)
    method: str = "none"


class SpectralSpeakerSeparator:
    """Separates overlapping voice sources using spatial and harmonic filters."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._n_fft = 1024
        self._hop = 256

    def process(
        self,
        audio: np.ndarray,
        overlap_probability: float = 0.0,
        noise_floor_db: float = -60.0,
    ) -> SeparationResult:
        """Separate the input audio signal into source streams before identity checks."""
        is_stereo = audio.ndim > 1 and audio.shape[1] == 2

        if is_stereo:
            # ── Stereo Spatial Filtering ─────────────────────────────────────
            freqs, times, spec_L = stft(
                audio[:, 0],
                fs=self.config.sample_rate,
                window="hann",
                nperseg=self._n_fft,
                noverlap=self._n_fft - self._hop,
                boundary="zeros",
                padded=True,
            )
            _, _, spec_R = stft(
                audio[:, 1],
                fs=self.config.sample_rate,
                window="hann",
                nperseg=self._n_fft,
                noverlap=self._n_fft - self._hop,
                boundary="zeros",
                padded=True,
            )

            # Panning index from -1.0 (pure Right) to 1.0 (pure Left)
            mag_sum = np.abs(spec_L) + np.abs(spec_R) + 1e-8
            p = (np.abs(spec_L) - np.abs(spec_R)) / mag_sum

            # Soft spatial masks
            mask_L = np.clip((p - 0.15) / 0.20, 0.0, 1.0)
            mask_R = np.clip((-p - 0.15) / 0.20, 0.0, 1.0)
            mask_C = 1.0 - mask_L - mask_R

            spec_mean = 0.5 * (spec_L + spec_R)

            stream_L = self._restore(spec_L * mask_L, len(audio))
            stream_R = self._restore(spec_R * mask_R, len(audio))
            stream_C = self._restore(spec_mean * mask_C, len(audio))

            # Filter out silent/inactive channels
            candidates = [stream_L, stream_R, stream_C]
            speaker_streams = []
            for stream in candidates:
                rms = float(np.sqrt(np.mean(stream**2) + 1e-12))
                if rms >= 0.005:  # Standard speech activity floor
                    speaker_streams.append(stream)

            # Fallback if spatial filtering fails to find active sources
            if len(speaker_streams) < 2:
                speaker_streams = [audio[:, 0], audio[:, 1]]

            processed_audio = audio.mean(axis=1)
            return SeparationResult(
                processed_audio=processed_audio,
                speaker_streams=speaker_streams,
                method="stereo-spatial-filtering",
            )

        # ── Mono Harmonic Separation ─────────────────────────────────────────
        freqs, times, spec = stft(
            audio.astype(np.float32),
            fs=self.config.sample_rate,
            window="hann",
            nperseg=self._n_fft,
            noverlap=self._n_fft - self._hop,
            boundary="zeros",
            padded=True,
        )
        magnitude = np.abs(spec)
        
        # Apply standard spectral gate for noise reduction on the mixture
        noise_profile = np.percentile(magnitude, 18, axis=1, keepdims=True)
        spectral_gate = np.clip(
            1.0 - (1.35 * noise_profile / (magnitude + 1e-8)),
            self.config.separation_mask_floor,
            1.0,
        )
        filtered_magnitude = magnitude * spectral_gate
        filtered_spectrum = filtered_magnitude * np.exp(1j * np.angle(spec))
        processed = self._restore(filtered_spectrum, len(audio))



        # Multi-pitch estimation directly on mixture spectrogram
        pitch_grid = np.arange(
            self.config.speaker_pitch_min_hz,
            self.config.speaker_pitch_max_hz + 1.0,
            2.0,
        )
        n_frames = magnitude.shape[1]
        frame_pitches = []

        # Convert noise floor from dBFS to linear RMS (assume 0 dBFS corresponds to amplitude 1.0)
        noise_rms = 10.0 ** (noise_floor_db / 20.0)
        rms_threshold = max(2.5 * noise_rms, self.config.speaker_frame_rms_threshold)

        for t_idx in range(n_frames):
            # Check frame RMS energy to avoid detecting pitch in quiet/silent frames
            start_sample = t_idx * self._hop
            end_sample = start_sample + self._n_fft
            frame_samples = audio[start_sample:end_sample]
            rms = float(np.sqrt(np.mean(frame_samples**2) + 1e-12)) if len(frame_samples) > 0 else 0.0

            if rms < rms_threshold:
                frame_pitches.append([])
                continue

            frame_mag = filtered_magnitude[:, t_idx]

            # Compute Harmonic Sum Spectrum (HSS) to find candidate pitches
            scores = np.zeros(len(pitch_grid))
            for h_idx, h_weight in [(1, 1.0), (2, 0.70), (3, 0.50), (4, 0.35)]:
                h_freqs = pitch_grid * h_idx
                scores += h_weight * np.interp(h_freqs, freqs, frame_mag)

            # Find peaks with overtone/subharmonic rejection to prevent duplicate counts
            peak_pitches = []
            max_score = np.max(scores)
            if max_score > 1e-10:
                for idx in np.argsort(scores)[::-1]:
                    score = scores[idx]
                    pitch = pitch_grid[idx]
                    if score < 0.55 * max_score:
                        break
                    
                    # Enforce minimum distance between pitch peaks
                    if any(abs(pitch - existing) < 35.0 for existing in peak_pitches):
                        continue

                    # Harmonic/overtone/subharmonic rejection with wider tolerance for grid/STFT resolution
                    is_harmonic = False
                    for existing in peak_pitches:
                        ratio = pitch / existing
                        if any(abs(ratio - k) < 0.15 for k in [1.33, 1.5, 2.0, 2.5, 3.0, 4.0]):
                            is_harmonic = True
                            break
                        ratio_sub = existing / pitch
                        if any(abs(ratio_sub - k) < 0.15 for k in [1.33, 1.5, 2.0, 2.5, 3.0, 4.0]):
                            is_harmonic = True
                            break
                    
                    if not is_harmonic:
                        peak_pitches.append(pitch)
                        if len(peak_pitches) == 2:
                            break
            frame_pitches.append(peak_pitches)

        # Count active and multi-pitch frames to estimate overlap ratio
        active_frames = sum(1 for candidates in frame_pitches if len(candidates) >= 1)
        multi_pitch_frames = sum(1 for candidates in frame_pitches if len(candidates) >= 2)
        multi_ratio = multi_pitch_frames / max(active_frames, 1)

        # Skip separation and speaker clustering if overlap evidence is weak
        if multi_ratio < 0.15:
            return SeparationResult(processed_audio=processed, method="none")

        # Cluster frame pitch candidates to identify speaker pitch centers
        all_pitches = [p for frame in frame_pitches for p in frame]
        if len(all_pitches) >= 8:
            centers = np.percentile(all_pitches, [30, 70])
            for _ in range(10):
                dists = np.abs(np.array(all_pitches)[:, None] - centers[None, :])
                labels = np.argmin(dists, axis=1)
                new_centers = np.zeros(2)
                for c_idx in range(2):
                    mask = labels == c_idx
                    new_centers[c_idx] = (
                        np.mean(np.array(all_pitches)[mask])
                        if np.any(mask)
                        else centers[c_idx]
                    )
                if np.allclose(centers, new_centers, atol=0.5):
                    break
                centers = new_centers
            centers = np.sort(centers)
            gap = centers[1] - centers[0]
        else:
            centers = []
            gap = 0.0

        # If we confirm two distinct pitch clusters, perform harmonic separation
        if len(centers) == 2 and gap >= self.config.speaker_pitch_cluster_min_gap_hz:
            f0_s1 = np.zeros(n_frames)
            f0_s2 = np.zeros(n_frames)

            for t_idx, candidates in enumerate(frame_pitches):
                if len(candidates) == 2:
                    c1, c2 = candidates
                    if abs(c1 - centers[0]) + abs(c2 - centers[1]) < abs(c2 - centers[0]) + abs(c1 - centers[1]):
                        f0_s1[t_idx] = c1
                        f0_s2[t_idx] = c2
                    else:
                        f0_s1[t_idx] = c2
                        f0_s2[t_idx] = c1
                elif len(candidates) == 1:
                    c = candidates[0]
                    if abs(c - centers[0]) < abs(c - centers[1]):
                        f0_s1[t_idx] = c
                        f0_s2[t_idx] = centers[1]
                    else:
                        f0_s1[t_idx] = centers[0]
                        f0_s2[t_idx] = c
                else:
                    f0_s1[t_idx] = centers[0]
                    f0_s2[t_idx] = centers[1]

            # Generate dynamic time-frequency harmonic masks
            aff1 = self._harmonic_affinity_map(freqs, f0_s1)
            aff2 = self._harmonic_affinity_map(freqs, f0_s2)

            mask_sum = aff1 + aff2 + 1e-8
            mask1 = aff1 / mask_sum
            mask2 = aff2 / mask_sum

            stream1 = self._restore(filtered_spectrum * mask1, len(audio))
            stream2 = self._restore(filtered_spectrum * mask2, len(audio))

            return SeparationResult(
                processed_audio=processed,
                speaker_streams=[stream1, stream2],
                method="pitch-guided-soft-mask",
            )

        return SeparationResult(processed_audio=processed, method="none")

    def _harmonic_affinity_map(
        self, freqs: np.ndarray, f0_contour: np.ndarray
    ) -> np.ndarray:
        """Build a time-varying harmonic affinity map of shape (n_freqs, n_frames)."""
        n_freqs = len(freqs)
        n_frames = len(f0_contour)
        affinity = np.full((n_freqs, n_frames), self.config.separation_mask_floor, dtype=np.float64)
        width = 25.0  # Harmonic filter bandwidth

        for t_idx in range(n_frames):
            f0 = f0_contour[t_idx]
            if f0 <= 0:
                continue
            for harmonic in range(1, 12):
                harmonic_hz = f0 * harmonic
                if harmonic_hz >= freqs[-1]:
                    break
                harmonic_width = width + harmonic * 2.0
                affinity[:, t_idx] += (1.0 / np.sqrt(harmonic)) * np.exp(
                    -0.5 * ((freqs - harmonic_hz) / harmonic_width) ** 2
                )
        return affinity

    def _restore(self, spectrum: np.ndarray, expected_length: int) -> np.ndarray:
        """Inverse-STFT, trim, and normalize an output waveform."""
        _, audio = istft(
            spectrum,
            fs=self.config.sample_rate,
            window="hann",
            nperseg=self._n_fft,
            noverlap=self._n_fft - self._hop,
            input_onesided=True,
        )
        audio = audio[:expected_length].astype(np.float32)
        if len(audio) < expected_length:
            audio = np.pad(audio, (0, expected_length - len(audio)))
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        if peak > 0.95:
            audio = audio * (0.95 / peak)
        return audio.astype(np.float32)
