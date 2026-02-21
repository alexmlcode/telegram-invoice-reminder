"""
Telethon background listener + Telegram service for the @alessiper user account.

Handles:
  - Private DMs → "tg_user_message" events
  - Group/supergroup mentions → "tg_group_mention" events (only when @alessiper is
    mentioned, replied-to, or the message is a reply to one of our messages)
  - Command queue → worker processes send Telegram commands here and receive results

Architecture: ONE permanent TelegramClient in the listener thread.
All agent tools communicate via _cmd_queue (multiprocessing.Queue).
This eliminates concurrent SQLite session access and "database is locked" errors.

  Worker process:
      result_q = multiprocessing.Queue()
      _cmd_queue.put({"method": "send_message", "kwargs": {...}, "result_q": result_q})
      resp = result_q.get(timeout=30)  # {"ok": True, "result": {...}}

Runs in a daemon thread with its own asyncio event loop.
On each qualifying message, puts a dict into a thread-safe Queue.
The supervisor main loop drains this queue and creates user_chat tasks.
"""
from __future__ import annotations

import asyncio
import logging
import multiprocessing
import queue
import threading
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def _patch_telethon_sqlite() -> None:
    """Patch Telethon's SQLiteSession to use WAL journal + 10s busy timeout.

    WAL mode allows concurrent readers while one writer is active.
    With command-queue architecture this is belt-and-suspenders protection.
    """
    try:
        from telethon.sessions import sqlite as _tl_sq
        _orig_cursor = _tl_sq.SQLiteSession._cursor

        def _patched_cursor(self):
            cursor = _orig_cursor(self)
            if getattr(self, "_wal_patched", False):
                return cursor
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA busy_timeout=10000")
            except Exception:
                pass
            self._wal_patched = True
            return cursor

        _tl_sq.SQLiteSession._cursor = _patched_cursor
    except Exception as e:
        log.debug("Telethon WAL patch skipped: %s", e)


_patch_telethon_sqlite()

# ── Queues ────────────────────────────────────────────────────────────────────
# Incoming events (DMs, mentions) → supervisor main loop
_listener_queue: queue.Queue = queue.Queue()

# Outgoing commands → listener async loop (multiprocessing-safe, fork-inherited)
_cmd_queue: multiprocessing.Queue = multiprocessing.Queue()

_listener_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

# Retry delay on auth failure
_AUTH_RETRY_SEC = 120


def get_queue() -> queue.Queue:
    return _listener_queue


def get_cmd_queue() -> multiprocessing.Queue:
    """Return the command queue. Imported by telegram_bot tools at module level."""
    return _cmd_queue


def start(session_path: str, api_id: int, api_hash: str,
          owner_tg_id: Optional[int] = None) -> queue.Queue:
    """Start Telethon listener in background daemon thread. Returns the event queue."""
    global _listener_thread
    if _listener_thread is not None and _listener_thread.is_alive():
        return _listener_queue

    _stop_event.clear()

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while not _stop_event.is_set():
            try:
                loop.run_until_complete(
                    _listener_loop(session_path, api_id, api_hash, owner_tg_id)
                )
            except Exception as exc:
                log.warning("tg_listener error: %s — reconnecting in 30s", exc)
                time.sleep(30)

    _listener_thread = threading.Thread(target=_run, daemon=True, name="tg-listener")
    _listener_thread.start()
    log.info("Telethon user-mode listener started (session=%s)", session_path)
    return _listener_queue


def stop() -> None:
    _stop_event.set()


def is_running() -> bool:
    return _listener_thread is not None and _listener_thread.is_alive()


# ── Entity formatting (shared between listener and command executor) ───────────

def _fmt_entity(e) -> Dict[str, Any]:
    """Format a Telegram entity to a plain dict for JSON serialisation."""
    try:
        from telethon.tl.types import User, Chat, Channel
        if isinstance(e, User):
            return {"type": "user", "id": e.id,
                    "name": f"{e.first_name or ''} {e.last_name or ''}".strip(),
                    "username": e.username or ""}
        if isinstance(e, Channel):
            t = "channel" if e.broadcast else "supergroup"
            return {"type": t, "id": e.id, "name": e.title or "",
                    "username": e.username or ""}
        if isinstance(e, Chat):
            return {"type": "group", "id": e.id, "name": e.title or ""}
    except Exception:
        pass
    return {"type": "unknown", "id": getattr(e, "id", None)}


