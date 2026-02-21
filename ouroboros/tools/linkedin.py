"""
LinkedIn tools via Playwright APIRequestContext.

Uses Chromium's HTTP stack (correct TLS fingerprint) without page navigation,
avoiding redirect loops caused by IP-bound li_at cookies.
Cookies injected via add_cookies() are automatically used by ctx.request.

Required env vars (set in .env on server, never in git):
  LINKEDIN_LI_AT       — li_at cookie value
  LINKEDIN_JSESSIONID  — JSESSIONID value, WITHOUT quotes (e.g. ajax:1234...)
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)

# Persistent browser profile dir (saves session between calls)
def _profile_dir() -> str:
    drive = os.environ.get("DRIVE_ROOT", str(pathlib.Path.home() / ".ouroboros"))
    d = str(pathlib.Path(drive) / "memory" / "linkedin_browser")
    os.makedirs(d, exist_ok=True)
    return d


def _make_context(p):
    """Launch a persistent Chromium context (no page navigation needed)."""
    return p.chromium.launch_persistent_context(
        _profile_dir(),
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ],
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
        timezone_id="Europe/Moscow",
        ignore_https_errors=False,
    )


def _inject_cookies(ctx, li_at: str, jsid: str) -> None:
    """Inject LinkedIn session cookies into the browser context."""
    ctx.add_cookies([
        {"name": "li_at",      "value": li_at,            "domain": ".linkedin.com",     "path": "/"},
        {"name": "li_at",      "value": li_at,            "domain": ".www.linkedin.com", "path": "/"},
        {"name": "JSESSIONID", "value": f'"{jsid}"',      "domain": ".www.linkedin.com", "path": "/"},
        {"name": "lang",       "value": "v=2&lang=en-us", "domain": ".linkedin.com",     "path": "/"},
    ])


def _run(fn):
    """Run fn(ctx, jsid) with injected LinkedIn cookies via Playwright APIRequestContext.

    Uses Chromium's HTTP stack (correct TLS fingerprint) — no page navigation,
    so no redirect loops from IP-bound sessions.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"error": "playwright not installed"}

    li_at = os.environ.get("LINKEDIN_LI_AT", "")
    jsid  = os.environ.get("LINKEDIN_JSESSIONID", "")
    if not li_at or not jsid:
        return {"error": "LINKEDIN_LI_AT and LINKEDIN_JSESSIONID must be set in env"}

    with sync_playwright() as p:
        ctx = _make_context(p)
        _inject_cookies(ctx, li_at, jsid)
        try:
            return fn(ctx, jsid)
        finally:
            ctx.close()


