"""
execution/queue.py
===================
Execution Queue Manager.
Reads the arbitration decision and executes commands using the SLM/MCP server.
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

def process_arbitration(context_payload: dict):
    """
    Takes the context.json payload containing arbitration route and executes it.
    """
    route = context_payload.get("route", "IGNORE")
    arbitration_data = context_payload.get("arbitration", {})
    speakers = arbitration_data.get("speakers", context_payload.get("speakers", []))
    
    profiles = load_user_profiles()
    
    print("\n  ╔══════════════════════════════════════════════════╗")
    print("  ║   EXECUTION ENGINE                              ║")
    print("  ╚══════════════════════════════════════════════════╝")
    
    # 1. Check for Known-User Conflict Override
    commands = [s for s in speakers if s.get("wakeword") and s.get("type") == "COMMAND"]
    known_user_commands = [c for c in commands if c.get("known_user")]
    
    if len(known_user_commands) >= 2:
        # If there are multiple commands from known users, we ask to clarify, 
        # overriding the normal arbitration output!
        print("  [Queue] Override: Conflicting commands from multiple known users.")
        names = [c.get("identity", "Unknown") for c in known_user_commands]
        name_str = " and ".join(names)
        speak(f"I heard multiple requests from {name_str}. Please clarify who I should listen to.")
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
        winner_id = arbitration_data.get("winner")
        if not winner_id:
            print("  [Queue] Error: Route is EXECUTE but no winner found.")
            return
            
        winner = next((s for s in speakers if s.get("id") == winner_id), None)
        if not winner:
            return
            
        identity = winner.get("identity", "Unknown")
        spk_id = identity if winner.get("known_user") else winner.get("id", "Unknown")
        intent = winner.get("intent", "GENERAL_COMMAND")
        text = winner.get("transcript", "")
        
        print(f"  [Queue] Single Execution for {spk_id}")
        profile = profiles.get(identity) if winner.get("known_user") else None
        execute_intent(intent, text, profile)
        
    elif route == "SEQUENTIAL":
        print(f"  [Queue] Sequential Execution for {len(commands)} commands")
        for cmd in commands:
            identity = cmd.get("identity", "Unknown")
            spk_id = identity if cmd.get("known_user") else cmd.get("id", "Unknown")
            intent = cmd.get("intent", "GENERAL_COMMAND")
            text = cmd.get("transcript", "")
            
            print(f"  --- Executing for {spk_id} ---")
            profile = profiles.get(identity) if cmd.get("known_user") else None
            execute_intent(intent, text, profile)
            
    print("  ─────────────────────────────────────────────\n")
