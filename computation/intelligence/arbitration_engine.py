
from __future__ import annotations

from typing import Any

KNOWN_USER_BONUS  = 1.0
PRIORITY_GAP      = 0.15

W_WAKEWORD    = 0.40
W_IDENTITY    = 0.40
W_KNOWN_USER  = 0.20


def _compute_priority(speaker: dict) -> float:
    wakeword_score   = float(speaker.get("wakeword_confidence", 0.0)) \
                       if speaker.get("wakeword") else 0.0
    identity_conf    = float(speaker.get("identity_confidence", 0.0))
    known_bonus      = KNOWN_USER_BONUS if speaker.get("known_user") else 0.0

    priority = (
        W_WAKEWORD   * wakeword_score
      + W_IDENTITY   * identity_conf
      + W_KNOWN_USER * known_bonus
    )
    return round(min(priority, 1.0), 4)


def _coarse_intent(transcript: str) -> str | None:
    t = transcript.lower()
    if any(w in t for w in ("play", "music", "song", "songs", "album", "artist", "playlist")):
        return "PLAY_MEDIA"
    if any(w in t for w in ("stop", "pause", "halt")):
        return "STOP_MEDIA"
    if any(w in t for w in ("turn on", "switch on", "power on", "lights on")):
        return "DEVICE_ON"
    if any(w in t for w in ("turn off", "switch off", "power off", "lights off")):
        return "DEVICE_OFF"
    if any(w in t for w in ("volume up", "louder", "increase volume", "turn up")):
        return "VOLUME_UP"
    if any(w in t for w in ("volume down", "quieter", "decrease volume", "turn down")):
        return "VOLUME_DOWN"
    if any(w in t for w in ("call", "ring", "dial", "phone")):
        return "CALL"
    if any(w in t for w in ("remind", "reminder", "alarm", "timer", "set", "schedule")):
        return "REMINDER"
    if any(w in t for w in ("weather", "temperature", "forecast")):
        return "WEATHER"
    if any(w in t for w in ("who are you", "how are you", "hello", "hi", "hey")):
        return "GREETING"
    return "GENERAL_COMMAND"


