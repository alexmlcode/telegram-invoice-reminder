"""
Email tools — Gmail IMAP/SMTP via Google App Password.

Requires env vars:
  EMAIL_ADDRESS      — Gmail address (e.g. user@gmail.com)
  EMAIL_APP_PASSWORD — Google App Password (16 chars, no spaces)
  EMAIL_IMAP_HOST    — default: imap.gmail.com
  EMAIL_SMTP_HOST    — default: smtp.gmail.com
"""
from __future__ import annotations

import email as _emaillib
import imaplib
import json
import logging
import os
import smtplib
from email.header import decode_header as _decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Any, Dict, List, Optional

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def _creds():
    addr = os.environ.get("EMAIL_ADDRESS", "")
    pw   = os.environ.get("EMAIL_APP_PASSWORD", "")
    if not addr or not pw:
        raise RuntimeError(
            "EMAIL_ADDRESS and EMAIL_APP_PASSWORD must be set in env"
        )
    return addr, pw


def _imap_host() -> str:
    return os.environ.get("EMAIL_IMAP_HOST", "imap.gmail.com")


def _smtp_host() -> str:
    return os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_str(raw: Any) -> str:
    """Decode a possibly-encoded email header value to plain str."""
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


def _get_body(msg) -> str:
    """Extract plaintext body from a parsed email.Message (prefers text/plain)."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ct == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(charset, errors="replace")[:2000]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")[:2000]
    return ""


def _parse_message(raw_bytes: bytes) -> Dict[str, Any]:
    """Parse raw RFC 2822 bytes into a structured dict."""
    msg = _emaillib.message_from_bytes(raw_bytes)
    return {
        "message_id":  msg.get("Message-ID", "").strip(),
        "from":        _decode_str(msg.get("From", "")),
        "to":          _decode_str(msg.get("To", "")),
        "cc":          _decode_str(msg.get("Cc", "")),
        "subject":     _decode_str(msg.get("Subject", "")),
        "date":        msg.get("Date", ""),
        "body":        _get_body(msg),
        "in_reply_to": msg.get("In-Reply-To", "").strip(),
        "references":  msg.get("References", "").strip(),
    }


def _imap_connect() -> imaplib.IMAP4_SSL:
    addr, pw = _creds()
    imap = imaplib.IMAP4_SSL(_imap_host(), 993)
    imap.login(addr, pw)
    return imap


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _email_read(ctx: ToolContext, folder: str = "INBOX",
                limit: int = 10, unread_only: bool = False) -> str:
    """Read emails from a folder. Returns list of messages newest-first."""
    try:
        imap = _imap_connect()
        imap.select(f'"{folder}"')

        criteria = "UNSEEN" if unread_only else "ALL"
        _, data = imap.search(None, criteria)
        ids = data[0].split()
        if not ids:
            imap.logout()
            return json.dumps({"folder": folder, "messages": [], "total": 0})

        # Take the last `limit` ids (newest) in reverse order
        selected = ids[-min(int(limit), len(ids)):][::-1]

        messages = []
        for uid in selected:
            _, raw_data = imap.fetch(uid, "(RFC822 FLAGS)")
            if not raw_data or raw_data[0] is None:
                continue
            # raw_data[0] = (b'... FLAGS (\\Seen)', b'<raw bytes>')
            flags_info = raw_data[0][0] if isinstance(raw_data[0], tuple) else b""
            raw_bytes  = raw_data[0][1] if isinstance(raw_data[0], tuple) else raw_data[0]
            if not isinstance(raw_bytes, bytes):
                continue
            parsed = _parse_message(raw_bytes)
            parsed["unread"] = b"\\Seen" not in flags_info
            parsed["uid"] = uid.decode()
            messages.append(parsed)

        imap.logout()
        return json.dumps({"folder": folder, "messages": messages,
                           "total": len(ids)}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _email_search(ctx: ToolContext, query: str, limit: int = 10) -> str:
    """Search emails using Gmail/IMAP search syntax.

    Examples: 'from:boss@co.com', 'subject:invoice', 'is:unread', 'has:attachment'.
    Gmail-specific terms require X-GM-RAW extension (available via Gmail IMAP).
    """
    try:
        imap = _imap_connect()
        imap.select("INBOX")

        # Try Gmail X-GM-RAW first (supports full Gmail search)
        try:
            _, data = imap.search(None, f'X-GM-RAW "{query}"')
        except Exception:
            # Fallback to basic IMAP search (subject/from/body TEXT)
            safe = query.replace('"', "")
            _, data = imap.search(None, f'TEXT "{safe}"')

        ids = data[0].split()
        if not ids:
            imap.logout()
            return json.dumps({"query": query, "messages": [], "total": 0})

        selected = ids[-min(int(limit), len(ids)):][::-1]
        messages = []
        for uid in selected:
            _, raw_data = imap.fetch(uid, "(RFC822 FLAGS)")
            if not raw_data or raw_data[0] is None:
                continue
            flags_info = raw_data[0][0] if isinstance(raw_data[0], tuple) else b""
            raw_bytes  = raw_data[0][1] if isinstance(raw_data[0], tuple) else raw_data[0]
            if not isinstance(raw_bytes, bytes):
                continue
            parsed = _parse_message(raw_bytes)
            parsed["unread"] = b"\\Seen" not in flags_info
            parsed["uid"] = uid.decode()
            messages.append(parsed)

        imap.logout()
        return json.dumps({"query": query, "messages": messages,
                           "total": len(ids)}, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _email_send(ctx: ToolContext, to: str, subject: str, body: str,
                cc: str = "") -> str:
    """Send an email to one or more recipients."""
    try:
        addr, pw = _creds()
        msg = MIMEMultipart("alternative")
        msg["From"]    = addr
        msg["To"]      = to
        msg["Subject"] = subject
        msg["Date"]    = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        if cc:
            msg["Cc"] = cc
        msg.attach(MIMEText(body, "plain", "utf-8"))

        recipients = [a.strip() for a in (to + ("," + cc if cc else "")).split(",") if a.strip()]
        smtp = smtplib.SMTP(_smtp_host(), 587)
        smtp.ehlo()
        smtp.starttls()
        smtp.login(addr, pw)
        smtp.sendmail(addr, recipients, msg.as_bytes())
        smtp.quit()
        log.info("email_send: sent to %s subject=%r", to, subject)
        return json.dumps({"sent": True, "to": to, "subject": subject,
                           "message_id": msg["Message-ID"]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"sent": False, "error": str(e)}, ensure_ascii=False)


def _email_reply(ctx: ToolContext, message_id: str, to: str,
                 subject: str, body: str) -> str:
    """Reply to an existing email, preserving the thread.

    message_id: the Message-ID header of the original email
                (e.g. '<CABxxx@mail.gmail.com>').
    to:         recipient address(es), comma-separated.
    subject:    reply subject (usually 'Re: original subject').
    body:       plaintext reply body.
    """
    try:
        addr, pw = _creds()
        msg = MIMEMultipart("alternative")
        msg["From"]       = addr
        msg["To"]         = to
        msg["Subject"]    = subject
        msg["Date"]       = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        msg["In-Reply-To"] = message_id
        msg["References"]  = message_id
        msg.attach(MIMEText(body, "plain", "utf-8"))

        recipients = [a.strip() for a in to.split(",") if a.strip()]
        smtp = smtplib.SMTP(_smtp_host(), 587)
        smtp.ehlo()
        smtp.starttls()
        smtp.login(addr, pw)
        smtp.sendmail(addr, recipients, msg.as_bytes())
        smtp.quit()
        log.info("email_reply: replied to %s thread=%s", to, message_id)
        return json.dumps({"sent": True, "to": to, "subject": subject,
                           "in_reply_to": message_id,
                           "message_id": msg["Message-ID"]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"sent": False, "error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("email_read", {
            "name": "email_read",
            "description": (
                "Read emails from Gmail. Returns newest messages first with "
                "from/to/subject/date/body/message_id fields. "
                "Use message_id from results to reply with email_reply."
            ),
            "parameters": {"type": "object", "properties": {
                "folder": {"type": "string",
                           "description": "Folder to read (default: INBOX)",
                           "default": "INBOX"},
                "limit":  {"type": "integer",
                           "description": "Max messages to return (default: 10, max: 50)",
                           "default": 10},
                "unread_only": {"type": "boolean",
                                "description": "Only return unread messages",
                                "default": False},
            }},
        }, _email_read, timeout_sec=30),

        ToolEntry("email_search", {
            "name": "email_search",
            "description": (
                "Search Gmail using search syntax. "
                "Supports Gmail terms: 'from:x@y.com', 'subject:invoice', "
                "'is:unread', 'has:attachment', 'after:2024/01/01', etc."
            ),
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string",
                          "description": "Gmail search query"},
                "limit": {"type": "integer",
                          "description": "Max results (default: 10)", "default": 10},
            }, "required": ["query"]},
        }, _email_search, timeout_sec=30),

        ToolEntry("email_send", {
            "name": "email_send",
            "description": "Send a new email from the configured Gmail account.",
            "parameters": {"type": "object", "properties": {
                "to":      {"type": "string",
                            "description": "Recipient(s), comma-separated"},
                "subject": {"type": "string", "description": "Email subject"},
                "body":    {"type": "string", "description": "Plaintext body"},
                "cc":      {"type": "string",
                            "description": "CC recipients, comma-separated (optional)",
                            "default": ""},
            }, "required": ["to", "subject", "body"]},
        }, _email_send, timeout_sec=30),

        ToolEntry("email_reply", {
            "name": "email_reply",
            "description": (
                "Reply to an existing email, preserving the Gmail thread. "
                "Get message_id from email_read results."
            ),
            "parameters": {"type": "object", "properties": {
                "message_id": {"type": "string",
                               "description": "Message-ID of the email being replied to "
                                              "(e.g. '<CABxxx@mail.gmail.com>')"},
                "to":      {"type": "string",
                            "description": "Reply-to address(es), comma-separated"},
                "subject": {"type": "string",
                            "description": "Reply subject (usually 'Re: original subject')"},
                "body":    {"type": "string", "description": "Plaintext reply body"},
            }, "required": ["message_id", "to", "subject", "body"]},
        }, _email_reply, timeout_sec=30),
    ]
