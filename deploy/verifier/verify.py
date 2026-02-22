#!/usr/bin/env python3
"""
Ouroboros Startup Verifier — tamper-proof health check.

Runs after ouroboros.service starts. Checks agent health and triggers
rollback if critical failures are detected.

Owned by root, deployed to /opt/ouroboros-verifier/.
The agent (user 'a') can READ this file but CANNOT modify it.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.json"
KNOWN_GOOD_PATH = SCRIPT_DIR / "known_good.json"
RETRY_COUNT_PATH = SCRIPT_DIR / "retry_count.txt"
SAFE_MODE_FLAG = SCRIPT_DIR / "safe_mode.flag"
ROLLBACK_SCRIPT = SCRIPT_DIR / "rollback.sh"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_env(working_dir: str) -> dict:
    """Load .env file from working directory (key=value pairs)."""
    env_file = Path(working_dir) / ".env"
    env = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return env


def get_current_sha(repo_dir: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


# --- Health Checks ---


def check_service_active() -> tuple[str, str]:
    """Check that ouroboros.service is running."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "ouroboros.service"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = result.stdout.strip()
        if status == "active":
            return "ok", "service is active"
        return "fail", f"service status: {status}"
    except Exception as e:
        return "fail", f"cannot check service: {e}"


def check_import(venv_python: str, working_dir: str) -> tuple[str, str]:
    """Verify Python imports work."""
    try:
        result = subprocess.run(
            [
                venv_python,
                "-c",
                "import ouroboros, ouroboros.agent; print('import_ok')",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_dir,
            env={**os.environ, "PYTHONPATH": working_dir},
        )
        if "import_ok" in result.stdout:
            return "ok", "imports successful"
        stderr = result.stderr.strip()[-200:] if result.stderr else ""
        return "fail", f"import failed (rc={result.returncode}): {stderr}"
    except Exception as e:
        return "fail", f"import error: {e}"


def check_tool_count(venv_python: str, working_dir: str, min_count: int) -> tuple[str, str]:
    """Verify tool registry has enough tools."""
    try:
        script = (
            "import sys, pathlib; sys.path.insert(0, '.');"
            "from ouroboros.tools.registry import ToolRegistry;"
            "r = ToolRegistry(repo_dir=pathlib.Path('.'), drive_root=pathlib.Path('/tmp'));"
            "print(len(r.available_tools()))"
        )
        result = subprocess.run(
            [venv_python, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=working_dir,
            env={**os.environ, "PYTHONPATH": working_dir},
        )
        count_str = result.stdout.strip()
        if count_str.isdigit():
            count = int(count_str)
            if count >= min_count:
                return "ok", f"tool count: {count} (>= {min_count})"
            return "fail", f"tool count: {count} < {min_count}"
        stderr = result.stderr.strip()[-200:] if result.stderr else ""
        return "fail", f"cannot count tools: {stderr}"
    except Exception as e:
        return "fail", f"tool count error: {e}"


def check_bible_integrity(working_dir: str, expected_hash: str) -> tuple[str, str]:
    """Verify BIBLE.md SHA256 matches expected."""
    bible_path = Path(working_dir) / "BIBLE.md"
    if not bible_path.exists():
        return "fail", "BIBLE.md not found"
    try:
        actual = hashlib.sha256(bible_path.read_bytes()).hexdigest()
        if actual == expected_hash:
            return "ok", "BIBLE.md integrity verified"
        return "fail", f"BIBLE.md hash mismatch: {actual[:16]}... != {expected_hash[:16]}..."
    except Exception as e:
        return "fail", f"BIBLE.md check error: {e}"


def check_critical_files(working_dir: str) -> tuple[str, str]:
    """Verify critical files exist."""
    required = [
        "BIBLE.md",
        "VERSION",
        "ouroboros/agent.py",
        "ouroboros/loop.py",
        "ouroboros/tools/registry.py",
    ]
    missing = []
    for f in required:
        if not (Path(working_dir) / f).exists():
            missing.append(f)
    if not missing:
        return "ok", "all critical files present"
    return "fail", f"missing: {', '.join(missing)}"


def check_telegram(bot_token: str) -> tuple[str, str]:
    """Check Telegram bot API is reachable."""
    if not bot_token:
        return "skip", "no TELEGRAM_BOT_TOKEN"
    try:
        import urllib.request
        import urllib.error

        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return "ok", f"bot: @{data['result'].get('username', '?')}"
            return "fail", f"getMe returned ok=false"
    except Exception as e:
        return "fail", f"telegram check failed: {e}"


def check_llm_endpoint(base_url: str) -> tuple[str, str]:
    """Check LLM API is reachable."""
    if not base_url:
        return "skip", "no OUROBOROS_BASE_URL"
    try:
        import urllib.request
        import urllib.error

        url = f"{base_url.rstrip('/')}/models"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return "ok", f"LLM endpoint reachable: {base_url}"
            return "fail", f"LLM endpoint returned {resp.status}"
    except Exception as e:
        return "warn", f"LLM endpoint unreachable: {e}"


# --- Notification ---


def notify_owner(bot_token: str, owner_id: str, message: str) -> None:
    """Send Telegram message directly (bypassing the bot framework)."""
    if not bot_token or not owner_id:
        print(f"[verifier] Cannot notify: no token/owner_id. Message: {message}")
        return
    try:
        import urllib.request
        import urllib.parse

        url = (
            f"https://api.telegram.org/bot{bot_token}/sendMessage?"
            f"chat_id={urllib.parse.quote(str(owner_id))}&"
            f"text={urllib.parse.quote(message[:4000])}&"
            f"parse_mode=Markdown"
        )
        urllib.request.urlopen(url, timeout=10)
    except Exception as e:
        print(f"[verifier] Failed to notify owner: {e}")


# --- Main ---


def run_verification() -> dict:
    config = load_config()
    working_dir = config["working_dir"]
    repo_dir = config["repo_dir"]
    drive_root = config["drive_root"]
    venv_python = config["venv_python"]

    # Load env for tokens
    env = load_env(working_dir)
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "")
    base_url = env.get("OUROBOROS_BASE_URL", "")
    owner_id = env.get("TELEGRAM_OWNER_ID", "")

    current_sha = get_current_sha(repo_dir)

    # Run all checks
    checks = {}
    checks["service_active"] = check_service_active()
    checks["import_test"] = check_import(venv_python, working_dir)
    checks["tool_count"] = check_tool_count(
        venv_python, working_dir, config.get("min_tool_count", 33)
    )
    checks["bible_integrity"] = check_bible_integrity(
        working_dir, config.get("bible_sha256", "")
    )
    checks["critical_files"] = check_critical_files(working_dir)
    checks["telegram"] = check_telegram(bot_token)
    checks["llm_endpoint"] = check_llm_endpoint(base_url)

    # Determine overall status
    failures = {k: v for k, v in checks.items() if v[0] == "fail"}
    overall = "fail" if failures else "ok"
    action = "none"

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sha": current_sha,
        "checks": {k: {"status": v[0], "detail": v[1]} for k, v in checks.items()},
        "overall": overall,
        "action": action,
        "failures": list(failures.keys()),
    }

    # Write results to agent-readable location
    logs_dir = Path(drive_root) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    result_path = logs_dir / "startup_verification.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    # Make readable by agent user
    os.chmod(result_path, 0o644)

    if overall == "ok":
        # Update known-good
        known_good = {
            "sha": current_sha,
            "timestamp": result["timestamp"],
            "branch": "main",
        }
        with open(KNOWN_GOOD_PATH, "w") as f:
            json.dump(known_good, f, indent=2)

        # Reset retry counter
        RETRY_COUNT_PATH.write_text("0")

        # Remove safe mode flag
        if SAFE_MODE_FLAG.exists():
            SAFE_MODE_FLAG.unlink()

        print(f"[verifier] All checks passed. SHA {current_sha[:8]} marked as known-good.")

        if bot_token and owner_id:
            notify_owner(
                bot_token,
                owner_id,
                f"Startup verification *PASSED*\nSHA: `{current_sha[:8]}`",
            )
    else:
        # Check retry counter
        retries = 0
        if RETRY_COUNT_PATH.exists():
            try:
                retries = int(RETRY_COUNT_PATH.read_text().strip())
            except ValueError:
                retries = 0

        max_retries = config.get("max_retries", 3)
        failure_details = "\n".join(
            f"  - {k}: {v[1]}" for k, v in failures.items()
        )

        if retries >= max_retries:
            # Enter safe mode — do NOT restart
            SAFE_MODE_FLAG.write_text(
                f"Safe mode entered at {result['timestamp']}\n"
                f"SHA: {current_sha}\n"
                f"Retries exhausted: {retries}/{max_retries}\n"
                f"Failures:\n{failure_details}\n"
            )
            result["action"] = "safe_mode"
            print(f"[verifier] SAFE MODE: {retries} retries exhausted. NOT restarting.")

            if bot_token and owner_id:
                notify_owner(
                    bot_token,
                    owner_id,
                    f"SAFE MODE ENTERED\n"
                    f"SHA: `{current_sha[:8]}`\n"
                    f"Retries exhausted ({retries}/{max_retries})\n"
                    f"Failures:\n{failure_details}\n\n"
                    f"Manual intervention required.",
                )
        else:
            # Rollback and restart
            known_good_sha = "unknown"
            if KNOWN_GOOD_PATH.exists():
                try:
                    kg = json.load(open(KNOWN_GOOD_PATH))
                    known_good_sha = kg.get("sha", "unknown")
                except Exception:
                    pass

            result["action"] = f"rollback_to_{known_good_sha[:8]}"
            print(
                f"[verifier] FAILURES detected (retry {retries + 1}/{max_retries}):"
            )
            print(failure_details)
            print(f"[verifier] Rolling back to {known_good_sha[:8]}...")

            if bot_token and owner_id:
                notify_owner(
                    bot_token,
                    owner_id,
                    f"Startup verification *FAILED*\n"
                    f"SHA: `{current_sha[:8]}`\n"
                    f"Retry: {retries + 1}/{max_retries}\n"
                    f"Failures:\n{failure_details}\n\n"
                    f"Rolling back to `{known_good_sha[:8]}`...",
                )

            # Update result file before rollback
            with open(result_path, "w") as f:
                json.dump(result, f, indent=2)

            # Execute rollback
            if known_good_sha != "unknown":
                try:
                    subprocess.run(
                        ["bash", str(ROLLBACK_SCRIPT), known_good_sha],
                        timeout=120,
                        check=False,
                    )
                except Exception as e:
                    print(f"[verifier] Rollback script failed: {e}")
            else:
                print("[verifier] No known-good SHA available. Cannot rollback.")

    # Write final result
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    os.chmod(result_path, 0o644)

    return result


if __name__ == "__main__":
    # Optional delay to let the service fully start
    if len(sys.argv) > 1 and sys.argv[1] == "--delay":
        config = load_config()
        delay = config.get("verify_delay_sec", 45)
        print(f"[verifier] Waiting {delay}s for service to start...")
        time.sleep(delay)

    result = run_verification()
    sys.exit(0 if result["overall"] == "ok" else 1)
