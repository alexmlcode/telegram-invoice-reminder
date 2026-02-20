"""External repository tools: sync/list/read for GitHub repos."""

from __future__ import annotations

import json
import logging
import pathlib
import re
import subprocess
from typing import List, Tuple

from ouroboros.tools.registry import ToolContext, ToolEntry
from ouroboros.utils import read_text, safe_relpath

log = logging.getLogger(__name__)

_ALIAS_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}$")


def _repos_root(ctx: ToolContext) -> pathlib.Path:
    root = ctx.drive_path("archive/external_repos")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_github_url(url: str) -> Tuple[str, str]:
    raw = str(url or "").strip()
    if not raw:
        raise ValueError("url is required")

    # git@github.com:owner/repo(.git)
    if raw.startswith("git@github.com:"):
        tail = raw[len("git@github.com:") :]
        if tail.endswith(".git"):
            tail = tail[:-4]
        parts = [p for p in tail.split("/") if p]
        if len(parts) != 2:
            raise ValueError(f"Invalid GitHub SSH URL: {url}")
        owner, repo = parts
        canonical = f"https://github.com/{owner}/{repo}.git"
        return canonical, f"{owner}__{repo}"

    # https://github.com/owner/repo(.git)
    if raw.startswith("https://github.com/"):
        tail = raw[len("https://github.com/") :]
        if tail.endswith(".git"):
            tail = tail[:-4]
        parts = [p for p in tail.split("/") if p]
        if len(parts) < 2:
            raise ValueError(f"Invalid GitHub HTTPS URL: {url}")
        owner, repo = parts[0], parts[1]
        canonical = f"https://github.com/{owner}/{repo}.git"
        return canonical, f"{owner}__{repo}"

    raise ValueError("Only GitHub repositories are supported (git@github.com or https://github.com)")


def _safe_alias(alias: str, fallback: str) -> str:
    candidate = str(alias or "").strip() or fallback
    if not _ALIAS_RE.match(candidate):
        raise ValueError("alias must match [a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}")
    return candidate


def _resolve_repo_dir(ctx: ToolContext, repo: str) -> pathlib.Path:
    alias = _safe_alias(repo, repo)
    root = _repos_root(ctx).resolve()
    path = (root / alias).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escape detected for repo alias '{repo}'") from exc
    return path


def _run_git(args: List[str], cwd: pathlib.Path | None = None, timeout: int = 180) -> str:
    cmd = ["git"] + args
    res = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if res.returncode != 0:
        stderr = (res.stderr or "").strip()
        stdout = (res.stdout or "").strip()
        detail = stderr or stdout or f"git exited {res.returncode}"
        raise RuntimeError(detail)
    return (res.stdout or "").strip()


def _checkout_latest(repo_dir: pathlib.Path) -> str:
    # Prefer remote default branch. Fallback to common names.
    refs = ["origin/HEAD", "origin/main", "origin/master"]
    for ref in refs:
        try:
            _run_git(["checkout", "--detach", ref], cwd=repo_dir, timeout=120)
            return ref
        except Exception:
            continue
    raise RuntimeError("Failed to checkout origin/HEAD (or main/master fallback)")


