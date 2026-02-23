"""Patch tools: apply_patch."""

from __future__ import annotations

import logging
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry
from ouroboros.utils import utc_now_iso, run_cmd

log = logging.getLogger(__name__)


def _apply_patch(ctx: ToolContext, patch: str) -> str:
    """Apply a multi-file patch using the internal apply_patch.py mechanism.
    
    Patch format:
    *** Begin Patch
    *** Update File: path/to/file.py
    - old line
    + new line
    *** End Patch
    """
    patch_script = ctx.repo_dir / "ouroboros" / "apply_patch.py"
    if not patch_script.exists():
        return f"⚠️ PATCH_ERROR: apply_patch.py not found at {patch_script}"

    try:
        # Run the script and pass patch to stdin
        process = subprocess.Popen(
            [sys.executable, str(patch_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ctx.repo_dir),
            text=True
        )
        stdout, stderr = process.communicate(input=patch)
        
        if process.returncode == 0:
            return f"✅ PATCH_APPLIED: Successfully applied patch.\n{stdout}"
        else:
            return f"❌ PATCH_FAILED: exit={process.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
            
    except Exception as e:
        return f"⚠️ PATCH_ERROR: {e}"


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("apply_patch", {
            "name": "apply_patch",
            "description": "Apply a surgical patch to one or more files. Use this for files > 300 lines to avoid corruption.",
            "parameters": {"type": "object", "properties": {
                "patch": {"type": "string", "description": "The patch content in *** Update File: format"},
            }, "required": ["patch"]},
        }, _apply_patch, is_code_tool=True),
    ]
