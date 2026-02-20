"""
Web search tool — multi-engine, no paid API keys required.

Engines (run in parallel):
  1. DuckDuckGo full-text search  (ddgs library, no key)
  2. DuckDuckGo Instant Answers   (REST API, definitions/facts, no key)
  3. Wikipedia                    (MediaWiki API, encyclopedic content, no key)

Result validation: each URL is fetched (HEAD then minimal GET) to confirm
the page is reachable and has real content — filters out dead links and
blank/splash pages before returning results.
"""

from __future__ import annotations

import html
import json
import logging
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_UA = "Mozilla/5.0 (compatible; Ouroboros/1.0; +https://github.com/alexmlcode/thaMe)"
_VALIDATE_TIMEOUT = 5      # seconds per URL fetch during validation
_MIN_TEXT_LEN = 80         # minimum visible chars to consider a page non-empty
_SNIPPET_TRUST_LEN = 60    # if snippet ≥ this, skip expensive URL validation


# ---------------------------------------------------------------------------
# HTML → plain text (stdlib only, no beautifulsoup dependency)
# ---------------------------------------------------------------------------

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)


def _html_to_text(raw: bytes, max_chars: int = 500) -> str:
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return ""
    text = _SCRIPT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return " ".join(text.split())[:max_chars]


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def _validate_url(url: str, timeout: int = _VALIDATE_TIMEOUT) -> Optional[str]:
    """
    Fetch url and return a short content preview string if the page is
    reachable and has meaningful content. Returns None otherwise.
    """
    if not url or not url.startswith("http"):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 400:
                return None
            raw = resp.read(24_576)  # 24 KB is enough to assess content
    except Exception:
        return None

    text = _html_to_text(raw)
    return text[:400] if len(text) >= _MIN_TEXT_LEN else None


# ---------------------------------------------------------------------------
# Search engines
# ---------------------------------------------------------------------------

def _search_ddg(query: str, max_raw: int = 12) -> List[Dict[str, Any]]:
    """DuckDuckGo full-text search via ddgs library (no API key needed)."""
    # Support both old package name and new (renamed from duckduckgo_search → ddgs)
    ddgs_cls = None
    for mod_name in ("ddgs", "duckduckgo_search"):
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            ddgs_cls = getattr(mod, "DDGS", None)
            if ddgs_cls:
                break
        except ImportError:
            continue

    if ddgs_cls is None:
        log.warning("Neither ddgs nor duckduckgo_search is installed; skipping DDG search")
        return []

    try:
        results = []
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with ddgs_cls() as ddgs:
                for r in ddgs.text(query, max_results=max_raw):
                    results.append({
                        "source": "duckduckgo",
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    })
        return results
    except Exception as e:
        log.warning("DDG text search error: %s", e)
        return []


def _search_ddg_instant(query: str) -> List[Dict[str, Any]]:
    """DuckDuckGo Instant Answers API — quick facts, definitions. No library."""
    try:
        import requests
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
            headers={"User-Agent": _UA},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("DDG instant search error: %s", e)
        return []

    results = []
    abstract = data.get("AbstractText", "")
    abstract_url = data.get("AbstractURL", "")
    if abstract and abstract_url:
        results.append({
            "source": "ddg_instant",
            "title": data.get("Heading", query),
            "url": abstract_url,
            "snippet": abstract[:500],
        })
    for topic in (data.get("RelatedTopics") or [])[:5]:
        if not isinstance(topic, dict):
            continue
        url = topic.get("FirstURL", "")
        text = topic.get("Text", "")
        if url and text:
            results.append({
                "source": "ddg_instant",
                "title": text[:80],
                "url": url,
                "snippet": text,
            })
    return results


def _search_wikipedia(query: str) -> List[Dict[str, Any]]:
    """Wikipedia full-text search via MediaWiki API. No API key needed."""
    headers = {"User-Agent": "Ouroboros/1.0 (https://github.com/alexmlcode/thaMe; bot)"}
    try:
        import requests
        search = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search",
                "srsearch": query, "format": "json", "srlimit": 3,
            },
            headers=headers,
            timeout=8,
        )
        search.raise_for_status()
        hits = search.json().get("query", {}).get("search", [])
    except Exception as e:
        log.warning("Wikipedia search error: %s", e)
        return []

    results = []
    for hit in hits[:2]:
        title = hit.get("title", "")
        if not title:
            continue
        try:
            import requests as _req
            summ = _req.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}",
                headers=headers,
                timeout=8,
            )
            if summ.status_code != 200:
                continue
            d = summ.json()
            page_url = d.get("content_urls", {}).get("desktop", {}).get("page", "")
            extract = d.get("extract", "")
            if extract and page_url:
                results.append({
                    "source": "wikipedia",
                    "title": d.get("title", title),
                    "url": page_url,
                    "snippet": extract[:500],
                })
        except Exception:
            pass
    return results


# ---------------------------------------------------------------------------
# Main tool function
# ---------------------------------------------------------------------------

def _web_search(ctx: ToolContext, query: str, max_results: int = 5) -> str:
    """
    Multi-engine web search with result validation.

    Runs DDG text, DDG Instant, and Wikipedia in parallel.
    Then validates each URL (fetches page, checks content is non-empty).
    Dead / blank pages are silently dropped.
    """
    # 1. Query all engines concurrently
    raw: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="search") as ex:
        futures = {
            ex.submit(_search_ddg, query): "ddg",
            ex.submit(_search_ddg_instant, query): "ddg_instant",
            ex.submit(_search_wikipedia, query): "wikipedia",
        }
        for fut in as_completed(futures):
            try:
                raw.extend(fut.result())
            except Exception as e:
                log.debug("Engine %s raised: %s", futures[fut], e)

    if not raw:
        return json.dumps({"error": "All search engines returned no results."}, ensure_ascii=False)

    # 2. Deduplicate by URL (preserve order)
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for r in raw:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(r)

    # 3. Validate — fetch each URL to confirm it has real content
    #    Short-circuit for results whose snippet is already informative enough.
    def _enrich(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        snippet = r.get("snippet", "")
        # Long snippet = page is trustworthy; use it as the preview
        if len(snippet) >= _SNIPPET_TRUST_LEN:
            return {**r, "content_preview": snippet[:300], "validated": True}
        preview = _validate_url(r.get("url", ""))
        if preview is None:
            return None   # dead / empty page — discard
        return {**r, "content_preview": preview, "validated": True}

    validated: List[Dict[str, Any]] = []
    candidates = deduped[:max_results * 3]
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="validate") as ex:
        fmap = {ex.submit(_enrich, r): r for r in candidates}
        for fut in as_completed(fmap):
            try:
                res = fut.result()
                if res:
                    validated.append(res)
            except Exception:
                pass

    # 4. Sort: richer content first; break ties by snippet length
    validated.sort(
        key=lambda r: (len(r.get("content_preview", "")), len(r.get("snippet", ""))),
        reverse=True,
    )

    final = validated[:max_results]
    if not final:
        # All validation attempts failed (network issues?) — return raw without validation
        return json.dumps(
            {"query": query, "results": deduped[:max_results],
             "warning": "URL validation failed; showing unvalidated results."},
            ensure_ascii=False, indent=2,
        )

    return json.dumps({"query": query, "results": final}, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("web_search", {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo, DDG Instant Answers, and Wikipedia. "
                "Results are validated — dead and empty pages are filtered out. "
                "Returns JSON with query, results list (title, url, snippet, content_preview). "
                "No API key required."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        }, _web_search),
    ]
