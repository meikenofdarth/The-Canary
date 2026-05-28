"""ASR Engine — sherpa-onnx + SenseVoiceSmall.

Converts separated audio waveforms into text transcriptions.
Supports parallel decoding of multiple streams via multiprocessing.

SenseVoiceSmall capabilities:
- 50+ languages (including English, Hindi, Chinese, Japanese, Korean)
- Emotion detection (happy, sad, angry, neutral)
- Inverse text normalization (ITN)
- ~70ms for 10s of audio on CPU (17x real-time)
"""
import logging
import os
import time
import numpy as np
from typing import Optional
from multiprocessing import Process, Queue

import sherpa_onnx

logger = logging.getLogger(__name__)


class ASREngine:
    """Automatic Speech Recognition engine using SenseVoiceSmall via sherpa-onnx."""
    
    def __init__(self, model_path: str, num_threads: int = 2):
        """Initialize the ASR recognizer.
        
        Args:
            model_path: Path to SenseVoiceSmall ONNX model directory.
                        Should contain model.int8.onnx and tokens.txt
            num_threads: Number of threads for ONNX Runtime inference
        """
        self.model_path = model_path
        self.num_threads = num_threads
        self.recognizer = None
        self._init_recognizer()
    
    def _init_recognizer(self):
        """Set up the sherpa-onnx offline recognizer with SenseVoice."""
        model_file = os.path.join(self.model_path, "model.int8.onnx")
        tokens_file = os.path.join(self.model_path, "tokens.txt")
        
        if not os.path.exists(model_file):
            logger.error("Model file not found: %s", model_file)
            raise FileNotFoundError(
                f"SenseVoiceSmall model not found at {model_file}. "
                f"Download it from sherpa-onnx releases."
            )
        
        if not os.path.exists(tokens_file):
            logger.error("Tokens file not found: %s", tokens_file)
            raise FileNotFoundError(
                f"Tokens file not found at {tokens_file}."
            )
        
        logger.info("Loading SenseVoiceSmall from %s ...", self.model_path)
        start = time.time()
        
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model_file,
            tokens=tokens_file,
            num_threads=self.num_threads,
            use_itn=True,
            debug=False,
        )
        
        elapsed = time.time() - start
        logger.info("SenseVoiceSmall loaded in %.2fs", elapsed)
    
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        """Transcribe a single audio stream.
        
        Args:
            audio: float32 numpy array, mono, 16kHz
            sample_rate: Sample rate (must be 16000)
            
        Returns:
            dict with keys: text, confidence, language, emotion
        """
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        if sample_rate != 16000:
            logger.warning("Expected 16kHz, got %d. Resampling not implemented.", sample_rate)
        
        if self.recognizer is None:
            logger.error("Recognizer not initialized")
            return {
                "text": "[ASR not initialized]",
                "confidence": 0.0,
                "language": "unknown",
                "emotion": "neutral"
            }
        
        start = time.time()
        
        # Create stream and feed audio
        stream = self.recognizer.create_stream()
        stream.accept_waveform(sample_rate, audio)
        self.recognizer.decode_stream(stream)
        
        result = stream.result
        text = result.text.strip()
        language = self._parse_tag(result.lang)
        emotion = self._parse_tag(result.emotion).lower()
        event = self._parse_tag(result.event).lower()
        
        elapsed = time.time() - start
        duration = len(audio) / sample_rate
        rtf = elapsed / duration if duration > 0 else 0
        
        logger.info(
            "Transcribed %.1fs audio in %.3fs (RTF=%.3f) [%s/%s]: \"%s\"",
            duration, elapsed, rtf, language, emotion, text[:80]
        )
        
        return {
            "text": text,
            "confidence": self._estimate_confidence(text, duration),
            "language": language,
            "emotion": emotion,
            "event": event,
            "rtf": rtf,
            "duration": duration,
        }
    
    def transcribe_parallel(
        self, streams: list[np.ndarray], sample_rate: int = 16000
    ) -> list[dict]:
        """Transcribe multiple audio streams.
        
        sherpa-onnx's OfflineRecognizer supports batch decoding natively
        via decode_streams(), which is more efficient than multiprocessing
        for this use case since it handles threading internally.
        
        Args:
            streams: List of float32 numpy arrays (one per speaker)
            sample_rate: Sample rate for all streams
            
        Returns:
            List of transcription result dicts
        """
        if not streams:
            return []
        
        if len(streams) == 1:
            return [self.transcribe(streams[0], sample_rate)]
        
        if self.recognizer is None:
            return [self.transcribe(s, sample_rate) for s in streams]
        
        start = time.time()
        
        # Create streams and feed audio
        onnx_streams = []
        for audio in streams:
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)
            s = self.recognizer.create_stream()
            s.accept_waveform(sample_rate, audio)
            onnx_streams.append(s)
        
        # Batch decode — sherpa-onnx handles parallelism internally
        self.recognizer.decode_streams(onnx_streams)
        
        elapsed = time.time() - start
        
        # Collect results
        results = []
        for i, (s, audio) in enumerate(zip(onnx_streams, streams)):
            result = s.result
            text = result.text.strip()
            language = self._parse_tag(result.lang)
            emotion = self._parse_tag(result.emotion).lower()
            event = self._parse_tag(result.event).lower()
            duration = len(audio) / sample_rate
            
            results.append({
                "text": text,
                "confidence": self._estimate_confidence(text, duration),
                "language": language,
                "emotion": emotion,
                "event": event,
                "rtf": elapsed / duration if duration > 0 else 0,
                "duration": duration,
            })
            logger.info("Stream %d: \"%s\" (%s, %s)", i, text[:60], language, emotion)
        
        logger.info(
            "Parallel transcription of %d streams in %.3fs", 
            len(streams), elapsed
        )
        
        return results
    
    @staticmethod
    def _parse_tag(tag_value: str) -> str:
        """Strip <| |> wrapper from SenseVoice tag attributes.
        
        sherpa-onnx result objects return tags like '<|en|>', '<|NEUTRAL|>'.
        This extracts the inner value.
        
        Args:
            tag_value: Raw tag string, e.g. '<|en|>' or '<|HAPPY|>'
            
        Returns:
            Clean string, e.g. 'en' or 'HAPPY'
        """
        if tag_value and tag_value.startswith('<|') and tag_value.endswith('|>'):
            return tag_value[2:-2]
        return tag_value or "unknown"
    
    def _estimate_confidence(self, text: str, duration: float) -> float:
        """Estimate transcription confidence.
        
        SenseVoice doesn't output per-token confidence directly,
        so we use heuristics:
        - Empty text = 0.0
        - Very short text for long audio = low confidence
        - Normal text density = high confidence
        """
        if not text or text == "[ASR not initialized]":
            return 0.0
        
        # Words per second heuristic (normal speech: 2-3 words/sec)
        word_count = len(text.split())
        if duration > 0:
            wps = word_count / duration
            if wps < 0.5:
                return 0.4  # Suspiciously few words
            elif wps > 6:
                return 0.5  # Suspiciously many words
            else:
                return min(0.95, 0.7 + (wps / 10))  # Normal range
        
        return 0.7  # Default
