"""
execution/mcp_server.py
========================
Mock MCP (Model Context Protocol) Server.
Contains minimally working simulated SmartHome tools for execution.
"""

def control_smart_home(device: str, state: str) -> dict:
    """Mock tool to control smart home devices."""
    print(f"    [SmartHome] ⚙️ Executing: Turn {device} {state}")
    return {"status": "success", "message": f"{device} turned {state}"}

def play_media(media_type: str, query: str = "") -> dict:
    """Mock tool to play media."""
    action = f"Playing {media_type}"
    if query:
        action += f" ({query})"
    print(f"    [Media] 🎵 Executing: {action}")
    return {"status": "success", "message": action}

def stop_media() -> dict:
    """Mock tool to stop media."""
    print(f"    [Media] ⏹️ Executing: Stopping all media playback")
    return {"status": "success", "message": "Media stopped"}

def get_weather(location: str = "current location") -> dict:
    """Mock tool to get weather."""
    print(f"    [Weather] 🌤️ Executing: Fetching weather for {location}")
    return {"status": "success", "message": f"Weather in {location}: 72°F and sunny"}

# Registry mapping intents (from context_engine) to tools
INTENT_TOOL_MAP = {
    "DEVICE_ON": (control_smart_home, {"state": "ON"}),
    "DEVICE_OFF": (control_smart_home, {"state": "OFF"}),
    "PLAY_MEDIA": (play_media, {"media_type": "music"}),
    "STOP_MEDIA": (stop_media, {}),
    "WEATHER": (get_weather, {}),
}

def execute_intent(intent: str, transcript: str) -> dict:
    """
    Given a coarse intent and transcript, invoke the appropriate mock tool.
    In a real system, an SLM Agent would parse the transcript to extract args.
    """
    if not intent or intent not in INTENT_TOOL_MAP:
        print(f"    [Agent] ❓ No specific tool for intent '{intent}' (Transcript: {transcript})")
        return {"status": "ignored", "message": "No matching tool"}

    func, default_args = INTENT_TOOL_MAP[intent]
    
    # Very rudimentary arg extraction just to look nice in the CLI output
    args = dict(default_args)
    if func == control_smart_home:
        # Extract device naively
        t = transcript.lower()
        if "light" in t: args["device"] = "lights"
        elif "thermostat" in t: args["device"] = "thermostat"
        elif "tv" in t: args["device"] = "TV"
        else: args["device"] = "device"
        
    elif func == play_media:
        args["query"] = transcript
        
    return func(**args)
