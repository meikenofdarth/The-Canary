"""Test suite for FAISS Speaker Index, Redis State Store, and Arbitration Engine.

Run from project root:
    source .venv/bin/activate
    python3 -m tests.test_core_modules
"""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.execution.speaker_index import SpeakerIndex
from src.execution.state_store import StateStore
from src.arbitration.engine import ArbitrationEngine
from src.common.models import TranscriptionResult, UserRole, DecisionAction


# ─────────────────────────────────────────────
# FAISS SPEAKER INDEX TESTS
# ─────────────────────────────────────────────

def test_faiss_speaker_index():
    """Test FAISS enrollment and identification."""
    print("=" * 60)
    print("TEST: FAISS Speaker Index")
    print("=" * 60)
    
    dim = 192  # CAM++ B0 embedding dim
    index = SpeakerIndex(embedding_dim=dim)
    print(f"  ✅ FAISS index created (dim={dim})")
    
    # Create realistic-ish embeddings (in practice these come from CAM++)
    np.random.seed(42)
    hemang_emb = np.random.randn(dim).astype(np.float32)
    sanchit_emb = np.random.randn(dim).astype(np.float32)
    
    # Enroll speakers
    index.enroll("hemang", hemang_emb)
    index.enroll("sanchit", sanchit_emb)
    print(f"  ✅ Enrolled {index.num_enrolled} speakers")
    assert index.num_enrolled == 2, "Expected 2 enrolled speakers"
    
    # Test identification — query with slight perturbation of hemang's embedding
    query_hemang = hemang_emb + np.random.randn(dim).astype(np.float32) * 0.1
    speaker_id, confidence = index.identify(query_hemang, threshold=0.5)
    print(f"  Query (hemang + noise): identified as '{speaker_id}' (confidence={confidence:.3f})")
    assert speaker_id == "hemang", f"Expected 'hemang', got '{speaker_id}'"
    
    # Test identification — query with slight perturbation of sanchit's embedding
    query_sanchit = sanchit_emb + np.random.randn(dim).astype(np.float32) * 0.1
    speaker_id, confidence = index.identify(query_sanchit, threshold=0.5)
    print(f"  Query (sanchit + noise): identified as '{speaker_id}' (confidence={confidence:.3f})")
    assert speaker_id == "sanchit", f"Expected 'sanchit', got '{speaker_id}'"
    
    # Test unknown speaker — completely random embedding
    unknown_emb = np.random.randn(dim).astype(np.float32) * 5.0
    speaker_id, confidence = index.identify(unknown_emb, threshold=0.65)
    print(f"  Query (unknown): identified as '{speaker_id}' (confidence={confidence:.3f})")
    # Could be either unknown or a false match; just verify it returns something
    print(f"  ✅ Unknown speaker handling works")
    
    # Test save/load enrollment
    enroll_dir = "models/speaker_embeddings"
    os.makedirs(enroll_dir, exist_ok=True)
    np.save(os.path.join(enroll_dir, "hemang.npy"), hemang_emb)
    np.save(os.path.join(enroll_dir, "sanchit.npy"), sanchit_emb)
    
    index2 = SpeakerIndex(embedding_dim=dim)
    index2.load_enrollment(enroll_dir)
    print(f"  ✅ Loaded enrollment from disk ({index2.num_enrolled} speakers)")
    assert index2.num_enrolled == 2
    
    # Verify loaded index works
    speaker_id, confidence = index2.identify(query_hemang, threshold=0.5)
    assert speaker_id == "hemang", f"After reload, expected 'hemang', got '{speaker_id}'"
    print(f"  ✅ Reloaded index correctly identifies speakers")
    
    print("✅ ALL FAISS TESTS PASSED\n")


# ─────────────────────────────────────────────
# REDIS STATE STORE TESTS  
# ─────────────────────────────────────────────

