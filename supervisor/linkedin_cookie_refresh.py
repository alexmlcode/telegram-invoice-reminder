"""
supervisor/linkedin_cookie_refresh.py — Auto-refresh LinkedIn session cookies.

Uses Playwright stealth to log in as the account owner and extract fresh
li_at + JSESSIONID cookies. Updates os.environ AND rewrites the .env file
on disk so restarts also pick up the new values.

Required env vars:
  LINKEDIN_EMAIL    — LinkedIn login email
  LINKEDIN_PASSWORD — LinkedIn login password
  LINKEDIN_LI_AT    — updated in-place after refresh
  LINKEDIN_JSESSIONID — updated in-place after refresh

Optional:
  DOTENV_PATH — absolute path to .env file (default: auto-detect)
"""
from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import re
import threading
import time
from typing import Optional, Tuple

log = logging.getLogger(__name__)

_refresh_lock = threading.Lock()
_last_refresh_ts: float = 0.0
MIN_REFRESH_INTERVAL_SEC = 1800  # never refresh more than once per 30 min


def refresh_cookies(force: bool = False) -> bool:
    """Log in to LinkedIn and update LINKEDIN_LI_AT + LINKEDIN_JSESSIONID.

    Returns True on success, False on failure (credentials missing,
    Playwright error, CAPTCHA, etc.).
    Thread-safe — concurrent calls block until the first completes.
    """
    global _last_refresh_ts
    with _refresh_lock:
        if not force and time.time() - _last_refresh_ts < MIN_REFRESH_INTERVAL_SEC:
            log.info("linkedin_cookie_refresh: skipping — refreshed recently")
            return True  # treat as success (cookies were just refreshed)
        try:
            li_at, jsid = asyncio.run(_login())
        except Exception as e:
            log.error("linkedin_cookie_refresh: login failed: %s", e)
            return False

        if not li_at:
            log.error("linkedin_cookie_refresh: li_at cookie not found after login")
            return False

        os.environ["LINKEDIN_LI_AT"] = li_at
        os.environ["LINKEDIN_JSESSIONID"] = jsid
        _update_env_file(li_at, jsid)
        _last_refresh_ts = time.time()
        log.info("linkedin_cookie_refresh: cookies refreshed successfully")
        return True


# ── Playwright login ──────────────────────────────────────────────────────────

async def _login() -> Tuple[str, str]:
    """Return (li_at, jsessionid_without_quotes) after stealth Playwright login."""
    email    = os.environ.get("LINKEDIN_EMAIL", "")
    password = os.environ.get("LINKEDIN_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set")

    from playwright.async_api import async_playwright
    try:
        from playwright_stealth import stealth_async
    except ImportError:
        stealth_async = None
        log.warning("playwright_stealth not available — running without stealth")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Europe/Moscow",
        )
        page = await ctx.new_page()
        if stealth_async:
            await stealth_async(page)

        try:
            log.info("linkedin_cookie_refresh: navigating to login page")
            await page.goto("https://www.linkedin.com/login", timeout=30_000)
            await page.wait_for_load_state("networkidle", timeout=15_000)

            # Fill credentials
            await page.fill("#username", email)
            await asyncio.sleep(0.5)
            await page.fill("#password", password)
            await asyncio.sleep(0.3)
            await page.click('[data-litms-control-urn="login-submit"]')

            # Wait for successful redirect to feed (or checkpoint)
            try:
                await page.wait_for_url("**/feed/**", timeout=30_000)
            except Exception:
                # May land on checkpoint or captcha
                url = page.url
                if "checkpoint" in url or "challenge" in url or "captcha" in url:
                    raise RuntimeError(
                        f"LinkedIn security challenge detected at {url!r}. "
                        "Manual login required to clear."
                    )
                # If we're on some other page but logged in, try cookies anyway
                log.warning("linkedin_cookie_refresh: unexpected URL after login: %s", url)

            # Extract cookies
            cookies = await ctx.cookies()
            li_at = ""
            jsid  = ""
            for c in cookies:
                if c["name"] == "li_at" and "linkedin.com" in c.get("domain", ""):
                    li_at = c["value"]
                elif c["name"] == "JSESSIONID" and "linkedin.com" in c.get("domain", ""):
                    # Strip surrounding quotes if present
                    jsid = c["value"].strip('"')

            return li_at, jsid

        finally:
            await browser.close()


# ── .env update ───────────────────────────────────────────────────────────────

def _find_env_file() -> Optional[pathlib.Path]:
    """Locate the .env file. Checks DOTENV_PATH, then common locations."""
    explicit = os.environ.get("DOTENV_PATH", "")
    if explicit:
        p = pathlib.Path(explicit)
        if p.exists():
            return p

    # Walk up from this file's location looking for .env
    candidates = [
        pathlib.Path(__file__).parent.parent / ".env",  # repo root
        pathlib.Path.home() / "ouroboros" / ".env",     # server path
        pathlib.Path("/home/a/ouroboros/.env"),          # server absolute
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _update_env_file(li_at: str, jsid: str) -> None:
    """Rewrite LINKEDIN_LI_AT and LINKEDIN_JSESSIONID lines in the .env file."""
    env_path = _find_env_file()
    if env_path is None:
        log.warning("linkedin_cookie_refresh: .env file not found — env updated in-memory only")
        return

    try:
        text = env_path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("linkedin_cookie_refresh: cannot read %s: %s", env_path, e)
        return

    def _replace_or_append(content: str, key: str, value: str) -> str:
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        new, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
        if count == 0:
            new = content.rstrip("\n") + f"\n{replacement}\n"
        return new

    text = _replace_or_append(text, "LINKEDIN_LI_AT", li_at)
    text = _replace_or_append(text, "LINKEDIN_JSESSIONID", jsid)

    try:
        env_path.write_text(text, encoding="utf-8")
        log.info("linkedin_cookie_refresh: updated %s", env_path)
    except Exception as e:
        log.warning("linkedin_cookie_refresh: cannot write %s: %s", env_path, e)
