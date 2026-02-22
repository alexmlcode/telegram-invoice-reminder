"""
LinkedIn tools via requests.

Uses Python requests with LinkedIn session cookies for Voyager API access.
Works when the server shares the same public IP as the browser that created
the li_at session (i.e. same home network behind NAT).

Required env vars (set in .env on server, never in git):
  LINKEDIN_LI_AT       — li_at cookie value
  LINKEDIN_JSESSIONID  — JSESSIONID value, WITHOUT quotes (e.g. ajax:1234...)

To refresh: open LinkedIn in browser → F12 → Application → Cookies → www.linkedin.com
Copy li_at and JSESSIONID (without quotes) values into .env.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from ouroboros.tools.registry import ToolContext, ToolEntry

log = logging.getLogger(__name__)


def _session():
    """Build a requests.Session with LinkedIn cookies and headers."""
    import requests
    li_at = os.environ.get("LINKEDIN_LI_AT", "")
    jsid  = os.environ.get("LINKEDIN_JSESSIONID", "")
    if not li_at or not jsid:
        return None, "LINKEDIN_LI_AT and LINKEDIN_JSESSIONID must be set in env"

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
        "x-li-track": '{"clientVersion":"1.13","osName":"web","timezoneOffset":3}',
    })
    return s, None


def _get(path: str, params: Dict = None) -> Dict:
    """GET Voyager API endpoint. Returns dict with 'status' and 'data'."""
    s, err = _session()
    if err:
        return {"error": err}
    try:
        r = s.get(f"https://www.linkedin.com{path}", params=params,
                  allow_redirects=False, timeout=15)
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("location", "")
            return {"error": f"Redirect (session expired or IP mismatch). Refresh LINKEDIN_LI_AT.",
                    "redirect_to": loc[:100]}
        try:
            data = r.json()
        except Exception:
            data = {}
        return {"status": r.status_code, "data": data}
    except Exception as e:
        return {"error": str(e)}


def _post(path: str, body: Dict) -> Dict:
    """POST to Voyager API endpoint."""
    s, err = _session()
    if err:
        return {"error": err}
    try:
        headers = {"content-type": "application/json"}
        r = s.post(f"https://www.linkedin.com{path}", json=body,
                   headers=headers, allow_redirects=False, timeout=15)
        if r.status_code in (301, 302, 303, 307, 308):
            return {"error": "Redirect (session expired or IP mismatch). Refresh LINKEDIN_LI_AT."}
        try:
            data = r.json()
        except Exception:
            data = {}
        return {"status": r.status_code, "data": data}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _linkedin_get_me(ctx: ToolContext) -> str:
    """Check session and return current LinkedIn user info."""
    r = _get("/voyager/api/me")
    if "error" in r:
        return json.dumps(r, ensure_ascii=False)
    if r.get("status") != 200:
        return json.dumps({"error": f"API status {r.get('status')}", "raw": str(r)[:200]}, ensure_ascii=False)
    data = r.get("data", {})
    included = data.get("included", [{}])
    profile = included[0] if included else {}
    return json.dumps({
        "id": data.get("plainId"),
        "firstName": profile.get("firstName"),
        "lastName": profile.get("lastName"),
        "occupation": profile.get("occupation"),
        "urn": data.get("*miniProfile"),
    }, ensure_ascii=False, indent=2)


def _linkedin_get_invitations(ctx: ToolContext, limit: int = 10) -> str:
    """Get pending LinkedIn connection requests."""
    r = _get("/voyager/api/relationships/invitationViews",
             params={"q": "receivedInvitation", "start": 0, "count": min(int(limit), 50)})
    if "error" in r:
        return json.dumps(r, ensure_ascii=False)
    if r.get("status") != 200:
        return json.dumps({"error": f"status {r.get('status')}"}, ensure_ascii=False)
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
    return json.dumps({"count": len(invitations), "invitations": invitations},
                      ensure_ascii=False, indent=2)


def _linkedin_accept_invitation(ctx: ToolContext, invitation_id: str, shared_secret: str) -> str:
    """Accept a LinkedIn connection request by invitationId + sharedSecret."""
    r = _post(
        f"/voyager/api/relationships/invitations/{invitation_id}?action=accept",
        {"invitationType": "CONNECTION", "sharedSecret": shared_secret},
    )
    if "error" in r:
        return json.dumps(r, ensure_ascii=False)
    status = r.get("status", 0)
    if status in (200, 201, 204):
        return json.dumps({"accepted": True, "invitationId": invitation_id}, ensure_ascii=False, indent=2)
    return json.dumps({"accepted": False, "status": status, "raw": str(r.get("data", ""))[:200]},
                      ensure_ascii=False, indent=2)


def _linkedin_get_messages(ctx: ToolContext, limit: int = 10) -> str:
    """Get recent LinkedIn conversations."""
    r = _get("/voyager/api/messaging/conversations",
             params={"keyVersion": "LEGACY_INBOX", "start": 0, "count": min(int(limit), 20)})
    if "error" in r:
        return json.dumps(r, ensure_ascii=False)
    if r.get("status") != 200:
        return json.dumps({"error": f"status {r.get('status')}"}, ensure_ascii=False)
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
    return json.dumps({"count": len(convs), "conversations": convs},
                      ensure_ascii=False, indent=2)


def _linkedin_send_message(ctx: ToolContext, conversation_urn: str, text: str) -> str:
    """Send a message to an existing LinkedIn conversation.

    conversation_urn: from linkedin_get_messages result (entityUrn field).
    """
    import time
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
    r = _post("/voyager/api/messaging/conversations", body)
    if "error" in r:
        return json.dumps(r, ensure_ascii=False)
    status = r.get("status", 0)
    if status in (200, 201):
        return json.dumps({"sent": True, "conversation": conversation_urn},
                          ensure_ascii=False, indent=2)
    return json.dumps({"sent": False, "status": status, "raw": str(r.get("data", ""))[:200]},
                      ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Cookie refresh tool
# ---------------------------------------------------------------------------

def _linkedin_refresh_cookies(ctx: ToolContext) -> str:
    """Use Playwright stealth to log in to LinkedIn and refresh session cookies."""
    try:
        from supervisor.linkedin_cookie_refresh import refresh_cookies
        ok = refresh_cookies(force=True)
        if ok:
            li_at = os.environ.get("LINKEDIN_LI_AT", "")
            return json.dumps({
                "refreshed": True,
                "li_at_preview": li_at[:20] + "..." if li_at else "(empty)",
                "message": "Cookies updated in env and .env file. linkedin_listener will use them on next poll.",
            }, ensure_ascii=False, indent=2)
        return json.dumps({
            "refreshed": False,
            "message": "Refresh failed. Check logs for details (CAPTCHA, wrong credentials, network).",
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"refreshed": False, "error": str(e)}, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def get_tools() -> List[ToolEntry]:
    return [
        ToolEntry("linkedin_get_me", {
            "name": "linkedin_get_me",
            "description": (
                "Check LinkedIn session status and return current user profile info. "
                "If returns 'Redirect (session expired)', update LINKEDIN_LI_AT and LINKEDIN_JSESSIONID "
                "env vars with fresh values from browser DevTools → Application → Cookies."
            ),
            "parameters": {"type": "object", "properties": {}},
        }, _linkedin_get_me, timeout_sec=20),

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
        }, _linkedin_get_invitations, timeout_sec=20),

        ToolEntry("linkedin_accept_invitation", {
            "name": "linkedin_accept_invitation",
            "description": "Accept a LinkedIn connection request. Get invitationId and sharedSecret from linkedin_get_invitations.",
            "parameters": {"type": "object", "properties": {
                "invitation_id": {"type": "string", "description": "invitationId from linkedin_get_invitations"},
                "shared_secret": {"type": "string", "description": "sharedSecret from linkedin_get_invitations"},
            }, "required": ["invitation_id", "shared_secret"]},
        }, _linkedin_accept_invitation, timeout_sec=20),

        ToolEntry("linkedin_get_messages", {
            "name": "linkedin_get_messages",
            "description": "Get recent LinkedIn conversations with last message preview.",
            "parameters": {"type": "object", "properties": {
                "limit": {"type": "integer", "description": "Max conversations to return (default 10)", "default": 10},
            }},
        }, _linkedin_get_messages, timeout_sec=20),

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
        }, _linkedin_send_message, timeout_sec=20),

        ToolEntry("linkedin_refresh_cookies", {
            "name": "linkedin_refresh_cookies",
            "description": (
                "Auto-refresh LinkedIn session cookies using Playwright stealth browser login. "
                "Use when linkedin_get_me() returns 'Redirect (session expired)' or when "
                "linkedin_listener reports session expiry. "
                "Requires LINKEDIN_EMAIL and LINKEDIN_PASSWORD env vars. "
                "Updates LINKEDIN_LI_AT and LINKEDIN_JSESSIONID in env and .env file."
            ),
            "parameters": {"type": "object", "properties": {}},
        }, _linkedin_refresh_cookies, timeout_sec=120),
    ]