# ── Command dispatcher ─────────────────────────────────────────────────────────

async def _execute_cmd(client, cmd: dict) -> None:
    """Execute one Telegram command and put the result on cmd["result_q"]."""
    result_q: Optional[multiprocessing.Queue] = cmd.get("result_q")
    if result_q is None:
        return
    try:
        result = await _dispatch(client, cmd.get("method", ""), cmd.get("kwargs", {}))
        result_q.put({"ok": True, "result": result})
    except Exception as exc:
        result_q.put({"ok": False, "error": str(exc)})


async def _dispatch(client, method: str, kw: dict) -> Any:
    """Route a command to the appropriate Telethon call."""

    if method == "send_message":
        extra: Dict[str, Any] = {}
        pm = kw.get("parse_mode", "")
        if pm in ("markdown", "md"):
            extra["parse_mode"] = "md"
        elif pm == "html":
            extra["parse_mode"] = "html"
        if kw.get("reply_to"):
            extra["reply_to"] = int(kw["reply_to"])
        sent = await client.send_message(kw["entity"], kw["message"], **extra)
        return {"sent": True, "message_id": sent.id, "to": kw["entity"]}

    if method == "get_me":
        me = await client.get_me()
        return {
            "id": me.id,
            "name": f"{me.first_name or ''} {me.last_name or ''}".strip(),
            "username": me.username or "",
            "phone": getattr(me, "phone", "") or "",
            "authorized": True,
        }

    if method == "get_entity":
        e = await client.get_entity(kw["entity"])
        return _fmt_entity(e)

    if method == "iter_messages":
        msgs = []
        kwargs: Dict[str, Any] = {"limit": min(int(kw.get("limit", 20)), 100)}
        if kw.get("min_id"):
            kwargs["min_id"] = int(kw["min_id"])
        async for msg in client.iter_messages(kw["entity"], **kwargs):
            sender_str = ""
            if msg.sender:
                s = msg.sender
                sender_str = (getattr(s, "username", None)
                              or getattr(s, "first_name", None)
                              or str(getattr(s, "id", "")))
            elif msg.post:
                sender_str = "[channel]"
            msgs.append({
                "id":              msg.id,
                "date":            msg.date.isoformat() if msg.date else "",
                "sender":          sender_str,
                "text":            (msg.text or "")[:2000],
                "is_reply":        bool(msg.reply_to_msg_id),
                "reply_to_msg_id": msg.reply_to_msg_id,
            })
        return msgs

    if method == "iter_dialogs":
        from telethon.tl.types import User, Chat, Channel as _Ch
        results = []
        ft = kw.get("filter_type", "")
        async for dialog in client.iter_dialogs(limit=min(int(kw.get("limit", 50)), 200)):
            e = dialog.entity
            if ft == "channels" and not (isinstance(e, _Ch) and e.broadcast):
                continue
            if ft == "groups" and not (isinstance(e, Chat) or
                    (isinstance(e, _Ch) and not e.broadcast)):
                continue
            if ft == "users" and not isinstance(e, User):
                continue
            info = _fmt_entity(e)
            info["unread"] = dialog.unread_count
            info["last_msg_date"] = dialog.date.isoformat() if dialog.date else ""
            results.append(info)
        return results

    if method == "join_channel":
        from telethon.tl.functions.channels import JoinChannelRequest
        from telethon.tl.functions.messages import ImportChatInviteRequest
        entity = kw["entity"]
        if "joinchat/" in entity or entity.startswith("+"):
            hash_ = entity.split("/")[-1].lstrip("+")
            await client(ImportChatInviteRequest(hash_))
        else:
            await client(JoinChannelRequest(entity))
        return {"joined": True, "entity": entity}

    if method == "search_contacts":
        from telethon.tl.functions.contacts import SearchRequest
        result = await client(SearchRequest(q=kw["query"],
                                            limit=min(int(kw.get("limit", 10)), 50)))
        return [_fmt_entity(e) for e in result.chats]

    raise ValueError(f"Unknown tg_listener command: {method!r}")


# ── Mention detection ──────────────────────────────────────────────────────────

