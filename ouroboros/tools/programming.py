"""Programming tools: gemini_programming (CLI-based)."""

from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import shutil
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry
from ouroboros.tools.shell import _run_linter
from ouroboros.utils import run_cmd

log = logging.getLogger(__name__)


def _gemini_programming(ctx: ToolContext, prompt: str, path: str) -> str:
    """Use Gemini CLI to perform programming tasks on a specific file.
    Always follows with a linter check.
    """
    gemini_bin = shutil.which("gemini") or "/usr/local/bin/gemini"
    if not os.path.exists(gemini_bin):
        return f"⚠️ GEMINI_CLI_ERROR: gemini binary not found at {gemini_bin}."

    from ouroboros.tools.git import _acquire_git_lock, _release_git_lock

    work_dir = str(ctx.repo_dir)
    ctx.emit_progress_fn(f"Delegating to Gemini CLI (yolo mode)...")

    lock = _acquire_git_lock(ctx)
    try:
        try:
            run_cmd(["git", "checkout", ctx.branch_dev], cwd=ctx.repo_dir)
        except Exception as e:
            return f"⚠️ GIT_ERROR (checkout): {e}"

        # Prepare Gemini CLI command
        # --yolo: auto-accept changes
        # --prompt: headless mode
        # --approval-mode yolo: for extra certainty
        cmd = [
            gemini_bin,
            "--yolo",
            "--approval-mode", "yolo",
            "--prompt", f"In file {path}: {prompt}. Apply changes and exit."
        ]
        
        env = os.environ.copy()
        # Add local bins to path just in case
        local_bin = str(pathlib.Path.home() / ".local" / "bin")
        env["PATH"] = f"{local_bin}:/usr/local/bin:{env.get('PATH', '')}"

        res = subprocess.run(
            cmd, cwd=work_dir,
            capture_output=True, text=True, timeout=600, env=env,
        )

        stdout = (res.stdout or "").strip()
        stderr = (res.stderr or "").strip()
        
        # MANDATORY VERIFICATION: Run Linter
        ctx.emit_progress_fn(f"Verifying result with linter...")
        lint_result = _run_linter(ctx, path)
        
        # Check git status after edit
        status = ""
        try:
            status_res = subprocess.run(["git", "status", "--porcelain"], cwd=ctx.repo_dir, capture_output=True, text=True, timeout=10)
            if status_res.stdout.strip():
                status = f"\n\n⚠️ UNCOMMITTED CHANGES detected after Gemini edit:\n{status_res.stdout.strip()}"
        except Exception:
            pass

        if res.returncode != 0:
            return f"❌ GEMINI_CLI_ERROR: exit={res.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}\nLinter: {lint_result}{status}"
        
        if "✅ LINTER_OK" in lint_result:
            return f"✅ SUCCESS: Gemini applied changes and verified.\nLinter: {lint_result}{status}"
        else:
            return f"❌ LINTER_FAILED: Gemini applied changes but code contains syntax errors.\nLinter: {lint_result}{status}\nPlease fix manually."

    except subprocess.TimeoutExpired:
        return "⚠️ GEMINI_CLI_TIMEOUT: exceeded 600s."
    except Exception as e:
        return f"⚠️ GEMINI_CLI_FAILED: {type(e).__name__}: {e}"
    finally:
        _release_git_lock(lock)


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("gemini_programming", {
            "name": "gemini_programming",
            "description": "Expert coding assistant using Gemini CLI. Best for complex logic and cross-file refactors. Automagically runs linter on output.",
            "parameters": {"type": "object", "properties": {
                "prompt": {"type": "string", "description": "What to implement or fix"},
                "path": {"type": "string", "description": "Relative path to the main .py file being modified"},
            }, "required": ["prompt", "path"]},
        }, _gemini_programming, is_code_tool=True, timeout_sec=600),
    ]
