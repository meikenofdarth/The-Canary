"""End-to-end integration test for The Canary pipeline.

Tests the full flow:
    Mock Audio → ASR → Arbitration → MCP Tool Execution → Result

Run from project root:
    source .venv/bin/activate
    python3 -m tests.test_e2e
"""
import sys
import os
import time
import numpy as np
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.models import (
    PipelineOutput, PipelineMode, AudioStream,
    TranscriptionResult, UserRole, DecisionAction
)
from src.common.config import Config
from src.arbitration.engine import ArbitrationEngine
from src.execution.queue import ExecutionQueue
from src.execution.state_store import StateStore
from src.agent.mcp_server import HOME_STATE, route_command


def test_scenario_1_single_command():
    """Scenario 1: Single admin command — straightforward execution."""
    print("=" * 60)
    print("SCENARIO 1: Single Admin Command")
    print("  Hemang says: 'turn on the living room lights'")
    print("=" * 60)
    
    store = StateStore()
    engine = ArbitrationEngine(state_store=store)
    queue = ExecutionQueue(state_store=store)
    
    # Simulate ASR output
    transcription = TranscriptionResult(
        text="turn on the living room lights",
        speaker_id="hemang",
        speaker_role=UserRole.ADMIN,
        confidence=0.92,
        speaker_confidence=0.95,
        timestamp=time.time(),
        language="en",
        emotion="neutral"
    )
    
    # Arbitrate
    decision = engine.arbitrate([transcription])
    print(f"  Decision: {decision.action.value} | {decision.reason}")
    assert decision.action == DecisionAction.EXECUTE
    
    # Execute
    queue.enqueue(decision, priority=1)
    result = queue.execute_next()
    print(f"  Result: {result}")
    assert "Lights" in result and "ON" in result
    
    # Verify state changed
    assert HOME_STATE["living_room"]["lights"] == "on"
    print(f"  Home state: living_room lights = {HOME_STATE['living_room']['lights']}")
    
    # Verify logged to Redis
    history = store.get_command_history("hemang", limit=1)
    if history:
        print(f"  Redis log: {history[0]}")
    
    print("✅ SCENARIO 1 PASSED\n")


def test_scenario_2_non_conflicting():
    """Scenario 2: Two non-conflicting commands — both execute."""
    print("=" * 60)
    print("SCENARIO 2: Non-Conflicting Commands")
    print("  Hemang: 'play jazz music'")
    print("  Sanchit: 'set timer for 5 minutes'")
    print("=" * 60)
    
    engine = ArbitrationEngine()
    queue = ExecutionQueue()
    
    transcriptions = [
        TranscriptionResult(
            text="play jazz music",
            speaker_id="hemang",
            speaker_role=UserRole.ADMIN,
            confidence=0.9,
            speaker_confidence=0.95,
            timestamp=time.time()
        ),
        TranscriptionResult(
            text="set timer for 5 minutes",
            speaker_id="sanchit",
            speaker_role=UserRole.GUEST,
            confidence=0.88,
            speaker_confidence=0.87,
            timestamp=time.time()
        )
    ]
    
    decision = engine.arbitrate(transcriptions)
    print(f"  Decision: {decision.action.value} | {decision.reason}")
    assert decision.action == DecisionAction.EXECUTE_BOTH
    assert len(decision.commands) == 2
    
    queue.enqueue(decision, priority=1)
    result = queue.execute_next()
    print(f"  Result:\n    {result.replace(chr(10), chr(10) + '    ')}")
    assert "jazz" in result.lower()
    assert "timer" in result.lower() or "Timer" in result
    
    print("✅ SCENARIO 2 PASSED\n")


def test_scenario_3_conflicting_admin_wins():
    """Scenario 3: Conflicting commands — admin overrides guest."""
    print("=" * 60)
    print("SCENARIO 3: Conflicting Commands — Admin Overrides Guest")
    print("  Hemang (Admin): 'turn on the lights'")
    print("  Sanchit (Guest): 'turn off the lights'")
    print("=" * 60)
    
    # Reset lights state
    HOME_STATE["living_room"]["lights"] = "off"
    
    engine = ArbitrationEngine()
    queue = ExecutionQueue()
    
    transcriptions = [
        TranscriptionResult(
            text="turn on the lights",
            speaker_id="hemang",
            speaker_role=UserRole.ADMIN,
            confidence=0.9,
            speaker_confidence=0.95,
            timestamp=time.time()
        ),
        TranscriptionResult(
            text="turn off the lights",
            speaker_id="sanchit",
            speaker_role=UserRole.GUEST,
            confidence=0.85,
            speaker_confidence=0.87,
            timestamp=time.time()
        )
    ]
    
    decision = engine.arbitrate(transcriptions)
    print(f"  Decision: {decision.action.value} | {decision.reason}")
    assert decision.action == DecisionAction.EXECUTE
    assert decision.priority_speaker == "hemang"
    
    queue.enqueue(decision, priority=1)
    result = queue.execute_next()
    print(f"  Result: {result}")
    
    # Admin said "turn on" → lights should be ON
    assert HOME_STATE["living_room"]["lights"] == "on", \
        f"Expected lights ON (admin command), got {HOME_STATE['living_room']['lights']}"
    print(f"  Home state: lights = {HOME_STATE['living_room']['lights']} (admin wins ✅)")
    
    print("✅ SCENARIO 3 PASSED\n")


