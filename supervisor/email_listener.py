"""
Email listener — polls Gmail IMAP every 60s for new UNSEEN messages.

Architecture mirrors tg_listener: a daemon thread polls IMAP, puts events
into a thread-safe Queue, and a background drain thread in colab_launcher
converts events to user_chat tasks immediately (without waiting for the
bot-API long-poll cycle).

Events put in queue:
  {
    "type":       "email_message",
    "from":       "Name <addr@domain.com>",
    "to":         "me@gmail.com",
    "subject":    "Hello",
    "message_id": "<CABxxx@mail.gmail.com>",
    "date":       "Fri, 21 Feb 2026 ...",
    "body":       "...(up to 3000 chars)...",
  }

Requires env vars (optional — listener is skipped if not set):
  EMAIL_ADDRESS      — Gmail address
  EMAIL_APP_PASSWORD — Google App Password (16 chars, no spaces)
  EMAIL_IMAP_HOST    — default: imap.gmail.com
"""
from __future__ import annotations

import email as _emaillib
import imaplib
import logging
import os
import queue
import threading
import time
from email.header import decode_header as _decode_header
from typing import Any, Optional

log = logging.getLogger(__name__)

_email_queue: queue.Queue = queue.Queue()
_listener_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

POLL_INTERVAL_SEC = 60


def get_queue() -> queue.Queue:
    return _email_queue


def start() -> queue.Queue:
    """Start IMAP polling in a daemon thread. Returns the event queue."""
    global _listener_thread
    if _listener_thread is not None and _listener_thread.is_alive():
        return _email_queue
    _stop_event.clear()
    _listener_thread = threading.Thread(
        target=_run, daemon=True, name="email-listener"
    )
    _listener_thread.start()
    log.info("Email listener started (poll every %ds)", POLL_INTERVAL_SEC)
    return _email_queue


def stop() -> None:
    _stop_event.set()


def is_running() -> bool:
    return _listener_thread is not None and _listener_thread.is_alive()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_str(raw: Any) -> str:
    if raw is None:
        return ""
    parts = _decode_header(str(raw))
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _get_body(msg: Any) -> str:
    """Extract plaintext body, preferring text/plain over text/html."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ct == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(charset, errors="replace")[:3000]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")[:3000]
    return ""


# ── Main polling loop ─────────────────────────────────────────────────────────

def _run() -> None:
    seen_uids: set = set()
    while not _stop_event.is_set():
        try:
            _poll(seen_uids)
        except Exception as e:
            log.warning("email_listener: poll error: %s", e)
        _stop_event.wait(timeout=POLL_INTERVAL_SEC)


def _poll(seen_uids: set) -> None:
    """Connect to IMAP, find UNSEEN messages, enqueue new ones, mark as seen."""
    addr     = os.environ.get("EMAIL_ADDRESS", "")
    pw       = os.environ.get("EMAIL_APP_PASSWORD", "")
    imap_host = os.environ.get("EMAIL_IMAP_HOST", "imap.gmail.com")
    if not addr or not pw:
        return

    imap = imaplib.IMAP4_SSL(imap_host, 993)
    try:
        imap.login(addr, pw)
        imap.select("INBOX")

        _, data = imap.search(None, "UNSEEN")
        uids = data[0].split() if data and data[0] else []
        if not uids:
            return

        for uid in uids:
            uid_str = uid.decode()
            if uid_str in seen_uids:
                continue
            seen_uids.add(uid_str)

            # Fetch raw RFC822 bytes
            _, raw_data = imap.fetch(uid, "(RFC822)")
            if not raw_data or raw_data[0] is None:
                continue
            raw_bytes = raw_data[0][1] if isinstance(raw_data[0], tuple) else raw_data[0]
            if not isinstance(raw_bytes, bytes):
                continue

            # Mark as \Seen so restarts don't re-enqueue processed mail
            try:
                imap.store(uid, "+FLAGS", "\\Seen")
            except Exception:
                pass

            msg = _emaillib.message_from_bytes(raw_bytes)
            evt = {
                "type":       "email_message",
                "from":       _decode_str(msg.get("From", "")),
                "to":         _decode_str(msg.get("To", "")),
                "subject":    _decode_str(msg.get("Subject", "")),
                "message_id": msg.get("Message-ID", "").strip(),
                "date":       msg.get("Date", ""),
                "body":       _get_body(msg),
            }
            log.info("email_listener: new email from %s subject=%r",
                     evt["from"], evt["subject"][:60])
            _email_queue.put(evt)
    finally:
        try:
            imap.logout()
        except Exception:
            pass
