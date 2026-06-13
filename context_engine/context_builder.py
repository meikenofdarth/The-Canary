"""
context_engine/context_builder.py
====================================
Assembles all pipeline outputs into a single structured context.json,
runs the User Arbitration Engine, and prints the terminal summary.

Input
-----
    out_dir   : pathlib.Path — session output directory (speakers/.txt files live here)
    drs       : dict         — result from drs_shadow() in run_canary.py
    n_spk     : int          — number of detected speakers
    voice_ids : dict         — keyed by "speaker_N.wav" → ranker result dict
                               (may be empty / missing keys for UNKNOWN speakers)

Output
------
    context.json written to out_dir/
    dict returned to caller

Routing table  (post-arbitration)
---------------------------------------------------------------------------
    IGNORE            — no wakeword commands
    EXECUTE           — single clear winner
    CLARIFY           — conflicting commands, needs user input
    SEQUENTIAL        — multiple non-conflicting commands, queue them
"""

from __future__ import annotations

import json
import datetime
import re
from pathlib import Path

from .wakeword_detector  import detect_wakeword
from .utterance_analyzer import analyze_utterance
from .conflict_detector  import detect_conflict
from .arbitration_engine import arbitrate, print_arbitration
from .intent_engine      import analyze_intents_for_speakers
from .response_builder   import build_response, print_response_summary


# ─────────────────────────────────────────────────────────────────────────────
#  TRANSCRIPT PARSER
#  Reads speaker_N.txt files written by asr/transcribe.py
# ─────────────────────────────────────────────────────────────────────────────
def _parse_transcript(txt_path: Path) -> tuple[str | None, str, float]:
    """
    Extract the clean transcript text, status, and first segment start time from a speaker .txt file.

    .txt file format (READY example):
        [Language: en]
        [Status: ✓  READY — meaningful speech detected]
        [RMS: -18.0 dBFS | Speech ratio: 69%]

        Hey, how are you? My day was not that good.

        --- Segments ---
        [0.00s → 3.10s] Hey, how are you?
        ...

    Returns (transcript | None, status_string, start_time)
    """
    try:
        content = txt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "MISSING", 0.0

    lines = content.split("\n")

    # ── Determine status ──────────────────────────────────────────────────
    status = "UNKNOWN"
    for line in lines:
        if "[Status:" in line:
            status = "READY" if "READY" in line else "REJECTED"
            break

    # ── Parse segment starting time ───────────────────────────────────────
    start_time = 0.0
    for line in lines:
        m = re.search(r"\[([0-9\.]+)s\s*(?:→|->)\s*[0-9\.]+s\]", line)
        if m:
            try:
                start_time = float(m.group(1))
                break
            except ValueError:
                pass

    if status != "READY":
        return None, status, start_time

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
        return None, "REJECTED", start_time

    return (transcript if transcript else None), status, start_time


