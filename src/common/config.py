"""Central configuration for The Canary system."""
from dataclasses import dataclass


@dataclass
class Config:
    """Global configuration — adjust for your hardware."""
    
    # ASR
    sensevoice_model_path: str = "models/sensevoice-small"
    asr_num_threads: int = 2
    
    # Speaker verification
    faiss_embedding_dim: int = 192  # CAM++ B0 output dimension
    speaker_similarity_threshold: float = 0.65
    enrollment_dir: str = "models/speaker_embeddings"
    
    # SLM
    ollama_model: str = "qwen2.5:1.5b"
    ollama_base_url: str = "http://localhost:11434"
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    session_ttl: int = 300  # seconds
    
    # Pipeline
    min_confidence_threshold: float = 0.5
    max_audio_duration: float = 10.0  # seconds
    sample_rate: int = 16000
    
    # Demo
    demo_mode: bool = False  # Use pre-recorded audio
    demo_audio_dir: str = "data/test_audio"