def arbitrate(
    speakers:        list[dict],
    voice_ids:       dict[str, dict],
    conflict_result: dict,
) -> dict:

    arb_speakers = []
    for spk in speakers:
        fname     = spk["id"] + ".wav"
        vid       = voice_ids.get(fname, {})

        identity  = vid.get("speaker", "UNKNOWN")
        id_conf   = float(vid.get("confidence", 0.0)) if identity != "UNKNOWN" else 0.0
        known     = identity != "UNKNOWN"
        sep_q     = float(vid.get("separation_quality", 1.0))

        if sep_q < 0.5 and id_conf > 0.0:
            identity_note = f"conf penalised (sep_quality={sep_q:.2f})"
        else:
            identity_note = ""

        rec = {
            "id":                  spk["id"],
            "identity":            identity,
            "identity_confidence": round(id_conf, 4),
            "known_user":          known,
            "wakeword":            spk.get("wakeword", False),
            "wakeword_confidence": float(spk.get("wakeword_confidence", 0.0)),
            "transcript":          spk.get("transcript", ""),
            "type":                spk.get("type", "UNKNOWN"),
            "separation_quality":  sep_q,
            "identity_note":       identity_note,
            "start_time":          spk.get("start_time", 0.0),
        }
        rec["priority"] = _compute_priority(rec)
        if spk.get("transcript"):
            rec["intent"] = _coarse_intent(spk["transcript"])
        else:
            rec["intent"] = None

        arb_speakers.append(rec)

    active = [s for s in arb_speakers if s["wakeword"] and s.get("type") == "COMMAND"]

    active_known = [s for s in active if s["known_user"]]
    active_unknown = [s for s in active if not s["known_user"]]
    if active_known and active_unknown:
        active = active_known


    if not active:
        return {
            "arbitration": arb_speakers,
            "winner":       None,
            "route":        "IGNORE",
            "reason":       "No wakeword commands detected.",
            "conflict":     False,
        }

    if len(active) == 1:
        winner = active[0]
        return {
            "arbitration": arb_speakers,
            "winner":       winner["id"],
            "route":        "EXECUTE",
            "reason":       (
                f"{winner['identity'] if winner['known_user'] else 'Unknown speaker'} "
                f"issued the only wakeword command. "
                f"Priority: {winner['priority']:.2f}."
            ),
            "conflict":     False,
        }

    active_sorted = sorted(active, key=lambda s: (-s["priority"], s.get("start_time", 0.0)))
    top    = active_sorted[0]
    second = active_sorted[1]
    gap    = top["priority"] - second["priority"]

    if top["known_user"] and not second["known_user"]:
        return {
            "arbitration": arb_speakers,
            "winner":       top["id"],
            "route":        "EXECUTE",
            "reason":       (
                f"Known user ({top['identity']}) takes priority over unknown speaker. "
                f"Priorities: {top['priority']:.2f} vs {second['priority']:.2f}."
            ),
            "conflict":     False,
        }

    if gap > PRIORITY_GAP:
        return {
            "arbitration": arb_speakers,
            "winner":       top["id"],
            "route":        "EXECUTE",
            "reason":       (
                f"{top['identity'] if top['known_user'] else 'Speaker'} wins "
                f"with priority gap {gap:.2f} > {PRIORITY_GAP}."
            ),
            "conflict":     conflict_result.get("conflict", False),
        }

    intents = [s["intent"] for s in active if s["intent"]]
    if len(active) >= 2 and len(set(intents)) == 1 and intents[0] not in (None, "GENERAL_COMMAND"):
        names = ", ".join(
            s["identity"] if s["known_user"] else s["id"] for s in active_sorted
        )
        return {
            "arbitration": arb_speakers,
            "winner":       top["id"],
            "route":        "SEQUENTIAL",
            "reason":       (
                f"Multiple speakers ({names}) share the same intent ({intents[0]}). "
                f"Executing sequentially in priority order."
            ),
            "conflict":     False,
        }

    if conflict_result.get("conflict"):
        names = " vs ".join(
            s["identity"] if s["known_user"] else s["id"] for s in active_sorted[:2]
        )
        cp = conflict_result.get("conflict_pair") or []
        conflict_desc = f"{cp[0]!r} ↔ {cp[1]!r}" if len(cp) >= 2 else "opposing commands"
        return {
            "arbitration": arb_speakers,
            "winner":       None,
            "route":        "CLARIFY",
            "reason":       (
                f"Conflicting commands from {names}: {conflict_desc}. "
                f"Priorities {top['priority']:.2f} vs {second['priority']:.2f} "
                f"(gap={gap:.2f} ≤ {PRIORITY_GAP}). Clarification needed."
            ),
            "conflict":     True,
        }

    by_time = sorted(active, key=lambda s: s.get("start_time", 0.0))
    winner_spk = by_time[0]
    return {
        "arbitration": arb_speakers,
        "winner":       winner_spk["id"],
        "route":        "SEQUENTIAL",
        "reason":       (
            f"Non-conflicting commands from "
            f"{', '.join(s['identity'] if s['known_user'] else s['id'] for s in by_time)}. "
            f"Sequential execution ordered by time of command."
        ),
        "conflict":     False,
    }


def print_arbitration(result: dict) -> None:

    route_icons = {
        "EXECUTE":    "🟢  EXECUTE",
        "CLARIFY":    "🟡  CLARIFY",
        "SEQUENTIAL": "🔵  SEQUENTIAL EXECUTION",
        "IGNORE":     "⚫  IGNORE",
    }

    print()
    print("  ── Arbitration ──────────────────────────────────")

    arb = result.get("arbitration", [])
    active = [s for s in arb if s.get("wakeword") and s.get("type") == "COMMAND"]
    winner_id = result.get("winner")

    if not active:
        for spk in arb:
            identity = spk["identity"] if spk["known_user"] else "Unknown"
            print(f"  {spk['id']:<12} {identity:<14} priority {spk['priority']:.2f}  "
                  f"wakeword {'yes' if spk['wakeword'] else 'no'}")
    else:
        for spk in active:
            mark     = " ◀ winner" if spk["id"] == winner_id else ""
            identity = spk["identity"] if spk["known_user"] else "Unknown"
            print(f"  {identity:<14} priority {spk['priority']:.2f}  "
                  f"id {spk['identity_confidence']:.2f}{mark}")
            if spk.get("identity_note"):
                print(f"  ⚠ {spk['identity_note']}")

    route_str = route_icons.get(result["route"], result["route"])
    print(f"  Decision: {route_str} — {result['reason']}")

    if result["route"] == "CLARIFY":
        active_sorted = sorted(active, key=lambda s: s["priority"], reverse=True)
        names = " and ".join(
            s["identity"] if s["known_user"] else s["id"]
            for s in active_sorted[:2]
        )
        print(f"  ⚠ ask: \"I heard commands from {names}. Which should I execute?\"")
    print()
