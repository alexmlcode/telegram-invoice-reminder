"""
Telethon background listener — incoming messages to the @alessiper user account.

Handles:
  - Private DMs → "tg_user_message" events
  - Group/supergroup mentions → "tg_group_mention" events (only when @alessiper is
    mentioned, replied-to, or the message is a reply to one of our messages)

Runs in a daemon thread with its own asyncio event loop.
On each qualifying message, puts a dict into a thread-safe Queue.
The supervisor main loop drains this queue and creates user_chat tasks.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def _patch_telethon_sqlite() -> None:
    """Patch Telethon's SQLiteSession to use WAL journal + 10s busy timeout.

    WAL mode allows concurrent readers while one writer is active, greatly
    reducing 'database is locked' errors when tg_listener and agent tools
    both open the same session file from different processes.
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

_listener_queue: queue.Queue = queue.Queue()
_listener_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

# Retry delay on auth failure — wait before re-checking session (in case it
# was just restored). Does NOT permanently disable the listener.
_AUTH_RETRY_SEC = 120


def get_queue() -> queue.Queue:
    return _listener_queue


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


async def _is_mentioned(event: Any, me_id: int, my_username: Optional[str]) -> bool:
    """Return True if our account is mentioned or the message is a reply to us."""
    msg = event.message
    text = (msg.text or "").lower()

    # @username mention in plain text
    if my_username and f"@{my_username.lower()}" in text:
        return True

    # Telegram entity-based mention (InputMentionName / MentionName entities)
    if msg.entities:
        for ent in msg.entities:
            uid = getattr(ent, "user_id", None)
            if uid is not None and uid == me_id:
                return True

    # Reply to one of our own messages
    if getattr(msg, "reply_to", None) and getattr(msg.reply_to, "reply_to_msg_id", None):
        try:
            replied = await event.get_reply_message()
            if replied and replied.sender_id == me_id:
                return True
        except Exception:
            pass

    return False


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
            # Session not ready yet — wait and retry, don't permanently disable.
            log.warning(
                "tg_listener: session not authorized — will retry in %ds", _AUTH_RETRY_SEC
            )
            await client.disconnect()
            await asyncio.sleep(_AUTH_RETRY_SEC)
            return  # outer while loop will reconnect

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

            # Skip self-messages
            if sender_id == my_id:
                return

            first = getattr(sender, "first_name", "") or ""
            last  = getattr(sender, "last_name",  "") or ""
            name  = (first + " " + last).strip() or f"user_{sender_id}"
            uname = getattr(sender, "username", "") or ""

            reply_to_msg_id: Optional[int] = None
            if getattr(msg, "reply_to", None):
                reply_to_msg_id = getattr(msg.reply_to, "reply_to_msg_id", None)

            # ── Private DM ──────────────────────────────────────────────────────
            if event.is_private:
                # Skip owner — they use the privileged bot-token channel
                if owner_tg_id and sender_id == owner_tg_id:
                    return

                log.info("tg_listener: DM from %s (@%s): %.80s", name, uname, msg.text)
                _listener_queue.put({
                    "type":              "tg_user_message",
                    "chat_type":         "private",
                    "chat_id":           sender_id,
                    "chat_title":        name,
                    "msg_id":            msg.id,
                    "reply_to_msg_id":   reply_to_msg_id,
                    "sender_id":         sender_id,
                    "sender_name":       name,
                    "sender_username":   uname,
                    "text":              msg.text,
                })

            # ── Group / supergroup ───────────────────────────────────────────────
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
                    "type":              "tg_group_mention",
                    "chat_type":         "group",
                    "chat_id":           event.chat_id,
                    "chat_title":        chat_title,
                    "msg_id":            msg.id,
                    "reply_to_msg_id":   reply_to_msg_id,
                    "sender_id":         sender_id,
                    "sender_name":       name,
                    "sender_username":   uname,
                    "text":              msg.text,
                })

        await client.run_until_disconnected()
    finally:
        # Clean disconnect to suppress "Task destroyed" noise on shutdown
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass
