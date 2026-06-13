import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from execution.queue import process_arbitration
import io
import contextlib

def test_single_execute():
    payload = {
        "route": "EXECUTE",
        "arbitration": {
            "winner": "speaker_2",
            "speakers": [
                {
                    "id": "speaker_1",
                    "intent": "GREETING",
                    "transcript": "Hello there.",
                    "wakeword": False,
                    "type": "UNKNOWN"
                },
                {
                    "id": "speaker_2",
                    "intent": "DEVICE_ON",
                    "transcript": "Turn on the lights please.",
                    "wakeword": True,
                    "type": "COMMAND"
                }
            ]
        }
    }
    
    # Capture stdout to verify
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        process_arbitration(payload)
    output = f.getvalue()
    
    assert "Single Execution for speaker_2" in output
    assert "Executing: Turn lights ON" in output
    print("✓ test_single_execute passed")

def test_sequential_execute():
    payload = {
        "route": "SEQUENTIAL",
        "arbitration": {
            "speakers": [
                {
                    "id": "speaker_1",
                    "intent": "DEVICE_ON",
                    "transcript": "Turn on the TV.",
                    "wakeword": True,
                    "type": "COMMAND"
                },
                {
                    "id": "speaker_2",
                    "intent": "PLAY_MEDIA",
                    "transcript": "Play some jazz music.",
                    "wakeword": True,
                    "type": "COMMAND"
                }
            ]
        }
    }
    
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        process_arbitration(payload)
    output = f.getvalue()
    
    assert "Sequential Execution for 2 commands" in output
    assert "Executing: Turn TV ON" in output
    assert "Executing: Playing music (Play some jazz music.)" in output
    print("✓ test_sequential_execute passed")

if __name__ == "__main__":
    print("Running execution engine tests...")
    test_single_execute()
    test_sequential_execute()
    print("All tests passed!")
