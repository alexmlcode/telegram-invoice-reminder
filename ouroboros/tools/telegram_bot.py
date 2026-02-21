"""
Telegram user-mode tools — act as a real Telegram user.

Uses Telethon (MTProto). Requires:
  TELEGRAM_API_ID, TELEGRAM_API_HASH  — from my.telegram.org
  TELEGRAM_SESSION_PATH               — path to .session file (SQLite)

All tools share a single persistent client per process (lazy connect).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client lifecycle — one persistent client per process
# ---------------------------------------------------------------------------

_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_creds():
    api_id   = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    session  = os.environ.get("TELEGRAM_SESSION_PATH", "session.session")
    if not api_id or not api_hash:
        raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in env")
    return int(api_id), api_hash, session


def _run(coro):
    """Run async coroutine in a dedicated thread-safe event loop."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop.run_until_complete(coro)


async def _make_client():
    """Create a fresh connected Telethon client. Caller must disconnect when done.

    Does NOT maintain a persistent client: tg_listener owns the persistent
    session connection; tools connect briefly and disconnect to avoid
    concurrent keepalive conflicts causing 'database is locked' errors.
    """
    from telethon import TelegramClient
    for attempt in range(4):
        try:
            api_id, api_hash, session = _get_creds()
            client = TelegramClient(session, api_id, api_hash)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise RuntimeError(
                    "Telegram session not authorized. Run tg_auth_step1 on server, "
                    "enter the code, then tg_auth_step2 <code>."
                )
            return client
        except RuntimeError:
            raise
        except Exception as exc:
            if "database is locked" in str(exc).lower() and attempt < 3:
                log.warning("Telegram session locked, retry %d/3 in %ds", attempt + 1, 2 ** attempt)
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError("Telegram session unavailable after retries")


def _fmt_entity(e) -> Dict[str, Any]:
    """Format a Telegram entity (user/chat/channel) to dict.

    Types returned:
      "user"       — private user
      "channel"    — broadcast channel (read-only, post by admins)
      "supergroup" — megagroup (Channel with megagroup=True / broadcast=False)
      "group"      — legacy small group (Chat)
    """
    from telethon.tl.types import User, Chat, Channel
    if isinstance(e, User):
        return {"type": "user", "id": e.id,
                "name": f"{e.first_name or ''} {e.last_name or ''}".strip(),
                "username": e.username or ""}
    if isinstance(e, Channel):
        # broadcast=True → channel; broadcast=False → supergroup/megagroup
        t = "channel" if e.broadcast else "supergroup"
        return {"type": t, "id": e.id, "name": e.title or "",
                "username": e.username or ""}
    if isinstance(e, Chat):
        return {"type": "group", "id": e.id, "name": e.title or ""}
    return {"type": "unknown", "id": getattr(e, "id", None)}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tg_get_me(ctx: ToolContext) -> str:
    """Check session status and return current user info."""
    async def _inner():
        c = await _make_client()
        try:
            me = await c.get_me()
            return json.dumps({
                "id": me.id,
                "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
                "username": me.username or "",
                "phone": me.phone or "",
                "authorized": True,
            }, ensure_ascii=False)
        finally:
            await c.disconnect()
    try:
        return _run(_inner())
    except Exception as e:
        return json.dumps({"authorized": False, "error": str(e)}, ensure_ascii=False)


def _tg_send(ctx: ToolContext, entity: str, message: str,
             parse_mode: str = "", reply_to: int = 0) -> str:
    """Send a message to a user, group, or channel."""
    async def _inner():
        c = await _make_client()
        try:
            kwargs = {}
            if parse_mode in ("markdown", "md"):
                kwargs["parse_mode"] = "md"
            elif parse_mode in ("html",):
                kwargs["parse_mode"] = "html"
            if reply_to:
                kwargs["reply_to"] = int(reply_to)
            sent = await c.send_message(entity, message, **kwargs)
            return json.dumps({"sent": True, "message_id": sent.id,
                               "to": entity}, ensure_ascii=False)
        finally:
            await c.disconnect()
    try:
        return _run(_inner())
    except Exception as e:
        return json.dumps({"sent": False, "error": str(e)}, ensure_ascii=False)


