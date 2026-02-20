"""
GitHub search tool — uses GitHub REST API (no paid key; GITHUB_TOKEN optional for higher limits).

Supports searching:
  - repositories   (type="repositories") — name, description, stars, URL
  - code           (type="code")        — file name, repo, URL, text preview
  - topics         (type="topics")      — topic name, description, curated flag
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_UA = "Ouroboros/1.0 (https://github.com/alexmlcode/thaMe; bot)"


def _headers() -> Dict[str, str]:
    h = {"User-Agent": _UA, "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_API_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _get(path: str, params: Dict[str, Any], timeout: int = 12) -> Any:
    url = f"{_API_BASE}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _search_repos(query: str, max_results: int) -> List[Dict[str, Any]]:
    data = _get("/search/repositories", {
        "q": query, "sort": "stars", "order": "desc", "per_page": min(max_results, 10),
    })
    results = []
    for item in (data.get("items") or [])[:max_results]:
        results.append({
            "type": "repository",
            "title": item.get("full_name", ""),
            "url": item.get("html_url", ""),
            "description": (item.get("description") or "")[:300],
            "stars": item.get("stargazers_count", 0),
            "language": item.get("language") or "",
            "updated_at": item.get("updated_at", ""),
        })
    return results


def _search_code(query: str, max_results: int) -> List[Dict[str, Any]]:
    data = _get("/search/code", {
        "q": query, "per_page": min(max_results, 10),
    })
    results = []
    for item in (data.get("items") or [])[:max_results]:
        repo = item.get("repository", {})
        results.append({
            "type": "code",
            "title": item.get("name", ""),
            "url": item.get("html_url", ""),
            "repo": repo.get("full_name", ""),
            "repo_url": repo.get("html_url", ""),
            "repo_stars": repo.get("stargazers_count", 0),
            "path": item.get("path", ""),
        })
    return results


def _search_topics(query: str, max_results: int) -> List[Dict[str, Any]]:
    data = _get("/search/topics", {
        "q": query, "per_page": min(max_results, 10),
    }, )
    results = []
    for item in (data.get("items") or [])[:max_results]:
        results.append({
            "type": "topic",
            "title": item.get("name", ""),
            "url": f"https://github.com/topics/{item.get('name', '')}",
            "description": (item.get("short_description") or item.get("description") or "")[:300],
            "curated": bool(item.get("curated")),
        })
    return results


def _github_search(ctx: ToolContext, query: str,
                   type: str = "repositories", max_results: int = 5) -> str:  # noqa: A002
    """Search GitHub. type: 'repositories' | 'code' | 'topics'."""
    type = str(type or "repositories").lower().strip()
    max_results = max(1, min(int(max_results or 5), 20))

    try:
        if type == "code":
            results = _search_code(query, max_results)
        elif type == "topics":
            results = _search_topics(query, max_results)
        else:
            results = _search_repos(query, max_results)
    except Exception as e:
        log.warning("github_search error: %s", e)
        token_hint = " (tip: set GITHUB_TOKEN env var for higher rate limits)" if "403" in str(e) or "rate" in str(e).lower() else ""
        return json.dumps({"error": f"GitHub search failed: {e}{token_hint}"}, ensure_ascii=False)

    return json.dumps({"query": query, "type": type, "results": results},
                      ensure_ascii=False, indent=2)


def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("github_search", {
            "name": "github_search",
            "description": (
                "Search GitHub for repositories, code snippets, or topics. "
                "Useful for finding patterns, libraries, and implementations to inspire self-improvement. "
                "Returns JSON with query results. No API key required; set GITHUB_TOKEN for higher rate limits."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "type": {
                        "type": "string",
                        "enum": ["repositories", "code", "topics"],
                        "description": "What to search: repositories (default), code snippets, or topics",
                        "default": "repositories",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (1-20, default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        }, _github_search),
    ]