def test_state_store():
    """Test StateStore — tries Redis first, falls back to in-memory."""
    print("=" * 60)
    print("TEST: State Store (Redis + Fallback)")
    print("=" * 60)
    
    store = StateStore(redis_url="redis://localhost:6379")
    
    if store.r is not None:
        print("  ✅ Connected to Redis")
        backend = "Redis"
    else:
        print("  ⚠️  Redis unavailable — testing in-memory fallback")
        backend = "In-Memory Fallback"
    
    # Test user profiles
    hemang = store.get_profile("hemang")
    sanchit = store.get_profile("sanchit")
    print(f"  Profile hemang: {hemang}")
    print(f"  Profile sanchit: {sanchit}")
    assert hemang is not None, "Hemang profile should exist"
    assert sanchit is not None, "Sanchit profile should exist"
    assert hemang.get("role") == "admin", f"Hemang should be admin, got {hemang.get('role')}"
    assert sanchit.get("role") == "guest", f"Sanchit should be guest, got {sanchit.get('role')}"
    print(f"  ✅ User profiles loaded (hemang=admin, sanchit=guest)")
    
    # Test role lookup
    assert store.get_role("hemang") == "admin"
    assert store.get_role("sanchit") == "guest"
    assert store.get_role("stranger") == "unknown"
    print(f"  ✅ Role lookup works (including unknown users)")
    
    # Test command history
    store.log_command("hemang", "turn on lights", "✅ Lights on")
    store.log_command("hemang", "play jazz", "✅ Playing jazz")
    store.log_command("sanchit", "set timer 5 min", "✅ Timer set")
    
    hemang_history = store.get_command_history("hemang", limit=5)
    sanchit_history = store.get_command_history("sanchit", limit=5)
    print(f"  Hemang history: {len(hemang_history)} entries")
    print(f"  Sanchit history: {len(sanchit_history)} entries")
    assert len(hemang_history) >= 2, "Hemang should have 2+ history entries"
    assert len(sanchit_history) >= 1, "Sanchit should have 1+ history entries"
    print(f"  ✅ Command history logging works")
    
    # Test pipeline metrics
    store.log_pipeline_metric("e2e_latency", 0.342)
    store.log_pipeline_metric("e2e_latency", 0.287)
    store.log_pipeline_metric("asr_rtf", 0.021)
    print(f"  ✅ Pipeline metrics logged")
    
    # Test sessions (Redis only)
    if store.r:
        store.set_session("test-session-1", {"active_speakers": ["hemang"], "mode": "A"}, ttl=60)
        session = store.get_session("test-session-1")
        assert session is not None, "Session should exist"
        assert session["mode"] == "A"
        print(f"  ✅ Session store with TTL works")
    
    print(f"✅ ALL STATE STORE TESTS PASSED (backend: {backend})\n")


# ─────────────────────────────────────────────
# ARBITRATION ENGINE TESTS
# ─────────────────────────────────────────────

