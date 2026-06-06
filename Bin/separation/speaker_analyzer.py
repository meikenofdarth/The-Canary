"""Speaker profiling, counting, and diarization analysis post-separation.

This module analyzes separated audio streams to estimate pitch profiles,
intensity, and generate exact diarization segments (who spoke, when, for how long).
"""

from dataclasses import dataclass, field
import numpy as np
from ..config import VoiceConfig


@dataclass
class SpeakerProfile:
    """Approximate acoustic profile for one active voice."""

    profile_id: int
    pitch_hz: float
    pitch_std_hz: float
    mean_intensity_dbfs: float
    frame_count: int
    support_ratio: float

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "pitch_hz": round(self.pitch_hz, 1),
            "pitch_std_hz": round(self.pitch_std_hz, 1),
            "mean_intensity_dbfs": round(self.mean_intensity_dbfs, 1),
            "frame_count": self.frame_count,
            "support_ratio": round(self.support_ratio, 3),
        }


@dataclass
class SpeakerAnalysis:
    """Post-separation speaker statistics and diarization data."""

    estimated_speaker_count: int = 1
    profiles: list[SpeakerProfile] = field(default_factory=list)
    active_frame_ratio: float = 0.0
    multi_pitch_frame_ratio: float = 0.0
    overlap_probability: float = 0.0
    mean_intensity_dbfs: float = -120.0
    spectral_centroid_hz: float = 0.0
    diarization: list[dict] = field(default_factory=list)  # Diarization segments


class SpeakerAcousticAnalyzer:
    """Acoustic analyzer to estimate profiles and diarization from separated streams."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._frame_size = max(config.n_fft * 2, 1024)
        self._hop = config.hop_length
        self._window = np.hanning(self._frame_size).astype(np.float32)
        self._freqs = np.fft.rfftfreq(self._frame_size, 1.0 / config.sample_rate)
        self._pitch_grid = np.arange(
            config.speaker_pitch_min_hz,
            config.speaker_pitch_max_hz + 1.0,
            2.0,
        )

    def analyze(self, audio: np.ndarray) -> SpeakerAnalysis:
        """Fallback analysis when no separation has been performed (Mode A / Mode B)."""
        # Down-mix to mono if input is stereo
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return self.analyze_separated([audio])

    def analyze_separated(self, streams: list[np.ndarray]) -> SpeakerAnalysis:
        """Analyze separated streams to extract profiles, count active voices, and diarize."""
        profiles = []
        diarization_data = []
        
        all_intensity_values = []
        all_centroids = []
        
        sr = self.config.sample_rate
        total_duration = max(len(streams[0]) / sr if streams else 0.0, 1.0)
        
        active_speaker_count = 0
        active_intervals_per_speaker = []

        for stream_idx, stream in enumerate(streams):
            pitch_values = []
            intensity_values = []
            centroids = []
            
            n_samples = len(stream)
            frame_times = []
            frame_active = []
            
            total_frames = 0
            active_frames = 0

            for start in range(0, n_samples - self._frame_size + 1, self._hop):
                total_frames += 1
                t_sec = (start + self._frame_size / 2.0) / sr
                frame = stream[start : start + self._frame_size].astype(np.float64)
                rms = float(np.sqrt(np.mean(frame**2) + 1e-12))
                
                frame_times.append(t_sec)
                
                if rms < self.config.speaker_frame_rms_threshold:
                    frame_active.append(False)
                    continue

                active_frames += 1
                frame_active.append(True)
                
                intensity = float(20.0 * np.log10(max(rms, 1e-6)))
                intensity_values.append(intensity)
                all_intensity_values.append(intensity)
                
                windowed = frame * self._window
                magnitude = np.abs(np.fft.rfft(windowed))
                mag_sum = float(np.sum(magnitude))
                if mag_sum <= 1e-10:
                    continue

                centroid = float(np.sum(self._freqs * magnitude) / mag_sum)
                centroids.append(centroid)
                all_centroids.append(centroid)

                # Estimate pitch candidates for this frame
                candidates = self._pitch_candidates(windowed, magnitude)
                if candidates:
                    # Keep the best pitch candidate
                    pitch_values.append(candidates[0][0])

            # Extract diarization segments (who spoke, when, for how long)
            segments = self._compute_diarization_segments(
                frame_times, frame_active, stream_idx + 1
            )
            diarization_data.extend(segments)
            active_intervals_per_speaker.append(segments)
            
            # Determine if this stream represents an active speaker
            if segments:
                active_speaker_count += 1
                
            mean_intensity = float(np.mean(intensity_values)) if intensity_values else -120.0
            support = active_frames / max(total_frames, 1)

            if active_frames >= self.config.speaker_min_profile_frames:
                mean_pitch = float(np.mean(pitch_values)) if pitch_values else 0.0
                std_pitch = float(np.std(pitch_values)) if pitch_values else 0.0
                
                profiles.append(
                    SpeakerProfile(
                        profile_id=stream_idx + 1,
                        pitch_hz=mean_pitch,
                        pitch_std_hz=std_pitch,
                        mean_intensity_dbfs=mean_intensity,
                        frame_count=active_frames,
                        support_ratio=support,
                    )
                )

        # Compute overlap probability based on diarization interval intersections
        overlap_prob = self._compute_overlap_probability(active_intervals_per_speaker, total_duration)

        # Compute overall stats
        overall_intensity = float(np.mean(all_intensity_values)) if all_intensity_values else -120.0
        overall_centroid = float(np.mean(all_centroids)) if all_centroids else 0.0
        
        # Ensure speaker count is bounded [1, 3] and matches active streams
        est_count = max(1, min(active_speaker_count, 3))

        return SpeakerAnalysis(
            estimated_speaker_count=est_count,
            profiles=profiles,
            active_frame_ratio=len(all_intensity_values) / max(len(streams) * total_duration * 100, 1),
            multi_pitch_frame_ratio=overlap_prob,
            overlap_probability=overlap_prob,
            mean_intensity_dbfs=overall_intensity,
            spectral_centroid_hz=overall_centroid,
            diarization=diarization_data,
        )

    def _pitch_candidates(
        self, frame: np.ndarray, magnitude: np.ndarray
    ) -> list[tuple[float, float]]:
        """Return harmonic pitch candidates for one active frame."""
        scores = np.zeros(len(self._pitch_grid), dtype=np.float64)
        for harmonic, harmonic_weight in ((1, 1.0), (2, 0.70), (3, 0.45), (4, 0.25)):
            harmonic_freqs = self._pitch_grid * harmonic
            scores += harmonic_weight * np.interp(harmonic_freqs, self._freqs, magnitude)

        max_score = float(np.max(scores))
        if max_score <= 1e-10:
            return []
        scores /= max_score

        order = np.argsort(scores)[::-1]
        selected: list[tuple[float, float]] = []
        for idx in order:
            score = float(scores[idx])
            pitch = float(self._pitch_grid[idx])
            if score < 0.52:
                break
            selected.append((pitch, score))
            if len(selected) == 1:
                break
        return selected

    def _compute_diarization_segments(
        self, times: list[float], active: list[bool], speaker_id: int
    ) -> list[dict]:
        """Compute VAD segments with gap-closing and minimum duration thresholds."""
        segments = []
        in_segment = False
        start_t = 0.0

        for t, is_active in zip(times, active):
            if is_active and not in_segment:
                in_segment = True
                start_t = t
            elif not is_active and in_segment:
                in_segment = False
                end_t = t
                duration = end_t - start_t
                if duration >= 0.15:  # Min duration threshold
                    segments.append(
                        {
                            "speaker_id": f"speaker_profile_{speaker_id}",
                            "start_time_s": round(start_t, 2),
                            "end_time_s": round(end_t, 2),
                            "duration_s": round(duration, 2),
                        }
                    )

        if in_segment:
            end_t = times[-1]
            duration = end_t - start_t
            if duration >= 0.15:
                segments.append(
                    {
                        "speaker_id": f"speaker_profile_{speaker_id}",
                        "start_time_s": round(start_t, 2),
                        "end_time_s": round(end_t, 2),
                        "duration_s": round(duration, 2),
                    }
                )

        # Merge segments with small gaps (< 250ms) to avoid flickering
        merged = []
        if segments:
            current = segments[0]
            for next_seg in segments[1:]:
                gap = next_seg["start_time_s"] - current["end_time_s"]
                if gap < 0.25:
                    current["end_time_s"] = next_seg["end_time_s"]
                    current["duration_s"] = round(
                        current["end_time_s"] - current["start_time_s"], 2
                    )
                else:
                    merged.append(current)
                    current = next_seg
            merged.append(current)
            return merged
        return []

    def _compute_overlap_probability(
        self, active_intervals: list[list[dict]], total_duration: float
    ) -> float:
        """Calculate the proportion of overlapping speech between different speakers."""
        if len(active_intervals) < 2:
            return 0.0

        # Discretize timeline into 10ms bins
        n_bins = int(total_duration * 100) + 1
        timeline = np.zeros((len(active_intervals), n_bins), dtype=bool)

        for s_idx, speaker_segments in enumerate(active_intervals):
            for seg in speaker_segments:
                start_bin = int(seg["start_time_s"] * 100)
                end_bin = int(seg["end_time_s"] * 100)
                timeline[s_idx, start_bin : end_bin + 1] = True

        # Sum active speakers across time bins
        active_counts = np.sum(timeline, axis=0)
        overlap_bins = np.sum(active_counts >= 2)
        speech_bins = np.sum(active_counts >= 1)

        if speech_bins == 0:
            return 0.0

        return float(overlap_bins / speech_bins)