def _tg_read(ctx: ToolContext, entity: str, limit: int = 20,
             min_id: int = 0) -> str:
    """Read recent messages from a chat, group, or channel."""
    async def _inner():
        c = await _make_client()
        try:
            msgs = []
            kwargs: Dict[str, Any] = {"limit": min(int(limit), 100)}
            if min_id:
                kwargs["min_id"] = int(min_id)
            async for msg in c.iter_messages(entity, **kwargs):
                sender = ""
                if msg.sender:
                    s = msg.sender
                    sender = (getattr(s, "username", None)
                              or getattr(s, "first_name", None)
                              or str(getattr(s, "id", "")))
                elif msg.post:
                    sender = "[channel]"
                msgs.append({
                    "id": msg.id,
                    "date": msg.date.isoformat() if msg.date else "",
                    "sender": sender,
                    "text": (msg.text or "")[:2000],
                    "is_reply": bool(msg.reply_to_msg_id),
                    "reply_to_msg_id": msg.reply_to_msg_id,
                })
            return json.dumps({"entity": entity, "messages": msgs},
                              ensure_ascii=False, indent=2)
        finally:
            await c.disconnect()
    try:
        return _run(_inner())
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _tg_get_entity(ctx: ToolContext, entity: str) -> str:
    """Resolve any entity (username, chat_id, link) and return its type and info.

    Use this to determine if a chat_id is a user DM, group, supergroup, or channel
    before deciding how to reply.
    """
    async def _inner():
        c = await _make_client()
        try:
            e = await c.get_entity(entity)
            return json.dumps(_fmt_entity(e), ensure_ascii=False)
        finally:
            await c.disconnect()
    try:
        return _run(_inner())
    except Exception as ex:
        return json.dumps({"error": str(ex)}, ensure_ascii=False)


def _tg_join(ctx: ToolContext, entity: str) -> str:
    """Join a public channel or group by username or invite link."""
    async def _inner():
        c = await _make_client()
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.tl.functions.messages import ImportChatInviteRequest
            if "joinchat/" in entity or entity.startswith("+"):
                hash_ = entity.split("/")[-1].lstrip("+")
                await c(ImportChatInviteRequest(hash_))
            else:
                await c(JoinChannelRequest(entity))
            return json.dumps({"joined": True, "entity": entity}, ensure_ascii=False)
        finally:
            await c.disconnect()
    try:
        return _run(_inner())
    except Exception as e:
        return json.dumps({"joined": False, "entity": entity,
                           "error": str(e)}, ensure_ascii=False)


def _tg_list_chats(ctx: ToolContext, limit: int = 50,
                   filter_type: str = "") -> str:
    """List joined chats, groups, and channels.

    filter_type: '' (all) | 'channels' | 'groups' | 'users'
    """
    async def _inner():
        c = await _make_client()
        try:
            from telethon.tl.types import User, Chat, Channel
            results = []
            async for dialog in c.iter_dialogs(limit=min(int(limit), 200)):
                e = dialog.entity
                if filter_type == "channels" and not (isinstance(e, Channel) and e.broadcast):
                    continue
                if filter_type == "groups" and not (isinstance(e, (Chat,)) or
                        (isinstance(e, Channel) and not e.broadcast)):
                    continue
                if filter_type == "users" and not isinstance(e, User):
                    continue
                info = _fmt_entity(e)
                info["unread"] = dialog.unread_count
                info["last_msg_date"] = dialog.date.isoformat() if dialog.date else ""
                results.append(info)
            return json.dumps({"chats": results, "count": len(results)},
                              ensure_ascii=False, indent=2)
        finally:
            await c.disconnect()
    try:
        return _run(_inner())
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _tg_search(ctx: ToolContext, query: str, limit: int = 10) -> str:
    """Search for public channels and groups by keyword."""
    async def _inner():
        c = await _make_client()
        try:
            from telethon.tl.functions.contacts import SearchRequest
            result = await c(SearchRequest(q=query, limit=min(int(limit), 50)))
            chats = [_fmt_entity(e) for e in result.chats]
            return json.dumps({"query": query, "results": chats},
                              ensure_ascii=False, indent=2)
        finally:
            await c.disconnect()
    try:
        return _run(_inner())
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
                             "description": "Message ID to reply to (for threaded replies in groups)", "default": 0},
            }, "required": ["entity", "message"]},
        }, _tg_send, timeout_sec=30),

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
                "Use before replying to know if you're in a DM, group, or channel."
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
