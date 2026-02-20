import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import json
import os

log = logging.getLogger(__name__)


@dataclass
class Account:
    """Telegram account config. Each session = one account."""
    api_id: int
    api_hash: str
    session_path: str = ""
    proxy: Optional[Dict] = None
    
    @classmethod
    def from_env(cls) -> "Account":
        """Load from config/.env if present, otherwise ask user (not implemented yet)."""
        api_id = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if not (api_id and api_hash):
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set")
        session_path = os.environ.get("TELEGRAM_SESSION_PATH", "session.session")
        return cls(
            api_id=int(api_id),
            api_hash=api_hash,
            session_path=session_path,
        )


class TelegramBot:
    """Telegram bot wrapper based on OpenClaw patterns."""
    
    def __init__(self, account: Account, handlers: Optional[List] = None):
        self.account = account
        self.handlers = handlers or []
        self._client = None
        self._running = False
        self._message_queue = asyncio.Queue()
    
    def add_handler(self, handler):
        """Register a message handler."""
        self.handlers.append(handler)
    
    async def connect(self):
        """Connect to Telegram. Uses Telethon under the hood."""
        try:
            from telethon import TelegramClient
            self._client = TelegramClient(
                self.account.session_path,
                self.account.api_id,
                self.account.api_hash,
                proxy=self.account.proxy,
            )
            await self._client.start(bot_token=None)  # Will prompt for auth if needed
        except Exception as e:
            log.error(f"Failed to connect to Telegram: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect gracefully."""
        if self._client:
            await self._client.disconnect()
    
    async def send_message(self, entity, message, **kwargs):
        """Send a message safely with retry logic."""
        from ouroboros.tools.retry_policy import retry_with_backoff
        
        async def _send():
            if not self._client:
                raise RuntimeError("Not connected")
            return await self._client.send_message(entity, message, **kwargs)
        
        return await retry_with_backoff(_send, max_attempts=3)
    
    async def run(self):
        """Start the bot event loop."""
        self._running = True
        await self.connect()
        
        # Register handlers via grammY runner if needed
        # For now, just process messages as they come in
        
        async for event in self._client.iter_events():
            if not self._running:
                break
            
            if hasattr(event, 'message') and event.message and not event.message.out:
                await self._message_queue.put(event.message)
        
        await self.disconnect()
    
    async def process_messages(self):
        """Process incoming messages through registered handlers."""
        while self._running:
            try:
                message = await asyncio.wait_for(self._message_queue.get(), timeout=5.0)
                for handler in self.handlers:
                    try:
                        await handler(message)
                    except Exception as e:
                        log.error(f"Handler {handler} failed: {e}")
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                log.error(f"Error processing messages: {e}")


def get_tools() -> List[Dict[str, Any]]:
    """Return tool schemas for OpenClaw-inspired Telegram integration."""
    return [
        {
            "name": "tg_send",
            "description": "Send a message via Telegram. Requires TELEGRAM_API_ID and TELEGRAM_API_HASH in env.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Username, chat ID, or 'me' for self"},
                    "message": {"type": "string", "description": "Message text to send"},
                    "parse_mode": {"type": "string", "enum": ["markdown", "html"], "description": "Optional formatting"}
                },
                "required": ["entity", "message"]
            }
        },
        {
            "name": "tg_connect",
            "description": "Connect to Telegram and start listening for messages.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
    ]
