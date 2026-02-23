"""Shell tools: run_shell, opencode_edit, run_linter."""

from __future__ import annotations

import json
import logging
import os
import pathlib
import shlex
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry
from ouroboros.utils import utc_now_iso, run_cmd, append_jsonl, truncate_for_log

log = logging.getLogger(__name__)


def _run_shell(ctx: ToolContext, cmd, cwd: str = "") -> str:
    # Recover from LLM sending cmd as JSON string instead of list
    if isinstance(cmd, str):
        raw_cmd = cmd
        warning = "run_shell_cmd_string"
        try:
            parsed = json.loads(cmd)
            if isinstance(parsed, list):
                cmd = parsed
                warning = "run_shell_cmd_string_json_list_recovered"
            elif isinstance(parsed, str):
                try:
                    cmd = shlex.split(parsed)
                except ValueError:
                    cmd = parsed.split()
                warning = "run_shell_cmd_string_json_string_split"
            else:
                try:
                    cmd = shlex.split(cmd)
                except ValueError:
                    cmd = cmd.split()
                warning = "run_shell_cmd_string_json_non_list_split"
        except Exception:
            try:
                cmd = shlex.split(cmd)
            except ValueError:
                cmd = cmd.split()
            warning = "run_shell_cmd_string_split_fallback"

        try:
            append_jsonl(ctx.drive_logs() / "events.jsonl", {
                "ts": utc_now_iso(),
                "type": "tool_warning",
                "tool": "run_shell",
                "warning": warning,
                "cmd_preview": truncate_for_log(raw_cmd, 500),
            })
        except Exception:
            log.debug("Failed to log run_shell warning to events.jsonl", exc_info=True)
            pass

    if not isinstance(cmd, list):
        return "⚠️ SHELL_ARG_ERROR: cmd must be a list of strings."
    cmd = [str(x) for x in cmd]

    work_dir = ctx.repo_dir
    if cwd and cwd.strip() not in ("", ".", "./"):
        candidate = (ctx.repo_dir / cwd).resolve()
        if candidate.exists() and candidate.is_dir():
            work_dir = candidate

    try:
        res = subprocess.run(
            cmd, cwd=str(work_dir),
            capture_output=True, text=True, timeout=120,
        )
        out = res.stdout + ("\n--- STDERR ---\n" + res.stderr if res.stderr else "")
        if len(out) > 50000:
            out = out[:25000] + "\n...(truncated)...\n" + out[-25000:]
        prefix = f"exit_code={res.returncode}\n"
        return prefix + out
    except subprocess.TimeoutExpired:
        return "⚠️ TIMEOUT: command exceeded 120s."
    except Exception as e:
        return f"⚠️ SHELL_ERROR: {e}"


def _opencode_edit(ctx: ToolContext, prompt: str, cwd: str = "") -> str:
    """Delegate code edits to OpenCode CLI. Can take up to 1 hour."""
    from ouroboros.tools.git import _acquire_git_lock, _release_git_lock

    opencode_bin = "/home/a/.opencode/bin/opencode"
    if not os.path.exists(opencode_bin):
        return "⚠️ OpenCode CLI not found at /home/a/.opencode/bin/opencode."

    work_dir = str(ctx.repo_dir)
    if cwd and cwd.strip() not in ("", ".", "./"):
        candidate = (ctx.repo_dir / cwd).resolve()
        if candidate.exists():
            work_dir = str(candidate)

    ctx.emit_progress_fn("Delegating to OpenCode CLI (this may take a long time)...")

    lock = _acquire_git_lock(ctx)
    try:
        try:
            run_cmd(["git", "checkout", ctx.branch_dev], cwd=ctx.repo_dir)
        except Exception as e:
            return f"⚠️ GIT_ERROR (checkout): {e}"

        # OpenCode expects a message via 'run' command
        cmd = [opencode_bin, "run", prompt]
        
        env = os.environ.copy()
        # Add bin to path just in case it needs other tools from its bundle
        env["PATH"] = f"/home/a/.opencode/bin:{env.get('PATH', '')}"

        res = subprocess.run(
            cmd, cwd=work_dir,
            capture_output=True, text=True, timeout=3600, env=env,
        )

        stdout = (res.stdout or "").strip()
        stderr = (res.stderr or "").strip()
        
        # Check git status after edit
        status = ""
        try:
            status_res = subprocess.run(["git", "status", "--porcelain"], cwd=ctx.repo_dir, capture_output=True, text=True, timeout=10)
            if status_res.stdout.strip():
                status = f"\n\n⚠️ UNCOMMITTED CHANGES detected after OpenCode edit:\n{status_res.stdout.strip()}"
        except Exception:
            pass

        if res.returncode != 0:
            return f"⚠️ OPENCODE_ERROR: exit={res.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}{status}"
        
        return f"OK: OpenCode completed.\nSTDOUT:\n{stdout}{status}"

    except subprocess.TimeoutExpired:
        return "⚠️ OPENCODE_TIMEOUT: exceeded 3600s."
    except Exception as e:
        return f"⚠️ OPENCODE_FAILED: {type(e).__name__}: {e}"
    finally:
        _release_git_lock(lock)


def _run_linter(ctx: ToolContext, path: str) -> str:
    """Check Python file for syntax errors using py_compile."""
    full_path = ctx.repo_path(path)
    if not full_path.exists():
        return f"⚠️ LINTER_ERROR: file not found: {path}"
    
    if not path.endswith(".py"):
        return f"⚠️ LINTER_SKIP: Not a Python file: {path}"

    try:
        res = subprocess.run(
            ["python3", "-m", "py_compile", str(full_path)],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode == 0:
            return f"✅ LINTER_OK: {path} is syntactically correct."
        else:
            return f"❌ LINTER_FAIL: {path} has syntax errors.\n{res.stderr}"
    except Exception as e:
        return f"⚠️ LINTER_ERROR: {e}"


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("run_shell", {
            "name": "run_shell",
            "description": "Run a shell command (list of args) inside the repo. Returns stdout+stderr.",
            "parameters": {"type": "object", "properties": {
                "cmd": {"type": "array", "items": {"type": "string"}},
                "cwd": {"type": "string", "default": ""},
            }, "required": ["cmd"]},
        }, _run_shell, is_code_tool=True),
        ToolEntry("opencode_edit", {
            "name": "opencode_edit",
            "description": "Delegate code edits to OpenCode CLI. Preferred for complex refactors. NOTE: This tool can run for up to 1 hour.",
            "parameters": {"type": "object", "properties": {
                "prompt": {"type": "string", "description": "Instructions for OpenCode"},
                "cwd": {"type": "string", "default": ""},
            }, "required": ["prompt"]},
        }, _opencode_edit, is_code_tool=True, timeout_sec=3600),
        ToolEntry("run_linter", {
            "name": "run_linter",
            "description": "Check a Python file for syntax errors. Use this after every manual edit.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string", "description": "Relative path to the .py file"},
            }, "required": ["path"]},
        }, _run_linter, is_code_tool=True),
    ]
