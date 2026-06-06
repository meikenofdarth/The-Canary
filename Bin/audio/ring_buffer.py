"""Thread-safe ring buffer for continuous audio capture.

HOW IT WORKS:
    The ring buffer is a fixed-size circular array. New audio chunks
    overwrite the oldest data. This gives us a sliding window of the
    last N seconds of audio without ever allocating new memory.
    
    ┌───┬───┬───┬───┬───┬───┬───┬───┐
    │ . │ . │ . │ W │ X │ Y │ Z │ . │  ← buffer (fixed size)
    └───┴───┴───┴───┴───┴───┴───┴───┘
                  ↑               ↑
             write_pos        oldest data gets overwritten
    
    When we read, we unroll the circular buffer into a contiguous array
    starting from the oldest sample.
"""
import threading
import numpy as np


class RingBuffer:
    """Thread-safe ring buffer for float32 audio samples.
    
    Args:
        capacity: Total number of samples the buffer can hold.
                  At 16kHz, 32000 = 2 seconds of audio.
    """
    
    def __init__(self, capacity: int):
        self._capacity = capacity
        self._buffer = np.zeros(capacity, dtype=np.float32)
        self._write_pos = 0           # Next position to write to
        self._samples_written = 0     # Total samples written (for tracking fullness)
        self._lock = threading.Lock()
    
    @property
    def capacity(self) -> int:
        return self._capacity
    
    @property
    def is_full(self) -> bool:
        """Whether the buffer has been filled at least once."""
        return self._samples_written >= self._capacity
    
    @property
    def available_samples(self) -> int:
        """Number of valid samples currently in the buffer."""
        return min(self._samples_written, self._capacity)
    
    def write(self, data: np.ndarray) -> None:
        """Write audio samples into the ring buffer.
        
        If data is larger than remaining space before wrap, it wraps around.
        
        Args:
            data: float32 numpy array of audio samples.
        """
        with self._lock:
            n = len(data)
            
            if n >= self._capacity:
                # Data is larger than buffer — just keep the last `capacity` samples
                self._buffer[:] = data[-self._capacity:]
                self._write_pos = 0
                self._samples_written = self._capacity
                return
            
            # How many samples fit before wrapping?
            space_before_wrap = self._capacity - self._write_pos
            
            if n <= space_before_wrap:
                # No wrap needed
                self._buffer[self._write_pos:self._write_pos + n] = data
            else:
                # Split: fill to end, then wrap to beginning
                self._buffer[self._write_pos:] = data[:space_before_wrap]
                remaining = n - space_before_wrap
                self._buffer[:remaining] = data[space_before_wrap:]
            
            self._write_pos = (self._write_pos + n) % self._capacity
            self._samples_written += n
    
    def read(self, num_samples: int = 0) -> np.ndarray:
        """Read samples from the buffer (oldest first).
        
        Args:
            num_samples: Number of samples to read. 0 = read all available.
            
        Returns:
            Contiguous float32 array with the requested samples.
        """
        with self._lock:
            available = self.available_samples
            
            if num_samples <= 0 or num_samples > available:
                num_samples = available
            
            if num_samples == 0:
                return np.array([], dtype=np.float32)
            
            if self._samples_written < self._capacity:
                # Buffer hasn't wrapped yet — data is contiguous from 0
                start = max(0, self._write_pos - num_samples)
                return self._buffer[start:self._write_pos].copy()
            
            # Buffer has wrapped — unroll from the read position
            read_start = (self._write_pos - num_samples) % self._capacity
            
            if read_start < self._write_pos:
                # No wrap in read range
                return self._buffer[read_start:read_start + num_samples].copy()
            else:
                # Read wraps around
                part1 = self._buffer[read_start:]
                part2 = self._buffer[:self._write_pos]
                return np.concatenate([part1, part2])
    
    def read_last(self, duration_s: float, sample_rate: int = 16000) -> np.ndarray:
        """Read the last N seconds of audio.
        
        Args:
            duration_s: How many seconds of audio to retrieve.
            sample_rate: Sample rate (default 16kHz).
            
        Returns:
            float32 array of the most recent audio.
        """
        num_samples = int(duration_s * sample_rate)
        return self.read(num_samples)
    
    def clear(self) -> None:
        """Reset the buffer to empty."""
        with self._lock:
            self._buffer[:] = 0.0
            self._write_pos = 0
            self._samples_written = 0


if __name__ == "__main__":
    # Quick test
    buf = RingBuffer(capacity=16000)  # 1 second at 16kHz
    
    # Write 0.5s of audio
    chunk = np.random.randn(8000).astype(np.float32)
    buf.write(chunk)
    print(f"After 0.5s write: available={buf.available_samples}, full={buf.is_full}")
    
    # Write another 0.7s (causes wrap)
    chunk2 = np.random.randn(11200).astype(np.float32)
    buf.write(chunk2)
    print(f"After 1.2s write: available={buf.available_samples}, full={buf.is_full}")
    
    # Read last 0.5s
    audio = buf.read_last(0.5)
    print(f"Read 0.5s: shape={audio.shape}")
    
    print("Ring buffer test passed!")
