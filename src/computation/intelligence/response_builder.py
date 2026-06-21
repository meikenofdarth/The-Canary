
from __future__ import annotations

import json
import datetime
from pathlib import Path


def _speaker_domain(spk: dict) -> str:
    ir = spk.get("intent_result") or {}
    return ir.get("domain", "UNKNOWN")


def _speaker_polarity(spk: dict) -> str:
    ir = spk.get("intent_result") or {}
    return ir.get("polarity", "NEUTRAL")


def _speaker_intent_conf(spk: dict) -> float:
    ir = spk.get("intent_result") or {}
    return float(ir.get("confidence", 0.0))


def _speaker_entities(spk: dict) -> dict:
    ir = spk.get("intent_result") or {}
    return ir.get("entities", {})


def _speaker_raw_signals(spk: dict) -> list:
    ir = spk.get("intent_result") or {}
    return ir.get("raw_signals", [])


def _priority_from_arb(arb_list: list[dict], speaker_id: str) -> float:
    for rec in arb_list:
        if rec.get("id") == speaker_id:
            return float(rec.get("priority", 0.0))
    return 0.0


def _identity_conf_from_arb(arb_list: list[dict], speaker_id: str) -> float:
    for rec in arb_list:
        if rec.get("id") == speaker_id:
            return float(rec.get("identity_confidence", 0.0))
    return 0.0


_SYSTEM_PROMPT_TEMPLATE = """\
You are The Canary, a smart home voice assistant.
You have received and analysed a voice command from a household session.
Your job is to act on the command described below, respond naturally,
and if clarification is needed, ask concisely.

Rules:
- Always address the user by their enrolled name if known.
- If the command is ambiguous or in conflict, ask a single clarifying question.
- If the domain is UNKNOWN, politely acknowledge you did not understand.
- Keep your spoken response short (1-3 sentences max).
- Never mention internal system fields (priority scores, speaker IDs, etc.).\
"""


def _build_llm_prompt(
    route: str,
    active_command: dict | None,
    conflict: dict,
    clarification_prompt: str | None,
    sequential_queue: list[dict],
) -> dict:
    system = _SYSTEM_PROMPT_TEMPLATE

    if route == "IGNORE":
        user = (
            "No wake word was detected in the audio session. "
            "All speech was ambient or background. No action is required."
        )

    elif route == "EXECUTE" and active_command:
        domain   = active_command.get("domain", "UNKNOWN")
        polarity = active_command.get("polarity", "NEUTRAL")
        identity = active_command.get("identity") or "the user"
        transcript = active_command.get("transcript", "")
        entities = active_command.get("entities", {})

        if polarity == "POSITIVE":
            action_desc = f"{identity} wants the system to handle a {domain} request."
        elif polarity == "NEGATIVE":
            action_desc = (
                f"{identity} explicitly does NOT want a {domain} response. "
                f"Acknowledge and stop or skip the relevant action."
            )
        else:
            action_desc = f"{identity} issued a {domain} command with neutral polarity."

        entity_str = ""
        if entities:
            parts = [f"{k}={v!r}" for k, v in entities.items()]
            entity_str = "  Extracted details: " + ", ".join(parts) + "."

        user = (
            f"Command received from {identity}.\n"
            f"Transcript: \"{transcript}\"\n"
            f"Domain: {domain}  |  Polarity: {polarity}\n"
            f"{entity_str}\n"
            f"Action: {action_desc}\n"
            f"Generate a spoken response to this command."
        )

    elif route == "CLARIFY":
        cp = conflict.get("conflict_pair") or []
        conflict_desc = " vs ".join(cp) if cp else "conflicting commands"
        speakers_str = clarification_prompt or "Multiple speakers issued conflicting commands."
        user = (
            f"Multiple speakers issued conflicting commands ({conflict_desc}). "
            f"{speakers_str} "
            f"Ask the household which command to execute. "
            f"Be polite and concise."
        )

    elif route == "SEQUENTIAL" and sequential_queue:
        items = []
        for entry in sequential_queue:
            items.append(
                f"  {entry['order']}. {entry['identity']} — {entry['domain']} — \"{entry['transcript']}\""
            )
        queue_str = "\n".join(items)
        user = (
            f"Multiple non-conflicting commands were received and will be executed in order:\n"
            f"{queue_str}\n"
            f"Acknowledge all commands and confirm sequential execution."
        )

    else:
        user = "An unknown routing decision was made. No action taken."

    return {"system": system, "user": user}