def _fetch(ctx, jsid: str, url: str, method: str = "GET", body=None) -> Dict:
    """Call LinkedIn Voyager API via Playwright APIRequestContext (Chromium HTTP stack)."""
    headers = {
        "accept": "application/vnd.linkedin.normalized+json+2.1",
        "csrf-token": jsid,
        "x-restli-protocol-version": "2.0.0",
        "x-li-lang": "en_US",
        "x-li-track": '{"clientVersion":"1.13","osName":"web","timezoneOffset":3}',
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
    }
    if method.upper() == "GET":
        resp = ctx.request.get(url, headers=headers)
    else:
        headers["content-type"] = "application/json"
        resp = ctx.request.post(
            url,
            headers=headers,
            data=json.dumps(body) if body else None,
        )

    try:
        data = resp.json()
    except Exception:
        data = {}

    return {"status": resp.status, "data": data}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _linkedin_get_me(ctx_: ToolContext) -> str:
    """Check session and return current LinkedIn user info."""
    def _inner(ctx, jsid):
        r = _fetch(ctx, jsid, "https://www.linkedin.com/voyager/api/me")
        if r.get("status") != 200:
            return {"error": f"API status {r.get('status')}", "raw": str(r)[:200]}
        data = r.get("data", {})
        included = data.get("included", [{}])
        profile = included[0] if included else {}
        return {
            "id": data.get("plainId"),
            "firstName": profile.get("firstName"),
            "lastName": profile.get("lastName"),
            "occupation": profile.get("occupation"),
            "urn": data.get("*miniProfile"),
        }
    try:
        return json.dumps(_run(_inner), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _linkedin_get_invitations(ctx_: ToolContext, limit: int = 10) -> str:
    """Get pending LinkedIn connection requests."""
    def _inner(ctx, jsid):
        url = (
            "https://www.linkedin.com/voyager/api/relationships/invitationViews"
            f"?q=receivedInvitation&start=0&count={min(int(limit), 50)}"
        )
        r = _fetch(ctx, jsid, url)
        if r.get("status") != 200:
            return {"error": f"status {r.get('status')}", "raw": str(r)[:200]}
        elements = r.get("data", {}).get("elements", [])
        invitations = []
        for el in elements:
            m = el.get("fromMember", {}).get("miniProfile", {})
            inv = el.get("invitation", {})
            invitations.append({
                "firstName":    m.get("firstName"),
                "lastName":     m.get("lastName"),
                "occupation":   m.get("occupation", "")[:80],
                "profileUrl":   f"https://linkedin.com/in/{m.get('publicIdentifier', '')}",
                "invitationId": inv.get("invitationId"),
                "sharedSecret": inv.get("sharedSecret"),
                "message":      inv.get("message", ""),
            })
        return {"count": len(invitations), "invitations": invitations}
    try:
        return json.dumps(_run(_inner), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _linkedin_accept_invitation(ctx_: ToolContext, invitation_id: str, shared_secret: str) -> str:
    """Accept a LinkedIn connection request by invitationId + sharedSecret."""
    def _inner(ctx, jsid):
        url = (
            f"https://www.linkedin.com/voyager/api/relationships/invitations/{invitation_id}"
            "?action=accept"
        )
        body = {"invitationType": "CONNECTION", "sharedSecret": shared_secret}
        r = _fetch(ctx, jsid, url, method="POST", body=body)
        status = r.get("status", 0)
        if status in (200, 201, 204):
            return {"accepted": True, "invitationId": invitation_id}
        return {"accepted": False, "status": status, "raw": str(r.get("data", ""))[:200]}
    try:
        return json.dumps(_run(_inner), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _linkedin_get_messages(ctx_: ToolContext, limit: int = 10) -> str:
    """Get recent LinkedIn conversations."""
    def _inner(ctx, jsid):
        url = (
            "https://www.linkedin.com/voyager/api/messaging/conversations"
            f"?keyVersion=LEGACY_INBOX&start=0&count={min(int(limit), 20)}"
        )
        r = _fetch(ctx, jsid, url)
        if r.get("status") != 200:
            return {"error": f"status {r.get('status')}", "raw": str(r)[:200]}
        elements = r.get("data", {}).get("elements", [])
        convs = []
        for c in elements:
            participants = [
                p.get("miniProfile", {}).get("firstName", "?")
                for p in c.get("participants", [])
                if p.get("miniProfile", {}).get("firstName")
            ]
            events = c.get("events", [])
            last_text = ""
            if events:
                body = events[0].get("eventContent", {}).get("attributedBody", {})
                last_text = body.get("text", "")[:200] if body else ""
            convs.append({
                "participants": participants,
                "lastMessage":  last_text,
                "conversationUrn": c.get("entityUrn", ""),
            })
        return {"count": len(convs), "conversations": convs}
    try:
        return json.dumps(_run(_inner), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _linkedin_send_message(ctx_: ToolContext, conversation_urn: str, text: str) -> str:
    """Send a message to an existing LinkedIn conversation.

    conversation_urn: from linkedin_get_messages result (entityUrn field).
    """
    def _inner(ctx, jsid):
        import time
        url = "https://www.linkedin.com/voyager/api/messaging/conversations"
        body = {
            "keyVersion": "LEGACY_INBOX",
            "conversationUrn": conversation_urn,
            "eventCreate": {
                "value": {
                    "com.linkedin.voyager.messaging.create.MessageCreate": {
                        "body": text,
                        "attachments": [],
                        "attributedBody": {"text": text, "attributes": []},
                        "mediaAttachments": [],
                    }
                },
                "originToken": f"ouroboros-{int(time.time()*1000)}",
            },
        }
        r = _fetch(ctx, jsid, url, method="POST", body=body)
        status = r.get("status", 0)
        if status in (200, 201):
            return {"sent": True, "conversation": conversation_urn}
        return {"sent": False, "status": status, "raw": str(r.get("data", ""))[:200]}
    try:
        return json.dumps(_run(_inner), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def _get_tools_for_registry_only() -> List[ToolEntry]:
    return [
        ToolEntry("linkedin_get_me", {
            "name": "linkedin_get_me",
            "description": "Check LinkedIn session status and return current user profile info.",
            "parameters": {"type": "object", "properties": {}},
        }, _linkedin_get_me, timeout_sec=60),

        ToolEntry("linkedin_get_invitations", {
            "name": "linkedin_get_invitations",
            "description": (
                "Get pending LinkedIn connection requests. "
                "Returns list with firstName, lastName, occupation, invitationId, sharedSecret. "
                "Use invitationId + sharedSecret to accept with linkedin_accept_invitation."
            ),
            "parameters": {"type": "object", "properties": {
                "limit": {"type": "integer", "description": "Max invitations to return (default 10)", "default": 10},
            }},
        }, _linkedin_get_invitations, timeout_sec=60),

        ToolEntry("linkedin_accept_invitation", {
            "name": "linkedin_accept_invitation",
            "description": "Accept a LinkedIn connection request. Get invitationId and sharedSecret from linkedin_get_invitations.",
            "parameters": {"type": "object", "properties": {
                "invitation_id": {"type": "string", "description": "invitationId from linkedin_get_invitations"},
                "shared_secret": {"type": "string", "description": "sharedSecret from linkedin_get_invitations"},
            }, "required": ["invitation_id", "shared_secret"]},
        }, _linkedin_accept_invitation, timeout_sec=60),

        ToolEntry("linkedin_get_messages", {
            "name": "linkedin_get_messages",
            "description": "Get recent LinkedIn conversations with last message preview.",
            "parameters": {"type": "object", "properties": {
                "limit": {"type": "integer", "description": "Max conversations to return (default 10)", "default": 10},
            }},
        }, _linkedin_get_messages, timeout_sec=60),

        ToolEntry("linkedin_send_message", {
            "name": "linkedin_send_message",
            "description": (
                "Send a message to an existing LinkedIn conversation. "
                "Get conversation_urn from linkedin_get_messages (entityUrn field)."
            ),
            "parameters": {"type": "object", "properties": {
                "conversation_urn": {"type": "string", "description": "Conversation entityUrn from linkedin_get_messages"},
                "text": {"type": "string", "description": "Message text to send"},
            }, "required": ["conversation_urn", "text"]},
        }, _linkedin_send_message, timeout_sec=60),
    ]
