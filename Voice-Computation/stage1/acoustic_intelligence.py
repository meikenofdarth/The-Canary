import numpy as np
from dataclasses import dataclass


@dataclass
class AcousticSceneOutput:
    P_overlap: float
    N_norm: float
    U_speaker: float
    speaker_count_estimate: int
    window_id: int
    raw_audio: np.ndarray


class AcousticIntelligence:

    def __init__(self, config: dict):
        self._raw_audio_buffer: list[np.ndarray] = []
        stage1_cfg = config['stage1']

    def accumulate_raw_chunk(self, chunk: np.ndarray) -> None:
        self._raw_audio_buffer.append(chunk.copy())

    def analyze_full(self, audio: np.ndarray, noise_floor: float = 0.0) -> AcousticSceneOutput:
        spk = self._estimate_speaker_count(audio)
        P_overlap = self._estimate_overlap(audio, spk)
        N_norm = self._normalize_noise_floor(noise_floor)
        U_speaker = 0.0 if spk == 1 else 0.5

        return AcousticSceneOutput(
            P_overlap=P_overlap,
            N_norm=N_norm,
            U_speaker=U_speaker,
            speaker_count_estimate=spk,
            window_id=0,
            raw_audio=audio,
        )

    def _estimate_speaker_count(self, audio: np.ndarray) -> int:
        frame_len = 160
        hop = 80
        n_frames = max(1, (len(audio) - frame_len) // hop + 1)

        energies = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + frame_len] if start + frame_len <= len(audio) else audio[start:]
            if len(frame) < frame_len:
                frame = np.pad(frame, (0, frame_len - len(frame)), 'constant')
            energies[i] = float(np.sqrt(np.mean(frame ** 2) + 1e-12))

        energy_mean = float(np.mean(energies))
        if energy_mean < 1e-8:
            return 1
        energy_cv = float(np.std(energies)) / energy_mean

        centroid = self._compute_spectral_centroid(audio)
        centroid_mean = float(np.mean(centroid))
        centroid_cv = 0.0 if centroid_mean < 1e-8 else float(np.std(centroid)) / centroid_mean

        energy_diff = np.abs(np.diff(energies))
        med_diff = float(np.median(energy_diff)) if len(energy_diff) > 0 else 0.0
        transition_rate = float(np.mean(energy_diff > med_diff * 2)) if med_diff > 0 else 0.0

        speaker_score = (
            0.4 * min(energy_cv / 0.8, 1.0) +
            0.3 * min(centroid_cv / 0.5, 1.0) +
            0.3 * min(transition_rate / 0.3, 1.0)
        )

        return 2 if speaker_score >= 0.65 else 1

    def _estimate_overlap(self, audio: np.ndarray, speaker_count: int) -> float:
        if speaker_count <= 1:
            return 0.0
        frame_len = 160
        hop = 80
        n_frames = max(1, (len(audio) - frame_len) // hop + 1)
        energies = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + frame_len] if start + frame_len <= len(audio) else audio[start:]
            if len(frame) < frame_len:
                frame = np.pad(frame, (0, frame_len - len(frame)), 'constant')
            energies[i] = float(np.sqrt(np.mean(frame ** 2) + 1e-12))

        med_en = float(np.median(energies))
        max_en = float(np.max(energies))
        high_ratio = float(np.mean(energies > med_en * 1.2))
        gap_ratio = float(np.mean(energies < max_en * 0.2)) if max_en > 1e-8 else 0.0
        overlap = high_ratio * (1.0 - gap_ratio)

        if speaker_count >= 3:
            overlap = min(overlap * 1.3, 1.0)
        return float(np.clip(overlap, 0.0, 1.0))

    def _normalize_noise_floor(self, noise_floor: float) -> float:
        db = -60.0 + (float(np.clip(noise_floor, 0.0, 1.0)) * 50.0)
        norm = (db + 60.0) / 40.0
        return float(np.clip(norm, 0.0, 1.0))

    def _compute_spectral_centroid(self, audio: np.ndarray) -> np.ndarray:
        frame_len = 160
        hop = 80
        n_frames = max(1, (len(audio) - frame_len) // hop + 1)
        cents = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + frame_len] if start + frame_len <= len(audio) else audio[start:]
            if len(frame) < frame_len:
                frame = np.pad(frame, (0, frame_len - len(frame)), 'constant')
            D = np.abs(np.fft.rfft(frame))
            freqs = np.fft.rfftfreq(len(frame), d=1.0 / 16000)
            if np.sum(D) > 1e-12:
                cents[i] = float(np.sum(freqs * D) / np.sum(D))
        return cents
