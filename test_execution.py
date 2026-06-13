import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

import execution.queue
executed_calls = []

def mock_execute_intent(domain, transcript, profile, entities, polarity="POSITIVE"):
    executed_calls.append((domain, transcript, profile, entities, polarity))

# Replace real execute_intent with mock
execution.queue.execute_intent = mock_execute_intent

from execution.queue import process_arbitration

def test_single_execute():
    global executed_calls
    executed_calls = []
    
    payload = {
        "route": "EXECUTE",
        "active_command": {
            "speaker_id": "speaker_2",
            "identity": "Hemang Seth",
            "known_user": True,
            "transcript": "Raju stop playing the music.",
            "domain": "SONGS",
            "polarity": "NEGATIVE",
            "entities": {}
        }
    }
    
    process_arbitration(payload)
    
    assert len(executed_calls) == 1
    assert executed_calls[0] == ("SONGS", "Raju stop playing the music.", {"location": "New York", "favorite_music_genre": "Rock"}, {}, "NEGATIVE")
    print("✓ test_single_execute passed")

def test_sequential_execute():
    global executed_calls
    executed_calls = []
    
    payload = {
        "route": "SEQUENTIAL",
        "sequential_queue": [
            {
                "speaker_id": "speaker_1",
                "identity": "Sanchit",
                "known_user": True,
                "transcript": "Raju, tell me the weather in Luxembourg.",
                "domain": "WEATHER",
                "polarity": "POSITIVE",
                "entities": {"location": "Luxembourg"}
            },
            {
                "speaker_id": "speaker_2",
                "identity": "Hemang Seth",
                "known_user": True,
                "transcript": "Raju stop playing the music.",
                "domain": "SONGS",
                "polarity": "NEGATIVE",
                "entities": {}
            }
        ]
    }
    
    process_arbitration(payload)
    
    assert len(executed_calls) == 2
    assert executed_calls[0] == ("WEATHER", "Raju, tell me the weather in Luxembourg.", {"location": "Bengaluru", "favorite_music_genre": "Jazz"}, {"location": "Luxembourg"}, "POSITIVE")
    assert executed_calls[1] == ("SONGS", "Raju stop playing the music.", {"location": "New York", "favorite_music_genre": "Rock"}, {}, "NEGATIVE")
    print("✓ test_sequential_execute passed")

if __name__ == "__main__":
    print("Running execution engine tests...")
    test_single_execute()
    test_sequential_execute()
    print("All tests passed!")
