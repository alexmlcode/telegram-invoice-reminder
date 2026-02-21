import asyncio
import os
from telethon import TelegramClient

API_ID = 24553863
API_HASH = '9364ce0067c945a18425912fb9ab92bb'
SESSION_PATH = '/home/a/ouroboros_repo/session.session'

async def main():
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.start()
    
    entity = await client.get_entity('it_laboratory_bar')
    print(f'Entity: {entity.title}')
    
    count = 0
    async for msg in client.iter_messages(entity, limit=5):
        count += 1
        print(f'Message {count}: {msg.message[:50] if msg.message else "(no text)"}')
    print(f'Total: {count}')
    
    await client.disconnect()

asyncio.run(main())