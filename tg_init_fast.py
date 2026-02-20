#!/usr/bin/env python3
"""Non-interactive Telegram user-mode init — phone hardcoded, SMS code entered once."""

import os
from telethon import TelegramClient
from dotenv import load_dotenv

# Load API keys from .env or use defaults from owner
load_dotenv('/home/a/.ouroboros/memory/.env')
api_id = int(os.getenv('TELEGRAM_API_ID', '24553863'))
api_hash = os.getenv('TELEGRAM_API_HASH', '9364ce0067c945a18425912fb9ab92bb')

# Hardcoded real phone
PHONE = '+77054026507'

# Session path in Drive (persistent)
SESSION_PATH = '/home/a/.ouroboros/memory/telegram'

client = TelegramClient(SESSION_PATH, api_id, api_hash)

async def main():
    await client.start(PHONE, lambda: input('Enter SMS code: '))
    me = await client.get_me()
    print(f"\u2705 Connected as: {me.first_name} @{me.username or 'no-username'}")
    print(f"Session saved to: {SESSION_PATH}.session")
    await client.send_message('me', '\u2705 Telegram user-mode OK')

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
