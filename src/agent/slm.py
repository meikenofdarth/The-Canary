"""SLM Integration — Ollama + Qwen2.5 for agentic reasoning.

Provides natural-language reasoning for complex conflict resolution.
This is SECONDARY to rule-based arbitration — a bonus for demo wow-factor.
"""
import json
from typing import Optional


# System prompt for the Canary arbitration agent
SYSTEM_PROMPT = """You are the Canary smart home arbitration agent. You receive structured 
transcriptions from multiple speakers in a household. Your job is to:
1. Identify if commands conflict
2. Check user authority (Admin > Guest)
3. Decide: execute, queue, or request clarification
4. Call the appropriate tool

RULES:
- Admin commands always override Guest commands on the same device
- Non-conflicting commands execute in parallel  
- If confidence < 0.5, always request clarification
- Never execute commands from unrecognized speakers

Available users:
- hemang: role=admin
- sanchit: role=guest

Respond with a JSON object:
{"action": "execute|clarify|reject", "tool": "tool_name", "args": {...}, "reason": "..."}
"""


class SLMClient:
    """Client for local SLM via Ollama."""
    
    def __init__(self, model: str = "qwen2.5:1.5b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.client = None
        # TODO: Initialize ollama client
        # import ollama
        # self.client = ollama.Client(host=base_url)
    
    def reason(self, transcriptions: list[dict], context: Optional[dict] = None) -> dict:
        """Send transcriptions to SLM for reasoning.
        
        Args:
            transcriptions: List of {"text": ..., "speaker_id": ..., "confidence": ...}
            context: Optional additional context (home state, history)
            
        Returns:
            Decision dict from SLM
        """
        user_message = f"""Transcriptions from pipeline:
{json.dumps(transcriptions, indent=2)}

{f'Context: {json.dumps(context)}' if context else ''}

Analyze and decide what action to take."""
        
        # TODO: Implement with ollama client
        # response = self.client.chat(
        #     model=self.model,
        #     messages=[
        #         {"role": "system", "content": SYSTEM_PROMPT},
        #         {"role": "user", "content": user_message}
        #     ]
        # )
        # return json.loads(response["message"]["content"])
        
        # Placeholder
        return {"action": "clarify", "reason": "SLM not initialized"}
