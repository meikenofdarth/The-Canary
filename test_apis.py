import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from execution.queue import process_arbitration

def test_weather():
    print("\n--- Testing Weather API ---")
    payload = {
        "route": "EXECUTE",
        "active_command": {
            "speaker_id": "speaker_1",
            "identity": "Sanchit",
            "known_user": True,
            "domain": "WEATHER",
            "transcript": "What's the weather today?",
            "wakeword": True,
            "type": "COMMAND"
        },
        "all_speakers": [
            {
                "speaker_id": "speaker_1",
                "identity": "Sanchit",
                "known_user": True,
                "domain": "WEATHER",
                "wakeword": True
            }
        ]
    }
    process_arbitration(payload)

def test_news():
    print("\n--- Testing News API ---")
    payload = {
        "route": "EXECUTE",
        "active_command": {
            "speaker_id": "speaker_2",
            "identity": "Hemang Seth",
            "known_user": True,
            "domain": "NEWS",
            "transcript": "Read me the news.",
            "wakeword": True,
            "type": "COMMAND"
        },
        "all_speakers": [
            {
                "speaker_id": "speaker_2",
                "identity": "Hemang Seth",
                "known_user": True,
                "domain": "NEWS",
                "wakeword": True
            }
        ]
    }
    process_arbitration(payload)

def test_music():
    print("\n--- Testing Music API ---")
    payload = {
        "route": "EXECUTE",
        "active_command": {
            "speaker_id": "speaker_1",
            "identity": "Sanchit",
            "known_user": True,
            "domain": "SONGS",
            "transcript": "Play a song.",
            "wakeword": True,
            "type": "COMMAND"
        },
        "all_speakers": [
            {
                "speaker_id": "speaker_1",
                "identity": "Sanchit",
                "known_user": True,
                "domain": "SONGS",
                "wakeword": True
            }
        ]
    }
    process_arbitration(payload)
    
def test_conflict():
    print("\n--- Testing Known-User Conflict ---")
    payload = {
        "route": "EXECUTE",
        "conflict": {
            "detected": True
        },
        "active_command": {
            "speaker_id": "speaker_1",
            "identity": "Sanchit",
            "known_user": True,
            "domain": "SONGS"
        },
        "all_speakers": [
            {
                "speaker_id": "speaker_1",
                "identity": "Sanchit",
                "known_user": True,
                "domain": "SONGS",
                "transcript": "Play some jazz.",
                "wakeword": True,
                "type": "COMMAND"
            },
            {
                "speaker_id": "speaker_2",
                "identity": "Hemang Seth",
                "known_user": True,
                "domain": "WEATHER",
                "transcript": "What's the weather?",
                "wakeword": True,
                "type": "COMMAND"
            }
        ]
    }
    process_arbitration(payload)

if __name__ == "__main__":
    import time
    test_weather()
    time.sleep(2)
    test_news()
    time.sleep(2)
    test_music()
    time.sleep(2)
    test_conflict()
