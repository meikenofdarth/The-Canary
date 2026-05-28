"""Quick ASR smoke test.

Run from project root:
    source .venv/bin/activate
    python3 -m tests.test_asr

Tests:
1. Model loads successfully
2. Transcribes a generated test tone (should output empty/noise)
3. Transcribes a .wav file if provided
"""
import sys
import os
import time
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.asr.engine import ASREngine


def generate_speech_like_audio(duration: float = 3.0, sr: int = 16000) -> np.ndarray:
    """Generate a simple test signal (not real speech, just for API testing)."""
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    # Mix of frequencies to simulate voice-like signal
    audio = (
        0.3 * np.sin(2 * np.pi * 200 * t) +  # fundamental
        0.2 * np.sin(2 * np.pi * 400 * t) +  # harmonic
        0.1 * np.sin(2 * np.pi * 800 * t) +  # harmonic
        0.05 * np.random.randn(len(t))         # noise
    ).astype(np.float32)
    return audio


def test_model_loading():
    """Test 1: Model loads without errors."""
    print("=" * 60)
    print("TEST 1: Model Loading")
    print("=" * 60)
    
    model_path = "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
    
    if not os.path.exists(model_path):
        print(f"❌ Model not found at: {model_path}")
        print("   Download with:")
        print("   curl -L -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2")
        print("   tar xvf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2 -C models/")
        return None
    
    start = time.time()
    engine = ASREngine(model_path=model_path, num_threads=2)
    elapsed = time.time() - start
    
    print(f"✅ Model loaded in {elapsed:.2f}s")
    print(f"   Recognizer: {engine.recognizer is not None}")
    return engine


def test_transcribe_synthetic(engine: ASREngine):
    """Test 2: Transcribe synthetic audio (should produce some output)."""
    print("\n" + "=" * 60)
    print("TEST 2: Transcribe Synthetic Audio")
    print("=" * 60)
    
    audio = generate_speech_like_audio(duration=3.0)
    print(f"   Audio: {audio.shape}, dtype={audio.dtype}, dur={len(audio)/16000:.1f}s")
    
    result = engine.transcribe(audio)
    
    print(f"   Text: \"{result['text']}\"")
    print(f"   Language: {result['language']}")
    print(f"   Emotion: {result['emotion']}")
    print(f"   Confidence: {result['confidence']:.2f}")
    print(f"   RTF: {result['rtf']:.4f}")
    print(f"✅ Transcription completed without errors")


def test_transcribe_wav(engine: ASREngine, wav_path: str):
    """Test 3: Transcribe a real .wav file."""
    print("\n" + "=" * 60)
    print(f"TEST 3: Transcribe WAV File: {wav_path}")
    print("=" * 60)
    
    import soundfile as sf
    audio, sr = sf.read(wav_path, dtype='float32')
    
    # Convert to mono if stereo
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)
    
    print(f"   Audio: {audio.shape}, sr={sr}, dur={len(audio)/sr:.1f}s")
    
    # Resample to 16kHz if needed
    if sr != 16000:
        print(f"   ⚠️  Sample rate is {sr}, not 16000. Results may be poor.")
    
    result = engine.transcribe(audio, sample_rate=sr)
    
    print(f"   Text: \"{result['text']}\"")
    print(f"   Language: {result['language']}")
    print(f"   Emotion: {result['emotion']}")
    print(f"   Confidence: {result['confidence']:.2f}")
    print(f"   RTF: {result['rtf']:.4f}")
    print(f"✅ WAV transcription completed")


def test_parallel_transcription(engine: ASREngine):
    """Test 4: Parallel transcription of 2 streams."""
    print("\n" + "=" * 60)
    print("TEST 4: Parallel Transcription (2 streams)")
    print("=" * 60)
    
    audio_1 = generate_speech_like_audio(duration=2.0)
    audio_2 = generate_speech_like_audio(duration=3.0)
    
    print(f"   Stream 1: {audio_1.shape}, dur={len(audio_1)/16000:.1f}s")
    print(f"   Stream 2: {audio_2.shape}, dur={len(audio_2)/16000:.1f}s")
    
    results = engine.transcribe_parallel([audio_1, audio_2])
    
    for i, r in enumerate(results):
        print(f"   Stream {i}: \"{r['text']}\" (lang={r['language']}, emotion={r['emotion']})")
    
    print(f"✅ Parallel transcription of {len(results)} streams completed")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
    
    print("🐤 The Canary — ASR Engine Test Suite")
    print()
    
    # Test 1: Load model
    engine = test_model_loading()
    if engine is None:
        sys.exit(1)
    
    # Test 2: Synthetic audio
    test_transcribe_synthetic(engine)
    
    # Test 3: WAV file (if provided as argument)
    if len(sys.argv) > 1:
        wav_path = sys.argv[1]
        if os.path.exists(wav_path):
            test_transcribe_wav(engine, wav_path)
        else:
            print(f"\n⚠️  WAV file not found: {wav_path}")
    else:
        print("\n💡 Tip: Pass a .wav file as argument to test real speech:")
        print("   python3 -m tests.test_asr path/to/audio.wav")
    
    # Test 4: Parallel transcription
    test_parallel_transcription(engine)
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
