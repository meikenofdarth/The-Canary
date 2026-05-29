"""Execution Queue — Priority-based command dispatch.

Queues arbitrated commands and executes them in priority order.
Logs all executions to Redis state store.
"""
import heapq
import time
from typing import Optional
from src.common.models import ArbitrationDecision, DecisionAction


class ExecutionQueue:
    """Priority queue for command execution."""
    
    def __init__(self, state_store=None):
        self._queue = []  # min-heap
        self._counter = 0
        self.state_store = state_store
    
    def enqueue(self, decision: ArbitrationDecision, priority: int = 5):
        """Add a decision to the execution queue.
        
        Lower priority number = higher priority (executed first).
        Admin commands get priority 1, Guest commands get priority 5.
        """
        heapq.heappush(self._queue, (priority, self._counter, decision))
        self._counter += 1
    
    def execute_next(self) -> Optional[str]:
        """Execute the highest-priority command."""
        if not self._queue:
            return None
        
        priority, _, decision = heapq.heappop(self._queue)
        return self._execute(decision)
    
    def execute_all(self) -> list[str]:
        """Execute all queued commands in priority order."""
        results = []
        while self._queue:
            result = self.execute_next()
            if result:
                results.append(result)
        return results
    
    def _execute(self, decision: ArbitrationDecision) -> str:
        """Execute a single arbitration decision."""
        if decision.action == DecisionAction.REJECT:
            return f"❌ Rejected: {decision.reason}"
        
        if decision.action == DecisionAction.CLARIFY:
            return f"🔊 Clarification needed: {decision.reason}"
        
        # Execute command(s) via MCP tool router
        from src.agent.mcp_server import route_command
        
        results = []
        for cmd in decision.commands:
            text = cmd.get('text', '')
            speaker = cmd.get('speaker', 'unknown')
            
            # Route to appropriate smart home tool
            result = route_command(text, speaker)
            results.append(result)
            
            # Log to state store
            if self.state_store:
                self.state_store.log_command(
                    user_id=speaker,
                    command=text,
                    result=result
                )
        
        return "\n".join(results)
    
    @property
    def size(self) -> int:
        return len(self._queue)
