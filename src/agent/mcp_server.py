"""MCP Server — Smart home tool definitions for The Canary.

Exposes mocked smart-home actions as MCP tools that the SLM
can invoke via FastMCP. All hardware actuation is simulated.
"""
# TODO: Uncomment when fastmcp is installed
# from fastmcp import FastMCP

import json
import time


# Simulated smart home state
HOME_STATE = {
    "living_room": {"lights": "off", "tv": "off", "ac": "off"},
    "bedroom": {"lights": "off", "fan": "off", "ac": "off"},
    "kitchen": {"lights": "off"},
    "thermostat": {"temperature": 24},
    "timers": [],
    "music": {"playing": False, "genre": None, "user": None},
}


def create_mcp_server():
    """Create and configure the FastMCP server with smart home tools."""
    # TODO: Initialize FastMCP server
    # mcp = FastMCP("canary-smart-home")
    # Register tools below
    # return mcp
    pass


def toggle_lights(room: str, state: str) -> str:
    """Turn lights on/off in a room.
    
    Args:
        room: Room name (living_room, bedroom, kitchen)
        state: 'on' or 'off'
    """
    room_key = room.lower().replace(" ", "_")
    if room_key in HOME_STATE and "lights" in HOME_STATE[room_key]:
        HOME_STATE[room_key]["lights"] = state
        return f"✅ Lights turned {state.upper()} in {room}"
    return f"❌ Room '{room}' not found"


def set_thermostat(temperature: int) -> str:
    """Set thermostat to target temperature."""
    HOME_STATE["thermostat"]["temperature"] = temperature
    return f"✅ Thermostat set to {temperature}°C"


def play_music(genre: str, user: str) -> str:
    """Play music for a specific user."""
    HOME_STATE["music"] = {"playing": True, "genre": genre, "user": user}
    return f"✅ Playing {genre} music for {user}"


def stop_music() -> str:
    """Stop currently playing music."""
    HOME_STATE["music"] = {"playing": False, "genre": None, "user": None}
    return f"✅ Music stopped"


def set_timer(minutes: int) -> str:
    """Set a countdown timer."""
    HOME_STATE["timers"].append({"minutes": minutes, "set_at": time.time()})
    return f"✅ Timer set for {minutes} minutes"


def get_weather() -> str:
    """Get current weather (mocked)."""
    return "🌤️ Currently 28°C, Partly Cloudy in Bangalore"


def request_clarification(reason: str) -> str:
    """Ask the user to repeat or clarify their command."""
    return f"🔊 I heard conflicting commands. {reason}. Could you please repeat?"


def get_home_state() -> str:
    """Return current smart home state (for debugging/UI)."""
    return json.dumps(HOME_STATE, indent=2)
