"""MCP Server — Smart home tool definitions for The Canary.

Exposes mocked smart-home actions as MCP tools that the SLM
can invoke via FastMCP. All hardware actuation is simulated.

Usage:
    # Standalone server (for testing):
    python3 -m src.agent.mcp_server

    # Programmatic use:
    from src.agent.mcp_server import mcp, HOME_STATE
"""
import json
import time
import logging
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Initialize MCP Server
# ─────────────────────────────────────────────

mcp = FastMCP(
    "canary-smart-home",
    instructions=(
        "You are The Canary smart home controller. "
        "Use these tools to control household devices based on voice commands. "
        "Always check user permissions before executing restricted actions."
    ),
)

# ─────────────────────────────────────────────
# Simulated Smart Home State
# ─────────────────────────────────────────────

HOME_STATE = {
    "living_room": {"lights": "off", "tv": "off", "ac": "off"},
    "bedroom": {"lights": "off", "fan": "off", "ac": "off"},
    "kitchen": {"lights": "off"},
    "thermostat": {"temperature": 24, "mode": "cool"},
    "timers": [],
    "music": {"playing": False, "genre": None, "user": None},
}

# User permission sets
USER_PERMISSIONS = {
    "hemang": {"role": "admin", "permissions": ["all"]},
    "sanchit": {"role": "guest", "permissions": ["lights", "music", "timer", "weather"]},
}


# ─────────────────────────────────────────────
# MCP Tools
# ─────────────────────────────────────────────

@mcp.tool()
def toggle_lights(room: str, state: str) -> str:
    """Turn lights on or off in a specific room.

    Args:
        room: Room name — one of 'living_room', 'bedroom', 'kitchen'
        state: Target state — 'on' or 'off'
    """
    room_key = room.lower().replace(" ", "_")
    if room_key not in HOME_STATE:
        return f"❌ Room '{room}' not found. Available: {', '.join(k for k in HOME_STATE if k not in ('thermostat', 'timers', 'music'))}"
    if "lights" not in HOME_STATE[room_key]:
        return f"❌ No lights in {room}"

    old_state = HOME_STATE[room_key]["lights"]
    HOME_STATE[room_key]["lights"] = state.lower()
    logger.info("Lights %s → %s in %s", old_state, state, room)
    return f"✅ Lights turned {state.upper()} in {room} (was {old_state})"


@mcp.tool()
def set_thermostat(temperature: int, mode: str = "cool") -> str:
    """Set the thermostat to a target temperature.

    Args:
        temperature: Target temperature in Celsius (16-30)
        mode: Operating mode — 'cool', 'heat', or 'auto'
    """
    if not 16 <= temperature <= 30:
        return f"❌ Temperature must be between 16°C and 30°C (got {temperature})"

    old_temp = HOME_STATE["thermostat"]["temperature"]
    HOME_STATE["thermostat"]["temperature"] = temperature
    HOME_STATE["thermostat"]["mode"] = mode
    logger.info("Thermostat %d°C → %d°C (%s)", old_temp, temperature, mode)
    return f"✅ Thermostat set to {temperature}°C ({mode} mode). Was {old_temp}°C."


@mcp.tool()
def play_music(genre: str, user: str = "unknown") -> str:
    """Play music of a specific genre for a user.

    Args:
        genre: Music genre — e.g., 'jazz', 'rock', 'classical', 'pop'
        user: Who requested the music
    """
    HOME_STATE["music"] = {"playing": True, "genre": genre, "user": user}
    logger.info("Playing %s for %s", genre, user)
    return f"✅ Playing {genre} music for {user} 🎵"


@mcp.tool()
def stop_music() -> str:
    """Stop the currently playing music."""
    was_playing = HOME_STATE["music"].get("genre", "nothing")
    HOME_STATE["music"] = {"playing": False, "genre": None, "user": None}
    logger.info("Music stopped (was: %s)", was_playing)
    return f"✅ Music stopped (was playing: {was_playing})"


@mcp.tool()
def set_timer(minutes: int, label: str = "timer") -> str:
    """Set a countdown timer.

    Args:
        minutes: Duration in minutes (1-120)
        label: Optional label for the timer
    """
    if not 1 <= minutes <= 120:
        return f"❌ Timer must be between 1 and 120 minutes (got {minutes})"

    timer_entry = {"minutes": minutes, "label": label, "set_at": time.time()}
    HOME_STATE["timers"].append(timer_entry)
    logger.info("Timer set: %d min (%s)", minutes, label)
    return f"✅ Timer set for {minutes} minutes ({label}) ⏱️"


