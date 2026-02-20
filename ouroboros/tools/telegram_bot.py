import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import os

from ouroboros.tools.registry import ToolContext, ToolEntry

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
        """Load from env vars TELEGRAM_API_ID and TELEGRAM_API_HASH."""
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
        self._message_queue = None  # Will be set when asyncio is available
    
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
            await self._client.start(bot_token=None)
        except Exception as e:
            log.error(f"Failed to connect to Telegram: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect gracefully."""
        if self._client:
            await self._client.disconnect()
    
    async def send_message(self, entity, message, **kwargs):
        """Send a message safely with retry logic."""
        from ouroboros.tools.retry_policy import retry_async
        
        async def _send():
            if not self._client:
                raise RuntimeError("Not connected")
            return await self._client.send_message(entity, message, **kwargs)
        
        return await retry_async(_send, 3)
    
    async def run(self):
        """Start the bot event loop."""
        self._running = True
        await self.connect()
        
        async for event in self._client.iter_events():
            if not self._running:
                break
            
            if hasattr(event, 'message') and event.message and not event.message.out:
                if self._message_queue:
                    await self._message_queue.put(event.message)
        
        await self.disconnect()


class TelegramTools:
    """Telegram tools wrapper for registry."""
    
    def __init__(self):
        self._bot: Optional[TelegramBot] = None
    
    def _ensure_bot(self) -> TelegramBot:
        if not self._bot:
            account = Account.from_env()
            self._bot = TelegramBot(account)
        return self._bot
    
    def tg_send(self, ctx: ToolContext, entity: str, message: str, parse_mode: Optional[str] = None) -> str:
        """Send a message via Telegram."""
        from telethon import TelegramClient
        
        try:
            bot = self._ensure_bot()
            account = bot.account
            
            async def _send():
                async with TelegramClient(account.session_path, account.api_id, account.api_hash) as client:
                    if parse_mode:
                        await client.send_message(entity, message, parse_mode=parse_mode)
                    else:
                        await client.send_message(entity, message)
                    return f"✓ Message sent to {entity}"
            
            import asyncio
            return asyncio.run(_send())
        except Exception as e:
            return f"⚠️ Failed to send: {e}"
    
    def tg_connect(self, ctx: ToolContext) -> str:
        """Connect to Telegram and start listening for messages."""
        from telethon import TelegramClient
        
        try:
            bot = self._ensure_bot()
            account = bot.account
            
            async def _connect():
                client = TelegramClient(account.session_path, account.api_id, account.api_hash)
                await client.start()
                return "✓ Connected to Telegram"
            
            import asyncio
            return asyncio.run(_connect())
        except Exception as e:
            return f"⚠️ Failed to connect: {e}"


# Global instance
telegram_tools = TelegramTools()


def get_tools() -> List[ToolEntry]:
    """Return tool entries for Telegram integration."""
    return [
        ToolEntry(
            "tg_send",
            {
                "name": "tg_send",
                "description": "Send a message via Telegram. Requires TELEGRAM_API_ID and TELEGRAM_API_HASH in env.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entity": {"type": "string", "description": "Username, chat ID, or 'me' for self"},
                        "message": {"type": "string", "description": "Message text to send"},
                        "parse_mode": {"type": "string", "enum": ["markdown", "html"], "description": "Optional formatting"},
                    },
                    "required": ["entity", "message"],
                },
            },
            telegram_tools.tg_send,
            timeout_sec=60,
        ),
        ToolEntry(
            "tg_connect",
            {
                "name": "tg_connect",
                "description": "Connect to Telegram and start listening for messages.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            telegram_tools.tg_connect,
            timeout_sec=120,
        ),
    ]
