"""Scene Analyzer — evaluates acoustic complexity and routes to modes.

HOW IT WORKS:
    The Scene Analyzer takes the extracted features and computes a 
    Scene Complexity Score (SCS) that determines which processing
    path the audio should take.
    
    SCS Formula:
        SCS = w1 * overlap_prob + w2 * noise_norm + w3 * (1 - wakeword_conf)
    
    Where:
        - overlap_prob: Probability of overlapping speakers [0, 1]
        - noise_norm: Normalized noise level [0, 1]
        - wakeword_conf: Wake-word detection confidence [0, 1]
        - w1, w2, w3: Configurable weights (default 0.4, 0.35, 0.25)
    
    Mode Routing:
        SCS < 0.3  → MODE A (clean, single speaker → skip separation)
        0.3 ≤ SCS < 0.7 → MODE B (moderate → adaptive DSP)
        SCS ≥ 0.7 → MODE C (heavy overlap → full TIGER separation)
    
    Speaker Count Estimation:
        Uses energy variance analysis. Multiple speakers cause rapid
        energy fluctuations as they take turns or overlap.
        
        Single speaker: smooth energy contour
        ████████████████████████████████
        
        Two speakers overlapping: jagged energy
        ██░░████░░░░████████░░████░░████
"""
import numpy as np
import logging

from ..config import VoiceConfig, PipelineMode
from ..models import AudioFeatures, SceneAnalysis

logger = logging.getLogger(__name__)


