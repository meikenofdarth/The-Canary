"""Main Pipeline Orchestrator — The Canary.

Connects all pipeline stages into a unified execution flow.
This is the main entry point for the system.
"""
import logging
import time
from typing import Optional

from src.common.models import (
    PipelineOutput, PipelineMode, TranscriptionResult,
    UserRole, ArbitrationDecision
)
from src.common.config import Config
from src.asr.engine import ASREngine
from src.arbitration.engine import ArbitrationEngine
from src.execution.queue import ExecutionQueue
from src.execution.state_store import StateStore
from src.execution.speaker_index import SpeakerIndex

logger = logging.getLogger(__name__)


class CanaryPipeline:
    """The Canary — Main pipeline orchestrator.
    
    Receives acoustic pipeline output (from Engineer A),
    runs ASR, arbitration, and executes commands.
    """
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._init_modules()
    
    def _init_modules(self):
        """Initialize all Engineer B modules."""
        logger.info("Initializing Canary pipeline...")
        
        # State store (Redis)
        self.state_store = StateStore(self.config.redis_url)
        
        # ASR Engine
        self.asr = ASREngine(
            model_path=self.config.sensevoice_model_path,
            num_threads=self.config.asr_num_threads
        )
        
        # Speaker index (FAISS)
        self.speaker_index = SpeakerIndex(
            embedding_dim=self.config.faiss_embedding_dim
        )
        
        # Arbitration engine
        self.arbitration = ArbitrationEngine(state_store=self.state_store)
        
        # Execution queue
        self.exec_queue = ExecutionQueue(state_store=self.state_store)
        
        logger.info("Canary pipeline initialized.")
    
    def process(self, pipeline_output: PipelineOutput) -> str:
        """Process acoustic pipeline output end-to-end.
        
        This is the main entry point called by Engineer A's code.
        
        Args:
            pipeline_output: Output from Stages 0-2
            
        Returns:
            Human-readable response string
        """
        start_time = time.time()
        
        # 1. Transcribe all audio streams
        transcriptions = self._transcribe_streams(pipeline_output)
        
        # 2. Run arbitration
        decision = self.arbitration.arbitrate(transcriptions)
        
        # 3. Execute
        result = self._execute_decision(decision)
        
        # 4. Log metrics
        elapsed = time.time() - start_time
        self.state_store.log_pipeline_metric("e2e_latency", elapsed)
        logger.info("Pipeline processed in %.3fs", elapsed)
        
        return result
    
    def _transcribe_streams(self, output: PipelineOutput) -> list[TranscriptionResult]:
        """Transcribe audio streams and build structured results."""
        results = []
        
        # Extract audio arrays
        audio_arrays = [s.audio for s in output.audio_streams]
        
        # Run ASR (parallel if multiple streams)
        if len(audio_arrays) == 1:
            asr_results = [self.asr.transcribe(audio_arrays[0])]
        else:
            asr_results = self.asr.transcribe_parallel(audio_arrays)
        
        # Build TranscriptionResults with speaker metadata
        for stream, asr_result in zip(output.audio_streams, asr_results):
            role_str = self.state_store.get_role(stream.speaker_id)
            try:
                role = UserRole(role_str)
            except ValueError:
                role = UserRole.UNKNOWN
            
            results.append(TranscriptionResult(
                text=asr_result["text"],
                speaker_id=stream.speaker_id,
                speaker_role=role,
                confidence=asr_result["confidence"],
                speaker_confidence=stream.speaker_confidence,
                timestamp=output.timestamp,
                language=asr_result.get("language", "en"),
                emotion=asr_result.get("emotion", "neutral")
            ))
        
        return results
    
    def _execute_decision(self, decision: ArbitrationDecision) -> str:
        """Execute an arbitration decision."""
        self.exec_queue.enqueue(decision, priority=1)
        return self.exec_queue.execute_next() or "No action taken"


if __name__ == "__main__":
    # Quick smoke test with mock data
    from src.common.models import AudioStream
    import numpy as np
    
    logging.basicConfig(level=logging.INFO)
    
    config = Config()
    pipeline = CanaryPipeline(config)
    
    # Create mock pipeline output
    mock_output = PipelineOutput(
        mode=PipelineMode.MODE_A,
        timestamp=time.time(),
        audio_streams=[
            AudioStream(
                stream_id=0,
                audio=np.zeros(16000 * 3, dtype=np.float32),
                speaker_id="hemang",
                speaker_confidence=0.95,
                duration_seconds=3.0
            )
        ],
        scene_complexity_score=0.2,
        vad_confidence=0.95,
        wakeword_confidence=0.88,
    )
    
    result = pipeline.process(mock_output)
    print(result)
