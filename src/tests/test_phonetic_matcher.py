
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from computation.intelligence.phonetic_matcher import (
    phonetic_code, nw_distance, match_command, best_intent, _zero_pairs,
)

COMMANDS = [
    "play some music",
    "stop the music",
    "what is the weather",
    "set a timer",
    "turn on the lights",
    "tell me the news",
]

COMMAND_MAP = {
    "play some music":     "SONGS",
    "stop the music":      "SONGS",
    "what is the weather": "WEATHER",
    "tell me the news":    "NEWS",
}


def test_lisp_zero_cost_substitution():
    pairs = _zero_pairs("lisp", None)
    assert nw_distance(phonetic_code("sing"), phonetic_code("thing"), pairs) == 0.0


def test_lisped_command_matches_with_profile():
    lisped = "play thome muthic"

    default = match_command(lisped, COMMANDS, profile="default")
    lisp = match_command(lisped, COMMANDS, profile="lisp")

    print(f"\n  default -> {default['command']} (d={default['distance']})")
    print(f"  lisp    -> {lisp['command']} (d={lisp['distance']})")

    assert lisp["command"] == "play some music"
    assert lisp["matched"] is True
    assert lisp["distance"] < default["distance"]


def test_intent_mapping():
    res = best_intent("play thome muthic", COMMAND_MAP, profile="lisp")
    assert res["intent"] == "SONGS"


def test_clean_transcript_unaffected():
    res = match_command("what is the weather", COMMANDS, profile="default")
    assert res["command"] == "what is the weather"
    assert res["distance"] == 0.0


def test_no_false_match_on_unrelated_speech():
    res = match_command("i think we should grab lunch later", COMMANDS, profile="lisp")
    print(f"\n  chatter -> {res['command']} (d={res['distance']}, matched={res['matched']})")
    assert res["matched"] is False
