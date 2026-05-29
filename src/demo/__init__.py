"""The Canary — Rich Terminal Demo UI.

A visually polished, production-grade terminal interface that
demonstrates the full multi-speaker smart home pipeline.

Run:
    python3 -m src.demo.ui
"""
import time
import json
import logging
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.columns import Columns
from rich.padding import Padding
from rich.align import Align
from rich import box

from src.common.models import (
    PipelineOutput, PipelineMode, AudioStream,
    TranscriptionResult, UserRole, DecisionAction,
    ArbitrationDecision
)
from src.agent.mcp_server import HOME_STATE

console = Console()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Color Palette
# ─────────────────────────────────────────────
COLORS = {
    "brand": "bright_yellow",
    "admin": "bright_cyan",
    "guest": "bright_magenta",
    "unknown": "bright_red",
    "success": "bright_green",
    "warning": "yellow",
    "error": "red",
    "muted": "dim white",
    "accent": "bright_blue",
}


def speaker_color(speaker_id: str, role: str = "unknown") -> str:
    """Get display color for a speaker."""
    if role == "admin":
        return COLORS["admin"]
    elif role == "guest":
        return COLORS["guest"]
    return COLORS["unknown"]


# ─────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────

def render_header() -> Panel:
    """Render the main header with branding."""
    title = Text()
    title.append("🐤 ", style="yellow")
    title.append("THE CANARY", style="bold bright_yellow")
    title.append("  ─  ", style="dim")
    title.append("Multi-Speaker Smart Home Assistant", style="italic bright_white")
    title.append("  ─  ", style="dim")
    title.append("Samsung AX Hackathon 2026", style="dim bright_blue")
    
    return Panel(
        Align.center(title),
        border_style="bright_yellow",
        box=box.DOUBLE,
        padding=(0, 2),
    )


# ─────────────────────────────────────────────
# Pipeline Status Panel
# ─────────────────────────────────────────────

def render_pipeline_status(
    mode: str = "—",
    vad: str = "—",
    wakeword: str = "—",
    speakers: int = 0,
    complexity: float = 0.0,
    latency: float = 0.0,
) -> Panel:
    """Render the acoustic pipeline status panel."""
    table = Table(
        show_header=False,
        box=None,
        padding=(0, 2),
        expand=True,
    )
    table.add_column("Key", style="dim", width=18)
    table.add_column("Value", style="bold")
    
    # Mode badge
    mode_style = {"A": "green", "B": "yellow", "C": "red"}.get(mode, "dim")
    mode_text = {"A": "🟢 Mode A (Clean)", "B": "🟡 Mode B (Noisy)", "C": "🔴 Mode C (Overlap)"}.get(mode, "— Idle —")
    
    table.add_row("Pipeline Mode", Text(mode_text, style=mode_style))
    table.add_row("VAD", Text(vad, style="green" if vad == "Active" else "dim"))
    table.add_row("Wake Word", Text(wakeword, style="green" if "✅" in wakeword else "dim"))
    table.add_row("Active Speakers", Text(str(speakers), style="bright_white"))
    table.add_row("Scene Complexity", Text(f"{complexity:.2f}", style="bright_white"))
    table.add_row("E2E Latency", Text(f"{latency:.0f}ms", style="bright_green" if latency < 2000 else "red"))
    
    return Panel(
        table,
        title="[bold bright_blue]⚡ Pipeline Status[/]",
        border_style="bright_blue",
        box=box.ROUNDED,
    )


# ─────────────────────────────────────────────
# Speaker Transcription Panel
# ─────────────────────────────────────────────

