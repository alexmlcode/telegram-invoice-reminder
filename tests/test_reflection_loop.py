"""Tests for the self-modifying reflection loop."""
import pathlib
import tempfile

import pytest

from ouroboros.reflection_loop import (
    make_reflection_loop,
    IdentitySystem,
    RollbackManager,
    SVRLayer,
    GEPAgent,
)


def test_make_reflection_loop_creates_instance():
    """make_reflection_loop returns a ReflectionLoop instance."""
    with tempfile.TemporaryDirectory() as tmp:
        loop = make_reflection_loop(
            pathlib.Path("/home/a/ouroboros_repo"),
            pathlib.Path(tmp),
        )
        assert type(loop).__name__ == "ReflectionLoop"


def test_reflection_loop_introspect():
    """introspect() returns structured data with version, history, decision_log."""
    with tempfile.TemporaryDirectory() as tmp:
        loop = make_reflection_loop(
            pathlib.Path("/home/a/ouroboros_repo"),
            pathlib.Path(tmp),
        )
        introspection = loop.introspect()
        assert "version" in introspection
        assert "performance_history" in introspection
        assert "decision_log" in introspection
        assert "identity" in introspection


def test_identity_system_layered():
    """IdentitySystem supports channel → account → global → fallback layers."""
    identity = IdentitySystem()
    # Test global layer
    assert identity.get("name", "global") == "Ouroboros"
    # Test fallback
    assert identity.get("nonexistent", "global") is None


def test_rollback_manager_creates_backup():
    """RollbackManager creates backup before diff application."""
    with tempfile.TemporaryDirectory() as tmp:
        manager = RollbackManager(pathlib.Path(tmp))
        # Create a test file
        test_file = pathlib.Path(tmp) / "test.py"
        test_file.write_text("original content")
        # Create backup
        backup_id = manager.create_backup("test.py")
        assert backup_id is not None
        # Verify backup exists
        backup_path = pathlib.Path(tmp) / "backups" / backup_id / "test.py"
        assert backup_path.exists()


def test_svr_layer_simulate():
    """SVRLayer simulate() returns a prediction."""
    svr = SVRLayer()
    # Mock tool execution
    def mock_tool(params):
        return {"result": params.get("x", 0) * 2}
    
    prediction = svr.simulate("multiply_by_two", {"x": 5}, mock_tool)
    assert "prediction" in prediction


def test_gep_agent_coder_reviewer_planner():
    """GEPAgent supports Coder → Reviewer → Evolution Planner sequence."""
    gep = GEPAgent()
    
    # Test coder generates code
    code = gep.coder("add two numbers")
    assert "def add" in code.lower() or "def plus" in code.lower()
    
    # Test reviewer evaluates
    feedback = gep.evaluator(code)
    assert "score" in feedback.lower() or "review" in feedback.lower()
    
    # Test evolution planner proposes changes
    plan = gep.planner("add type hints")
    assert "plan" in plan.lower() or "change" in plan.lower()


def test_full_reflection_cycle():
    """Complete reflection cycle: reflect → score → generate → validate."""
    with tempfile.TemporaryDirectory() as tmp:
        loop = make_reflection_loop(
            pathlib.Path("/home/a/ouroboros_repo"),
            pathlib.Path(tmp),
        )
        
        # Simulate a reflection cycle
        reflection = loop.reflect("add validation to tool calls")
        assert "reflection" in reflection.lower() or "analysis" in reflection.lower()
        
        # Score the reflection
        score = loop.score(reflection)
        assert "score" in score.lower() or "quality" in score.lower()
        
        # Generate changes
        changes = loop.generate(reflection)
        assert "diff" in changes.lower() or "change" in changes.lower()
        
        # Validate
        valid = loop.validate(changes)
        assert valid in (True, False)


def test_reflection_loop_saves_state():
    """ReflectionLoop persists introspection data."""
    with tempfile.TemporaryDirectory() as tmp:
        loop = make_reflection_loop(
            pathlib.Path("/home/a/ouroboros_repo"),
            pathlib.Path(tmp),
        )
        
        # Initial state
        state1 = loop.introspect()
        assert state1["decision_log"] == []
        
        # Add a decision
        loop.record_decision("test_decision", {"result": "success"})
        
        # New state should have the decision
        state2 = loop.introspect()
        assert len(state2["decision_log"]) == 1
        assert state2["decision_log"][0]["action"] == "test_decision"