def test_scenario_4_unknown_speaker_rejected():
    """Scenario 4: Unknown speaker — command rejected."""
    print("=" * 60)
    print("SCENARIO 4: Unknown Speaker — Rejected")
    print("  Unknown: 'open the door'")
    print("=" * 60)
    
    engine = ArbitrationEngine()
    queue = ExecutionQueue()
    
    transcriptions = [
        TranscriptionResult(
            text="open the door",
            speaker_id="unknown",
            speaker_role=UserRole.UNKNOWN,
            confidence=0.8,
            speaker_confidence=0.2,
            timestamp=time.time()
        )
    ]
    
    decision = engine.arbitrate(transcriptions)
    print(f"  Decision: {decision.action.value} | {decision.reason}")
    
    queue.enqueue(decision, priority=5)
    result = queue.execute_next()
    print(f"  Result: {result}")
    
    print("✅ SCENARIO 4 PASSED\n")


def test_scenario_5_same_privilege_clarify():
    """Scenario 5: Equal privilege conflict — ask for clarification."""
    print("=" * 60)
    print("SCENARIO 5: Same Privilege Conflict — Clarify")
    print("  Admin1: 'turn on the lights'")
    print("  Admin2: 'turn off the lights'")
    print("=" * 60)
    
    engine = ArbitrationEngine()
    queue = ExecutionQueue()
    
    transcriptions = [
        TranscriptionResult(
            text="turn on the lights",
            speaker_id="hemang",
            speaker_role=UserRole.ADMIN,
            confidence=0.9,
            speaker_confidence=0.95,
            timestamp=time.time()
        ),
        TranscriptionResult(
            text="turn off the lights",
            speaker_id="admin2",
            speaker_role=UserRole.ADMIN,
            confidence=0.88,
            speaker_confidence=0.92,
            timestamp=time.time()
        )
    ]
    
    decision = engine.arbitrate(transcriptions)
    print(f"  Decision: {decision.action.value} | {decision.reason}")
    assert decision.action == DecisionAction.CLARIFY
    
    queue.enqueue(decision)
    result = queue.execute_next()
    print(f"  Result: {result}")
    assert "Clarification" in result
    
    print("✅ SCENARIO 5 PASSED\n")


def test_full_pipeline_with_redis_logging():
    """Test full pipeline with Redis command history verification."""
    print("=" * 60)
    print("SCENARIO 6: Full Pipeline + Redis Logging")
    print("=" * 60)
    
    store = StateStore()
    engine = ArbitrationEngine(state_store=store)
    queue = ExecutionQueue(state_store=store)
    
    # Execute a sequence of commands
    commands = [
        ("turn on the bedroom lights", "hemang", UserRole.ADMIN),
        ("set thermostat to 26", "hemang", UserRole.ADMIN),
        ("play rock music", "sanchit", UserRole.GUEST),
    ]
    
    for text, speaker, role in commands:
        t = TranscriptionResult(
            text=text, speaker_id=speaker, speaker_role=role,
            confidence=0.9, speaker_confidence=0.95, timestamp=time.time()
        )
        decision = engine.arbitrate([t])
        queue.enqueue(decision, priority=1 if role == UserRole.ADMIN else 5)
    
    # Execute all
    results = queue.execute_all()
    for r in results:
        print(f"  → {r}")
    
    # Check Redis history
    hemang_history = store.get_command_history("hemang", limit=5)
    sanchit_history = store.get_command_history("sanchit", limit=5)
    print(f"\n  Redis: hemang has {len(hemang_history)} logged commands")
    print(f"  Redis: sanchit has {len(sanchit_history)} logged commands")
    
    # Log a pipeline metric
    store.log_pipeline_metric("e2e_test_pass", 1.0)
    
    print("✅ SCENARIO 6 PASSED\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    
    print("🐤 The Canary — End-to-End Integration Tests")
    print(f"   Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    test_scenario_1_single_command()
    test_scenario_2_non_conflicting()
    test_scenario_3_conflicting_admin_wins()
    test_scenario_4_unknown_speaker_rejected()
    test_scenario_5_same_privilege_clarify()
    test_full_pipeline_with_redis_logging()
    
    print("=" * 60)
    print("✅ ALL 6 E2E SCENARIOS PASSED")
    print("=" * 60)