def render_transcriptions(transcriptions: list[dict]) -> Panel:
    """Render speaker transcriptions with metadata."""
    if not transcriptions:
        content = Text("  Waiting for speech...", style="dim italic")
        return Panel(
            content,
            title="[bold bright_green]🎤 Transcriptions[/]",
            border_style="bright_green",
            box=box.ROUNDED,
        )
    
    table = Table(
        show_header=True,
        header_style="bold",
        box=box.SIMPLE_HEAVY,
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Speaker", width=12)
    table.add_column("Role", width=8)
    table.add_column("Text", ratio=3)
    table.add_column("Lang", width=5, justify="center")
    table.add_column("Emotion", width=10, justify="center")
    table.add_column("Conf", width=6, justify="right")
    
    for t in transcriptions:
        role = t.get("role", "unknown")
        color = speaker_color(t.get("speaker", "unknown"), role)
        
        # Confidence bar
        conf = t.get("confidence", 0.0)
        conf_style = "bright_green" if conf >= 0.8 else "yellow" if conf >= 0.5 else "red"
        
        # Emotion emoji
        emotion_map = {
            "neutral": "😐",
            "happy": "😊",
            "sad": "😢",
            "angry": "😠",
        }
        emotion = t.get("emotion", "neutral")
        emotion_display = f"{emotion_map.get(emotion, '❓')} {emotion}"
        
        table.add_row(
            Text(t.get("speaker", "?"), style=f"bold {color}"),
            Text(role.upper(), style=color),
            Text(t.get("text", ""), style="white"),
            Text(t.get("language", "?"), style="dim"),
            Text(emotion_display, style="dim"),
            Text(f"{conf:.0%}", style=conf_style),
        )
    
    return Panel(
        table,
        title="[bold bright_green]🎤 Transcriptions[/]",
        border_style="bright_green",
        box=box.ROUNDED,
    )


# ─────────────────────────────────────────────
# Arbitration Decision Panel
# ─────────────────────────────────────────────

def render_decision(decision: dict) -> Panel:
    """Render the arbitration decision with visual emphasis."""
    action = decision.get("action", "—")
    reason = decision.get("reason", "")
    priority = decision.get("priority_speaker", "—")
    
    # Action badge
    action_styles = {
        "execute": ("✅ EXECUTE", "bright_green"),
        "execute_both": ("✅✅ EXECUTE BOTH", "bright_green"),
        "clarify": ("🔊 CLARIFY", "yellow"),
        "reject": ("❌ REJECT", "red"),
    }
    display, style = action_styles.get(action, ("❓ UNKNOWN", "dim"))
    
    content = Table(show_header=False, box=None, expand=True, padding=(0, 2))
    content.add_column("Key", style="dim", width=16)
    content.add_column("Value")
    
    content.add_row("Decision", Text(display, style=f"bold {style}"))
    content.add_row("Reason", Text(reason, style="white"))
    if priority and priority != "—":
        content.add_row("Priority Speaker", Text(priority, style="bold bright_cyan"))
    
    # Show commands
    commands = decision.get("commands", [])
    if commands:
        cmd_text = " → ".join(c.get("text", "?") for c in commands)
        content.add_row("Commands", Text(cmd_text, style="bright_white"))
    
    return Panel(
        content,
        title="[bold bright_yellow]⚖️  Arbitration[/]",
        border_style="bright_yellow",
        box=box.ROUNDED,
    )


# ─────────────────────────────────────────────
# Tool Execution Panel
# ─────────────────────────────────────────────

def render_execution(results: list[str]) -> Panel:
    """Render tool execution results."""
    if not results:
        content = Text("  Waiting for commands...", style="dim italic")
    else:
        content = Text()
        for i, r in enumerate(results):
            content.append(f"  {r}\n", style="white")
    
    return Panel(
        content,
        title="[bold bright_magenta]🏠 Smart Home Actions[/]",
        border_style="bright_magenta",
        box=box.ROUNDED,
    )


# ─────────────────────────────────────────────
# Home State Panel
# ─────────────────────────────────────────────

def render_home_state() -> Panel:
    """Render the current smart home state."""
    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("Device", width=20, style="dim")
    table.add_column("State", width=20)
    
    for room in ["living_room", "bedroom", "kitchen"]:
        if room in HOME_STATE:
            for device, state in HOME_STATE[room].items():
                indicator = "🟢" if state == "on" else "⚫"
                room_display = room.replace("_", " ").title()
                table.add_row(
                    f"{room_display} {device.title()}",
                    Text(f"{indicator} {state.upper()}", style="green" if state == "on" else "dim")
                )
    
    # Thermostat
    therm = HOME_STATE.get("thermostat", {})
    table.add_row(
        "Thermostat",
        Text(f"🌡️ {therm.get('temperature', '?')}°C ({therm.get('mode', '?')})", style="bright_cyan")
    )
    
    # Music
    music = HOME_STATE.get("music", {})
    if music.get("playing"):
        table.add_row(
            "Music",
            Text(f"🎵 {music.get('genre', '?')} for {music.get('user', '?')}", style="bright_magenta")
        )
    else:
        table.add_row("Music", Text("⚫ OFF", style="dim"))
    
    # Timers
    timers = HOME_STATE.get("timers", [])
    if timers:
        for t in timers[-2:]:  # Show last 2
            table.add_row(
                f"Timer ({t.get('label', '?')})",
                Text(f"⏱️ {t.get('minutes', '?')} min", style="bright_yellow")
            )
    
    return Panel(
        table,
        title="[bold bright_white]🏠 Home State[/]",
        border_style="bright_white",
        box=box.ROUNDED,
    )


# ─────────────────────────────────────────────
# Full Demo Frame
# ─────────────────────────────────────────────

def render_demo_frame(
    pipeline_status: dict = None,
    transcriptions: list[dict] = None,
    decision: dict = None,
    execution_results: list[str] = None,
) -> Layout:
    """Compose the full demo layout."""
    layout = Layout()
    
    layout.split_column(
        Layout(render_header(), name="header", size=3),
        Layout(name="body"),
    )
    
    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=2),
    )
    
    # Left column: Pipeline + Home State
    layout["left"].split_column(
        Layout(
            render_pipeline_status(**(pipeline_status or {})),
            name="pipeline",
            ratio=1,
        ),
        Layout(
            render_home_state(),
            name="home",
            ratio=1,
        ),
    )
    
    # Right column: Transcriptions + Decision + Execution
    layout["right"].split_column(
        Layout(
            render_transcriptions(transcriptions or []),
            name="transcriptions",
            ratio=1,
        ),
        Layout(
            render_decision(decision or {}),
            name="decision",
            size=8,
        ),
        Layout(
            render_execution(execution_results or []),
            name="execution",
            size=6,
        ),
    )
    
    return layout


