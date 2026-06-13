import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from execution.queue import process_arbitration

def test_weather():
    print("\n--- Testing Weather API ---")
    payload = {
        "route": "EXECUTE",
        "arbitration": {
            "winner": "speaker_1",
            "speakers": [
                {
                    "id": "speaker_1",
                    "identity": "Sanchit",
                    "known_user": True,
                    "intent": "WEATHER",
                    "transcript": "What's the weather today?",
                    "wakeword": True,
                    "type": "COMMAND"
                }
            ]
        }
    }
    process_arbitration(payload)

def test_news():
    print("\n--- Testing News API ---")
    payload = {
        "route": "EXECUTE",
        "arbitration": {
            "winner": "speaker_2",
            "speakers": [
                {
                    "id": "speaker_2",
                    "identity": "Hemang Seth",
                    "known_user": True,
                    "intent": "NEWS",
                    "transcript": "Read me the news.",
                    "wakeword": True,
                    "type": "COMMAND"
                }
            ]
        }
    }
    process_arbitration(payload)

def test_music():
    print("\n--- Testing Music API ---")
    payload = {
        "route": "EXECUTE",
        "arbitration": {
            "winner": "speaker_1",
            "speakers": [
                {
                    "id": "speaker_1",
                    "identity": "Sanchit",
                    "known_user": True,
                    "intent": "PLAY_MEDIA",
                    "transcript": "Play a song.",
                    "wakeword": True,
                    "type": "COMMAND"
                }
            ]
        }
    }
    process_arbitration(payload)
    
def test_conflict():
    print("\n--- Testing Known-User Conflict ---")
    payload = {
        "route": "EXECUTE", # Note: the override happens inside process_arbitration!
        "arbitration": {
            "winner": "speaker_1",
            "speakers": [
                {
                    "id": "speaker_1",
                    "identity": "Sanchit",
                    "known_user": True,
                    "intent": "PLAY_MEDIA",
                    "transcript": "Play some jazz.",
                    "wakeword": True,
                    "type": "COMMAND"
                },
                {
                    "id": "speaker_2",
                    "identity": "Hemang Seth",
                    "known_user": True,
                    "intent": "WEATHER",
                    "transcript": "What's the weather?",
                    "wakeword": True,
                    "type": "COMMAND"
                }
            ]
        }
    }
    process_arbitration(payload)

if __name__ == "__main__":
    test_weather()
    test_news()
    test_music()
    test_conflict()
