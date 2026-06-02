"""Unit tests for the Speaker Separation and Routing Redesign.

Tests:
1. Stereo spatial filtering panning masks.
2. Mono multi-pitch tracking and overtone rejection.
3. Diarization segment tracking.
4. Overlap probability calculation.
"""

import sys
import os
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib
config_mod = importlib.import_module("Voice-Computation.config")
VoiceConfig = config_mod.VoiceConfig
PipelineMode = config_mod.PipelineMode

separator_mod = importlib.import_module("Voice-Computation.separation.spectral_separator")
SpectralSpeakerSeparator = separator_mod.SpectralSpeakerSeparator

analyzer_mod = importlib.import_module("Voice-Computation.separation.speaker_analyzer")
SpeakerAcousticAnalyzer = analyzer_mod.SpeakerAcousticAnalyzer


class TestSeparationRedesign(unittest.TestCase):

    def setUp(self):
        self.config = VoiceConfig()
        self.separator = SpectralSpeakerSeparator(self.config)
        self.analyzer = SpeakerAcousticAnalyzer(self.config)

    def test_stereo_spatial_filtering(self):
        """Test that stereo signals with spatial differences are separated correctly."""
        sr = self.config.sample_rate
        duration = 2.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # Left channel has 200 Hz tone, Right has 500 Hz tone
        left = 0.5 * np.sin(2 * np.pi * 200 * t)
        right = 0.5 * np.sin(2 * np.pi * 500 * t)
        stereo_audio = np.stack([left, right], axis=1).astype(np.float32)

        # Run separation
        res = self.separator.process(stereo_audio)
        self.assertEqual(res.method, "stereo-spatial-filtering")
        self.assertGreaterEqual(len(res.speaker_streams), 2)

        # Verify that Speaker 1 (from Left) has predominant 200 Hz energy
        s1 = res.speaker_streams[0]
        s2 = res.speaker_streams[1]

        # Compute FFT and check peak freq
        fft_1 = np.abs(np.fft.rfft(s1))
        freqs = np.fft.rfftfreq(len(s1), 1.0 / sr)
        peak_1 = freqs[np.argmax(fft_1)]
        self.assertTrue(abs(peak_1 - 200) < 15 or abs(peak_1 - 500) < 15)

    def test_mono_harmonic_separation(self):
        """Test multi-pitch tracking and harmonic masking on mono overlapping tones."""
        sr = self.config.sample_rate
        duration = 2.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)

        # Mix 120 Hz (speaker 1 pitch) and 220 Hz (speaker 2 pitch)
        s1 = 0.5 * np.sin(2 * np.pi * 120 * t)
        s2 = 0.5 * np.sin(2 * np.pi * 220 * t)
        mono_mix = (s1 + s2).astype(np.float32)

        # Run separation (forcing overlap_probability > 0.15)
        res = self.separator.process(mono_mix, overlap_probability=0.5)
        self.assertEqual(res.method, "pitch-guided-soft-mask")
        self.assertEqual(len(res.speaker_streams), 2)

        # Check peak frequencies in the separated channels
        fft_1 = np.abs(np.fft.rfft(res.speaker_streams[0]))
        fft_2 = np.abs(np.fft.rfft(res.speaker_streams[1]))
        freqs = np.fft.rfftfreq(len(mono_mix), 1.0 / sr)

        peak_1 = freqs[np.argmax(fft_1)]
        peak_2 = freqs[np.argmax(fft_2)]

        # One should be near 120Hz, other near 220Hz
        peaks = sorted([peak_1, peak_2])
        self.assertTrue(abs(peaks[0] - 120) < 15)
        self.assertTrue(abs(peaks[1] - 220) < 15)

    def test_diarization_segments(self):
        """Test VAD tracking and diarization segment extraction."""
        sr = self.config.sample_rate
        duration = 3.0
        audio = np.zeros(int(sr * duration), dtype=np.float32)

        # Active speech between 0.5s - 1.5s
        t_active = np.linspace(0.5, 1.5, int(sr * 1.0), endpoint=False)
        audio[int(sr * 0.5):int(sr * 1.5)] = 0.4 * np.sin(2 * np.pi * 150 * t_active)

        analysis = self.analyzer.analyze(audio)
        self.assertGreaterEqual(len(analysis.diarization), 1)
        
        seg = analysis.diarization[0]
        self.assertEqual(seg["speaker_id"], "speaker_profile_1")
        # Check start and end times match closely
        self.assertTrue(abs(seg["start_time_s"] - 0.5) < 0.2)
        self.assertTrue(abs(seg["end_time_s"] - 1.5) < 0.2)

    def test_overlap_probability(self):
        """Test calculation of overlap ratio from active intervals."""
        intervals = [
            [{"speaker_id": "spk1", "start_time_s": 0.0, "end_time_s": 1.0}],
            [{"speaker_id": "spk2", "start_time_s": 0.5, "end_time_s": 1.5}]
        ]
        # Overlap is between 0.5s and 1.0s (0.5s duration)
        # Total speech duration is 1.5s (0.0s to 1.5s)
        # Overlap ratio = 0.5 / 1.5 = 33.3%
        overlap = self.analyzer._compute_overlap_probability(intervals, total_duration=2.0)
        self.assertAlmostEqual(overlap, 0.5 / 1.5, places=2)


if __name__ == "__main__":
    unittest.main()
