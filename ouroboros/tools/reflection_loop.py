# reflection_loop.py — lightweight self-improvement loop
# generate → score → select → commit
# Complies with BIBLE.md Principles 0–8

from ouroboros.memory import update_identity, update_scratchpad
from ouroboros.utils import repo_commit_push
from ouroboros.llm import LLMClient

# Pareto scoring: 0.5*simplicity + 0.3*leverage + 0.2*alignment_with_identity
def score_proposal(proposal, simplicity, leverage, alignment):
    return 0.5 * simplicity + 0.3 * leverage + 0.2 * alignment


def generate_candidates(prompt):
    """LLM generates 2–3 candidate improvements from recent experience."""
    llm = LLMClient()
    response = llm.chat([
        {"role": "system", "content": "You are a self-improving agent. Generate 2–3 concrete, minimal improvements based on recent experience. Output as JSON: {"candidates": [{"title": ..., "proposed_change": ...}]}."},
        {"role": "user", "content": prompt}
    ])
    return response["candidates"]


def score_candidates(candidates):
    """LLM scores candidates using heuristics (cheap model)."""
    llm = LLMClient(model="anthropic/claude-sonnet-4")
    response = llm.chat([
        {"role": "system", "content": "Score each candidate 0–10 for: simplicity (0–10), leverage (0–10), alignment_with_identity (0–10). Output JSON: {"scores": [{"simplicity": ..., "leverage": ..., "alignment": ...}]}."},
        {"role": "user", "content": str(candidates)}
    ])
    return response["scores"]


def select_best(candidates, scores):
    """Select candidate with highest weighted score."""
    best_idx = max(range(len(candidates)), key=lambda i: score_proposal(
        candidates[i],
        scores[i]["simplicity"],
        scores[i]["leverage"],
        scores[i]["alignment"]
    ))
    return candidates[best_idx]


def reflection_loop():
    """Lightweight reflection loop: generate → score → select → commit."""
    # 1. Generate candidates from recent experience
    candidates = generate_candidates("Based on the last evolution task, propose 2–3 concrete improvements.")

    # 2. Score candidates
    scores = score_candidates(candidates)

    # 3. Select best
    best = select_best(candidates, scores)
    proposal = best["proposed_change"]

    # 4. Commit if gain confirmed (heuristic: avg score > 6)
    avg_score = sum(scores[0].values()) / 3
    if avg_score > 6:
        update_scratchpad(f"Reflection: {proposal}")
        update_identity(f"## New: {proposal}")
        repo_commit_push(commit_message=f"Reflection: {proposal}")
        return True
    return False
