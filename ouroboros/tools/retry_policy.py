"""
Ouroboros — Retry policy utilities (inspired by OpenClaw).

Port of `src/infra/retry.ts` to Python, adapted for our async needs.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Callable, Dict, Optional, TypeVar

T = TypeVar("T")


class RetryConfig:
    """Retry configuration with sensible defaults."""

    def __init__(
        self,
        attempts: int = 3,
        min_delay_ms: float = 300,
        max_delay_ms: float = 30_000,
        jitter: float = 0.1,
    ):
        self.attempts = max(1, int(attempts))
        self.min_delay_ms = max(0.0, float(min_delay_ms))
        self.max_delay_ms = max(self.min_delay_ms, float(max_delay_ms))
        self.jitter = max(0.0, min(1.0, float(jitter)))

    def __repr__(self):
        return (f"RetryConfig(attempts={self.attempts}, "
                f"min_delay_ms={self.min_delay_ms}, "
                f"max_delay_ms={self.max_delay_ms}, "
                f"jitter={self.jitter})")


DEFAULT_RETRY_CONFIG = RetryConfig()


def resolve_retry_config(
    defaults: RetryConfig = DEFAULT_RETRY_CONFIG,
    overrides: Optional[Dict[str, Any]] = None,
) -> RetryConfig:
    """Resolve config: merge defaults with overrides, clamp values."""
    if overrides is None:
        return defaults
    return RetryConfig(
        attempts=overrides.get("attempts", defaults.attempts),
        min_delay_ms=overrides.get("min_delay_ms", defaults.min_delay_ms),
        max_delay_ms=overrides.get("max_delay_ms", defaults.max_delay_ms),
        jitter=overrides.get("jitter", defaults.jitter),
    )


def apply_jitter(delay_ms: float, jitter: float) -> int:
    """Apply jitter to delay: [delay*(1-jitter), delay*(1+jitter)]."""
    if jitter <= 0:
        return int(delay_ms)
    offset = (random.random() * 2 - 1) * jitter
    return max(0, int(delay_ms * (1 + offset)))


class RetryInfo:
    """Information passed to on_retry callback."""

    def __init__(
        self,
        attempt: int,
        max_attempts: int,
        delay_ms: float,
        err: Exception,
        label: Optional[str] = None,
    ):
        self.attempt = attempt
        self.max_attempts = max_attempts
        self.delay_ms = delay_ms
        self.err = err
        self.label = label

    def __repr__(self):
        return (f"RetryInfo(attempt={self.attempt}/{self.max_attempts}, "
                f"delay_ms={self.delay_ms:.0f}, "
                f"err={self.err!r}, "
                f"label={self.label})")


class RetryOptions:
    """Full retry options with callbacks."""

    def __init__(
        self,
        config: RetryConfig = DEFAULT_RETRY_CONFIG,
        label: Optional[str] = None,
        should_retry: Optional[Callable[[Exception, int], bool]] = None,
        retry_after_ms: Optional[Callable[[Exception], Optional[float]]] = None,
        on_retry: Optional[Callable[[RetryInfo], None]] = None,
    ):
        self.config = config
        self.label = label
        self.should_retry = should_retry
        self.retry_after_ms = retry_after_ms
        self.on_retry = on_retry


async def retry_async(
    fn: Callable[[], Any],  # sync or async callable returning awaitable
    attempts_or_options: int | RetryOptions = 3,
    initial_delay_ms: float = 300,
) -> Any:
    """
    Execute async function with exponential backoff and jitter.

    Usage:
        # simple
        result = await retry_async(lambda: dangerous_call(), 3)

        # full options
        result = await retry_async(
            lambda: dangerous_call(),
            RetryOptions(
                config=RetryConfig(attempts=5, min_delay_ms=500, max_delay_ms=5000),
                should_retry=lambda e, a: "TEMP" not in str(e),
                retry_after_ms=lambda e: 2000 if "RATE" in str(e) else None,
            )
        )
    """
    # Unwrap sync function into async if needed
    import inspect

    if inspect.iscoroutinefunction(fn):
        async_call = fn
    else:
        async def async_call():
            return fn()

    # Resolve options
    if isinstance(attempts_or_options, int):
        attempts = max(1, attempts_or_options)
        options = RetryOptions(config=RetryConfig(attempts=attempts))
    else:
        options = attempts_or_options

    config = options.config
    max_attempts = config.attempts
    min_delay_ms = config.min_delay_ms
    max_delay_ms = config.max_delay_ms
    jitter = config.jitter
    should_retry = options.should_retry or (lambda _, __: True)

    last_err = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await async_call()
        except Exception as err:
            last_err = err
            if attempt >= max_attempts or not should_retry(err, attempt):
                break

            # Determine delay
            retry_after_ms = options.retry_after_ms
            has_retry_after = retry_after_ms and isinstance(retry_after_ms(err), (int, float))
            base_delay = (
                max(retry_after_ms(err), min_delay_ms)
                if has_retry_after
                else min_delay_ms * (2 ** (attempt - 1))
            )
            delay = min(base_delay, max_delay_ms)
            delay = apply_jitter(delay, jitter)
            delay = max(min_delay_ms, min(delay, max_delay_ms))

            if options.on_retry:
                options.on_retry(RetryInfo(attempt, max_attempts, delay, err, options.label))
            await asyncio.sleep(delay / 1000.0)

    raise last_err if last_err else Exception("Retry failed")


# ---------------------------------------------------------------------------
# Telegram-specific helpers
# ---------------------------------------------------------------------------

TELEGRAM_RETRYABLE_CODES = {
    "FLOOD", "WAIT", "TIMEOUT", "NETWORK", "SERVICE_UNAVAILABLE",
    "GATEWAY_TIMEOUT", "TOO_MANY_REQUESTS",
}


def should_retry_telegram(err: Exception, attempt: int) -> bool:
    """Should we retry a Telegram error?"""
    err_str = str(err).upper()
    # Never retry on auth errors
    if any(code in err_str for code in ["API_ID", "API_HASH", "AUTH_KEY", "BOT_TOKEN", "USER_AUTH"]):
        return False
    # Always retry on network/timeouts, sometimes on flood
    if any(code in err_str for code in ["NETWORK", "TIMEOUT", "FLOOD"]):
        return attempt < 5
    return False


def telegram_retry_after_ms(err: Exception) -> Optional[float]:
    """Extract FLOOD wait time if present."""
    err_str = str(err).upper()
    if "FLOOD" in err_str or "TOO_MANY_REQUESTS" in err_str:
        # Try to parse WAIT_X or similar
        import re
        match = re.search(r"(?:FLOOD_WAIT|WAIT|TOO_MANY_REQUESTS)_?(\d+)", err_str, re.IGNORECASE)
        if match:
            return float(match.group(1)) * 1000
        # Default to 2 seconds if pattern not matched but error detected
        return 2000.0
    return None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

__all__ = [
    "RetryConfig",
    "DEFAULT_RETRY_CONFIG",
    "resolve_retry_config",
    "RetryInfo",
    "RetryOptions",
    "retry_async",
    "TELEGRAM_RETRYABLE_CODES",
    "should_retry_telegram",
    "telegram_retry_after_ms",
]