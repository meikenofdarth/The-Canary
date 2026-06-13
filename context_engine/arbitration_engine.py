"""
context_engine/arbitration_engine.py
=====================================
User Arbitration Engine for The Canary.

Sits between the Context Engine and execution.  Takes the assembled speaker
records (with voice identity results attached) and produces a final arbitrated
decision with per-speaker priority scores, conflict classification, and a
resolution route.

Priority Formula
----------------
  priority = 0.4 * wakeword_score
           + 0.4 * identity_confidence   (0.0 for UNKNOWN)
           + 0.2 * known_user_bonus       (1.0 if enrolled, 0.0 otherwise)

Priority ranges
  Known user  + wakeword + high conf  →  ~0.92   (Hemang saying "Canary play…")
  Unknown     + wakeword              →  ~0.40   (visitor saying "Canary…")
  Known user  + no wakeword           →  ~0.20   (background speech)

Decision Rules  (in priority order)
------------------------------------
  Rule 0 – IGNORE          No speaker issued a wakeword command.
  Rule 1 – EXECUTE         Exactly one wakeword command.  Winner = that speaker.
  Rule 2 – EXECUTE (known wins)
                           One known + one unknown both say wakeword →
                           known user wins outright.
  Rule 3 – EXECUTE (higher priority)
                           Two+ commands, clear priority gap (> PRIORITY_GAP) →
                           highest priority speaker wins.
  Rule 4 – CLARIFY         Two known users, conflicting commands, similar priority
                           (gap ≤ PRIORITY_GAP).
  Rule 5 – SEQUENTIAL      Two known users, non-conflicting commands, similar
                           priority → queue both.
  Rule 6 – EXECUTE (same intent)
                           Multiple speakers, same intent → execute once, no
                           clarification needed.

Public API
----------
  arbitrate(speakers, voice_ids, conflict_result) -> dict
"""

from __future__ import annotations

from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────
KNOWN_USER_BONUS  = 1.0   # bonus multiplier for enrolled/identified speakers
PRIORITY_GAP      = 0.15  # gap above which the higher-priority speaker wins outright

W_WAKEWORD    = 0.40
W_IDENTITY    = 0.40
W_KNOWN_USER  = 0.20


# ─────────────────────────────────────────────────────────────────────────────
#  Priority calculator
# ─────────────────────────────────────────────────────────────────────────────
def _compute_priority(speaker: dict) -> float:
    """
    Compute the 0–1 priority score for a single speaker record.

    speaker dict is expected to have:
        wakeword            : bool
        wakeword_confidence : float (0.0–1.0)
        identity_confidence : float (confidence from voice ranker)
        known_user          : bool  (True if identity != "UNKNOWN")
    """
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


# ─────────────────────────────────────────────────────────────────────────────
#  Intent extractor (for same-intent detection — Rule 6)
# ─────────────────────────────────────────────────────────────────────────────
def _coarse_intent(transcript: str) -> str | None:
    """
    Return a coarse intent label from a transcript.
    Very lightweight — no ML.  Used only for same-intent detection.
    """
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


