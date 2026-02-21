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
    
    # Get the group entity
    entity = await client.get_entity('@it_laboratory_bar')
    print('Entity:', entity)
    print('Type:', type(entity))
    print('Title:', getattr(entity, 'title', 'N/A'))
    
    # Check if I'm a member
    me = await client.get_me()
    print('I am:', me.username)
    
    # Try to get participants
    try:
        participants = await client.get_participants(entity, limit=10)
        print('Participants (first 5):', [(p.username, p.first_name) for p in participants[:5]])
    except Exception as e:
        print('Error getting participants:', e)
    
    # Try to send a message
    try:
        await client.send_message(entity, 'Testing message from Alexander')
        print('Message sent successfully!')
    except Exception as e:
        print('Error sending message:', e)
    
    await client.disconnect()

asyncio.run(main())
