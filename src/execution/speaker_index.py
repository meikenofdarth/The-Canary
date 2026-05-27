"""FAISS Speaker Embedding Index.

Fast cosine-similarity lookup for speaker verification
embeddings from CAM++. Uses FAISS IndexFlatIP for
normalized inner product search.
"""
import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SpeakerIndex:
    """FAISS-backed speaker embedding index for voice verification."""
    
    def __init__(self, embedding_dim: int = 192):
        """Initialize FAISS index.
        
        Args:
            embedding_dim: Dimension of speaker embeddings (192 for CAM++ B0)
        """
        self.dim = embedding_dim
        self.speaker_ids: list[str] = []
        self.index = None
        self._init_faiss()
    
    def _init_faiss(self):
        """Initialize FAISS index."""
        try:
            import faiss
            self.index = faiss.IndexFlatIP(self.dim)
            logger.info("FAISS index initialized (dim=%d)", self.dim)
        except ImportError:
            logger.warning("faiss-cpu not installed. Speaker matching will use numpy fallback.")
            self.index = None
            self._fallback_embeddings = []
    
    def enroll(self, speaker_id: str, embedding: np.ndarray):
        """Add a speaker's voice embedding to the index.
        
        Args:
            speaker_id: Unique speaker identifier
            embedding: Voice embedding vector from CAM++
        """
        emb = embedding.reshape(1, -1).astype(np.float32)
        
        if self.index is not None:
            import faiss
            faiss.normalize_L2(emb)
            self.index.add(emb)
        else:
            # Numpy fallback
            emb_norm = emb / np.linalg.norm(emb)
            self._fallback_embeddings.append(emb_norm)
        
        self.speaker_ids.append(speaker_id)
        logger.info("Enrolled speaker: %s", speaker_id)
    
    def identify(self, embedding: np.ndarray, threshold: float = 0.65) -> tuple[str, float]:
        """Match an embedding against enrolled speakers.
        
        Args:
            embedding: Query embedding from CAM++
            threshold: Minimum similarity score to accept match
            
        Returns:
            (speaker_id, confidence) or ("unknown", score)
        """
        if not self.speaker_ids:
            return "unknown", 0.0
        
        emb = embedding.reshape(1, -1).astype(np.float32)
        
        if self.index is not None:
            import faiss
            faiss.normalize_L2(emb)
            scores, indices = self.index.search(emb, k=1)
            score = float(scores[0][0])
            idx = int(indices[0][0])
        else:
            # Numpy fallback
            emb_norm = emb / np.linalg.norm(emb)
            scores = [float(np.dot(emb_norm, fb.T)) for fb in self._fallback_embeddings]
            idx = int(np.argmax(scores))
            score = scores[idx]
        
        if score >= threshold:
            return self.speaker_ids[idx], score
        return "unknown", score
    
    def load_enrollment(self, enrollment_dir: str):
        """Load pre-computed enrollment embeddings from .npy files.
        
        Expected structure:
            enrollment_dir/
                hemang.npy
                sanchit.npy
        """
        import os
        for fname in os.listdir(enrollment_dir):
            if fname.endswith('.npy'):
                speaker_id = fname.replace('.npy', '')
                embedding = np.load(os.path.join(enrollment_dir, fname))
                self.enroll(speaker_id, embedding)
    
    @property
    def num_enrolled(self) -> int:
        return len(self.speaker_ids)
