"""
context_engine/context_builder.py
====================================
Assembles all pipeline outputs into a single structured context.json.

Input
-----
    out_dir  : pathlib.Path — session output directory (speakers/.txt files live here)
    drs      : dict         — result from drs_shadow() in run_canary.py
    n_spk    : int          — number of detected speakers

Output
------
    context.json written to out_dir/
    dict returned to caller

Routing table  (based on command_count = speakers with wakeword AND COMMAND type)
---------------------------------------------------------------------------
    command_count == 0                           → IGNORE
    command_count == 1                           → EXECUTE
    command_count >= 2  AND conflict found       → CLARIFY
    command_count >= 2  AND no conflict          → MULTI_EXECUTE

Key insight: wakeword_count is NOT used for routing.
  • "Cannery, no no no" has wakeword=True but type=CONVERSATION → does NOT count.
  • "Hey Canary play music" has wakeword=True AND type=COMMAND → counts.
"""

from __future__ import annotations

import json
import datetime
from pathlib import Path

from .wakeword_detector  import detect_wakeword
from .utterance_analyzer import analyze_utterance
from .conflict_detector  import detect_conflict


# ─────────────────────────────────────────────────────────────────────────────
#  TRANSCRIPT PARSER
#  Reads speaker_N.txt files written by asr/transcribe.py
# ─────────────────────────────────────────────────────────────────────────────
def _parse_transcript(txt_path: Path) -> tuple[str | None, str]:
    """
    Extract the clean transcript text and status from a speaker .txt file.

    .txt file format (READY example):
        [Language: en]
        [Status: ✓  READY — meaningful speech detected]
        [RMS: -18.0 dBFS | Speech ratio: 69%]

        Hey, how are you? My day was not that good.

        --- Segments ---
        [0.00s → 3.10s] Hey, how are you?
        ...

    Returns (transcript | None, status_string)
    """
    try:
        content = txt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "MISSING"

    lines = content.split("\n")

    # ── Determine status ──────────────────────────────────────────────────
    status = "UNKNOWN"
    for line in lines:
        if "[Status:" in line:
            status = "READY" if "READY" in line else "REJECTED"
            break

    if status != "READY":
        return None, status

    # ── Extract transcript ─────────────────────────────────────────────────
    # Metadata block = everything up to the first blank line.
    # Transcript = lines between that blank line and "--- Segments ---".
    in_header      = True
    transcript_buf = []

    for line in lines:
        if in_header:
            if line.strip() == "":
                in_header = False
            continue
        if line.strip().startswith("--- Segments ---"):
            break
        transcript_buf.append(line)

    transcript = "\n".join(transcript_buf).strip()

    # Reject parenthetical rejection messages like "(no speech detected...)"
    if transcript.startswith("(") and transcript.endswith(")"):
        return None, "REJECTED"

    return (transcript if transcript else None), status


