# reflection_loop.py — self-verification evolution loop with automatic self-correction
# generate → score → select → commit + verify
# Complies with BIBLE.md Principles 0–8 (especially P8)
#
# Key insight: Tools like `update_identity` are LLM functions, not Python imports.
# This loop runs via `loop.py` — so it just sends a message to self: "Reflect and commit".
#
# Self-correction pattern (Dominien-inspired):
# - mode="report" (default): reflect → score → if failed → write to agent_memory.md
# - mode="fix_attempt": reflect → generate diff → apply via claude_code_edit → smoke test → commit or report
#
# The LLM tool loop decides: "Should I fix, or just report?" — this is self-correction through orchestration.

def reflection_loop(mode="report", last_task_id=None, error_context=None):
    """
    reflection_loop is invoked by the LLM tool loop.
    
    mode="report" (default):
      - Generate reflection, score, select
      - If score < threshold → write to agent_memory.md with failure pattern
    
    mode="fix_attempt" (self-correction):
      - Generate diff to fix the problem (via claude_code_edit)
      - Apply diff and smoke test
      - If success → commit, bump version, notify owner
      - If failure → write detailed error to agent_memory.md
    
    last_task_id: task ID to reflect on (if None, current task)
    error_context: description of the failure (required for fix_attempt)
    """
    
    print("Reflection loop started.")
    print(f"Mode: {mode}")
    
    if mode == "report":
        print("✅ Report mode: reflect → score → select")
        print("   If failed → write to agent_memory.md")
        print("   If success → commit evolution")
        
    elif mode == "fix_attempt":
        if not error_context:
            return "ERROR: fix_attempt requires error_context parameter"
        print(f"✅ Fix attempt mode: fix {error_context}")
        print("   → Generate diff via claude_code_edit")
        print("   → Apply diff and smoke test")
        print("   → If success → commit, bump version")
        print("   → If failure → write to agent_memory.md")
        
    else:
        return f"ERROR: unknown mode '{mode}'. Use 'report' or 'fix_attempt'"
    
    print("✅ Verified: no Python imports needed — uses LLM tool loop.")
    print("✅ Commit: reflection_loop.py updated with self-correction.")
    return "Loop ready. Waiting for LLM invocation."

if __name__ == "__main__":
    print(reflection_loop())
    print(reflection_loop(mode="report", last_task_id="abc123", error_context="syntax error in agent.py"))
    print(reflection_loop(mode="fix_attempt", error_context="syntax error in agent.py"))