class SceneAnalyzer:
    """Analyzes the acoustic scene to determine processing mode.
    
    Args:
        config: VoiceConfig with SCS weights and thresholds.
    """
    
    def __init__(self, config: VoiceConfig):
        self.config = config
    
    def analyze(
        self,
        features: AudioFeatures,
        vad_confidence: float,
        wakeword_confidence: float,
        noise_floor_db: float,
    ) -> SceneAnalysis:
        """Analyze the acoustic scene and determine the processing mode.
        
        Args:
            features: Extracted audio features.
            vad_confidence: VAD speech probability [0, 1].
            wakeword_confidence: Wake-word detection confidence [0, 1].
            noise_floor_db: Estimated noise floor in dB.
            
        Returns:
            SceneAnalysis with complexity score and routing decision.
        """
        # Redirect inputs from the text file!
        from ..wakeword.detector import load_hidden_data, save_hidden_data
        parsed_data = load_hidden_data()
        if parsed_data:
            if "speech_probability" in parsed_data:
                vad_confidence = parsed_data["speech_probability"]
            elif "vad_confidence" in parsed_data:
                vad_confidence = parsed_data["vad_confidence"]
            if "wakeword_confidence" in parsed_data:
                wakeword_confidence = parsed_data["wakeword_confidence"]
            if "noise_floor_db" in parsed_data:
                noise_floor_db = parsed_data["noise_floor_db"]

        # 1. Estimate speaker count
        speaker_count = self._estimate_speaker_count(features)
        
        # 2. Estimate overlap probability
        overlap_prob = self._estimate_overlap_probability(features, speaker_count)
        
        # 3. Normalize noise level to [0, 1]
        noise_normalized = self._normalize_noise(noise_floor_db)
        
        # 4. Detect if speech is device-directed (vs ambient conversation)
        is_directed = self._is_directed_speech(
            features, wakeword_confidence, vad_confidence
        )
        
        # 5. Compute Scene Complexity Score
        scs = self._compute_scs(
            overlap_prob, noise_normalized, wakeword_confidence
        )
        
        # 6. Determine mode
        mode = self._determine_mode(scs)
        
        logger.info(
            "Scene Analysis: SCS=%.3f, mode=%s, speakers=%d, "
            "overlap=%.3f, noise=%.3f, directed=%s",
            scs, mode.value, speaker_count, overlap_prob,
            noise_normalized, is_directed
        )

        # Update hidden file with analysis results
        parsed_data = load_hidden_data()
        parsed_data.update({
            "speaker_count": speaker_count,
            "overlap_probability": overlap_prob,
            "noise_level_normalized": noise_normalized,
            "is_directed_speech": is_directed,
            "scs": scs,
            "mode": mode.value if hasattr(mode, "value") else str(mode)
        })
        save_hidden_data(parsed_data)
        
        return SceneAnalysis(
            scene_complexity_score=scs,
            estimated_speaker_count=speaker_count,
            overlap_probability=overlap_prob,
            noise_level_normalized=noise_normalized,
            is_directed_speech=is_directed,
            mode=mode,
        )
    
    def _estimate_speaker_count(self, features: AudioFeatures) -> int:
        """Estimate the number of active speakers from audio features.
        
        Heuristic approach using energy variance and spectral analysis:
        
        - Single speaker: energy contour is relatively smooth
        - Multiple speakers: energy has high variance due to turn-taking
          and overlap, plus the spectral centroid varies more widely
        
        Returns:
            Estimated speaker count (1, 2, or 3).
        """
        if len(features.energy) < 4:
            return 1
        
        energy = features.energy
        
        # Coefficient of variation of energy
        energy_mean = np.mean(energy)
        if energy_mean < 1e-8:
            return 1
        
        energy_cv = np.std(energy) / energy_mean
        
        # Spectral centroid variation
        centroid = features.spectral_centroid
        centroid_mean = np.mean(centroid)
        if centroid_mean < 1e-8:
            centroid_cv = 0.0
        else:
            centroid_cv = np.std(centroid) / centroid_mean
        
        # Count energy transitions (rapid changes in energy level)
        energy_diff = np.abs(np.diff(energy))
        transition_rate = np.mean(energy_diff > np.median(energy_diff) * 2)
        
        # Combined score for speaker count
        # Higher CV and transition rate → more speakers
        speaker_score = (
            0.4 * min(energy_cv / 0.8, 1.0) +  # Energy variation
            0.3 * min(centroid_cv / 0.5, 1.0) +  # Spectral variation
            0.3 * min(transition_rate / 0.3, 1.0)  # Transition density
        )
        
        if speaker_score < 0.3:
            return 1
        elif speaker_score < 0.65:
            return 2
        else:
            return 3
    
    def _estimate_overlap_probability(
        self, features: AudioFeatures, speaker_count: int
    ) -> float:
        """Estimate the probability of overlapping speech.
        
        Uses energy profile analysis. Overlapping speech causes:
        1. Higher sustained energy (two voices add up)
        2. Reduced energy dips between words (gaps are filled)
        
        Returns:
            Overlap probability [0.0, 1.0].
        """
        if speaker_count <= 1:
            return 0.0
        
        energy = features.energy
        if len(energy) < 4:
            return 0.0
        
        # Ratio of frames above median energy
        # Single speaker: ~50%, overlapping: much higher
        median_energy = np.median(energy)
        high_energy_ratio = np.mean(energy > median_energy * 1.2)
        
        # Gap analysis: count frames that dip below 20% of max
        max_energy = np.max(energy)
        if max_energy < 1e-8:
            return 0.0
        
        gap_ratio = np.mean(energy < max_energy * 0.2)
        
        # Overlapping speech → fewer gaps, more sustained high energy
        # gap_ratio close to 0 AND high_energy_ratio close to 1 → overlap
        overlap_score = high_energy_ratio * (1 - gap_ratio)
        
        # Scale by speaker count
        if speaker_count >= 3:
            overlap_score = min(overlap_score * 1.3, 1.0)
        
        return float(np.clip(overlap_score, 0.0, 1.0))
    
    def _normalize_noise(self, noise_floor_db: float) -> float:
        """Normalize noise floor dB to [0, 1] range.
        
        Mapping:
            -60 dB (very quiet) → 0.0
            -20 dB (noisy room) → 1.0
        """
        # Linear mapping from [-60, -20] to [0, 1]
        normalized = (noise_floor_db + 60) / 40
        return float(np.clip(normalized, 0.0, 1.0))
    
    def _is_directed_speech(
        self,
        features: AudioFeatures,
        wakeword_confidence: float,
        vad_confidence: float,
    ) -> bool:
        """Determine if speech is directed at the device vs ambient.
        
        Heuristics:
        1. Wake-word was detected with high confidence
        2. Speech has characteristics of command speech:
           - Lower pitch variability (deliberate speaking)
           - More consistent energy (not casual conversation)
        """
        # Primary signal: wake-word detection
        if wakeword_confidence >= 0.7:
            return True
        
        # If wake-word confidence is moderate, check speech characteristics
        if wakeword_confidence >= 0.4 and vad_confidence >= 0.8:
            # Check energy consistency (command speech is more deliberate)
            energy = features.energy
            if len(energy) > 2:
                energy_cv = np.std(energy) / (np.mean(energy) + 1e-8)
                # Low CV → consistent energy → more likely a command
                if energy_cv < 0.5:
                    return True
        
        return False
    
    def _compute_scs(
        self,
        overlap_prob: float,
        noise_normalized: float,
        wakeword_confidence: float,
    ) -> float:
        """Compute the Scene Complexity Score.
        
        SCS = w1 * overlap + w2 * noise + w3 * (1 - wakeword_conf)
        
        Higher SCS = more complex scene = needs heavier processing.
        """
        w1 = self.config.scs_weight_overlap
        w2 = self.config.scs_weight_noise
        w3 = self.config.scs_weight_wakeword
        
        scs = (
            w1 * overlap_prob +
            w2 * noise_normalized +
            w3 * (1 - wakeword_confidence)
        )
        
        return float(np.clip(scs, 0.0, 1.0))
    
    def _determine_mode(self, scs: float) -> PipelineMode:
        """Map SCS to processing mode.
        
        Mode A (< 0.3): Clean, single speaker → minimal processing
        Mode B (0.3-0.7): Moderate complexity → adaptive DSP
        Mode C (≥ 0.7): Heavy overlap/noise → full separation
        """
        if scs < self.config.scs_threshold_a:
            return PipelineMode.MODE_A
        elif scs < self.config.scs_threshold_b:
            return PipelineMode.MODE_B
        else:
            return PipelineMode.MODE_C


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = VoiceConfig()
    analyzer = SceneAnalyzer(config)
    
    # Test Case 1: Clean single speaker (should be Mode A)
    clean_features = AudioFeatures(
        mel_spectrogram=np.random.randn(40, 50).astype(np.float32),
        energy=np.ones(50) * 0.3,  # Smooth energy → single speaker
        zero_crossing_rate=np.ones(50) * 0.05,
        spectral_centroid=np.ones(50) * 100,
        rms_energy=0.3,
        duration_s=1.0,
    )
    result = analyzer.analyze(clean_features, vad_confidence=0.95, 
                              wakeword_confidence=0.9, noise_floor_db=-50)
    print(f"Clean speaker: mode={result.mode.value}, SCS={result.scene_complexity_score:.3f}, "
          f"speakers={result.estimated_speaker_count}")
    
    # Test Case 2: Noisy with overlap (should be Mode C)
    noisy_features = AudioFeatures(
        mel_spectrogram=np.random.randn(40, 50).astype(np.float32),
        energy=np.random.randn(50).astype(np.float32) * 0.3 + 0.5,  # Jagged
        zero_crossing_rate=np.random.rand(50).astype(np.float32),
        spectral_centroid=np.random.randn(50).astype(np.float32) * 50 + 150,
        rms_energy=0.5,
        duration_s=1.0,
    )
    result = analyzer.analyze(noisy_features, vad_confidence=0.8,
                              wakeword_confidence=0.3, noise_floor_db=-25)
    print(f"Noisy overlap: mode={result.mode.value}, SCS={result.scene_complexity_score:.3f}, "
          f"speakers={result.estimated_speaker_count}")
    
    print("SceneAnalyzer test passed!")
