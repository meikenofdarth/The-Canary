"""
execution/queue.py
===================
Execution Queue Manager.
Reads the response.json payload and executes commands using the SLM/MCP server.
"""

import json
from pathlib import Path
from .mcp_server import execute_intent
from .tts import speak

def load_user_profiles():
    profiles_path = Path(__file__).parent / "user_profiles.json"
    if profiles_path.exists():
        with open(profiles_path, "r") as f:
            return json.load(f)
    return {}

def process_arbitration(response_payload: dict):
    """
    Takes the response.json payload containing arbitration route and executes it.
    """
    route = response_payload.get("route", "IGNORE")
    all_speakers = response_payload.get("all_speakers", [])
    active_command = response_payload.get("active_command", {})
    sequential_queue = response_payload.get("sequential_queue", [])
    
    profiles = load_user_profiles()
    
    print("\n  ╔══════════════════════════════════════════════════╗")
    print("  ║   EXECUTION ENGINE                              ║")
    print("  ╚══════════════════════════════════════════════════╝")
    
    # 1. Check for Known-User Conflict Override
    commands = [s for s in all_speakers if s.get("wakeword") and s.get("domain")]
    known_user_commands = [c for c in commands if c.get("known_user")]
    
    # Check if there's an actual conflict flag from Hemang's engine
    conflict_data = response_payload.get("conflict", {})
    is_conflict = conflict_data.get("detected", False)
    
    if is_conflict and len(known_user_commands) >= 2:
        # If there are multiple commands from known users AND they conflict, we ask to clarify, 
        # overriding the normal arbitration output!
        print("  [Queue] Override: Conflicting commands from multiple known users.")
        names = [c.get("identity", "Unknown") for c in known_user_commands]
        name_str = " and ".join(names)
        speak(f"I heard multiple conflicting requests from {name_str}. Please clarify who I should listen to.")
        return
    
    # 2. Proceed with normal routing
    if route == "IGNORE":
        print("  [Queue] Route is IGNORE. No action taken.")
        return
        
    elif route == "CLARIFY":
        print("  [Queue] Route is CLARIFY. Awaiting user clarification.")
        speak("I heard multiple conflicting requests. Could you please clarify?")
        return
        
    elif route == "EXECUTE":
        if not active_command:
            print("  [Queue] Error: Route is EXECUTE but no active_command found.")
            return
            
        identity = active_command.get("identity", "Unknown")
        spk_id = identity if active_command.get("known_user") else active_command.get("speaker_id", "Unknown")
        domain = active_command.get("domain", "UNKNOWN")
        text = active_command.get("transcript", "")
        entities = active_command.get("entities", {})
        polarity = active_command.get("polarity", "POSITIVE")
        
        print(f"  [Queue] Single Execution for {spk_id}")
        profile = profiles.get(identity) if active_command.get("known_user") else None
        execute_intent(domain, text, profile, entities, polarity)
        
    elif route == "SEQUENTIAL":
        print(f"  [Queue] Sequential Execution for {len(sequential_queue)} commands")
        for cmd in sequential_queue:
            identity = cmd.get("identity", "Unknown")
            spk_id = identity if cmd.get("known_user") else cmd.get("speaker_id", "Unknown")
            domain = cmd.get("domain", "UNKNOWN")
            text = cmd.get("transcript", "")
            entities = cmd.get("entities", {})
            polarity = cmd.get("polarity", "POSITIVE")
            
            print(f"  --- Executing for {spk_id} ---")
            profile = profiles.get(identity) if cmd.get("known_user") else None
            execute_intent(domain, text, profile, entities, polarity)
            
    print("  ─────────────────────────────────────────────\n")
