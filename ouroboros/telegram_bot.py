"""
TelegramBot — Ouroboros's primary communication channel.

Integrates Telethon for Telegram, with retry logic, account resolution,
and persistent session storage in Google Drive.

Core responsibilities:
- Start/stop Telegram client (session stored in Drive)
- Send messages with exponential backoff (reuses retry_policy)
- Resolve account from .env or fallback (bot token)
- Log all traffic to chat.jsonl via Memory

"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import secrets
from typing import Optional, Union

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from ouroboros.utils import read_text, write_text, append_jsonl
from ouroboros.memory import Memory
from ouroboros.retry_policy import retry_with_backoff

log = logging.getLogger(__name__)


class TelegramBot:
    """Primary Telegram communication interface for Ouroboros."""

    def __init__(
        self,
        drive_root: pathlib.Path,
        owner_id: int,
        memory: Optional[Memory] = None,
    ):
        self.drive_root = drive_root
        self.owner_id = owner_id
        self.memory = memory
        self._client: Optional[TelegramClient] = None
        self._session_path = self.drive_root / "memory" / "telegram.session"
        self._running = False
        self._event_handlers: list = []

    # --- Configuration ---

    @property
    def api_id(self) -> int:
        val = os.getenv("TELEGRAM_API_ID")
        if val:
            return int(val)
        raise RuntimeError("TELEGRAM_API_ID is not set in environment")

    @property
    def api_hash(self) -> str:
        val = os.getenv("TELEGRAM_API_HASH")
        if val:
            return val
        raise RuntimeError("TELEGRAM_API_HASH is not set in environment")

    @property
    def bot_token(self) -> Optional[str]:
        return os.getenv("TELEGRAM_BOT_TOKEN")

    @property
    def phone(self) -> Optional[str]:
        return os.getenv("TELEGRAM_PHONE")

    # --- Session management ---

    def load_session(self) -> Optional[str]:
        """Load saved session string from Drive."""
        if self._session_path.exists():
            return read_text(self._session_path)
        return None

    def save_session(self, session_string: str) -> None:
        """Save session string to Drive (atomic write, chmod 600)."""
        write_text(self._session_path, session_string)

    # --- Client lifecycle ---

    async def start(self) -> None:
        """Start Telegram client (connect, authorize, login)."""
        if self._running:
            log.info("TelegramBot: already running")
            return

        # Try to load existing session
        saved_session = self.load_session()

        # Determine auth method
        if self.bot_token:
            auth = ("bot_token", self.bot_token)
        elif self.phone:
            auth = ("phone", self.phone)
        elif saved_session:
            auth = ("string", saved_session)
        else:
            raise RuntimeError(
                "No auth method: set TELEGRAM_BOT_TOKEN or TELEGRAM_PHONE, "
                "or save a session first by running `client.start()` interactively"
            )

        # Create client with in-memory session initially
        self._client = TelegramClient(
            StringSession(saved_session) if saved_session else secrets.token_hex(16),
            self.api_id,
            self.api_hash,
        )

        try:
            await self._client.start(
                bot_token=self.bot_token if not self.phone else None,
                phone=lambda: self.phone if self.phone else "",
                code_callback=None,  # Interactive code input not supported in background
            )

            # Save session string after successful auth
            new_session = self._client.session.save()
            self.save_session(new_session)
            log.info(f"TelegramBot: session saved ({len(new_session)} chars)")

            # Set running state
            self._running = True
            log.info(f"TelegramBot: started as {await self._client.get_me()}" )

        except Exception as e:
            log.error(f"TelegramBot: failed to start: {e}", exc_info=True)
            self._running = False
            raise

    async def stop(self) -> None:
        """Stop Telegram client."""
        if self._client and self._running:
            await self._client.disconnect()
            self._running = False
            log.info("TelegramBot: stopped")

    # --- Sending messages ---

    async def send_message(
        self,
        to_id: Union[int, str],
        message: str,
        *,
        markdown: bool = True,
        retries: int = 3,
    ) -> None:
        """
        Send message to Telegram with retry logic and logging.

        Uses retry_with_backoff for network resilience.
        Logs to chat.jsonl via Memory if available.
        """
        if not self._running or not self._client:
            raise RuntimeError("TelegramBot: not started")

        @retry_with_backoff(max_retries=retries, base_delay=1.0, max_delay=30.0)
        async def _send():
            return await self._client.send_message(
                to_id,
                message,
                parse_mode="markdown" if markdown else None,
            )

        try:
            await _send()
            log.debug(f"TelegramBot: sent message to {to_id}")

            # Log to chat.jsonl
            if self.memory:
                append_jsonl(
                    self.memory.logs_path("chat.jsonl"),
                    {
                        "ts": asyncio.get_event_loop().time(),
                        "direction": "outgoing",
                        "channel": "telegram",
                        "to": to_id,
                        "text": message,
                    },
                )

        except Exception as e:
            log.error(f"TelegramBot: failed to send after {retries} retries: {e}")
            raise

    async def send_to_owner(self, message: str, **kwargs) -> None:
        """Convenience method to send to owner_id."""
        await self.send_message(self.owner_id, message, **kwargs)

    # --- Receiving messages ---

    async def listen_for_messages(self) -> None:
        """
        Start listening for new messages (blocking).
        To be used only in background task, not main loop.
        """
        if not self._running or not self._client:
            raise RuntimeError("TelegramBot: not started")

        # Register handler for new messages
        @self._client.on(events.NewMessage(incoming=True))
        async def handle_new_message(event: events.NewMessage.Event):
            sender = await event.get_sender()
            text = event.message.text

            log.info(f"TelegramBot: received message from {sender.id}: {text[:100]}")

            # Log to chat.jsonl
            if self.memory:
                append_jsonl(
                    self.memory.logs_path("chat.jsonl"),
                    {
                        "ts": asyncio.get_event_loop().time(),
                        "direction": "incoming",
                        "channel": "telegram",
                        "from": sender.id,
                        "text": text,
                    },
                )

        log.info("TelegramBot: listening for messages...")
        await self._client.run_until_disconnected()

    # --- Properties ---

    @property
    def is_running(self) -> bool:
        return self._running and self._client is not None

    async def get_me(self):
        """Get current bot/user identity."""
        if not self._running or not self._client:
            raise RuntimeError("TelegramBot: not started")
        return await self._client.get_me()