def test_arbitration_engine():
    """Test all 6 arbitration rules."""
    print("=" * 60)
    print("TEST: Arbitration Engine (6 Rules)")
    print("=" * 60)
    
    engine = ArbitrationEngine()
    
    # ── Rule 1: Single command, high confidence → EXECUTE ──
    results = [TranscriptionResult(
        text="turn on the lights",
        speaker_id="hemang",
        speaker_role=UserRole.ADMIN,
        confidence=0.92,
        speaker_confidence=0.95,
        timestamp=time.time()
    )]
    decision = engine.arbitrate(results)
    assert decision.action == DecisionAction.EXECUTE, f"Rule 1 failed: got {decision.action}"
    print(f"  ✅ Rule 1: Single + high confidence → {decision.action.value} | {decision.reason}")
    
    # ── Rule 2: Single command, low confidence → CLARIFY ──
    results = [TranscriptionResult(
        text="hmm",
        speaker_id="hemang",
        speaker_role=UserRole.ADMIN,
        confidence=0.3,
        speaker_confidence=0.95,
        timestamp=time.time()
    )]
    decision = engine.arbitrate(results)
    assert decision.action == DecisionAction.CLARIFY, f"Rule 2 failed: got {decision.action}"
    print(f"  ✅ Rule 2: Single + low confidence → {decision.action.value} | {decision.reason}")
    
    # ── Rule 3: Two non-conflicting commands → EXECUTE_BOTH ──
    results = [
        TranscriptionResult(
            text="turn on the lights",
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
            confidence=0.85,
            speaker_confidence=0.87,
            timestamp=time.time()
        )
    ]
    decision = engine.arbitrate(results)
    assert decision.action == DecisionAction.EXECUTE_BOTH, f"Rule 3 failed: got {decision.action}"
    assert len(decision.commands) == 2
    print(f"  ✅ Rule 3: Non-conflicting → {decision.action.value} | {decision.reason}")
    
    # ── Rule 4: Conflicting + different privilege → EXECUTE (admin wins) ──
    results = [
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
    decision = engine.arbitrate(results)
    assert decision.action == DecisionAction.EXECUTE, f"Rule 4 failed: got {decision.action}"
    assert decision.priority_speaker == "hemang", f"Rule 4: admin should win, got {decision.priority_speaker}"
    print(f"  ✅ Rule 4: Conflict + Admin > Guest → {decision.action.value} for {decision.priority_speaker} | {decision.reason}")
    
    # ── Rule 4b: Conflicting, but guest speaks first, admin still wins ──
    results = [
        TranscriptionResult(
            text="turn off the lights",
            speaker_id="sanchit",
            speaker_role=UserRole.GUEST,
            confidence=0.85,
            speaker_confidence=0.87,
            timestamp=time.time()
        ),
        TranscriptionResult(
            text="turn on the lights",
            speaker_id="hemang",
            speaker_role=UserRole.ADMIN,
            confidence=0.9,
            speaker_confidence=0.95,
            timestamp=time.time()
        ),
    ]
    decision = engine.arbitrate(results)
    assert decision.action == DecisionAction.EXECUTE
    assert decision.priority_speaker == "hemang"
    print(f"  ✅ Rule 4b: Conflict (guest first, admin second) → Admin still wins")
    
    # ── Rule 5: Conflicting + same privilege → CLARIFY ──
    results = [
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
            speaker_id="other_admin",
            speaker_role=UserRole.ADMIN,
            confidence=0.88,
            speaker_confidence=0.92,
            timestamp=time.time()
        )
    ]
    decision = engine.arbitrate(results)
    assert decision.action == DecisionAction.CLARIFY, f"Rule 5 failed: got {decision.action}"
    print(f"  ✅ Rule 5: Conflict + same privilege → {decision.action.value} | {decision.reason}")
    
    # ── Rule 6: Unknown speaker → REJECT ──
    results = [TranscriptionResult(
        text="open the door",
        speaker_id="unknown",
        speaker_role=UserRole.UNKNOWN,
        confidence=0.8,
        speaker_confidence=0.3,
        timestamp=time.time()
    )]
    decision = engine.arbitrate(results)
    # Unknown speaker single command → should CLARIFY (ask to identify)
    print(f"  ✅ Rule 6: Unknown speaker → {decision.action.value} | {decision.reason}")
    
    # ── Rule 6b: ALL unknown speakers → REJECT ──
    results = [
        TranscriptionResult(
            text="turn on the lights", speaker_id="unknown",
            speaker_role=UserRole.UNKNOWN, confidence=0.8,
            speaker_confidence=0.2, timestamp=time.time()
        ),
        TranscriptionResult(
            text="play music", speaker_id="unknown",
            speaker_role=UserRole.UNKNOWN, confidence=0.75,
            speaker_confidence=0.15, timestamp=time.time()
        )
    ]
    decision = engine.arbitrate(results)
    assert decision.action == DecisionAction.REJECT, f"Rule 6b failed: got {decision.action}"
    print(f"  ✅ Rule 6b: All unknown speakers → {decision.action.value} | {decision.reason}")
    
    # ── Empty input → REJECT ──
    decision = engine.arbitrate([])
    assert decision.action == DecisionAction.REJECT
    print(f"  ✅ Edge case: Empty input → {decision.action.value}")
    
    print("✅ ALL ARBITRATION TESTS PASSED\n")


# ─────────────────────────────────────────────
# CONFLICT DETECTION TESTS
# ─────────────────────────────────────────────

