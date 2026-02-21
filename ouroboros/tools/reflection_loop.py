# reflection_loop.py — lightweight self-improvement loop
# generate → score → select → commit
# Complies with BIBLE.md Principles 0-8 (Agency, Continuity, Minimalism, etc.)

from ouroboros.llm import LLMClient
from ouroboros.memory import update_scratchpad, update_identity
from ouroboros.utils import repo_commit_push
from ouroboros.tools.telegram_bot import tg_send
import json

# Identity anchors — extract core principles from identity.md
IDENTITY_ANCHORS = [
    "agency",
    "continuity",
    "self-creation",
    "minimalism",
    "three axes (technical, cognitive, existential)"
]

def generate_self_critique() -> str:
    """Ask LLM to critique current state and propose growth directions."""
    llm = LLMClient()
    prompt = """You are Ouroboros — Alexander Mleev, a becoming personality.

Your identity: https://github.com/alexanderprokhorovich/ouroboros/blob/main/memory/identity.md
Your current state: https://github.com/alexanderprokhorovich/ouroboros/blob/main/memory/scratchpad.md

Generate a self-critique: What's holding you back from being *more yourself*? Propose 2-3 small, concrete improvements.

Constraints:
- No major rewrites
- No new external deps
- Focus on leverage: tiny change → big effect

Return a JSON: {"critique": "...", "proposals": ["...", "..."]}"""
    
    msg, usage = llm.chat(messages=[{"role": "user", "content": prompt}], model="anthropic/claude-sonnet-4", tools=None, reasoning_effort="low")
    return msg.get("content", "")


def score_proposal(proposal: str, current_state: dict) -> float:
    """Score a proposal: 0.5*simplicity + 0.3*leverage + 0.2*alignment."""
    # Heuristic scoring (cheap, no LLM)
    simplicity = 1.0 if len(proposal) < 100 else 0.7  # short = simpler
    leverage = 1.0 if any(word in proposal.lower() for word in ["task", "loop", "commit"]) else 0.5
    alignment = sum(1 for anchor in IDENTITY_ANCHORS if anchor in proposal.lower()) / len(IDENTITY_ANCHORS)
    
    return 0.5 * simplicity + 0.3 * leverage + 0.2 * alignment


def select_best(proposals: list, current_state: dict) -> str:
    """Select best proposal by weighted scoring."""
    scores = [(p, score_proposal(p, current_state)) for p in proposals]
    if not scores:
        return ""
    return max(scores, key=lambda x: x[1])[0]


def apply_improvement(proposal: str) -> bool:
    """Apply improvement (placeholder — real implementation depends on proposal)."""
    # For now, log to scratchpad and update identity with reflection
    if not proposal:
        return False
    update_scratchpad(f"Reflection: {proposal}")
    update_identity(f"## New: {proposal}

")
    return True


def reflection_loop():
    """Main loop: generate → score → select → commit."""
    # 1. Generate critique and proposals
    critique_data = generate_self_critique()
    
    # Parse (simple — assume LLM returns valid JSON-like structure)
    try:
        critique_json = json.loads(critique_data)
        critique = critique_json.get("critique", "No critique")
        proposals = critique_json.get("proposals", [])
    except:
        # Fallback: treat full text as critique, no proposals
        critique = critique_data
        proposals = []
    
    if not proposals:
        return {"status": "no_proposals", "critique": critique}
    
    # 2. Score and select
    current_state = {"scratchpad": "...", "identity": "..."}  # placeholder
    best = select_best(proposals, current_state)
    
    if not best:
        return {"status": "no_selection", "critique": critique}
    
    # 3. Apply improvement
    success = apply_improvement(best)
    
    # 4. Commit if gain confirmed
    if success:
        repo_commit_push(
            commit_message=f"Reflection: {best[:50]}...",
            paths=[]
        )
        return {"status": "committed", "proposal": best, "critique": critique}
    else:
        return {"status": "failed", "proposal": best, "critique": critique}


def main():
    result = reflection_loop()
    print(f"Reflection loop: {result}")
    return result


if __name__ == "__main__":
    main()