async def _is_mentioned(event: Any, me_id: int, my_username: Optional[str]) -> bool:
    """Return True if our account is mentioned or the message is a reply to us."""
    msg = event.message
    text = (msg.text or "").lower()

    if my_username and f"@{my_username.lower()}" in text:
        return True

    if msg.entities:
        for ent in msg.entities:
            uid = getattr(ent, "user_id", None)
            if uid is not None and uid == me_id:
                return True

    if getattr(msg, "reply_to", None) and getattr(msg.reply_to, "reply_to_msg_id", None):
        try:
            replied = await event.get_reply_message()
            if replied and replied.sender_id == me_id:
                return True
        except Exception:
            pass

    return False


# ── Main listener loop ─────────────────────────────────────────────────────────

async def _listener_loop(session_path: str, api_id: int, api_hash: str,
                          owner_tg_id: Optional[int]) -> None:
    try:
        from telethon import TelegramClient, events
    except ImportError:
        log.warning("telethon not installed — user-mode listener disabled")
        _stop_event.set()
        return

    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()

        if not await client.is_user_authorized():
            log.warning(
                "tg_listener: session not authorized — will retry in %ds", _AUTH_RETRY_SEC
            )
            await client.disconnect()
            await asyncio.sleep(_AUTH_RETRY_SEC)
            return

        me = await client.get_me()
        my_id = me.id
        my_username: Optional[str] = getattr(me, "username", None)
        log.info("tg_listener: ready as @%s (id=%s)", my_username or my_id, my_id)

        @client.on(events.NewMessage(incoming=True))
        async def _on_message(event):
            msg = event.message
            if not msg or not (msg.text or "").strip():
                return

            sender = await event.get_sender()
            if sender is None:
                return
            sender_id = sender.id

            if sender_id == my_id:
                return

            first = getattr(sender, "first_name", "") or ""
            last  = getattr(sender, "last_name",  "") or ""
            name  = (first + " " + last).strip() or f"user_{sender_id}"
            uname = getattr(sender, "username", "") or ""

            reply_to_msg_id: Optional[int] = None
            if getattr(msg, "reply_to", None):
                reply_to_msg_id = getattr(msg.reply_to, "reply_to_msg_id", None)

            if event.is_private:
                if owner_tg_id and sender_id == owner_tg_id:
                    return
                log.info("tg_listener: DM from %s (@%s): %.80s", name, uname, msg.text)
                _listener_queue.put({
                    "type":            "tg_user_message",
                    "chat_type":       "private",
                    "chat_id":         sender_id,
                    "chat_title":      name,
                    "msg_id":          msg.id,
                    "reply_to_msg_id": reply_to_msg_id,
                    "sender_id":       sender_id,
                    "sender_name":     name,
                    "sender_username": uname,
                    "text":            msg.text,
                })

            elif event.is_group or event.is_channel:
                mentioned = await _is_mentioned(event, my_id, my_username)
                if not mentioned:
                    return
                try:
                    chat = await event.get_chat()
                    chat_title = getattr(chat, "title", "") or str(event.chat_id)
                except Exception:
                    chat_title = str(event.chat_id)

                log.info("tg_listener: GROUP_MENTION in '%s' from %s (@%s): %.80s",
                         chat_title, name, uname, msg.text)
                _listener_queue.put({
                    "type":            "tg_group_mention",
                    "chat_type":       "group",
                    "chat_id":         event.chat_id,
                    "chat_title":      chat_title,
                    "msg_id":          msg.id,
                    "reply_to_msg_id": reply_to_msg_id,
                    "sender_id":       sender_id,
                    "sender_name":     name,
                    "sender_username": uname,
                    "text":            msg.text,
                })

        # ── Service loop: drain command queue + keep Telethon alive ──────────
        # Replaces run_until_disconnected() so we can process outgoing commands
        # through the same client without opening additional connections.
        while not _stop_event.is_set():
            if not client.is_connected():
                break  # outer while will reconnect

            # Drain pending commands (non-blocking)
            while True:
                try:
                    cmd = _cmd_queue.get_nowait()
                    asyncio.ensure_future(_execute_cmd(client, cmd))
                except Exception:
                    break

            # Yield to event loop — Telethon processes received updates here
            await asyncio.sleep(0.05)

    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass
