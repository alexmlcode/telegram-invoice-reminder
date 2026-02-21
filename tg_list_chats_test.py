import asyncio
import os
os.environ['TELEGRAM_SESSION_PATH'] = '/home/a/ouroboros_repo/session.session'
from telethon import TelegramClient

async def main():
    client = TelegramClient(os.environ['TELEGRAM_SESSION_PATH'], 24553863, '9364ce0067c945a18425912fb9ab92bb')
    await client.start()
    print("Chats I'm in:")
    async for dialog in client.iter_dialogs():
        print(f"  {dialog.entity.title or dialog.entity.first_name or ''}: @{dialog.entity.username or ''}")
    await client.disconnect()

asyncio.run(main())
