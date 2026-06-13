#!/usr/bin/env python3
"""
run_execution.py
================
CLI utility to process a response.json payload from The Canary and execute the
resulting intents using the simulated MCP server.

Usage:
    python3 run_execution.py [path/to/response.json]
    If no path is provided, it will automatically find the latest response.json in outputs/
"""

import sys
import json
from pathlib import Path
from execution.queue import process_arbitration

def get_latest_context():
    """Finds the most recently created response.json in the outputs directory."""
    outputs_dir = Path("outputs")
    if not outputs_dir.exists():
        return None
        
    # Get all response.json files sorted by modification time (newest first)
    contexts = list(outputs_dir.rglob("response.json"))
    if not contexts:
        return None
        
    contexts.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return contexts[0]

def main():
    target_file = None
    
    if len(sys.argv) > 1:
        target_file = Path(sys.argv[1])
        if not target_file.exists():
            print(f"Error: File '{target_file}' not found.")
            sys.exit(1)
    else:
        target_file = get_latest_context()
        if not target_file:
            print("Error: No context.json files found in outputs/")
            sys.exit(1)
            
    print(f"Reading context payload from: {target_file}")
    
    with open(target_file, "r") as f:
        try:
            payload = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            sys.exit(1)
            
    # Run the execution queue
    process_arbitration(payload)

if __name__ == "__main__":
    main()