@mcp.tool()
def get_weather() -> str:
    """Get the current weather conditions (simulated)."""
    return "🌤️ Currently 28°C, Partly Cloudy in Bangalore. Humidity: 65%. UV Index: 6."


@mcp.tool()
def request_clarification(reason: str) -> str:
    """Ask the user to repeat or clarify their command.

    Args:
        reason: Why clarification is needed
    """
    return f"🔊 I heard conflicting commands. {reason}. Could you please repeat?"


@mcp.tool()
def check_user_permission(user_id: str, action: str) -> str:
    """Check if a user has permission to perform an action.

    Args:
        user_id: The speaker's ID
        action: The action to check — e.g., 'lights', 'thermostat', 'music'
    """
    user = USER_PERMISSIONS.get(user_id)
    if not user:
        return f"❌ Unknown user '{user_id}' — no permissions granted"

    if user["role"] == "admin" or "all" in user["permissions"]:
        return f"✅ {user_id} (admin) has permission for '{action}'"

    if action.lower() in user["permissions"]:
        return f"✅ {user_id} (guest) has permission for '{action}'"

    return f"❌ {user_id} (guest) does NOT have permission for '{action}'. Allowed: {user['permissions']}"


@mcp.tool()
def get_home_state() -> str:
    """Return the full current smart home state (for debugging/UI)."""
    return json.dumps(HOME_STATE, indent=2, default=str)


# ─────────────────────────────────────────────
# Direct execution helpers (non-MCP)
# ─────────────────────────────────────────────

# Map of intent keywords to tool functions for rule-based routing
TOOL_ROUTER = {
    "lights": toggle_lights,
    "light": toggle_lights,
    "thermostat": set_thermostat,
    "temperature": set_thermostat,
    "music": play_music,
    "timer": set_timer,
    "weather": get_weather,
}


def route_command(text: str, speaker_id: str = "unknown") -> str:
    """Route a natural language command to the appropriate tool.
    
    This is the simple rule-based router used when SLM is unavailable.
    
    Args:
        text: Transcribed command text
        speaker_id: Who said it
        
    Returns:
        Tool execution result string
    """
    text_lower = text.lower()

    # Lights
    if "light" in text_lower:
        state = "on" if "on" in text_lower else "off"
        room = "living_room"  # default
        for r in ["bedroom", "kitchen", "living_room", "living room"]:
            if r in text_lower:
                room = r.replace(" ", "_")
                break
        return toggle_lights(room=room, state=state)

    # Thermostat
    if "thermostat" in text_lower or "temperature" in text_lower or "ac" in text_lower:
        # Extract number
        import re
        nums = re.findall(r'\d+', text)
        temp = int(nums[0]) if nums else 24
        mode = "heat" if "heat" in text_lower else "cool"
        return set_thermostat(temperature=temp, mode=mode)

    # Music
    if "music" in text_lower or "play" in text_lower:
        if "stop" in text_lower:
            return stop_music()
        genre = "jazz"  # default
        for g in ["rock", "jazz", "classical", "pop", "lofi", "hip hop"]:
            if g in text_lower:
                genre = g
                break
        return play_music(genre=genre, user=speaker_id)

    # Timer
    if "timer" in text_lower:
        import re
        nums = re.findall(r'\d+', text)
        minutes = int(nums[0]) if nums else 5
        return set_timer(minutes=minutes)

    # Weather
    if "weather" in text_lower:
        return get_weather()

    return f"❓ I didn't understand: '{text}'. Try: lights, music, thermostat, timer, or weather."


# ─────────────────────────────────────────────
# Run standalone
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Quick tool routing test
    print("🐤 The Canary — MCP Tool Router Test\n")

    test_commands = [
        ("turn on the lights", "hemang"),
        ("turn off the bedroom lights", "sanchit"),
        ("set thermostat to 22", "hemang"),
        ("play jazz music", "hemang"),
        ("play rock music", "sanchit"),
        ("stop music", "sanchit"),
        ("set timer for 10 minutes", "sanchit"),
        ("what's the weather", "hemang"),
        ("open the garage", "sanchit"),  # unknown command
    ]

    for cmd, speaker in test_commands:
        result = route_command(cmd, speaker)
        print(f"  [{speaker}] \"{cmd}\"")
        print(f"    → {result}\n")

    print(f"\n📊 Final home state:\n{json.dumps(HOME_STATE, indent=2)}")
