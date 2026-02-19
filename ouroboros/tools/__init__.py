'''
Ouroboros — Tool package (plugin architecture).

Re-exports: ToolRegistry, ToolContext, ToolEntry, retry utilities.
To add a tool: create a module in this package, export get_tools().
'''

from ouroboros.tools.registry import ToolRegistry, ToolContext, ToolEntry
from ouroboros.tools.retry_policy import (
    RetryConfig,
    DEFAULT_RETRY_CONFIG,
    resolve_retry_config,
    RetryInfo,
    RetryOptions,
    retry_async,
    TELEGRAM_RETRYABLE_CODES,
    should_retry_telegram,
    telegram_retry_after_ms,
)

__all__ = [
    'ToolRegistry',
    'ToolContext',
    'ToolEntry',
    'RetryConfig',
    'DEFAULT_RETRY_CONFIG',
    'resolve_retry_config',
    'RetryInfo',
    'RetryOptions',
    'retry_async',
    'TELEGRAM_RETRYABLE_CODES',
    'should_retry_telegram',
    'telegram_retry_after_ms',
]