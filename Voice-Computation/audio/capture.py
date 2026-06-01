"""Audio capture from microphone using sounddevice.

HOW IT WORKS:
    1. Opens a sounddevice InputStream at 16kHz mono
    2. Every 30ms, the callback fires with a chunk of ~480 samples
    3. The chunk is written to the ring buffer
    4. A separate thread can read from the ring buffer at any time

    The callback runs in a separate C thread (PortAudio), so it's
    NOT blocked by Python's GIL. This is critical for real-time audio.

USAGE:
    capture = AudioCapture(config)
    capture.start()

    # Read the last 1.5 seconds of audio
    audio = capture.get_audio(duration_s=1.5)

    capture.stop()
"""

import logging
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from ..config import VoiceConfig
from .ring_buffer import RingBuffer

logger = logging.getLogger(__name__)


class AudioCapture:
    """Captures audio from the microphone into a ring buffer.

    Args:
        config: VoiceConfig with sample_rate, channels, chunk settings.
    """

    def __init__(self, config: VoiceConfig):
        self.config = config
        self.ring_buffer = RingBuffer(capacity=config.buffer_size_samples)
        self._stream = None
        self._is_running = False
        self._callback_count = 0

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info, status
    ) -> None:
        """Called by sounddevice for every audio chunk.

        This runs in a C thread — keep it FAST. No allocations,
        no logging, no locks beyond the ring buffer's internal lock.
        """
        if status:
            # Overflow/underflow — not much we can do, just note it
            pass

        # indata shape: (frames, channels) — squeeze to mono
        audio = indata[:, 0].astype(np.float32)
        self.ring_buffer.write(audio)
        self._callback_count += 1

    def start(self) -> None:
        """Start capturing audio from the default microphone."""
        if self._is_running:
            logger.warning("AudioCapture already running")
            return

        logger.info(
            "Starting audio capture: %dHz, %dch, %dms chunks",
            self.config.sample_rate,
            self.config.channels,
            self.config.chunk_duration_ms,
        )

        self._stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype="float32",
            blocksize=self.config.chunk_size_samples,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._is_running = True
        logger.info("Audio capture started")

    def stop(self) -> None:
        """Stop capturing audio."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._is_running = False
        logger.info("Audio capture stopped (processed %d chunks)", self._callback_count)

    def get_audio(self, duration_s: float = 0) -> np.ndarray:
        """Get audio from the ring buffer.

        Args:
            duration_s: Seconds of audio to retrieve. 0 = all available.

        Returns:
            float32 numpy array of audio samples.
        """
        if duration_s > 0:
            return self.ring_buffer.read_last(duration_s, self.config.sample_rate)
        return self.ring_buffer.read()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


class FileAudioSource:
    """Reads audio from a WAV file instead of the microphone.

    Useful for testing and demos without a mic. Simulates real-time
    by yielding chunks at the correct rate.

    Args:
        file_path: Path to a WAV file.
        config: VoiceConfig for sample rate and chunk size.
    """

    def __init__(self, file_path: str, config: VoiceConfig):
        self.config = config
        self.file_path = Path(file_path)
        self._audio = None
        self._sample_rate = None
        self._load()

    def _load(self) -> None:
        """Load and resample audio file. Supports WAV, MP3, M4A, OGG, FLAC."""
        ext = self.file_path.suffix.lower()

        if ext in (".mp3", ".m4a", ".ogg", ".flac", ".aac", ".opus"):
            # Use librosa for compressed formats (needs ffmpeg or audioread)
            import librosa

            audio, sr = librosa.load(
                str(self.file_path),
                sr=self.config.sample_rate,
                mono=True,
            )
        else:
            # WAV / AIFF / etc. via soundfile (no ffmpeg needed)
            audio, sr = sf.read(str(self.file_path), dtype="float32")
            # Convert to mono if stereo
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            # Resample if needed
            if sr != self.config.sample_rate:
                import librosa

                audio = librosa.resample(
                    audio, orig_sr=sr, target_sr=self.config.sample_rate
                )
                sr = self.config.sample_rate

        self._audio = audio.astype(np.float32)
        self._sample_rate = self.config.sample_rate
        logger.info(
            "Loaded %s (%s): %.2fs @ %dHz",
            self.file_path.name,
            ext,
            len(self._audio) / self.config.sample_rate,
            self.config.sample_rate,
        )

    def get_audio(self, duration_s: float = 0) -> np.ndarray:
        """Get audio from the loaded file.

        Args:
            duration_s: Seconds of audio. 0 = entire file.
        """
        if duration_s > 0:
            n = int(duration_s * self.config.sample_rate)
            return self._audio[:n].copy()
        return self._audio.copy()

    def iter_chunks(self, chunk_duration_ms: int = 0):
        """Yield audio in chunks (simulates real-time streaming).

        Args:
            chunk_duration_ms: Chunk size in ms. 0 = use config default.

        Yields:
            float32 numpy arrays of chunk_size samples.
        """
        chunk_ms = chunk_duration_ms or self.config.chunk_duration_ms
        chunk_samples = int(self.config.sample_rate * chunk_ms / 1000)

        for i in range(0, len(self._audio), chunk_samples):
            chunk = self._audio[i : i + chunk_samples]
            if len(chunk) < chunk_samples:
                # Pad the last chunk with zeros
                chunk = np.pad(chunk, (0, chunk_samples - len(chunk)))
            yield chunk


if __name__ == "__main__":
    import time

    logging.basicConfig(level=logging.INFO)
    config = VoiceConfig()

    print("Testing AudioCapture (records 3 seconds from mic)...")
    print("Speak into your microphone!")

    with AudioCapture(config) as capture:
        time.sleep(3)
        audio = capture.get_audio(duration_s=2.0)

    print(
        f"Captured audio: shape={audio.shape}, "
        f"duration={len(audio) / config.sample_rate:.2f}s, "
        f"max_amplitude={np.abs(audio).max():.4f}"
    )
    print("Audio capture test passed!")
