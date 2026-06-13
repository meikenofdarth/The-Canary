"""
execution/queue.py
===================
Execution Queue Manager.
Reads the arbitration decision and executes commands using the SLM/MCP server.
"""

from .mcp_server import execute_intent

def process_arbitration(context_payload: dict):
    """
    Takes the context.json payload containing arbitration route and executes it.
    """
    route = context_payload.get("route", "IGNORE")
    arbitration_data = context_payload.get("arbitration", {})
    speakers = arbitration_data.get("speakers", context_payload.get("speakers", []))
    
    print("\n  ╔══════════════════════════════════════════════════╗")
    print("  ║   EXECUTION ENGINE                              ║")
    print("  ╚══════════════════════════════════════════════════╝")
    
    if route == "IGNORE":
        print("  [Queue] Route is IGNORE. No action taken.")
        return
        
    elif route == "CLARIFY":
        print("  [Queue] Route is CLARIFY. Awaiting user clarification (Interactive mode not implemented in CLI).")
        return
        
    elif route == "EXECUTE":
        # Find the winner using the arbitration data
        winner_id = arbitration_data.get("winner")
        if not winner_id:
            print("  [Queue] Error: Route is EXECUTE but no winner found.")
            return
            
        winner = next((s for s in speakers if s.get("id") == winner_id), None)
        if not winner:
            print(f"  [Queue] Error: Winner {winner_id} not found in speakers list.")
            return
            
        spk_id = winner.get("identity") if winner.get("known_user") else winner.get("id", "Unknown")
        intent = winner.get("intent", "GENERAL_COMMAND")
        text = winner.get("transcript", "")
        
        print(f"  [Queue] Single Execution for {spk_id}")
        execute_intent(intent, text)
        
    elif route == "SEQUENTIAL":
        commands = [s for s in speakers if s.get("wakeword") and s.get("type") == "COMMAND"]
        print(f"  [Queue] Sequential Execution for {len(commands)} commands")
        for cmd in commands:
            spk_id = cmd.get("identity") if cmd.get("known_user") else cmd.get("id", "Unknown")
            intent = cmd.get("intent", "GENERAL_COMMAND")
            text = cmd.get("transcript", "")
            print(f"  --- Executing for {spk_id} ---")
            execute_intent(intent, text)
            
    print("  ─────────────────────────────────────────────\n")
