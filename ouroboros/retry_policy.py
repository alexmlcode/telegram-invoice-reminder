"""
Retry policy for network operations (exponential backoff with jitter).

Based on OpenClaw's `src/retry.ts`, but simplified for Python and Telethon.

Key features:
- Exponential backoff with full jitter
- Configurable max retries and delays
- Simple decorator API
- Logs retries (optional)

Usage:
    @retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=30.0)
    async def my_network_call():
        ...
"""

import asyncio
import logging
import random
from typing import Callable, TypeVar, Any
from functools import wraps

log = logging.getLogger(__name__)

T = TypeVar("T")


def jitter(base: float, max_delay: float) -> float:
    """Full jitter: uniform random between 0 and min(base, max_delay)."""
    return random.uniform(0, min(base, max_delay))


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_exceptions: tuple = (Exception,),
):
    """
    Decorator for retrying async functions with exponential backoff + jitter.

    Args:
        max_retries: Maximum number of attempts (0 = no retries)
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        retry_exceptions: Tuple of exception types to retry on
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            delay = base_delay
            last_error: Optional[Exception] = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_exceptions as e:
                    last_error = e
                    if attempt == max_retries:
                        log.error(
                            f"RetryPolicy: {func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

                    jittered = jitter(delay, max_delay)
                    log.info(
                        f"RetryPolicy: {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), retry in {jittered:.2f}s"
                    )
                    await asyncio.sleep(jittered)
                    delay = min(delay * 2, max_delay)

            raise last_error

        return wrapper

    return decorator
