"""SLM Agent — Ollama-powered smart home reasoning.

This module provides an optional SLM (Small Language Model) layer
that can be used INSTEAD of the rule-based arbitration for more
nuanced command understanding.

Strategy:
- Rule-based arbitration is PRIMARY (always works, no latency)
- SLM is SECONDARY/BONUS (for demo impressiveness + edge cases)

Usage:
    agent = SLMAgent()
    result = agent.process_command("turn on the lights in the bedroom", speaker_id="hemang")
"""
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# System prompt for the Canary smart home agent
SYSTEM_PROMPT = """You are The Canary, an intelligent smart home assistant. 
You control household devices by calling the appropriate tool function.

IMPORTANT RULES:
1. Parse the user's voice command and determine the correct action.
2. Always respond with a JSON object containing:
   - "tool": the function to call (toggle_lights, set_thermostat, play_music, stop_music, set_timer, get_weather)
   - "args": a dictionary of arguments for the tool
   - "explanation": a brief explanation of why you chose this action
3. If the command is unclear, respond with:
   - "tool": "request_clarification"
   - "args": {"reason": "..."}
4. Available rooms: living_room, bedroom, kitchen
5. Available tools and their arguments:
   - toggle_lights(room: str, state: "on"|"off")
   - set_thermostat(temperature: int 16-30, mode: "cool"|"heat"|"auto")
   - play_music(genre: str, user: str)
   - stop_music()
   - set_timer(minutes: int, label: str)
   - get_weather()
   - request_clarification(reason: str)

Respond ONLY with valid JSON. No extra text."""


class SLMAgent:
    """Small Language Model agent for smart home command understanding."""
    
    def __init__(self, model: str = "qwen2.5:1.5b", base_url: str = "http://localhost:11434"):
        """Initialize SLM agent.
        
        Args:
            model: Ollama model name
            base_url: Ollama server URL
        """
        self.model = model
        self.base_url = base_url
        self._available = None
        self._warmed_up = False
    
    @property
    def available(self) -> bool:
        """Check if Ollama is running and model is available."""
        if self._available is not None:
            return self._available
        
        try:
            import httpx
            r = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                self._available = any(self.model in m for m in models)
                if self._available:
                    logger.info("SLM available: %s", self.model)
                else:
                    logger.warning("Model %s not found. Available: %s", self.model, models)
            else:
                self._available = False
        except Exception as e:
            logger.warning("Ollama not available: %s", e)
            self._available = False
        
        return self._available
    
    def warmup(self) -> bool:
        """Send a trivial prompt to pre-load the model into memory.
        
        Call this once at startup to avoid cold-start latency during demo.
        Returns True if warmup succeeded.
        """
        if self._warmed_up or not self.available:
            return self._warmed_up
        
        try:
            import httpx
            logger.info("Warming up SLM (%s)...", self.model)
            start = time.time()
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "options": {"num_predict": 5},
                },
                timeout=60.0,
            )
            elapsed = time.time() - start
            self._warmed_up = r.status_code == 200
            logger.info("SLM warmup %s in %.1fs", "OK" if self._warmed_up else "FAILED", elapsed)
        except Exception as e:
            logger.warning("SLM warmup failed: %s", e)
            self._warmed_up = False
        
        return self._warmed_up
    
    def process_command(self, text: str, speaker_id: str = "unknown") -> dict:
        """Process a voice command using the SLM.
        
        Args:
            text: Transcribed command text
            speaker_id: Who said it
            
        Returns:
            Dict with "tool", "args", and "explanation" keys
        """
        if not self.available:
            logger.warning("SLM not available, falling back to rule-based routing")
            return self._fallback(text, speaker_id)
        
        try:
            return self._query_ollama(text, speaker_id)
        except Exception as e:
            logger.error("SLM error: %s — falling back", e)
            return self._fallback(text, speaker_id)
    
    def _query_ollama(self, text: str, speaker_id: str) -> dict:
        """Query Ollama for command interpretation."""
        import httpx
        
        user_prompt = f"Speaker: {speaker_id}\nCommand: {text}\n\nParse this command into a tool call."
        
        start = time.time()
        
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 200,
                },
            },
            timeout=30.0 if not self._warmed_up else 15.0,
        )
        
        elapsed = time.time() - start
        
        if response.status_code != 200:
            raise RuntimeError(f"Ollama returned {response.status_code}")
        
        raw = response.json()["message"]["content"]
        logger.info("SLM response (%.2fs): %s", elapsed, raw[:100])
        
        # Parse JSON from response
        try:
            # Handle potential markdown code blocks
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            
            result = json.loads(raw.strip())
            result["slm_latency"] = elapsed
            return result
        except json.JSONDecodeError:
            logger.warning("Failed to parse SLM JSON: %s", raw)
            return {
                "tool": "request_clarification",
                "args": {"reason": "SLM output was not valid JSON"},
                "explanation": f"Raw SLM output: {raw[:200]}",
                "slm_latency": elapsed,
            }
    
    def _fallback(self, text: str, speaker_id: str) -> dict:
        """Rule-based fallback when SLM is unavailable."""
        from src.agent.mcp_server import route_command
        result = route_command(text, speaker_id)
        return {
            "tool": "direct_execution",
            "args": {"text": text, "speaker": speaker_id},
            "explanation": f"Rule-based routing (SLM unavailable): {result}",
            "result": result,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
    
    print("🐤 The Canary — SLM Agent Test\n")
    
    agent = SLMAgent()
    print(f"  Ollama available: {agent.available}")
    print(f"  Model: {agent.model}\n")
    
    test_commands = [
        ("turn on the lights", "hemang"),
        ("play jazz music", "sanchit"),
        ("set thermostat to 22 degrees", "hemang"),
        ("what's the weather like", "sanchit"),
    ]
    
    for cmd, speaker in test_commands:
        print(f"  [{speaker}] \"{cmd}\"")
        result = agent.process_command(cmd, speaker)
        print(f"    Tool: {result.get('tool')}")
        print(f"    Args: {result.get('args')}")
        print(f"    Why:  {result.get('explanation', '—')}")
        if 'slm_latency' in result:
            print(f"    Time: {result['slm_latency']:.2f}s")
        print()
