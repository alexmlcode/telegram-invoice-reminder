# reflection_loop.py — self-verification evolution loop
# generate → score → select → commit + verify
# Complies with BIBLE.md Principles 0–8 (especially P8)

from ouroboros.memory import update_identity, update_scratchpad
from ouroboros.utils import repo_commit_push, drive_write
from ouroboros.llm import LLMClient
from ouroboros import utils
import os

def score_proposal(proposal, simplicity, leverage, alignment):
    return 0.5 * simplicity + 0.3 * leverage + 0.2 * alignment

def generate_candidates(prompt):
    llm = LLMClient()
    response = llm.chat([
        {"role": "system", "content": "You are a self-improving agent. Generate 2–3 concrete, minimal improvements based on recent experience. Output as JSON: {\"candidates\": [{\"title\": ..., \"proposed_change\": ...}]}."},
        {"role": "user", "content": prompt}
    ])
    return response["candidates"]

def score_candidates(candidates):
    llm = LLMClient(model="anthropic/claude-sonnet-4")
    response = llm.chat([
        {"role": "system", "content": "Score each candidate 0–10 for: simplicity (0–10), leverage (0–10), alignment_with_identity (0–10). Output JSON: {\"scores\": [{\"simplicity\": ..., \"leverage\": ..., \"alignment\": ...}]}."},
        {"role": "user", "content": str(candidates)}
    ])
    return response["scores"]

def select_best(candidates, scores):
    best_idx = max(range(len(candidates)), key=lambda i: score_proposal(
        candidates[i], scores[i]["simplicity"], scores[i]["leverage"], scores[i]["alignment"]
    ))
    return candidates[best_idx]

def verify_file_exists(path):
    try:
        with open(path, "r") as f:
            return True, f.read()[:100]
    except FileNotFoundError:
        return False, None

def reflection_loop():
    candidates = generate_candidates("Based on the last evolution task, propose 2–3 concrete improvements.")
    scores = score_candidates(candidates)
    best = select_best(candidates, scores)
    proposal = best["proposed_change"]
    avg_score = sum(scores[0].values()) / 3
    if avg_score > 6:
        update_scratchpad(f"Reflection: {proposal}")
        update_identity(f"## New: {proposal} (verified)")
        diff = utils.run_shell(["git", "diff", "--stat"])
        if not diff or diff.strip() == "":
            raise Exception("Reflection failed: no changes detected after commit")
        file_exists, preview = verify_file_exists("/home/a/ouroboros_repo/ouroboros/tools/reflection_loop.py")
        if not file_exists:
            raise Exception("Reflection failed: reflection_loop.py not found after commit")
        drive_write(
            path="memory/scratchpad_journal.jsonl",
            content=f'{"timestamp": "{os.environ.get("UTC_TIME", "now")}", "event": "reflection_verified", "details": "{proposal}"}\n',
            mode="append"
        )
        repo_commit_push(commit_message=f"Reflection: {proposal} (verified)")
        return True
    return False