import asyncio
import os
from telethon import TelegramClient

async def main():
    session_path = '/home/a/ouroboros_repo/session.session'
    api_id = 24553863
    api_hash = '9364ce0067c945a18425912fb9ab92bb'
    
    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()
    print("✅ Authenticated")
    me = await client.get_me()
    print(me)

asyncio.run(main())
