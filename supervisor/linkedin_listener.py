"""
LinkedIn listener — polls Voyager API every 5 min for new messages and invitations.

Architecture mirrors email_listener: a daemon thread polls the API, puts events
into a thread-safe Queue, and a drain thread in colab_launcher converts events
to user_chat tasks.

Events put in queue:
  {
    "type":   "linkedin_invitation",
    "firstName": "...", "lastName": "...", "occupation": "...",
    "profileUrl": "https://linkedin.com/in/...",
    "invitationId": "...", "sharedSecret": "...",
    "message": "...",
  }
  {
    "type": "linkedin_message",
    "participants": ["Alice", "Bob"],
    "lastMessage": "...",
    "conversationUrn": "urn:li:fs_conversation:...",
  }

Requires env vars (optional — listener skipped if not set):
  LINKEDIN_LI_AT       — li_at cookie value
  LINKEDIN_JSESSIONID  — JSESSIONID value (without quotes)

Cookies expire periodically. When the API returns a redirect (session expired),
the listener logs a warning and pauses until the next poll.
"""
from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any, Dict, Optional, Set

log = logging.getLogger(__name__)

_linkedin_queue: queue.Queue = queue.Queue()
_listener_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()

POLL_INTERVAL_SEC = 300  # 5 minutes — conservative to avoid rate limiting


def get_queue() -> queue.Queue:
    return _linkedin_queue


def start() -> queue.Queue:
    """Start LinkedIn polling in a daemon thread. Returns the event queue."""
    global _listener_thread
    if _listener_thread is not None and _listener_thread.is_alive():
        return _linkedin_queue
    _stop_event.clear()
    _listener_thread = threading.Thread(
        target=_run, daemon=True, name="linkedin-listener"
    )
    _listener_thread.start()
    log.info("LinkedIn listener started (poll every %ds)", POLL_INTERVAL_SEC)
    return _linkedin_queue


def stop() -> None:
    _stop_event.set()


def is_running() -> bool:
    return _listener_thread is not None and _listener_thread.is_alive()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_session():
    """Build requests.Session with LinkedIn cookies. Returns (session, error_str)."""
    li_at = os.environ.get("LINKEDIN_LI_AT", "")
    jsid  = os.environ.get("LINKEDIN_JSESSIONID", "")
    if not li_at or not jsid:
        return None, "LINKEDIN_LI_AT and LINKEDIN_JSESSIONID not set"
    try:
        import requests
        s = requests.Session()
        for domain in [".linkedin.com", ".www.linkedin.com"]:
            s.cookies.set("li_at", li_at, domain=domain, path="/")
        s.cookies.set("JSESSIONID", f'"{jsid}"', domain=".www.linkedin.com", path="/")
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ),
            "csrf-token": jsid,
            "x-restli-protocol-version": "2.0.0",
            "accept": "application/vnd.linkedin.normalized+json+2.1",
            "x-li-lang": "en_US",
        })
        return s, None
    except ImportError:
        return None, "requests not installed"


def _api_get(path: str, params: Dict = None) -> Optional[Dict]:
    """GET Voyager API. Returns parsed JSON dict, or None on error/redirect."""
    s, err = _get_session()
    if err:
        return None
    try:
        r = s.get(f"https://www.linkedin.com{path}", params=params,
                  allow_redirects=False, timeout=15)
        if r.status_code in (301, 302, 303, 307, 308):
            log.warning("linkedin_listener: session expired (redirect). "
                        "Update LINKEDIN_LI_AT and LINKEDIN_JSESSIONID.")
            return None
        if r.status_code != 200:
            log.debug("linkedin_listener: API status %d for %s", r.status_code, path)
            return None
        return r.json()
    except Exception as e:
        log.debug("linkedin_listener: request error: %s", e)
        return None


# ── Main polling loop ─────────────────────────────────────────────────────────

def _run() -> None:
    seen_invitation_ids: Set[str] = set()
    # conversation_urn → last message text (to detect new messages)
    last_message_per_conv: Dict[str, str] = {}
    first_poll = True

    while not _stop_event.is_set():
        try:
            _poll(seen_invitation_ids, last_message_per_conv, first_poll)
        except Exception as e:
            log.warning("linkedin_listener: poll error: %s", e)
        first_poll = False
        _stop_event.wait(timeout=POLL_INTERVAL_SEC)


def _poll(
    seen_invitation_ids: Set[str],
    last_message_per_conv: Dict[str, str],
    first_poll: bool,
) -> None:
    """Poll invitations and messages, enqueue new ones."""
    # ── Invitations ─────────────────────────────────────────────────
    inv_data = _api_get(
        "/voyager/api/relationships/invitationViews",
        params={"q": "receivedInvitation", "start": 0, "count": 20},
    )
    if inv_data is not None:
        elements = inv_data.get("elements", [])
        for el in elements:
            m   = el.get("fromMember", {}).get("miniProfile", {})
            inv = el.get("invitation", {})
            inv_id = str(inv.get("invitationId", ""))
            if not inv_id:
                continue
            if inv_id in seen_invitation_ids:
                continue
            seen_invitation_ids.add(inv_id)
            if first_poll:
                continue  # baseline — don't fire for pre-existing invitations
            evt: Dict[str, Any] = {
                "type":         "linkedin_invitation",
                "firstName":    m.get("firstName", ""),
                "lastName":     m.get("lastName", ""),
                "occupation":   m.get("occupation", "")[:80],
                "profileUrl":   f"https://linkedin.com/in/{m.get('publicIdentifier', '')}",
                "invitationId": inv_id,
                "sharedSecret": inv.get("sharedSecret", ""),
                "message":      inv.get("message", ""),
            }
            log.info("linkedin_listener: new invitation from %s %s",
                     evt["firstName"], evt["lastName"])
            _linkedin_queue.put(evt)

    # ── Messages ─────────────────────────────────────────────────────
    msg_data = _api_get(
        "/voyager/api/messaging/conversations",
        params={"keyVersion": "LEGACY_INBOX", "start": 0, "count": 20},
    )
    if msg_data is not None:
        elements = msg_data.get("elements", [])
        for c in elements:
            urn = c.get("entityUrn", "")
            if not urn:
                continue
            events = c.get("events", [])
            if not events:
                continue
            body = events[0].get("eventContent", {}).get("attributedBody", {})
            last_text = body.get("text", "")[:500] if body else ""

            prev = last_message_per_conv.get(urn)
            last_message_per_conv[urn] = last_text

            if first_poll:
                continue  # baseline — don't fire for existing conversations

            if last_text and last_text != prev:
                participants = [
                    p.get("miniProfile", {}).get("firstName", "?")
                    for p in c.get("participants", [])
                    if p.get("miniProfile", {}).get("firstName")
                ]
                evt = {
                    "type":            "linkedin_message",
                    "participants":    participants,
                    "lastMessage":     last_text,
                    "conversationUrn": urn,
                }
                log.info("linkedin_listener: new message in conversation with %s",
                         ", ".join(participants[:3]))
                _linkedin_queue.put(evt)