def _external_repo_sync(ctx: ToolContext, url: str, alias: str = "", ref: str = "") -> str:
    try:
        canonical_url, fallback_alias = _normalize_github_url(url)
        repo_alias = _safe_alias(alias, fallback_alias)
    except ValueError as e:
        return f"⚠️ INPUT_ERROR: {e}"

    root = _repos_root(ctx)
    repo_dir = (root / repo_alias).resolve()

    try:
        if not (repo_dir / ".git").exists():
            if repo_dir.exists():
                return f"⚠️ PATH_CONFLICT: {repo_dir} exists but is not a git repository."
            _run_git(
                ["clone", "--filter=blob:none", "--no-tags", canonical_url, str(repo_dir)],
                timeout=300,
            )
            action = "cloned"
        else:
            _run_git(["remote", "set-url", "origin", canonical_url], cwd=repo_dir)
            action = "updated"

        if ref and str(ref).strip():
            _run_git(["fetch", "--depth", "1", "origin", str(ref).strip()], cwd=repo_dir, timeout=300)
            _run_git(["checkout", "--detach", "FETCH_HEAD"], cwd=repo_dir, timeout=120)
            checked_out = f"FETCH_HEAD ({ref.strip()})"
        else:
            _run_git(["fetch", "--depth", "1", "origin"], cwd=repo_dir, timeout=300)
            checked_out = _checkout_latest(repo_dir)

        sha = _run_git(["rev-parse", "HEAD"], cwd=repo_dir, timeout=30)
        status_short = _run_git(["status", "--short"], cwd=repo_dir, timeout=30)

        payload = {
            "status": action,
            "repo_alias": repo_alias,
            "origin_url": canonical_url,
            "path": str(repo_dir),
            "checked_out": checked_out,
            "commit": sha,
            "dirty": bool(status_short.strip()),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("external_repo_sync failed", exc_info=True)
        return f"⚠️ EXTERNAL_REPO_SYNC_ERROR: {e}"


def _external_repo_list(ctx: ToolContext, repo: str, dir: str = ".", max_entries: int = 500) -> str:
    try:
        repo_dir = _resolve_repo_dir(ctx, repo)
    except ValueError as e:
        return f"⚠️ INPUT_ERROR: {e}"

    if not repo_dir.exists() or not (repo_dir / ".git").exists():
        return f"⚠️ REPO_NOT_FOUND: '{repo}' is not synced yet. Call external_repo_sync first."

    try:
        rel = safe_relpath(dir or ".")
        target = (repo_dir / rel).resolve()
        try:
            target.relative_to(repo_dir.resolve())
        except ValueError:
            return "⚠️ PATH_ERROR: directory escapes repository root."
        if not target.exists():
            return f"⚠️ NOT_FOUND: {dir}"
        if not target.is_dir():
            return f"⚠️ NOT_A_DIRECTORY: {dir}"

        items = []
        for entry in sorted(target.iterdir()):
            if len(items) >= int(max_entries):
                items.append(f"...(truncated at {max_entries})")
                break
            suffix = "/" if entry.is_dir() else ""
            items.append(str(entry.relative_to(repo_dir)) + suffix)
        return json.dumps(items, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("external_repo_list failed", exc_info=True)
        return f"⚠️ EXTERNAL_REPO_LIST_ERROR: {e}"


def _external_repo_read(ctx: ToolContext, repo: str, path: str, max_chars: int = 120000) -> str:
    try:
        repo_dir = _resolve_repo_dir(ctx, repo)
    except ValueError as e:
        return f"⚠️ INPUT_ERROR: {e}"

    if not repo_dir.exists() or not (repo_dir / ".git").exists():
        return f"⚠️ REPO_NOT_FOUND: '{repo}' is not synced yet. Call external_repo_sync first."

    try:
        rel = safe_relpath(path)
        target = (repo_dir / rel).resolve()
        try:
            target.relative_to(repo_dir.resolve())
        except ValueError:
            return "⚠️ PATH_ERROR: file escapes repository root."
        if not target.exists():
            return f"⚠️ NOT_FOUND: {path}"
        if not target.is_file():
            return f"⚠️ NOT_A_FILE: {path}"

        text = read_text(target)
        cap = max(1000, int(max_chars))
        if len(text) > cap:
            return text[:cap] + f"\n\n...(truncated, original {len(text)} chars)..."
        return text
    except Exception as e:
        log.warning("external_repo_read failed", exc_info=True)
        return f"⚠️ EXTERNAL_REPO_READ_ERROR: {e}"


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry(
            "external_repo_sync",
            {
                "name": "external_repo_sync",
                "description": (
                    "Clone or refresh a GitHub repository into Drive cache for cross-project learning. "
                    "Supports HTTPS or SSH GitHub URLs; checks out latest default branch by default."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "GitHub repo URL (https://github.com/... or git@github.com:... )"},
                        "alias": {"type": "string", "description": "Optional local alias for cached repo"},
                        "ref": {"type": "string", "description": "Optional branch/tag/commit-ish to checkout"},
                    },
                    "required": ["url"],
                },
            },
            _external_repo_sync,
            is_code_tool=True,
            timeout_sec=300,
        ),
        ToolEntry(
            "external_repo_list",
            {
                "name": "external_repo_list",
                "description": "List files in a cached external repository synced by external_repo_sync.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "Repo alias returned by external_repo_sync"},
                        "dir": {"type": "string", "default": ".", "description": "Subdirectory path"},
                        "max_entries": {"type": "integer", "default": 500},
                    },
                    "required": ["repo"],
                },
            },
            _external_repo_list,
        ),
        ToolEntry(
            "external_repo_read",
            {
                "name": "external_repo_read",
                "description": "Read a text file from a cached external repository synced by external_repo_sync.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "Repo alias returned by external_repo_sync"},
                        "path": {"type": "string", "description": "File path inside external repo"},
                        "max_chars": {"type": "integer", "default": 120000},
                    },
                    "required": ["repo", "path"],
                },
            },
            _external_repo_read,
        ),
    ]

