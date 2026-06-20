
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


def _parse_transcript(txt_path: Path) -> tuple[str | None, str, float]:
    try:
        content = txt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "MISSING", 0.0

    lines = content.split("\n")

    status = "UNKNOWN"
    for line in lines:
        if "[Status:" in line:
            status = "READY" if "READY" in line else "REJECTED"
            break

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

    if transcript:
        transcript = transcript.lower()

    if transcript.startswith("(") and transcript.endswith(")"):
        return None, "REJECTED", start_time

    return (transcript if transcript else None), status, start_time


def _print_summary(ctx: dict) -> None:
    route_labels = {
        "IGNORE":     "⚫  IGNORE         — no wakeword detected, all ambient speech",
        "EXECUTE":    "🟢  EXECUTE         — single clear command, proceeding",
        "CLARIFY":    "🟡  CLARIFY         — conflicting commands, need confirmation",
        "SEQUENTIAL": "🔵  SEQUENTIAL      — multiple commands queued",
        "MULTI_EXECUTE": "🔵  MULTI_EXECUTE   — multiple commands, running sequentially",
    }

    print()
    print("  ── Context ──────────────────────────────────────")
    scene = ctx["scene"]
    print(f"  Mode {ctx['drs_mode']} · {scene['speaker_count']} speaker(s) · "
          f"complexity {scene['complexity']:.2f} · noise {scene['noise_level']:.2f}")

    for spk in ctx["speakers"]:
        ok   = "✓" if spk["transcript"] else "✗"
        ww   = "🔔" if spk["wakeword"] else "  "
        identity = spk.get("identity", "UNKNOWN")
        id_conf  = spk.get("identity_confidence", 0.0)
        id_str   = f"{identity} ({id_conf:.2f})" if identity != "UNKNOWN" else "UNKNOWN"
        print(f"  {ok} {spk['id']}  {ww}  {spk['type']:<8s} {id_str}")
        if spk["transcript"]:
            preview = spk["transcript"][:72] + ("…" if len(spk["transcript"]) > 72 else "")
            print(f"      \"{preview}\"")

    if ctx.get("conflict"):
        cp = ctx.get("conflict_pair") or []
        print(f"  ⚠ conflict: {cp[0]!r} vs {cp[1]!r}")


def build_context(
    out_dir:   Path,
    drs:       dict,
    n_spk:     int,
    voice_ids: dict | None = None,
) -> dict:
    out_dir   = Path(out_dir)
    voice_ids = voice_ids or {}
    speakers: list[dict] = []

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
            "identity":            identity,
            "identity_confidence": round(id_conf, 4),
            "known_user":          known,
            "start_time":          start_time,
        })

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

    arb_result = arbitrate(speakers, voice_ids, conflict_result)

    arb_route = arb_result.get("route", route)

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
        "arbitration": {
            "winner":      arb_result.get("winner"),
            "route":       arb_route,
            "reason":      arb_result.get("reason", ""),
            "speakers":    arb_result.get("arbitration", []),
        },
    }

    analyze_intents_for_speakers(context["speakers"])
    response = build_response(context, arb_result, out_dir)

    try:
        root_path = Path(__file__).parent.parent.parent / "response.json"
        root_path.write_text(
            json.dumps(response, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as _root_err:
        print(f"  [Context Engine] Warning: failed to save response.json to root — {_root_err}")

    ctx_path = out_dir / "context.json"
    ctx_path.write_text(
        json.dumps(context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    _print_summary(context)
    print_arbitration(arb_result)
    print_response_summary(response)

    return context
