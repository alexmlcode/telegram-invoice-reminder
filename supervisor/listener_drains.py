"""
supervisor/listener_drains.py — Event drain loops for all listener threads.

Converts raw events from tg_listener / email_listener / linkedin_listener
into user_chat tasks and enqueues them.

Usage in colab_launcher:
    import supervisor.listener_drains as _drains
    _drains.init(enqueue_task, assign_tasks, load_state,
                 _tg_listener, _email_listener, _linkedin_listener)
    _drains.start_all()
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

# Injected by init()
_enqueue_task: Optional[Callable] = None
_assign_tasks: Optional[Callable] = None
_load_state:   Optional[Callable] = None
_tg_listener   = None
_email_listener = None
_linkedin_listener = None


def init(
    enqueue_task: Callable,
    assign_tasks: Callable,
    load_state:   Callable,
    tg_listener,
    email_listener,
    linkedin_listener,
) -> None:
    """Inject dependencies before calling start_all()."""
    global _enqueue_task, _assign_tasks, _load_state
    global _tg_listener, _email_listener, _linkedin_listener
    _enqueue_task      = enqueue_task
    _assign_tasks      = assign_tasks
    _load_state        = load_state
    _tg_listener       = tg_listener
    _email_listener    = email_listener
    _linkedin_listener = linkedin_listener


def start_all() -> None:
    """Start tg-drain, email-drain, and linkedin-drain daemon threads."""
    threading.Thread(target=_tg_drain_loop,       daemon=True, name="tg-drain").start()
    threading.Thread(target=_email_drain_loop,    daemon=True, name="email-drain").start()
    threading.Thread(target=_linkedin_drain_loop, daemon=True, name="linkedin-drain").start()


def _owner_chat_id() -> int:
    try:
        return int(_load_state().get("owner_chat_id") or 0)
    except Exception:
        return 0


# ── Telegram ─────────────────────────────────────────────────────────────────

def process_tg_event(evt: dict) -> None:
    """Convert one tg_listener event to a user_chat task and assign it."""
    _evt_type    = evt.get("type", "tg_user_message")
    _sender_id   = evt.get("sender_id", 0)
    _sender_name = evt.get("sender_name", "")
    _sender_user = evt.get("sender_username", "")
    _tg_text     = evt.get("text", "")
    _msg_id      = evt.get("msg_id", 0)
    _reply_to    = evt.get("reply_to_msg_id")
    _who = f"@{_sender_user}" if _sender_user else f"id={_sender_id}"

    if _evt_type == "tg_group_mention":
        _chat_id    = evt.get("chat_id", _sender_id)
        _chat_title = evt.get("chat_title", "")
        _reply_hint = f", reply_to={_msg_id}" if _msg_id else ""
        task_text = (
            f"GROUP_MENTION in '{_chat_title}' (chat_id={_chat_id}) "
            f"from {_sender_name} ({_who}):\n{_tg_text}\n\n"
            f"Reply in the group: tg_send(entity={_chat_id!r}, message=...{_reply_hint}).\n"
            f"Use tg_read(entity={_chat_id!r}, limit=15) to get conversation context first.\n"
            f"Act as a real Telegram user (@alessiper), not a bot assistant."
        )
        _enqueue_task({
            "id":          uuid.uuid4().hex[:8],
            "type":        "user_chat",
            "chat_id":     _owner_chat_id(),
            "text":        task_text,
            "sender_id":   _chat_id,
            "sender_name": _chat_title,
        })
    else:
        _reply_hint = f" Reply to message {_reply_to} if relevant." if _reply_to else ""
        task_text = (
            f"USER_CHAT from {_sender_name} ({_who}):\n{_tg_text}\n\n"
            f"Reply via tg_send(entity={_sender_id!r}, ...).{_reply_hint} "
            f"You are acting as @alessiper — a real Telegram personality, not a bot."
        )
        _enqueue_task({
            "id":          uuid.uuid4().hex[:8],
            "type":        "user_chat",
            "chat_id":     _owner_chat_id(),
            "text":        task_text,
            "sender_id":   _sender_id,
            "sender_name": _sender_name,
        })
    _assign_tasks()


def _tg_drain_loop() -> None:
    """Drain tg_listener event queue every 100ms."""
    while True:
        time.sleep(0.1)
        try:
            tg_q = _tg_listener.get_queue()
            while not tg_q.empty():
                try:
                    evt = tg_q.get_nowait()
                except Exception:
                    break
                try:
                    process_tg_event(evt)
                except Exception:
                    log.warning("tg-drain: failed to process event", exc_info=True)
        except Exception:
            log.warning("tg-drain thread error", exc_info=True)


# ── Email ─────────────────────────────────────────────────────────────────────

def process_email_event(evt: dict) -> None:
    """Convert one email_listener event to a user_chat task and assign it."""
    sender     = evt.get("from", "unknown")
    subject    = evt.get("subject", "(no subject)")
    message_id = evt.get("message_id", "")
    date       = evt.get("date", "")
    body       = evt.get("body", "")
    to_addr    = evt.get("to", "")

    task_text = (
        f"NEW_EMAIL received:\n"
        f"From:       {sender}\n"
        f"To:         {to_addr}\n"
        f"Subject:    {subject}\n"
        f"Date:       {date}\n"
        f"Message-ID: {message_id}\n\n"
        f"{body}\n\n"
        f"---\n"
        f"To reply: email_reply(message_id={message_id!r}, "
        f"to=<sender address>, subject='Re: {subject}', body=...)\n"
        f"To ignore: do nothing. Only reply if the email warrants a response."
    )
    _enqueue_task({
        "id":          uuid.uuid4().hex[:8],
        "type":        "user_chat",
        "chat_id":     _owner_chat_id(),
        "text":        task_text,
        "sender_id":   0,
        "sender_name": sender,
    })
    _assign_tasks()


def _email_drain_loop() -> None:
    """Drain email_listener event queue every 1s."""
    while True:
        time.sleep(1)
        try:
            eq = _email_listener.get_queue()
            while not eq.empty():
                try:
                    evt = eq.get_nowait()
                except Exception:
                    break
                try:
                    process_email_event(evt)
                except Exception:
                    log.warning("email-drain: failed to process event", exc_info=True)
        except Exception:
            log.warning("email-drain thread error", exc_info=True)


# ── LinkedIn ─────────────────────────────────────────────────────────────────

def process_linkedin_event(evt: dict) -> None:
    """Convert one linkedin_listener event to a user_chat task and assign it."""
    evt_type = evt.get("type", "")
    if evt_type == "linkedin_invitation":
        first  = evt.get("firstName", "")
        last   = evt.get("lastName", "")
        occ    = evt.get("occupation", "")
        url    = evt.get("profileUrl", "")
        msg    = evt.get("message", "")
        inv_id = evt.get("invitationId", "")
        secret = evt.get("sharedSecret", "")
        task_text = (
            f"NEW_LINKEDIN_INVITATION:\n"
            f"From: {first} {last}\n"
            f"Occupation: {occ}\n"
            f"Profile: {url}\n"
            f"Message: {msg or '(none)'}\n\n"
            f"To accept: linkedin_accept_invitation(invitation_id={inv_id!r}, shared_secret={secret!r})\n"
            f"To decline: do nothing or check if they're relevant first with web_search."
        )
        sender_name = f"{first} {last}".strip() or "LinkedIn"
    elif evt_type == "linkedin_message":
        participants = evt.get("participants", [])
        last_msg = evt.get("lastMessage", "")
        urn = evt.get("conversationUrn", "")
        names = ", ".join(participants[:3]) or "unknown"
        task_text = (
            f"NEW_LINKEDIN_MESSAGE from {names}:\n{last_msg}\n\n"
            f"To reply: linkedin_send_message(conversation_urn={urn!r}, text=...)\n"
            f"To read full context: linkedin_get_messages(limit=5)."
        )
        sender_name = names
    else:
        return

    _enqueue_task({
        "id":          uuid.uuid4().hex[:8],
        "type":        "user_chat",
        "chat_id":     _owner_chat_id(),
        "text":        task_text,
        "sender_id":   0,
        "sender_name": sender_name,
    })
    _assign_tasks()


def _linkedin_drain_loop() -> None:
    """Drain linkedin_listener event queue every 30s."""
    while True:
        time.sleep(30)
        try:
            lq = _linkedin_listener.get_queue()
            while not lq.empty():
                try:
                    evt = lq.get_nowait()
                except Exception:
                    break
                try:
                    process_linkedin_event(evt)
                except Exception:
                    log.warning("linkedin-drain: failed to process event", exc_info=True)
        except Exception:
            log.warning("linkedin-drain thread error", exc_info=True)
