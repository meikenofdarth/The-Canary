"""Feature Extraction — mel-spectrogram, MFCC, FFT, ZCR, energy, pitch.

HOW IT WORKS:
    Extracts a rich set of audio features used by the Scene Analyzer
    and downstream modules. All computation uses numpy only (no librosa
    at runtime). Designed for 16kHz mono float32 audio.

    Features Extracted:
    ──────────────────────────────────────────────────────────────────
    1.  Mel Spectrogram (n_mels × frames)
        Log-scaled, approximates human auditory perception.
        Used for speaker counting and scene complexity.

    2.  MFCC — Mel-Frequency Cepstral Coefficients (13 × frames)
        Compact spectral envelope representation.
        Invariant to pitch, captures timbre/phoneme identity.
        Computed via: STFT → mel filterbank → log → DCT-II.

    3.  FFT Magnitude Spectrum  (n_fft//2+1,)
        Time-averaged amplitude spectrum, in dB.
        Useful for visualizing overall frequency content.

    4.  Per-Frame Energy (frames,)
        RMS energy per frame — speech activity and rhythm.

    5.  Zero-Crossing Rate  (frames,)
        Frequency of sign changes — discriminates voiced vs unvoiced.

    6.  Spectral Centroid  (frames,)
        "Brightness" of the spectrum — centre of mass of |X(f)|.

    7.  Spectral Flatness  (frames,)  [0 = tonal, 1 = noise-like]
        Wiener entropy: geometric_mean(|X|) / arithmetic_mean(|X|).

    8.  Spectral Rolloff  (frames,)   [Hz]
        Frequency below which 85% of total spectral energy lies.

    9.  Pitch / F0  (frames,)         [Hz, 0 = unvoiced]
        Fundamental frequency estimated via autocorrelation.
        Speech range: 80–400 Hz.
    ──────────────────────────────────────────────────────────────────

    Fourier Transform Chain (diagram):

    Audio  ──[Hann window × n_fft]──► rfft ──► |·|  ──► STFT magnitude
                                                  │
                                              mel FB
                                                  │
                                             log(·+ε)  ──► mel spectrogram
                                                  │
                                              DCT-II    ──► MFCC
                                                  │
                                         avg over time ──► FFT spectrum
"""

import logging
from typing import Optional

import numpy as np

from ..config import VoiceConfig
from ..models import AudioFeatures

logger = logging.getLogger(__name__)

# Speech F0 range
_F0_MIN_HZ = 80
_F0_MAX_HZ = 400


class FeatureExtractor:
    """Extracts audio features for scene analysis and downstream use.

    All computation is numpy-only. Call extract(audio) to get a
    fully-populated AudioFeatures object.

    Args:
        config: VoiceConfig with FFT and mel parameters.
    """

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._mel_filterbank = self._create_mel_filterbank()
        self._dct_matrix = self._create_dct_matrix(config.n_mels, 13)
        # Pre-compute frequency axis (used for centroid / rolloff / plot)
        self._freqs_hz = np.fft.rfftfreq(
            config.n_fft, d=1.0 / config.sample_rate
        ).astype(np.float32)

    # ── Public API ─────────────────────────────────────────────────────────

    def extract(self, audio: np.ndarray) -> AudioFeatures:
        """Extract all features from audio.

        Args:
            audio: float32 mono array @ config.sample_rate.

        Returns:
            AudioFeatures with all fields populated.
        """
        n_fft = self.config.n_fft
        hop = self.config.hop_length
        sr = self.config.sample_rate

        # ── Short audio guard ────────────────────────────────────────
        if len(audio) < n_fft:
            empty = AudioFeatures(
                mel_spectrogram=np.zeros((self.config.n_mels, 1), dtype=np.float32),
                energy=np.array([0.0], dtype=np.float32),
                zero_crossing_rate=np.array([0.0], dtype=np.float32),
                spectral_centroid=np.array([0.0], dtype=np.float32),
                mfcc=np.zeros((13, 1), dtype=np.float32),
                fft_magnitude=np.zeros(n_fft // 2 + 1, dtype=np.float32),
                fft_freqs=self._freqs_hz,
                pitch_hz=np.array([0.0], dtype=np.float32),
                spectral_flatness=np.array([0.0], dtype=np.float32),
                spectral_rolloff=np.array([0.0], dtype=np.float32),
                rms_energy=0.0,
                duration_s=len(audio) / sr,
            )
            return empty

        # ── STFT magnitude (n_fft//2+1, frames) ─────────────────────
        stft_mag = self._compute_stft_magnitude(audio)  # float32

        # ── 1. Mel Spectrogram ───────────────────────────────────────
        mel_spec = self._mel_filterbank @ stft_mag  # (n_mels, frames)
        mel_spec_db = 20.0 * np.log10(mel_spec + 1e-6)  # dB scale

        # ── 2. MFCC ─────────────────────────────────────────────────
        log_mel = np.log(self._mel_filterbank @ stft_mag + 1e-10)
        mfcc = self._dct_matrix @ log_mel  # (13, frames)

        # ── 3. Averaged FFT spectrum (dB) ────────────────────────────
        avg_spec = np.mean(stft_mag, axis=1)  # (n_fft//2+1,)
        fft_db = 20.0 * np.log10(avg_spec + 1e-6)

        # ── 4. Per-frame energy (RMS) ────────────────────────────────
        energy = self._compute_frame_energy(audio)

        # ── 5. Zero-Crossing Rate ────────────────────────────────────
        zcr = self._compute_zcr(audio)

        # ── 6. Spectral Centroid ─────────────────────────────────────
        spectral_centroid = self._compute_spectral_centroid(stft_mag)

        # ── 7. Spectral Flatness ─────────────────────────────────────
        spectral_flatness = self._compute_spectral_flatness(stft_mag)

        # ── 8. Spectral Rolloff ──────────────────────────────────────
        spectral_rolloff = self._compute_spectral_rolloff(stft_mag)

        # ── 9. Pitch (F0) ────────────────────────────────────────────
        pitch_hz = self._compute_pitch(audio)

        # ── Overall RMS ─────────────────────────────────────────────
        rms = float(np.sqrt(np.mean(audio**2)))

        return AudioFeatures(
            mel_spectrogram=mel_spec_db.astype(np.float32),
            energy=energy.astype(np.float32),
            zero_crossing_rate=zcr.astype(np.float32),
            spectral_centroid=spectral_centroid.astype(np.float32),
            mfcc=mfcc.astype(np.float32),
            fft_magnitude=fft_db.astype(np.float32),
            fft_freqs=self._freqs_hz,
            pitch_hz=pitch_hz.astype(np.float32),
            spectral_flatness=spectral_flatness.astype(np.float32),
            spectral_rolloff=spectral_rolloff.astype(np.float32),
            rms_energy=rms,
            duration_s=len(audio) / sr,
        )

    # ── STFT ───────────────────────────────────────────────────────────────

    def _compute_stft_magnitude(self, audio: np.ndarray) -> np.ndarray:
        """Compute STFT magnitude matrix.

        Returns:
            float32 array of shape (n_fft//2+1, n_frames).
        """
        n_fft = self.config.n_fft
        hop = self.config.hop_length
        window = np.hanning(n_fft).astype(np.float32)

        n_frames = max((len(audio) - n_fft) // hop + 1, 1)
        mag = np.zeros((n_fft // 2 + 1, n_frames), dtype=np.float32)

        for i in range(n_frames):
            start = i * hop
            end = start + n_fft
            frame = (
                audio[start:end]
                if end <= len(audio)
                else np.pad(audio[start:], (0, end - len(audio)))
            )
            mag[:, i] = np.abs(np.fft.rfft(frame * window)).astype(np.float32)

        return mag

    # ── Per-Frame Features ─────────────────────────────────────────────────

    def _compute_frame_energy(self, audio: np.ndarray) -> np.ndarray:
        """RMS energy per frame."""
        frame_len = self.config.n_fft
        hop = self.config.hop_length
        energies = []
        for i in range(0, len(audio) - frame_len + 1, hop):
            energies.append(float(np.sqrt(np.mean(audio[i : i + frame_len] ** 2))))
        return np.array(energies, dtype=np.float32) if energies else np.array([0.0])

    def _compute_zcr(self, audio: np.ndarray) -> np.ndarray:
        """Zero-crossing rate per frame."""
        frame_len = self.config.n_fft
        hop = self.config.hop_length
        zcr = []
        for i in range(0, len(audio) - frame_len + 1, hop):
            frame = audio[i : i + frame_len]
            n_crossings = float(np.sum(np.abs(np.diff(np.sign(frame)))) / 2)
            zcr.append(n_crossings / frame_len)
        return np.array(zcr, dtype=np.float32) if zcr else np.array([0.0])

    def _compute_spectral_centroid(self, stft_mag: np.ndarray) -> np.ndarray:
        """Spectral centroid (centre of spectral mass) per frame, in Hz."""
        freqs = self._freqs_hz
        centroids = []
        for i in range(stft_mag.shape[1]):
            mag_f = stft_mag[:, i]
            total = float(np.sum(mag_f))
            if total < 1e-10:
                centroids.append(0.0)
            else:
                centroids.append(float(np.sum(freqs * mag_f) / total))
        return np.array(centroids, dtype=np.float32)

    def _compute_spectral_flatness(self, stft_mag: np.ndarray) -> np.ndarray:
        """Wiener entropy (spectral flatness) per frame.

        flatness = geometric_mean(|X(f)|) / arithmetic_mean(|X(f)|)
        0 = perfectly tonal, 1 = white noise.
        """
        flatness = []
        eps = 1e-10
        for i in range(stft_mag.shape[1]):
            mag_f = stft_mag[:, i] + eps
            geo_mean = float(np.exp(np.mean(np.log(mag_f))))
            arith_mean = float(np.mean(mag_f))
            flatness.append(geo_mean / arith_mean if arith_mean > eps else 0.0)
        return np.clip(np.array(flatness, dtype=np.float32), 0.0, 1.0)

    def _compute_spectral_rolloff(
        self, stft_mag: np.ndarray, rolloff_pct: float = 0.85
    ) -> np.ndarray:
        """Frequency below which rolloff_pct of total energy lies, per frame.

        Returns frequency in Hz.
        """
        freqs = self._freqs_hz
        rolloffs = []
        for i in range(stft_mag.shape[1]):
            power = stft_mag[:, i] ** 2
            total = float(np.sum(power))
            if total < 1e-10:
                rolloffs.append(0.0)
                continue
            cumsum = np.cumsum(power)
            idx = np.searchsorted(cumsum, rolloff_pct * total)
            idx = int(np.clip(idx, 0, len(freqs) - 1))
            rolloffs.append(float(freqs[idx]))
        return np.array(rolloffs, dtype=np.float32)

    def _compute_pitch(self, audio: np.ndarray) -> np.ndarray:
        """Estimate fundamental frequency (F0) via autocorrelation.

        Processes in n_fft-length frames with hop_length hop.
        Returns 0 Hz for unvoiced frames.

        Speech F0 range: 80–400 Hz.
        """
        sr = self.config.sample_rate
        frame_len = self.config.n_fft
        hop = self.config.hop_length

        # Period range in samples
        lag_min = max(sr // _F0_MAX_HZ, 1)  # 40 samples @ 400 Hz
        lag_max = sr // _F0_MIN_HZ  # 200 samples @ 80 Hz

        window = np.hanning(frame_len).astype(np.float32)
        pitches = []

        for i in range(0, len(audio) - frame_len + 1, hop):
            frame = (audio[i : i + frame_len] * window).astype(np.float64)

            # Normalised autocorrelation (faster via FFT)
            n_fft2 = 2 * frame_len
            X = np.fft.rfft(frame, n=n_fft2)
            acf = np.fft.irfft(X * np.conj(X))[:frame_len]

            if acf[0] < 1e-10:
                pitches.append(0.0)
                continue

            acf /= acf[0]  # Normalise

            # Find peak in [lag_min, lag_max]
            search = acf[lag_min : lag_max + 1]
            if len(search) == 0:
                pitches.append(0.0)
                continue

            peak_lag = int(np.argmax(search)) + lag_min
            peak_val = float(acf[peak_lag])

            # Voiced threshold: autocorrelation peak > 0.3
            if peak_val > 0.30:
                pitches.append(float(sr) / float(peak_lag))
            else:
                pitches.append(0.0)

        return np.array(pitches, dtype=np.float32) if pitches else np.array([0.0])

    # ── Filterbank / DCT ──────────────────────────────────────────────────

    def _create_mel_filterbank(self) -> np.ndarray:
        """Create (n_mels, n_fft//2+1) mel filterbank matrix."""
        n_mels = self.config.n_mels
        n_fft = self.config.n_fft
        sr = self.config.sample_rate
        n_freqs = n_fft // 2 + 1

        def hz_to_mel(f: float) -> float:
            return 2595.0 * np.log10(1.0 + f / 700.0)

        def mel_to_hz(m: float) -> float:
            return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

        mel_lo = hz_to_mel(80.0)
        mel_hi = hz_to_mel(sr / 2.0)
        mel_pts = np.linspace(mel_lo, mel_hi, n_mels + 2)
        hz_pts = np.array([mel_to_hz(m) for m in mel_pts])
        bin_pts = np.floor((n_fft + 1) * hz_pts / sr).astype(int)

        fb = np.zeros((n_mels, n_freqs), dtype=np.float32)
        for i in range(n_mels):
            lo, ctr, hi = bin_pts[i], bin_pts[i + 1], bin_pts[i + 2]
            for j in range(lo, ctr):
                if 0 <= j < n_freqs and ctr > lo:
                    fb[i, j] = (j - lo) / (ctr - lo)
            for j in range(ctr, hi):
                if 0 <= j < n_freqs and hi > ctr:
                    fb[i, j] = (hi - j) / (hi - ctr)

        return fb

    @staticmethod
    def _create_dct_matrix(n_input: int, n_output: int) -> np.ndarray:
        """DCT-II matrix of shape (n_output, n_input)."""
        n = np.arange(n_input)
        k = np.arange(n_output)[:, np.newaxis]
        dct = np.cos(np.pi * k * (2 * n + 1) / (2 * n_input))
        dct = dct * np.sqrt(2.0 / n_input)
        dct[0] /= np.sqrt(2.0)
        return dct.astype(np.float32)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = VoiceConfig()
    extractor = FeatureExtractor(config)

    # Synthetic: 440 Hz tone + harmonics (voiced-like)
    t = np.linspace(0, 1.0, config.sample_rate, endpoint=False)
    audio = (
        0.4 * np.sin(2 * np.pi * 220 * t)
        + 0.2 * np.sin(2 * np.pi * 440 * t)
        + 0.05 * np.random.randn(config.sample_rate)
    ).astype(np.float32)

    features = extractor.extract(audio)

    print(f"Mel spectrogram:   {features.mel_spectrogram.shape}")
    print(f"MFCC:              {features.mfcc.shape}")
    print(
        f"FFT magnitude:     {features.fft_magnitude.shape}  "
        f"(range: {features.fft_magnitude.min():.1f}–{features.fft_magnitude.max():.1f} dB)"
    )
    print(f"Energy:            {features.energy.shape}")
    print(f"ZCR:               {features.zero_crossing_rate.shape}")
    print(f"Spectral centroid: {features.spectral_centroid.shape}")
    print(
        f"Spectral flatness: {features.spectral_flatness.shape}  "
        f"mean={features.spectral_flatness.mean():.3f}"
    )
    print(
        f"Spectral rolloff:  {features.spectral_rolloff.shape}  "
        f"mean={features.spectral_rolloff.mean():.0f} Hz"
    )
    pitch_voiced = features.pitch_hz[features.pitch_hz > 0]
    if len(pitch_voiced):
        print(
            f"Pitch (voiced):    {len(pitch_voiced)} frames, "
            f"mean={pitch_voiced.mean():.0f} Hz"
        )
    else:
        print("Pitch: no voiced frames detected (expected for pure sine)")
    print(f"RMS energy:        {features.rms_energy:.4f}")
    print("FeatureExtractor test passed!")