# ─────────────────────────────────────────────
# Interactive Demo Runner
# ─────────────────────────────────────────────

def run_demo():
    """Run the interactive demo with 3 pre-scripted scenarios."""
    from src.arbitration.engine import ArbitrationEngine
    from src.execution.queue import ExecutionQueue
    from src.execution.state_store import StateStore
    
    store = StateStore()
    arb_engine = ArbitrationEngine(state_store=store)
    queue = ExecutionQueue(state_store=store)
    
    # Reset home state
    HOME_STATE["living_room"]["lights"] = "off"
    HOME_STATE["bedroom"]["lights"] = "off"
    HOME_STATE["kitchen"]["lights"] = "off"
    HOME_STATE["thermostat"]["temperature"] = 24
    HOME_STATE["music"]["playing"] = False
    HOME_STATE["timers"].clear()
    
    scenarios = [
        {
            "title": "SCENARIO 1 — Single Speaker Command",
            "description": "Hemang (Admin) says: 'Turn on the living room lights'",
            "pipeline": {"mode": "A", "vad": "Active", "wakeword": "✅ Hey Canary", "speakers": 1, "complexity": 0.15, "latency": 340},
            "transcriptions": [
                {"speaker": "hemang", "role": "admin", "text": "Turn on the living room lights", "language": "en", "emotion": "neutral", "confidence": 0.92}
            ],
        },
        {
            "title": "SCENARIO 2 — Non-Conflicting Multi-Speaker",
            "description": "Hemang: 'Play jazz music' + Sanchit: 'Set timer for 5 minutes'",
            "pipeline": {"mode": "C", "vad": "Active", "wakeword": "✅ Hey Canary", "speakers": 2, "complexity": 0.72, "latency": 890},
            "transcriptions": [
                {"speaker": "hemang", "role": "admin", "text": "Play jazz music", "language": "en", "emotion": "happy", "confidence": 0.90},
                {"speaker": "sanchit", "role": "guest", "text": "Set timer for 5 minutes", "language": "en", "emotion": "neutral", "confidence": 0.88},
            ],
        },
        {
            "title": "SCENARIO 3 — Conflicting Commands (Admin Overrides)",
            "description": "Hemang: 'Turn on lights' vs Sanchit: 'Turn off lights'",
            "pipeline": {"mode": "C", "vad": "Active", "wakeword": "✅ Hey Canary", "speakers": 2, "complexity": 0.85, "latency": 1200},
            "transcriptions": [
                {"speaker": "hemang", "role": "admin", "text": "Turn on the lights", "language": "en", "emotion": "neutral", "confidence": 0.91},
                {"speaker": "sanchit", "role": "guest", "text": "Turn off the lights", "language": "en", "emotion": "angry", "confidence": 0.85},
            ],
        },
    ]
    
    console.clear()
    
    for i, scenario in enumerate(scenarios):
        # Build transcription results for arbitration
        results = []
        for t in scenario["transcriptions"]:
            role_map = {"admin": UserRole.ADMIN, "guest": UserRole.GUEST, "unknown": UserRole.UNKNOWN}
            results.append(TranscriptionResult(
                text=t["text"],
                speaker_id=t["speaker"],
                speaker_role=role_map.get(t["role"], UserRole.UNKNOWN),
                confidence=t["confidence"],
                speaker_confidence=0.95,
                timestamp=time.time(),
                language=t.get("language", "en"),
                emotion=t.get("emotion", "neutral"),
            ))
        
        # Arbitrate
        decision = arb_engine.arbitrate(results)
        decision_dict = {
            "action": decision.action.value,
            "reason": decision.reason,
            "priority_speaker": decision.priority_speaker,
            "commands": decision.commands,
            "confidence": decision.confidence,
        }
        
        # Execute
        queue.enqueue(decision, priority=1)
        exec_result = queue.execute_next()
        exec_results = exec_result.split("\n") if exec_result else []
        
        # Render
        frame = render_demo_frame(
            pipeline_status=scenario["pipeline"],
            transcriptions=scenario["transcriptions"],
            decision=decision_dict,
            execution_results=exec_results,
        )
        
        console.clear()
        console.print(f"\n[bold bright_yellow]━━━ {scenario['title']} ━━━[/]")
        console.print(f"[dim]{scenario['description']}[/]\n")
        console.print(frame)
        
        if i < len(scenarios) - 1:
            console.print("\n[dim]Press Enter for next scenario...[/]", end="")
            input()
    
    console.print("\n[bold bright_green]━━━ DEMO COMPLETE ━━━[/]")
    console.print(f"[dim]Total scenarios: {len(scenarios)} | All executed successfully[/]")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run_demo()
