import asyncio
import os

os.environ['TELEGRAM_SESSION_PATH'] = '/home/a/ouroboros_repo/session.session'

from telethon import TelegramClient

async def main():
    client = TelegramClient(os.environ['TELEGRAM_SESSION_PATH'], 24553863, '9364ce0067c945a18425912fb9ab92bb')
    await client.start()
    print(f'✅ Connected as {(await client.get_me()).username}')
    
    async for msg in client.iter_messages('alessiper', limit=5):
        print(f'\nMessage from {msg.sender_id}: {msg.text[:200] if msg.text else "(no text)"}')
    
    await client.disconnect()

asyncio.run(main())
