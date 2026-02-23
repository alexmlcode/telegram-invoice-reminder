"""
Telegram user-mode tools — act as a real Telegram user.

All tools communicate with the single persistent TelegramClient owned by
supervisor/tg_listener.py via a multiprocessing.Queue command bus.

No direct Telethon connections here — zero SQLite locking possible.

Requires (on server):
  TELEGRAM_API_ID, TELEGRAM_API_HASH  — from my.telegram.org
  TELEGRAM_SESSION_PATH               — path to .session file (SQLite)
"""
from __future__ import annotations

import json
import logging
import os
import queue as _stdlib_queue
import time
import uuid
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# PID of the process that imported this module.
# consciousness and supervisor run in the main process; workers are forked children.
_MAIN_PID: int = os.getpid()


# ---------------------------------------------------------------------------
# Command queue bridge — talks to the single TelegramClient in tg_listener
# ---------------------------------------------------------------------------

def _tg_exec(method: str, timeout: float = 25, **kwargs) -> Any:
    """Send a command to the Telethon service and wait for result.

    Two code paths depending on caller:

    Main process (consciousness, supervisor):
      Uses _local_cmd_queue (stdlib queue.Queue). No pickling needed — the
      listener daemon thread and consciousness thread share the same process.
      Result delivered via result_q (also stdlib queue.Queue, no pickling).

    Worker process (forked child):
      Uses _cmd_queue (multiprocessing.Queue with inherited FDs). Can only
      send picklable data, so passes a corr_id (str) instead of result_q.
      Listener delivers result to _worker_result_queue (pre-fork, shared).
      Worker polls _worker_result_queue filtering by corr_id.

    Raises RuntimeError if the service doesn't respond or returns an error.
    """
    from supervisor.tg_listener import (
        get_cmd_queue, get_local_cmd_queue, get_worker_result_queue,
    )

    if os.getpid() == _MAIN_PID:
        # ── Main process path ──────────────────────────────────────────────
        # thread-safe queue; no pickling; listener reads it every 50ms
        result_q: _stdlib_queue.Queue = _stdlib_queue.Queue()
        get_local_cmd_queue().put({"method": method, "kwargs": kwargs, "result_q": result_q})
        try:
            resp = result_q.get(timeout=timeout)
        except _stdlib_queue.Empty:
            raise RuntimeError(
                "Telegram service did not respond in time "
                "(is tg_listener running?)"
            )
    else:
        # ── Worker process path ────────────────────────────────────────────
        # Use corr_id instead of result_q — only picklable data in cmd dict
        corr_id = uuid.uuid4().hex
        get_cmd_queue().put({"method": method, "kwargs": kwargs, "corr_id": corr_id})
        wrq = get_worker_result_queue()
        deadline = time.monotonic() + timeout
        resp = None
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                item = wrq.get(timeout=min(remaining, 0.5))
                if item.get("corr_id") == corr_id:
                    resp = item
                    break
                # Belongs to another worker — put back immediately so they can find it.
                # Do NOT hold in a pending list: that causes livelock when workers run
                # concurrently (each holds the other's result until their own deadline).
                try:
                    wrq.put_nowait(item)
                except Exception:
                    pass
            except _stdlib_queue.Empty:
                continue  # keep polling until deadline; don't give up early
        if resp is None:
            raise RuntimeError(
                "Telegram service did not respond in time "
                "(is tg_listener running?)"
            )

    if not resp.get("ok"):
        raise RuntimeError(resp.get("error", "unknown error from Telegram service"))
    return resp["result"]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tg_get_me(ctx: ToolContext) -> str:
    """Check session status and return current user info."""
    try:
        return json.dumps(_tg_exec("get_me"), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"authorized": False, "error": str(e)}, ensure_ascii=False)


def _tg_send(ctx: ToolContext, entity: str, message: str,
             parse_mode: str = "", reply_to: int = 0) -> str:
    """Send a message to a user, group, or channel."""
    try:
        result = _tg_exec("send_message", entity=entity, message=message,
                          parse_mode=parse_mode, reply_to=reply_to)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"sent": False, "error": str(e)}, ensure_ascii=False)


def _tg_read(ctx: ToolContext, entity: str, limit: int = 20,
             min_id: int = 0) -> str:
    """Read recent messages from a chat, group, or channel."""
    try:
        msgs = _tg_exec("iter_messages", timeout=30,
                        entity=entity, limit=limit, min_id=min_id)
        return json.dumps({"entity": entity, "messages": msgs},
                          ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _tg_get_entity(ctx: ToolContext, entity: str) -> str:
    """Resolve any entity (username, chat_id, link) and return its type and info.

    Use this to determine if a chat_id is a user DM, group, supergroup, or channel
    before deciding how to reply.
    """
    try:
        return json.dumps(_tg_exec("get_entity", timeout=15, entity=entity),
                          ensure_ascii=False)
    except Exception as ex:
        return json.dumps({"error": str(ex)}, ensure_ascii=False)


def _tg_join(ctx: ToolContext, entity: str) -> str:
    """Join a public channel or group by username or invite link."""
    try:
        return json.dumps(_tg_exec("join_channel", entity=entity),
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"joined": False, "entity": entity,
                           "error": str(e)}, ensure_ascii=False)


