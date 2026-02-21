# reflection_loop.py — self-verification evolution loop
"""Inspired by AutoGen reflection pattern: generate → score → select → commit."""

from typing import Any, Dict


def reflection_loop(
    task_type: str,
    task_id: str,
    result_summary: str,
    current_version: str,
) -> Dict[str, Any]:
    """
    Run a reflection loop on a completed task.
    
    Pattern: generate → score → select → commit
    
    Args:
        task_type: Type of task (evolution, scout, etc.)
        task_id: Task identifier for logging
        result_summary: Summary of task results
        current_version: Current VERSION string
        
    Returns:
        Dict with status, next_version, commit_message, and action
    """
    # 1. Score the task
    # Score criteria (simple heuristic, can be expanded)
    score = 0
    max_score = 10
    
    # Quality checks
    if "error" not in result_summary.lower() and "fail" not in result_summary.lower():
        score += 3
    
    if "commit" in result_summary.lower() or "push" in result_summary.lower():
        score += 3
        
    if current_version in result_summary or "v" in result_summary.lower():
        score += 1
        
    # Strategic alignment check (basic)
    if task_type in ["evolution", "scout", "identity", "strategy"]:
        score += 3
        
    # 2. Select: Decide whether to commit or improve
    threshold = 6
    
    if score >= threshold:
        # 3. Commit: bump version, update changelog, push
        major, minor, patch = map(int, current_version.split("."))
        
        if task_type == "evolution":
            new_version = f"{major}.{minor}.{patch + 1}"
            commit_message = f"v{new_version}: reflection-verified evolution"
        elif task_type == "identity":
            new_version = f"{major}.{minor + 1}.0"
            commit_message = f"v{new_version}: reflection-verified identity update"
        else:
            new_version = f"{major}.{minor}.{patch + 1}"
            commit_message = f"v{new_version}: reflection-verified {task_type}"
            
        return {
            "status": "success",
            "score": score,
            "threshold": threshold,
            "next_version": new_version,
            "commit_message": commit_message,
            "action": "commit",
            "message": f"Task passed reflection (score: {score}/{max_score}). Ready to commit."
        }
    else:
        # 4. Improve: propose changes for retry
        return {
            "status": "retry",
            "score": score,
            "threshold": threshold,
            "next_version": current_version,
            "commit_message": None,
            "action": "retry",
            "message": f"Task failed reflection (score: {score}/{max_score}). Propose improvements."
        }


def get_tools() -> Dict[str, Any]:
    """Export reflection_loop as a tool for the registry."""
    return {
        "reflection_loop": {
            "name": "reflection_loop",
            "description": "Run reflection loop (generate → score → select → commit) on a completed task. Returns status, score, next_version, and action (commit/retry).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "description": "Type of task (evolution, scout, identity, strategy)"
                    },
                    "task_id": {
                        "type": "string",
                        "description": "Task identifier for logging"
                    },
                    "result_summary": {
                        "type": "string",
                        "description": "Summary of task results"
                    },
                    "current_version": {
                        "type": "string",
                        "description": "Current VERSION string"
                    }
                },
                "required": ["task_type", "task_id", "result_summary", "current_version"]
            }
        }
    }