# ─────────────────────────────────────────────────────────────────────────────
#  TERMINAL SUMMARY  (Context Engine block)
# ─────────────────────────────────────────────────────────────────────────────
def _print_summary(ctx: dict) -> None:
    route_labels = {
        "IGNORE":     "⚫  IGNORE         — no wakeword detected, all ambient speech",
        "EXECUTE":    "🟢  EXECUTE         — single clear command, proceeding",
        "CLARIFY":    "🟡  CLARIFY         — conflicting commands, need confirmation",
        "SEQUENTIAL": "🔵  SEQUENTIAL      — multiple commands queued",
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

        # Show identity if available
        identity = spk.get("identity", "UNKNOWN")
        id_conf  = spk.get("identity_confidence", 0.0)
        id_str   = f" [{identity}  {id_conf:.2f}]" if identity != "UNKNOWN" else " [UNKNOWN]"

        print(f"  [{ok}] {spk['id']}  [{type_label:<12s}]  {ww}{id_str}")
        if spk["transcript"]:
            preview = spk["transcript"][:72] + ("…" if len(spk["transcript"]) > 72 else "")
            print(f"       \"{preview}\"")

    print()
    if ctx.get("conflict"):
        cp = ctx.get("conflict_pair") or []
        print(f"  ⚠  Conflict detected: {cp[0]!r} vs {cp[1]!r}")

    route_str = route_labels.get(ctx["route"], ctx["route"])
    print(f"  Route       : {route_str}")
    print(f"  Saved       : {ctx['session_dir']}/context.json")
    print()


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
def build_context(
    out_dir:   Path,
    drs:       dict,
    n_spk:     int,
    voice_ids: dict | None = None,
) -> dict:
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
    voice_ids : dict | None
        Keyed by "speaker_N.wav" → voice ranker result dict.
        If None, identity fields will be UNKNOWN for all speakers.

    Returns
    -------
    dict — the full context (also written to out_dir/context.json).
    """
    out_dir   = Path(out_dir)
    voice_ids = voice_ids or {}
    speakers: list[dict] = []

    # ── Phase 1: Parse transcripts and detect wake words for all speakers ────
    for i in range(1, n_spk + 1):
        spk_id   = f"speaker_{i}"
        txt_path = out_dir / f"{spk_id}.txt"
        fname    = f"{spk_id}.wav"

        transcript, status, start_time = _parse_transcript(txt_path)

        if transcript:
            ww = detect_wakeword(transcript)
            utt = analyze_utterance(transcript)
            if ww["wakeword"]:
                type_val = "COMMAND"
                type_conf = max(utt["confidence"], 0.95)
            else:
                type_val = utt["type"]
                type_conf = utt["confidence"]
        else:
            ww = {"wakeword": False, "wakeword_confidence": 0.0, "matched_phrase": None}
            type_val = "UNKNOWN"
            type_conf = 0.0

        # Attach voice identity fields
        vid      = voice_ids.get(fname, {})
        identity = vid.get("speaker", "UNKNOWN")
        id_conf  = float(vid.get("confidence", 0.0))
        known    = identity != "UNKNOWN"

        speakers.append({
            "id":                  spk_id,
            "status":              status,
            "transcript":          transcript or "",
            "wakeword":            ww["wakeword"],
            "wakeword_confidence": ww["wakeword_confidence"],
            "wakeword_phrase":     ww["matched_phrase"],
            "type":                type_val,
            "type_confidence":     type_conf,
            # Voice identity fields
            "identity":            identity,
            "identity_confidence": round(id_conf, 4),
            "known_user":          known,
            "start_time":          start_time,
        })

    # ── Phase 2: Apply Routing Rules ─────────────────────────────────────────
    active_ww_indices = [idx for idx, s in enumerate(speakers) if s["wakeword"]]
    wakeword_count = len(active_ww_indices)

    if wakeword_count == 0:
        command_count = 0
        conflict = False
        conflict_pair = None
        conflict_result = {"conflict": False, "conflict_pair": None}
        route = "IGNORE"

    elif wakeword_count == 1:
        idx = active_ww_indices[0]
        transcript = speakers[idx]["transcript"]
        utt = analyze_utterance(transcript)
        speakers[idx]["type"] = "COMMAND"
        speakers[idx]["type_confidence"] = max(utt["confidence"], 0.95)

        command_count = 1
        conflict = False
        conflict_pair = None
        conflict_result = {"conflict": False, "conflict_pair": None}
        route = "EXECUTE"

    else:
        for idx in active_ww_indices:
            transcript = speakers[idx]["transcript"]
            utt = analyze_utterance(transcript)
            speakers[idx]["type"] = "COMMAND"
            speakers[idx]["type_confidence"] = max(utt["confidence"], 0.95)

        command_count = sum(1 for s in speakers if s["wakeword"] and s["type"] == "COMMAND")
        conflict_result = detect_conflict(speakers)
        conflict = conflict_result["conflict"]
        conflict_pair = conflict_result.get("conflict_pair")

        if command_count == 0:
            route = "IGNORE"
        elif command_count == 1:
            route = "EXECUTE"
        elif conflict:
            route = "CLARIFY"
        else:
            route = "MULTI_EXECUTE"

    # ── Phase 3: User Arbitration Engine ─────────────────────────────────────
    arb_result = arbitrate(speakers, voice_ids, conflict_result)

    # Arbitration may override the initial route
    arb_route = arb_result.get("route", route)

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
        "speakers":        speakers,
        "wakeword_count":  wakeword_count,
        "command_count":   command_count,
        "conflict":        conflict,
        "conflict_pair":   conflict_pair,
        "route":           arb_route,
        # Arbitration results
        "arbitration": {
            "winner":      arb_result.get("winner"),
            "route":       arb_route,
            "reason":      arb_result.get("reason", ""),
            "speakers":    arb_result.get("arbitration", []),
        },
    }

    # ── Intent Engine & Response Builder ─────────────────────────────────────
    analyze_intents_for_speakers(context["speakers"])
    response = build_response(context, arb_result, out_dir)

    # Save response.json also to project root directory
    try:
        root_path = Path("/Users/knight_striker/Desktop/The-Canary/response.json")
        root_path.write_text(
            json.dumps(response, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as _root_err:
        print(f"  [Context Engine] Warning: failed to save response.json to root — {_root_err}")

    # ── Save context.json ───────────────────────────────────────────────────
    ctx_path = out_dir / "context.json"
    ctx_path.write_text(
        json.dumps(context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── Print ─────────────────────────────────────────────────────────────
    _print_summary(context)
    print_arbitration(arb_result)
    print_response_summary(response)

    return context