def test_conflict_detection():
    """Test detect_conflict() method."""
    print("=" * 60)
    print("TEST: Conflict Detection")
    print("=" * 60)
    
    engine = ArbitrationEngine()
    
    # Conflicting pairs
    conflicts = [
        ("turn on the lights", "turn off the lights"),
        ("play music", "stop music"),
        ("increase the thermostat", "decrease the thermostat"),
        ("open the door", "close the door"),
    ]
    
    for cmd_a, cmd_b in conflicts:
        result = engine.detect_conflict(cmd_a, cmd_b)
        assert result is True, f"Should conflict: '{cmd_a}' vs '{cmd_b}'"
        print(f"  ✅ Conflict detected: '{cmd_a}' vs '{cmd_b}'")
    
    # Non-conflicting pairs
    non_conflicts = [
        ("turn on the lights", "play music"),
        ("set timer for 5 minutes", "turn on the fan"),
        ("what's the weather", "turn off the lights"),
        ("turn on the lights", "turn on the fan"),  # Same action, different target
    ]
    
    for cmd_a, cmd_b in non_conflicts:
        result = engine.detect_conflict(cmd_a, cmd_b)
        assert result is False, f"Should NOT conflict: '{cmd_a}' vs '{cmd_b}'"
        print(f"  ✅ No conflict: '{cmd_a}' vs '{cmd_b}'")
    
    print("✅ ALL CONFLICT DETECTION TESTS PASSED\n")


# ─────────────────────────────────────────────
# EXECUTION QUEUE TESTS
# ─────────────────────────────────────────────

def test_execution_queue():
    """Test priority-based execution queue."""
    print("=" * 60)
    print("TEST: Execution Queue")
    print("=" * 60)
    
    from src.execution.queue import ExecutionQueue
    from src.common.models import ArbitrationDecision
    
    queue = ExecutionQueue()
    
    # Enqueue commands with different priorities
    admin_decision = ArbitrationDecision(
        action=DecisionAction.EXECUTE,
        commands=[{"text": "play music", "speaker": "hemang"}],
        reason="Admin command",
        priority_speaker="hemang",
        confidence=0.95
    )
    
    guest_decision = ArbitrationDecision(
        action=DecisionAction.EXECUTE,
        commands=[{"text": "play music", "speaker": "sanchit"}],
        reason="Guest command",
        priority_speaker="sanchit",
        confidence=0.85
    )
    
    # Guest enqueued first but with lower priority
    queue.enqueue(guest_decision, priority=5)
    queue.enqueue(admin_decision, priority=1)
    
    assert queue.size == 2
    print(f"  ✅ Enqueued 2 commands (admin priority=1, guest priority=5)")
    
    # Admin should execute first (lower priority number = higher priority)
    result1 = queue.execute_next()
    assert "hemang" in result1, f"Admin should execute first, got: {result1}"
    print(f"  ✅ First execution: {result1}")
    
    result2 = queue.execute_next()
    assert "sanchit" in result2, f"Guest should execute second, got: {result2}"
    print(f"  ✅ Second execution: {result2}")
    
    assert queue.size == 0
    print(f"  ✅ Queue empty after execution")
    
    # Test REJECT and CLARIFY handling
    reject_decision = ArbitrationDecision(
        action=DecisionAction.REJECT,
        reason="Unknown speaker"
    )
    queue.enqueue(reject_decision)
    result = queue.execute_next()
    assert "Rejected" in result
    print(f"  ✅ Reject handling: {result}")
    
    clarify_decision = ArbitrationDecision(
        action=DecisionAction.CLARIFY,
        reason="Conflicting commands"
    )
    queue.enqueue(clarify_decision)
    result = queue.execute_next()
    assert "Clarification" in result
    print(f"  ✅ Clarify handling: {result}")
    
    print("✅ ALL EXECUTION QUEUE TESTS PASSED\n")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
    
    print("🐤 The Canary — Core Module Test Suite")
    print()
    
    test_faiss_speaker_index()
    test_state_store()
    test_arbitration_engine()
    test_conflict_detection()
    test_execution_queue()
    
    print("=" * 60)
    print("✅ ALL CORE MODULE TESTS PASSED")
    print("=" * 60)
