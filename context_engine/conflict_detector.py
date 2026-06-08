"""
context_engine/conflict_detector.py
=====================================
Detects conflicting commands between multiple speakers.

A conflict occurs when two speakers both issued wakeword commands
and their action words are antonyms (PLAY ↔ STOP, ON ↔ OFF, etc.).
No ML — pure keyword antonym matching.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
#  ANTONYM PAIRS
#  (set_of_action_A_words,  set_of_action_B_words)
#  Conflict = one stream hits set_A, another stream hits set_B
# ─────────────────────────────────────────────────────────────────────────────
_ANTONYM_PAIRS: list[tuple[frozenset, frozenset]] = [
    # Media playback
    (
        frozenset({"play", "resume", "unpause", "start playing", "continue"}),
        frozenset({"stop", "pause", "halt", "end", "cease"}),
    ),
    # Power state
    (
        frozenset({"turn on", "switch on", "power on", "enable", "activate", "start"}),
        frozenset({"turn off", "switch off", "power off", "disable", "deactivate", "shut down"}),
    ),
    # Volume / brightness direction
    (
        frozenset({"louder", "up", "increase", "raise", "brighter", "higher", "more",
                   "volume up", "turn up"}),
        frozenset({"quieter", "down", "decrease", "lower", "dimmer", "less", "reduce",
                   "volume down", "turn down"}),
    ),
    # Locks
    (
        frozenset({"lock", "secure", "bolt"}),
        frozenset({"unlock", "unsecure", "unbolt"}),
    ),
    # Doors / garage / blinds
    (
        frozenset({"open", "raise", "lift", "roll up"}),
        frozenset({"close", "shut", "lower", "roll down"}),
    ),
    # Security alarm
    (
        frozenset({"arm", "set alarm", "activate alarm", "enable alarm", "set the alarm"}),
        frozenset({"disarm", "disable alarm", "deactivate alarm", "cancel alarm",
                   "turn off alarm", "turn off the alarm"}),
    ),
    # Mute state
    (
        frozenset({"mute", "silence", "quiet", "silent"}),
        frozenset({"unmute", "unsilence", "audio on", "sound on"}),
    ),
    # Heating vs cooling
    (
        frozenset({"heat", "warmer", "hotter", "heater", "heating", "warm up"}),
        frozenset({"cool", "cooler", "colder", "ac", "air conditioning", "cool down"}),
    ),
    # Skip direction (media)
    (
        frozenset({"next", "skip", "forward", "fast forward"}),
        frozenset({"previous", "back", "rewind", "go back"}),
    ),
    # Record vs delete
    (
        frozenset({"record", "save", "keep", "capture"}),
        frozenset({"delete", "remove", "discard", "erase"}),
    ),
]


def detect_conflict(speaker_data: list[dict]) -> dict:
    """
    Check whether multiple wakeword-command speakers issued opposing commands.

    Parameters
    ----------
    speaker_data : list of per-speaker dicts containing at minimum:
        {
            "transcript": str,
            "wakeword":   bool,
            "type":       str,   # utterance type from utterance_analyzer
        }

    Returns
    -------
    {
        "conflict":      bool,
        "conflict_pair": [str, str] | None   # the conflicting action words
    }
    """
    # Only speakers who said the wakeword AND issued a command are relevant
    active = [
        s for s in speaker_data
        if s.get("wakeword") and s.get("type") == "COMMAND"
    ]

    if len(active) < 2:
        return {"conflict": False, "conflict_pair": None}

    texts = [s.get("transcript", "").lower() for s in active]

    for set_a, set_b in _ANTONYM_PAIRS:
        # Which texts contain words from set_a / set_b?
        texts_a = [t for t in texts if any(w in t for w in set_a)]
        texts_b = [t for t in texts if any(w in t for w in set_b)]

        if texts_a and texts_b:
            # Surface the actual matched words for reporting
            word_a = next(w for w in set_a if any(w in t for t in texts_a))
            word_b = next(w for w in set_b if any(w in t for t in texts_b))
            return {"conflict": True, "conflict_pair": [word_a, word_b]}

    return {"conflict": False, "conflict_pair": None}
