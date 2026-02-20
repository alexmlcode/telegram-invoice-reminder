import asyncio
from telethon import TelegramClient
import os
from dotenv import load_dotenv

async def main():
    # Load credentials
    load_dotenv('/home/a/.ouroboros/memory/.env')

    api_id = int(os.getenv('TELEGRAM_API_ID', '24553863'))
    api_hash = os.getenv('TELEGRAM_API_HASH', '9364ce0067c945a18425912fb9ab92bb')
    session = '/home/a/ouroboros_repo/session.session'

    print(f'Using session: {session}')

    client = TelegramClient(session, api_id, api_hash)
    await client.start()

    me = await client.get_me()
    print(f'✅ Connected as: {me.first_name} @{me.username}')
    print(f'ID: {me.id}')
    print(f'Authorized: {await client.is_user_authorized()}')

    # Test sending a message to yourself
    await client.send_message('me', '✅ Telegram human session verified')
    print('✅ Test message sent to "me"')

    await client.disconnect()
    print('✅ Done')

if __name__ == '__main__':
    asyncio.run(main())