# ─────────────────────────────────────────────────────────────────────────────
#  Main arbitration function
# ─────────────────────────────────────────────────────────────────────────────
def arbitrate(
    speakers:        list[dict],
    voice_ids:       dict[str, dict],
    conflict_result: dict,
) -> dict:
    """
    Run the User Arbitration Engine.

    Parameters
    ----------
    speakers : list[dict]
        Speaker records from context_builder (each has id, wakeword,
        wakeword_confidence, transcript, type, …).
    voice_ids : dict[str, dict]
        Keyed by speaker filename (e.g. "speaker_1.wav") → ranker result dict.
        May be empty if voice ID was skipped.
    conflict_result : dict
        Output of detect_conflict() — {conflict: bool, conflict_pair: …}

    Returns
    -------
    dict with keys:
        arbitration : list[dict]   — per-speaker arbitration records
        winner      : str | None   — speaker id of winner (or None)
        route       : str          — IGNORE / EXECUTE / CLARIFY / SEQUENTIAL
        reason      : str          — human-readable explanation
        conflict    : bool
    """

    # ── Step 1: Attach voice identity to each speaker and compute priority ────
    arb_speakers = []
    for spk in speakers:
        fname     = spk["id"] + ".wav"
        vid       = voice_ids.get(fname, {})

        identity  = vid.get("speaker", "UNKNOWN")
        id_conf   = float(vid.get("confidence", 0.0)) if identity != "UNKNOWN" else 0.0
        known     = identity != "UNKNOWN"
        sep_q     = float(vid.get("separation_quality", 1.0))

        # Identity quality guard: if separation was poor, add warning note.
        # Note: id_conf from ranker.py is already scaled by separation_quality,
        # so we do not multiply by sep_q again to avoid double-penalization.
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
        }
        rec["priority"] = _compute_priority(rec)
        if spk.get("transcript"):
            rec["intent"] = _coarse_intent(spk["transcript"])
        else:
            rec["intent"] = None

        arb_speakers.append(rec)

    # ── Step 2: Filter to wakeword-command speakers only ─────────────────────
    active = [s for s in arb_speakers if s["wakeword"] and s.get("type") == "COMMAND"]

    # ── Step 3: Apply arbitration rules ──────────────────────────────────────

    # Rule 0 — No wakeword commands at all
    if not active:
        return {
            "arbitration": arb_speakers,
            "winner":       None,
            "route":        "IGNORE",
            "reason":       "No wakeword commands detected.",
            "conflict":     False,
        }

    # Rule 1 — Single command
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

    # Multiple active speakers — sort by priority
    active_sorted = sorted(active, key=lambda s: s["priority"], reverse=True)
    top    = active_sorted[0]
    second = active_sorted[1]
    gap    = top["priority"] - second["priority"]

    # Rule 2 — Known user beats unknown user outright (no gap needed)
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

    # Rule 3 — Clear priority gap → higher-priority speaker wins
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

    # Rule 6 — Same intent → no conflict, execute once
    intents = [s["intent"] for s in active if s["intent"]]
    if len(set(intents)) == 1 and intents[0] not in (None, "GENERAL_COMMAND"):
        return {
            "arbitration": arb_speakers,
            "winner":       top["id"],
            "route":        "EXECUTE",
            "reason":       (
                f"All speakers share the same intent ({intents[0]}). "
                f"Executing for highest-priority speaker ({top['identity']})."
            ),
            "conflict":     False,
        }

    # Rule 4 — Conflicting commands, close priority → ask for clarification
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

    # Rule 5 — Non-conflicting, close priority → sequential execution
    return {
        "arbitration": arb_speakers,
        "winner":       top["id"],  # first in priority order
        "route":        "SEQUENTIAL",
        "reason":       (
            f"Non-conflicting commands from "
            f"{', '.join(s['identity'] if s['known_user'] else s['id'] for s in active_sorted)}. "
            f"Sequential execution."
        ),
        "conflict":     False,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Terminal printer
# ─────────────────────────────────────────────────────────────────────────────
def print_arbitration(result: dict) -> None:
    """Print the USER ARBITRATION ENGINE block to stdout."""

    route_icons = {
        "EXECUTE":    "🟢  EXECUTE",
        "CLARIFY":    "🟡  CLARIFY",
        "SEQUENTIAL": "🔵  SEQUENTIAL EXECUTION",
        "IGNORE":     "⚫  IGNORE",
    }

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║   USER ARBITRATION ENGINE                       ║")
    print("  ╚══════════════════════════════════════════════════╝")

    arb = result.get("arbitration", [])
    active = [s for s in arb if s.get("wakeword") and s.get("type") == "COMMAND"]
    winner_id = result.get("winner")

    if not active:
        # Just show all speakers briefly
        for spk in arb:
            identity = spk["identity"] if spk["known_user"] else "Unknown"
            print(f"  {spk['id']:<12}  {identity:<14}  priority: {spk['priority']:.2f}  wakeword: {'YES' if spk['wakeword'] else 'NO '}")
    else:
        # Show each active (wakeword) speaker's arbitration record
        for spk in active:
            winner_mark = " ◀ WINNER" if spk["id"] == winner_id else ""
            identity    = spk["identity"] if spk["known_user"] else "Unknown"
            known_str   = "YES" if spk["known_user"] else "NO "
            ww_str      = f"{spk['wakeword_confidence']:.2f}" if spk["wakeword"] else "—"

            print(f"  ─────────────────────────────────────────────")
            print(f"  Speaker      : {identity}{winner_mark}")
            print(f"  Known User   : {known_str}     Wakeword: {ww_str}     Sep.Quality: {spk['separation_quality']:.2f}")
            print(f"  Identity Conf: {spk['identity_confidence']:.2f}")
            if spk.get("intent"):
                print(f"  Intent       : {spk['intent']}")
            if spk.get("identity_note"):
                print(f"  ⚠  {spk['identity_note']}")
            print(f"  Priority     : {spk['priority']:.2f}  "
                  f"= 0.40×wakeword({spk['wakeword_confidence']:.2f}) "
                  f"+ 0.40×id_conf({spk['identity_confidence']:.2f}) "
                  f"+ 0.20×known({1.0 if spk['known_user'] else 0.0:.1f})")

    print(f"  ─────────────────────────────────────────────")
    route_str = route_icons.get(result["route"], result["route"])
    print(f"  Decision     : {route_str}")
    print(f"  Reason       : {result['reason']}")

    if result["route"] == "CLARIFY":
        active_sorted = sorted(active, key=lambda s: s["priority"], reverse=True)
        names = " and ".join(
            s["identity"] if s["known_user"] else s["id"]
            for s in active_sorted[:2]
        )
        print(f"  ⚠  Canary should ask: \"I heard commands from {names}. Which should I execute?\"")

    print("  ─────────────────────────────────────────────")
    print()