def _build_priority_log(arb_result: dict, speakers: list[dict]) -> list[str]:
    log: list[str] = []
    route = arb_result.get("route", "UNKNOWN")
    reason = arb_result.get("reason", "")
    arb_list = arb_result.get("arbitration", [])

    active = [
        s for s in arb_list
        if s.get("wakeword") and s.get("type") == "COMMAND"
    ]

    log.append("=== Priority Engine Trace ===")
    log.append(f"Total speakers in session: {len(arb_list)}")
    log.append(f"Speakers with wakeword+command: {len(active)}")

    if not active:
        log.append("Rule 0 FIRED — No wakeword commands. Route: IGNORE.")
        return log

    if len(active) == 1:
        s = active[0]
        ident = s['identity'] if s['known_user'] else "Unknown"
        log.append(f"Rule 1 FIRED — Single wakeword command from {ident}.")
        log.append(f"  Priority: {s['priority']:.4f}")
        log.append(f"  Route: EXECUTE")
        return log

    active_sorted = sorted(active, key=lambda s: s["priority"], reverse=True)
    top = active_sorted[0]
    second = active_sorted[1]
    gap = top["priority"] - second["priority"]

    for s in active_sorted:
        ident = s['identity'] if s['known_user'] else "Unknown"
        known_str = "known" if s['known_user'] else "unknown"
        log.append(
            f"  Speaker {s['id']} ({ident}, {known_str}): "
            f"priority={s['priority']:.4f}  "
            f"wakeword_conf={s['wakeword_confidence']:.4f}  "
            f"id_conf={s['identity_confidence']:.4f}"
        )

    if top["known_user"] and not second["known_user"]:
        log.append("Rule 2 FIRED — Known user vs Unknown user.")
        log.append(f"  Known user ({top['identity']}) beats Unknown outright.")
        log.append(f"  Route: EXECUTE (known user wins)")
        return log

    log.append(f"Priority gap between top-2: {gap:.4f}  (threshold: 0.15)")

    if gap > 0.15:
        log.append("Rule 3 FIRED — Clear priority gap detected.")
        log.append(f"  {top['identity'] if top['known_user'] else 'Speaker'} wins. Route: EXECUTE")
        return log

    intents = [s.get("intent") for s in active_sorted if s.get("intent")]
    if len(active_sorted) >= 2 and len(set(intents)) == 1 and intents[0] not in (None, "GENERAL_COMMAND"):
        log.append("Rule 6 FIRED — Multiple active speakers share the same intent.")
        log.append(f"  Intent: {intents[0]}. SEQUENTIAL execution in priority order")
        log.append(f"  (each user gets their personalized response).")
        for i, s in enumerate(active_sorted, start=1):
            ident = s['identity'] if s['known_user'] else s['id']
            log.append(f"  Queue position {i}: {ident}  priority={s['priority']:.2f}")
        log.append(f"  Route: SEQUENTIAL")
        return log

    if route == "CLARIFY":
        log.append("Rule 4 FIRED — Conflicting commands, close priority.")
        log.append("  Two known users with near-equal priority, opposite commands.")
        log.append("  Route: CLARIFY — ask user which to execute.")
        log.append(f"  Reason: {reason}")
        return log

    log.append("Rule 5 FIRED — Non-conflicting commands, close priority.")
    log.append("  Multiple known users, similar priority, compatible commands.")
    log.append("  Route: SEQUENTIAL — queue commands by priority order.")
    for i, s in enumerate(active_sorted, start=1):
        ident = s['identity'] if s['known_user'] else s['id']
        log.append(f"  Queue position {i}: {ident}")
    return log


