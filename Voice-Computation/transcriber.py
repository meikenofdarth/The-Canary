import numpy as np
import time
import re
from pathlib import Path


class Transcriber:

    def __init__(self, model_name: str = "tiny", device: str = "cpu"):
        self._model_name = model_name
        self._device = device
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        print("  [ASR] Loading Whisper model...")
        import whisper
        t0 = time.time()
        self._model = whisper.load_model(self._model_name, device=self._device)
        print(f"  [ASR] Model loaded in {time.time()-t0:.1f}s")

    def transcribe(self, audio: np.ndarray, sr: int = 16000) -> dict:
        self._load_model()
        t0 = time.time()
        result = self._model.transcribe(
            audio, language="en", task="transcribe", fp16=False,
        )
        elapsed = time.time() - t0
        text = result.get("text", "").strip()
        segments = result.get("segments", [])
        duration = len(audio) / sr
        rtf = elapsed / duration if duration > 0 else 0

        print(f"  [ASR] Transcribed {duration:.1f}s in {elapsed:.2f}s "
              f"(RTF={rtf:.2f})")

        words = text.split()
        word_confidences = []
        for seg in segments:
            for w in seg.get("words", []):
                word_confidences.append(w.get("probability", 0.5))

        avg_confidence = float(np.mean(word_confidences)) if word_confidences else 0.5

        return {
            "text": text,
            "words": words,
            "word_count": len(words),
            "confidence": avg_confidence,
            "language": result.get("language", "en"),
            "duration": duration,
            "rtf": rtf,
            "segments": segments,
        }


def detect_wake_word(transcript: dict, wake_word: str = "canary") -> dict:
    text = transcript.get("text", "").lower()
    words = [w.lower().strip(".,!?;:'\"()[]{}") for w in transcript.get("words", [])]

    found_exact = wake_word in text
    found_word = wake_word in words

    any_partial = any(
        wake_word in w or w in wake_word or
        (len(w) > 3 and len(wake_word) > 3 and
         (w.startswith(wake_word[:3]) or wake_word.startswith(w[:3])))
        for w in words
    )

    text_clean = re.sub(r'[^\w\s]', '', text)
    found_clean = wake_word in text_clean.split()

    detected = found_exact or found_word or found_clean or any_partial

    if detected:
        locations = [i for i, w in enumerate(words) if wake_word in w or w in wake_word]
    else:
        locations = []

    return {
        "detected": detected,
        "wake_word": wake_word,
        "found_exact": found_exact,
        "found_word": found_word,
        "found_clean": found_clean,
        "any_partial": any_partial,
        "word_locations": locations,
        "confidence": transcript.get("confidence", 0.0),
    }


def save_transcript(transcript: dict, path: Path) -> Path:
    text = transcript.get("text", "")
    with open(path, "w") as f:
        f.write(text)
        f.write("\n")
    return path