def _tg_list_chats(ctx: ToolContext, limit: int = 50,
                   filter_type: str = "") -> str:
    """List joined chats, groups, and channels.

    filter_type: '' (all) | 'channels' | 'groups' | 'users'
    """
    try:
        results = _tg_exec("iter_dialogs", timeout=30,
                           limit=limit, filter_type=filter_type)
        return json.dumps({"chats": results, "count": len(results)},
                          ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _tg_search(ctx: ToolContext, query: str, limit: int = 10) -> str:
    """Search for public channels and groups by keyword."""
    try:
        results = _tg_exec("search_contacts", query=query, limit=limit)
        return json.dumps({"query": query, "results": results},
                          ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("tg_get_me", {
            "name": "tg_get_me",
            "description": "Check Telegram session status. Returns current user info if authorized.",
            "parameters": {"type": "object", "properties": {}},
        }, _tg_get_me),

        ToolEntry("tg_send", {
            "name": "tg_send",
            "description": (
                "Send a Telegram message to a user, group, or channel. "
                "entity: username (@durov), chat_id (-1001234), phone, or 'me'."
            ),
            "parameters": {"type": "object", "properties": {
                "entity": {"type": "string", "description": "Username, chat_id, phone, or 'me'"},
                "message": {"type": "string", "description": "Message text"},
                "parse_mode": {"type": "string", "enum": ["", "markdown", "html"],
                               "description": "Text formatting (optional)", "default": ""},
                "reply_to": {"type": "integer",
                             "description": "Message ID to reply to (for threaded replies in groups)",
                             "default": 0},
            }, "required": ["entity", "message"]},
        }, _tg_send, timeout_sec=25),

        ToolEntry("tg_read", {
            "name": "tg_read",
            "description": (
                "Read recent messages from a Telegram chat, group, or channel. "
                "Works for channels the account is subscribed to."
            ),
            "parameters": {"type": "object", "properties": {
                "entity": {"type": "string", "description": "Username, chat_id, or invite link"},
                "limit": {"type": "integer", "description": "Number of messages (max 100)", "default": 20},
                "min_id": {"type": "integer", "description": "Only fetch messages after this ID", "default": 0},
            }, "required": ["entity"]},
        }, _tg_read, timeout_sec=30),

        ToolEntry("tg_join", {
            "name": "tg_join",
            "description": (
                "Join a public Telegram channel or group. "
                "entity: @username or invite link (t.me/joinchat/... or t.me/+...)."
            ),
            "parameters": {"type": "object", "properties": {
                "entity": {"type": "string", "description": "Channel @username or invite link"},
            }, "required": ["entity"]},
        }, _tg_join, timeout_sec=30),

        ToolEntry("tg_list_chats", {
            "name": "tg_list_chats",
            "description": "List all joined Telegram chats, groups, and channels with unread counts.",
            "parameters": {"type": "object", "properties": {
                "limit": {"type": "integer", "description": "Max chats to return (default 50)", "default": 50},
                "filter_type": {"type": "string",
                                "enum": ["", "channels", "groups", "users"],
                                "description": "Filter by type (default: all)", "default": ""},
            }},
        }, _tg_list_chats, timeout_sec=30),

        ToolEntry("tg_search", {
            "name": "tg_search",
            "description": "Search for public Telegram channels and groups by keyword.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default 10)", "default": 10},
            }, "required": ["query"]},
        }, _tg_search, timeout_sec=30),

        ToolEntry("tg_get_entity", {
            "name": "tg_get_entity",
            "description": (
                "Resolve a Telegram entity and return its type and info. "
                "Returns type: 'user' | 'channel' | 'supergroup' | 'group'. "
                "Use before replying to know if you'm in a DM, group, or channel."
            ),
            "parameters": {"type": "object", "properties": {
                "entity": {"type": "string",
                           "description": "Username (@x), chat_id, phone, or invite link"},
            }, "required": ["entity"]},
        }, _tg_get_entity, timeout_sec=15),

        ToolEntry("tg_connect", {
            "name": "tg_connect",
            "description": "Test Telegram connection. Alias for tg_get_me.",
            "parameters": {"type": "object", "properties": {}},
        }, _tg_get_me),
    ]