def build_response(
    context:    dict,
    arb_result: dict,
    out_dir:    Path,
) -> dict:
    out_dir = Path(out_dir)
    speakers = context.get("speakers", [])
    arb_list = arb_result.get("arbitration", [])
    route = arb_result.get("route", context.get("route", "IGNORE"))
    winner_id = arb_result.get("winner")

    all_speakers: list[dict] = []
    for spk in speakers:
        sid = spk["id"]
        all_speakers.append({
            "speaker_id":          sid,
            "identity":            spk.get("identity", "UNKNOWN"),
            "known_user":          spk.get("known_user", False),
            "status":              spk.get("status", "UNKNOWN"),
            "transcript":          spk.get("transcript", ""),
            "wakeword":            spk.get("wakeword", False),
            "wakeword_phrase":     spk.get("wakeword_phrase"),
            "wakeword_confidence": float(spk.get("wakeword_confidence", 0.0)),
            "domain":              _speaker_domain(spk),
            "polarity":            _speaker_polarity(spk),
            "intent_confidence":   _speaker_intent_conf(spk),
            "entities":            _speaker_entities(spk),
            "raw_signals":         _speaker_raw_signals(spk),
            "priority_score":      _priority_from_arb(arb_list, sid),
            "identity_confidence": _identity_conf_from_arb(arb_list, sid),
        })

    active_command: dict | None = None
    if winner_id:
        winner_spk = next((s for s in speakers if s["id"] == winner_id), None)
        if winner_spk:
            ir = winner_spk.get("intent_result") or {}
            active_command = {
                "speaker_id":          winner_id,
                "identity":            winner_spk.get("identity", "UNKNOWN"),
                "known_user":          winner_spk.get("known_user", False),
                "transcript":          winner_spk.get("transcript", ""),
                "domain":              ir.get("domain", "UNKNOWN"),
                "polarity":            ir.get("polarity", "NEUTRAL"),
                "intent_confidence":   float(ir.get("confidence", 0.0)),
                "entities":            ir.get("entities", {}),
                "wakeword":            winner_spk.get("wakeword", False),
                "wakeword_phrase":     winner_spk.get("wakeword_phrase"),
                "wakeword_confidence": float(winner_spk.get("wakeword_confidence", 0.0)),
                "priority_score":      _priority_from_arb(arb_list, winner_id),
            }

    conflict_detected = context.get("conflict", False)
    conflict_pair = context.get("conflict_pair")
    conflict_block = {
        "detected":      conflict_detected,
        "conflict_pair": conflict_pair,
        "description": (
            f"Conflicting commands detected: {conflict_pair[0]!r} vs {conflict_pair[1]!r}."
            if conflict_detected and conflict_pair
            else "No conflict."
        ),
    }

    sequential_queue: list[dict] = []
    if route == "SEQUENTIAL":
        active_sorted_spk = sorted(
            [s for s in speakers if s.get("wakeword") and s.get("type") == "COMMAND"],
            key=lambda s: s.get("priority_score", 0.0),
            reverse=True,
        )
        for order, spk in enumerate(active_sorted_spk, start=1):
            ir = spk.get("intent_result") or {}
            sequential_queue.append({
                "order":      order,
                "speaker_id": spk["id"],
                "identity":   spk.get("identity", "UNKNOWN"),
                "known_user": bool(spk.get("known_user", False)),
                "domain":     ir.get("domain", "UNKNOWN"),
                "transcript": spk.get("transcript", ""),
                "entities":   ir.get("entities", {}) or {},
                "polarity":   ir.get("polarity", "POSITIVE"),
            })

    clarification_prompt: str | None = None
    if route == "CLARIFY":
        active_arb = [
            s for s in arb_list
            if s.get("wakeword") and s.get("type") == "COMMAND"
        ]
        names = " and ".join(
            s["identity"] if s.get("known_user") else s["id"]
            for s in sorted(active_arb, key=lambda s: s.get("priority", 0), reverse=True)[:2]
        )
        clarification_prompt = (
            f"I heard commands from {names}. "
            f"Whose command should I execute?"
        )

    priority_log = _build_priority_log(arb_result, speakers)

    llm_prompt = _build_llm_prompt(
        route=route,
        active_command=active_command,
        conflict=conflict_block,
        clarification_prompt=clarification_prompt,
        sequential_queue=sequential_queue,
    )

    scene = context.get("scene", {})
    scene_block = {
        "drs_mode":      context.get("drs_mode", "?"),
        "speaker_count": scene.get("speaker_count", 0),
        "complexity":    scene.get("complexity", 0.0),
        "noise_level":   scene.get("noise_level", 0.0),
        "simul_speech":  scene.get("simul_speech", 0.0),
    }

    response: dict = {
        "schema_version":      "1.0",
        "timestamp":           datetime.datetime.now().isoformat(),
        "session_dir":         str(out_dir),
        "scene":               scene_block,
        "active_command":      active_command,
        "route":               route,
        "route_reason":        arb_result.get("reason", ""),
        "all_speakers":        all_speakers,
        "conflict":            conflict_block,
        "sequential_queue":    sequential_queue,
        "clarification_prompt": clarification_prompt,
        "llm_prompt":          llm_prompt,
        "priority_engine_log": priority_log,
    }

    rsp_path = out_dir / "response.json"
    rsp_path.write_text(
        json.dumps(response, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return response


def print_response_summary(response: dict) -> None:
    route = response.get("route", "?")
    ac    = response.get("active_command")
    scene = response.get("scene", {})

    print()
    print("  ── Intent ───────────────────────────────────────")
    print(f"  Route: {route} — {response.get('route_reason', '')[:80]}")

    if ac:
        ident = ac.get("identity", "UNKNOWN")
        domain = ac.get("domain", "UNKNOWN")
        polarity = ac.get("polarity", "NEUTRAL")
        conf = ac.get("intent_confidence", 0.0)
        entities = ac.get("entities", {})
        print(f"  Winner: {ident}  ·  {domain} ({polarity}, {conf:.2f})")
        if entities:
            print(f"  Entities: {entities}")
        tx = ac.get("transcript", "")
        if tx:
            preview = tx[:72] + ("..." if len(tx) > 72 else "")
            print(f"  \"{preview}\"")

    cp = response.get("clarification_prompt")
    if cp:
        print()
        print(f"  Clarify   : \"{cp}\"")

    sq = response.get("sequential_queue", [])
    if sq:
        print()
        print("  Sequential queue:")
        for entry in sq:
            print(f"    {entry['order']}. {entry['identity']} — {entry['domain']} — \"{entry['transcript'][:50]}\"")

    print()
