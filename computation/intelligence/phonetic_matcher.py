
from __future__ import annotations

import re
from typing import Iterable

from metaphone import doublemetaphone


CONFUSION_PROFILES: dict[str, list[tuple[str, str]]] = {
    "default":    [],
    "lisp":       [("S", "0"), ("S", "T"), ("S", "F"), ("X", "S")],
    "rhotacism":  [("R", "L"), ("R", "W"), ("R", "A")],
    "frontal":    [("T", "0"), ("D", "0"), ("K", "T"), ("G", "T")],
}

MATCH_THRESHOLD = 0.34

_WORD_RE = re.compile(r"[a-z']+")


def phonetic_code(text: str) -> str:
    words = _WORD_RE.findall((text or "").lower())
    return "".join(doublemetaphone(w)[0] for w in words)


def _zero_pairs(profile: str, extra_pairs: Iterable[tuple[str, str]] | None) -> set:
    pairs = set(CONFUSION_PROFILES.get(profile, []))
    if extra_pairs:
        pairs |= {tuple(p) for p in extra_pairs}
    return pairs | {(b, a) for (a, b) in pairs}


def _sub_cost(a: str, b: str, zero_pairs: set) -> float:
    if a == b:
        return 0.0
    if (a, b) in zero_pairs:
        return 0.0
    return 1.0


def nw_distance(a: str, b: str, zero_pairs: set, gap: float = 1.0) -> float:
    la, lb = len(a), len(b)
    if la == 0:
        return lb * gap
    if lb == 0:
        return la * gap

    prev = [j * gap for j in range(lb + 1)]
    for i in range(1, la + 1):
        cur = [i * gap]
        ai = a[i - 1]
        for j in range(1, lb + 1):
            sub = prev[j - 1] + _sub_cost(ai, b[j - 1], zero_pairs)
            dele = prev[j] + gap
            ins = cur[j - 1] + gap
            cur.append(min(sub, dele, ins))
        prev = cur
    return prev[lb]


def match_command(transcript: str,
                   commands: list[str],
                   profile: str = "default",
                   extra_pairs: Iterable[tuple[str, str]] | None = None,
                   threshold: float = MATCH_THRESHOLD) -> dict:
    zero_pairs = _zero_pairs(profile, extra_pairs)
    code_t = phonetic_code(transcript)

    scored = []
    for cmd in commands:
        code_c = phonetic_code(cmd)
        d = nw_distance(code_t, code_c, zero_pairs)
        norm = d / max(1, max(len(code_t), len(code_c)))
        scored.append((cmd, round(float(norm), 4)))

    scored.sort(key=lambda x: x[1])
    if not scored:
        return {"command": None, "distance": 1.0, "matched": False, "ranking": []}

    best_cmd, best_d = scored[0]
    return {
        "command":  best_cmd,
        "distance": best_d,
        "matched":  best_d <= threshold,
        "ranking":  scored,
    }


def best_intent(transcript: str,
                command_map: dict[str, str],
                profile: str = "default",
                extra_pairs: Iterable[tuple[str, str]] | None = None,
                threshold: float = MATCH_THRESHOLD) -> dict:
    res = match_command(transcript, list(command_map.keys()),
                        profile=profile, extra_pairs=extra_pairs, threshold=threshold)
    res["intent"] = command_map.get(res["command"]) if res["matched"] else None
    return res
