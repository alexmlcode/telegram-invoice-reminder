"""
supervisor/linkedin_cookie_refresh.py — Auto-refresh LinkedIn session cookies.

Strategy: runs Playwright login in a SUBPROCESS (not in the calling thread).
This avoids asyncio/thread lifecycle issues (hanging browser.close, etc.).

When imported: refresh_cookies() launches a subprocess of THIS file as __main__,
which performs the Playwright login, prints {li_at, jsid} as JSON to stdout,
then exits. The parent process reads stdout, updates os.environ + .env file.

Required env vars:
  LINKEDIN_EMAIL    — LinkedIn login email
  LINKEDIN_PASSWORD — LinkedIn login password
  LINKEDIN_LI_AT    — updated in-place after refresh
  LINKEDIN_JSESSIONID — updated in-place after refresh

Optional:
  DOTENV_PATH — absolute path to .env file (default: auto-detect)
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from typing import Optional

log = logging.getLogger(__name__)

_refresh_lock = threading.Lock()
_last_refresh_ts: float = 0.0
MIN_REFRESH_INTERVAL_SEC = 1800  # max one refresh per 30 min


# ── Public API ────────────────────────────────────────────────────────────────

def refresh_cookies(force: bool = False) -> bool:
    """Log in to LinkedIn in a subprocess and update cookies.

    Returns True on success, False on failure.
    Thread-safe — concurrent calls block until the first completes.
    """
    global _last_refresh_ts
    with _refresh_lock:
        if not force and time.time() - _last_refresh_ts < MIN_REFRESH_INTERVAL_SEC:
            log.info("linkedin_cookie_refresh: skipping — refreshed recently")
            return True

        log.info("linkedin_cookie_refresh: launching Playwright subprocess")
        try:
            result = subprocess.run(
                [sys.executable, __file__, "--login"],
                capture_output=True,
                text=True,
                timeout=120,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired:
            log.error("linkedin_cookie_refresh: subprocess timed out (120s)")
            return False
        except Exception as e:
            log.error("linkedin_cookie_refresh: subprocess error: %s", e)
            return False

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()[-500:]
            log.error("linkedin_cookie_refresh: subprocess failed (rc=%d): %s",
                      result.returncode, stderr)
            return False

        try:
            data = json.loads(result.stdout.strip())
        except Exception:
            log.error("linkedin_cookie_refresh: could not parse subprocess output: %r",
                      result.stdout[:200])
            return False

        li_at = data.get("li_at", "")
        jsid  = data.get("jsid", "")
        if not li_at:
            log.error("linkedin_cookie_refresh: li_at not in subprocess output")
            return False

        os.environ["LINKEDIN_LI_AT"] = li_at
        os.environ["LINKEDIN_JSESSIONID"] = jsid
        _update_env_file(li_at, jsid)
        _last_refresh_ts = time.time()
        log.info("linkedin_cookie_refresh: cookies refreshed (li_at=%s...)", li_at[:20])
        return True


# ── .env update ───────────────────────────────────────────────────────────────

def _find_env_file() -> Optional[pathlib.Path]:
    explicit = os.environ.get("DOTENV_PATH", "")
    if explicit:
        p = pathlib.Path(explicit)
        if p.exists():
            return p
    candidates = [
        pathlib.Path(__file__).parent.parent / ".env",
        pathlib.Path.home() / "ouroboros" / ".env",
        pathlib.Path("/home/a/ouroboros/.env"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _update_env_file(li_at: str, jsid: str) -> None:
    env_path = _find_env_file()
    if env_path is None:
        log.warning("linkedin_cookie_refresh: .env not found — env updated in-memory only")
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


# ── Subprocess entry point ────────────────────────────────────────────────────
# When this file is run as __main__ with --login, performs Playwright login
# and prints {"li_at": "...", "jsid": "..."} to stdout, then exits.

def _subprocess_login() -> None:
    """Run Playwright login, print JSON result to stdout, exit."""
    import asyncio

    async def _do_login():
        email    = os.environ.get("LINKEDIN_EMAIL", "")
        password = os.environ.get("LINKEDIN_PASSWORD", "")
        if not email or not password:
            print(json.dumps({"error": "LINKEDIN_EMAIL or LINKEDIN_PASSWORD not set"}))
            sys.exit(1)

        from playwright.async_api import async_playwright
        try:
            from playwright_stealth import stealth_async
        except ImportError:
            stealth_async = None

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
                await page.goto("https://www.linkedin.com/login", timeout=30_000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass  # networkidle may not fire on LinkedIn; proceed anyway

                await page.fill("#username", email)
                await asyncio.sleep(0.4)
                await page.fill("#password", password)
                await asyncio.sleep(0.3)
                await page.click('[data-litms-control-urn="login-submit"]')

                try:
                    await page.wait_for_url("**/feed/**", timeout=30_000)
                except Exception:
                    url = page.url
                    if "checkpoint" in url or "challenge" in url or "captcha" in url:
                        print(json.dumps({"error": f"LinkedIn challenge at {url}"}))
                        sys.exit(2)
                    # might be logged in on another page — try to extract cookies anyway

                cookies = await ctx.cookies()
                li_at = ""
                jsid  = ""
                for c in cookies:
                    if c["name"] == "li_at" and "linkedin.com" in c.get("domain", ""):
                        li_at = c["value"]
                    elif c["name"] == "JSESSIONID" and "linkedin.com" in c.get("domain", ""):
                        jsid = c["value"].strip('"')

                print(json.dumps({"li_at": li_at, "jsid": jsid}))

            finally:
                await browser.close()

    asyncio.run(_do_login())


if __name__ == "__main__" and "--login" in sys.argv:
    _subprocess_login()
