import asyncio
import os
os.environ['TELEGRAM_SESSION_PATH'] = '/home/a/ouroboros_repo/session.session'

from telethon import TelegramClient

async def main():
    client = TelegramClient(
        os.environ['TELEGRAM_SESSION_PATH'],
        24553863,
        '9364ce0067c945a18425912fb9ab92bb'
    )
    await client.start()
    print('Chats I am in:')
    async for dialog in client.iter_dialogs():
        title = getattr(dialog.entity, 'title', None)
        if not title:
            title = getattr(dialog.entity, 'first_name', '') or ''
        username = getattr(dialog.entity, 'username', '') or ''
        print(f'  {title}: @{username}')
    await client.disconnect()

asyncio.run(main())