# ─────────────────────────────────────────────────────────────────────────────
#  TERMINAL SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
def _print_summary(ctx: dict) -> None:
    route_labels = {
        "IGNORE":        "⚫  IGNORE         — no wakeword detected, all ambient speech",
        "EXECUTE":       "🟢  EXECUTE         — single clear command, proceeding",
        "CLARIFY":       "🟡  CLARIFY         — conflicting commands, need confirmation",
        "MULTI_EXECUTE": "🔵  MULTI_EXECUTE   — multiple commands, running sequentially",
    }

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║   CONTEXT ENGINE  ·  context.json               ║")
    print("  ╚══════════════════════════════════════════════════╝")
    scene = ctx["scene"]
    print(f"  Mode        : {ctx['drs_mode']}   "
          f"Speakers: {scene['speaker_count']}   "
          f"Complexity: {scene['complexity']:.3f}   "
          f"Noise: {scene['noise_level']:.3f}")
    print()

    for spk in ctx["speakers"]:
        ok   = "✓" if spk["transcript"] else "✗"
        ww   = "🔔 WAKEWORD" if spk["wakeword"] else "          "
        type_label = spk["type"]
        print(f"  [{ok}] {spk['id']}  [{type_label:<12s}]  {ww}")
        if spk["transcript"]:
            preview = spk["transcript"][:72] + ("…" if len(spk["transcript"]) > 72 else "")
            print(f"       \"{preview}\"")

    print()
    if ctx["conflict"]:
        cp = ctx.get("conflict_pair") or []
        print(f"  ⚠  Conflict detected: {cp[0]!r} vs {cp[1]!r}")

    route_str = route_labels.get(ctx["route"], ctx["route"])
    print(f"  Route       : {route_str}")
    print(f"  Saved       : {ctx['session_dir']}/context.json")
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
def build_context(out_dir: Path, drs: dict, n_spk: int) -> dict:
    """
    Build and save context.json for one pipeline run.

    Parameters
    ----------
    out_dir : pathlib.Path
        Session output directory (e.g. outputs/20260608_223606/).
    drs : dict
        The dict returned by drs_shadow() — contains mode, complexity_score,
        noise_level, overlap_prob, speaker_count.
    n_spk : int
        Number of speakers detected by the separation stage.

    Returns
    -------
    dict — the full context (also written to out_dir/context.json).
    """
    out_dir = Path(out_dir)
    speakers: list[dict] = []

    # ── Analyse each speaker stream ───────────────────────────────────────
    for i in range(1, n_spk + 1):
        spk_id   = f"speaker_{i}"
        txt_path = out_dir / f"{spk_id}.txt"

        transcript, status = _parse_transcript(txt_path)

        if transcript:
            ww  = detect_wakeword(transcript)
            utt = analyze_utterance(transcript)
        else:
            ww  = {"wakeword": False, "wakeword_confidence": 0.0, "matched_phrase": None}
            utt = {"type": "UNKNOWN", "confidence": 0.0}

        speakers.append({
            "id":                  spk_id,
            "status":              status,
            "transcript":          transcript or "",
            "wakeword":            ww["wakeword"],
            "wakeword_confidence": ww["wakeword_confidence"],
            "wakeword_phrase":     ww["matched_phrase"],
            "type":                utt["type"],
            "type_confidence":     utt["confidence"],
        })

    # ── Routing (intent-driven, not timing-driven) ─────────────────────────────
    # wakeword_count   = everyone who said "Canary" (including background mentions)
    # command_count    = speakers who said "Canary" AND issued a real COMMAND
    #                    This is what actually drives routing.
    wakeword_count = sum(1 for s in speakers if s["wakeword"])
    command_count  = sum(
        1 for s in speakers
        if s["wakeword"] and s["type"] == "COMMAND"
    )
    conflict_result = detect_conflict(speakers)

    if command_count == 0:
        route = "IGNORE"          # nobody gave Canary an actionable command
    elif command_count == 1:
        route = "EXECUTE"         # exactly one wakeword command — clear to proceed
    elif conflict_result["conflict"]:
        route = "CLARIFY"         # multiple commands that oppose each other
    else:
        route = "MULTI_EXECUTE"   # multiple non-conflicting commands

    # ── Assemble ──────────────────────────────────────────────────────────
    context: dict = {
        "timestamp":   datetime.datetime.now().isoformat(),
        "session_dir": str(out_dir),
        "drs_mode":    drs.get("mode",  "?"),
        "scene": {
            "speaker_count": n_spk,
            "complexity":    drs.get("complexity_score", 0.0),
            "noise_level":   drs.get("noise_level",      0.0),
            "simul_speech":  drs.get("overlap_prob",     0.0),
        },
        "speakers":       speakers,
        "wakeword_count":  wakeword_count,
        "command_count":   command_count,
        "conflict":        conflict_result["conflict"],
        "conflict_pair":   conflict_result.get("conflict_pair"),
        "route":           route,
    }

    # ── Save ──────────────────────────────────────────────────────────────
    ctx_path = out_dir / "context.json"
    ctx_path.write_text(
        json.dumps(context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── Print ─────────────────────────────────────────────────────────────
    _print_summary(context)

    return context
