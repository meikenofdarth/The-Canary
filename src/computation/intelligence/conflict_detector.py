
from __future__ import annotations

_ANTONYM_PAIRS: list[tuple[frozenset, frozenset]] = [
    (
        frozenset({"play", "resume", "unpause", "start playing", "continue"}),
        frozenset({"stop", "pause", "halt", "end", "cease"}),
    ),
    (
        frozenset({"turn on", "switch on", "power on", "enable", "activate", "start"}),
        frozenset({"turn off", "switch off", "power off", "disable", "deactivate", "shut down"}),
    ),
    (
        frozenset({"louder", "up", "increase", "raise", "brighter", "higher", "more",
                   "volume up", "turn up"}),
        frozenset({"quieter", "down", "decrease", "lower", "dimmer", "less", "reduce",
                   "volume down", "turn down"}),
    ),
    (
        frozenset({"lock", "secure", "bolt"}),
        frozenset({"unlock", "unsecure", "unbolt"}),
    ),
    (
        frozenset({"open", "raise", "lift", "roll up"}),
        frozenset({"close", "shut", "lower", "roll down"}),
    ),
    (
        frozenset({"arm", "set alarm", "activate alarm", "enable alarm", "set the alarm"}),
        frozenset({"disarm", "disable alarm", "deactivate alarm", "cancel alarm",
                   "turn off alarm", "turn off the alarm"}),
    ),
    (
        frozenset({"mute", "silence", "quiet", "silent"}),
        frozenset({"unmute", "unsilence", "audio on", "sound on"}),
    ),
    (
        frozenset({"heat", "warmer", "hotter", "heater", "heating", "warm up"}),
        frozenset({"cool", "cooler", "colder", "ac", "air conditioning", "cool down"}),
    ),
    (
        frozenset({"next", "skip", "forward", "fast forward"}),
        frozenset({"previous", "back", "rewind", "go back"}),
    ),
    (
        frozenset({"record", "save", "keep", "capture"}),
        frozenset({"delete", "remove", "discard", "erase"}),
    ),
]


_OVERRIDE_PHRASES: list[str] = [
    "listen to me",
    "is sent to me",
    "is send to me",
    "sent to me",
    "send to me",
    "don't listen",
    "dont listen",
    "ignore him",
    "ignore her",
    "ignore them",
    "pay attention",
    "focus on me",
    "talk to me",
    "speak to me",
    "stop listening",
    "override",
]


def detect_conflict(speaker_data: list[dict]) -> dict:
    active = [
        s for s in speaker_data
        if s.get("wakeword") and s.get("type") == "COMMAND"
    ]

    if len(active) < 2:
        return {"conflict": False, "conflict_pair": None}

    for s in active:
        txt = s.get("transcript", "").lower()
        matched_override = next((p for p in _OVERRIDE_PHRASES if p in txt), None)
        if matched_override:
            other = next((o for o in active if o["id"] != s["id"]), None)
            other_word = "command"
            if other:
                other_txt = other.get("transcript", "").lower()
                other_override = next((p for p in _OVERRIDE_PHRASES if p in other_txt), None)
                if other_override:
                    other_word = other_override
                else:
                    for word in ["play", "stop", "pause", "turn", "switch", "lock", "unlock", "set", "open", "close", "call", "brew"]:
                        if word in other_txt:
                            other_word = word
                            break
            return {"conflict": True, "conflict_pair": [matched_override, other_word]}

    texts = [s.get("transcript", "").lower() for s in active]

    for set_a, set_b in _ANTONYM_PAIRS:
        texts_a = [t for t in texts if any(w in t for w in set_a)]
        texts_b = [t for t in texts if any(w in t for w in set_b)]

        if texts_a and texts_b:
            word_a = next(w for w in set_a if any(w in t for t in texts_a))
            word_b = next(w for w in set_b if any(w in t for t in texts_b))
            return {"conflict": True, "conflict_pair": [word_a, word_b]}

    return {"conflict": False, "conflict_pair": None}
