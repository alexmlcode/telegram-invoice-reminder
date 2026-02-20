"""
Telegram user-mode health check.

Checks if session file exists and sends test message.
Use after first initialization via tg_init.py.

Usage: python tg_test.py
"""

import os
import sys
from pathlib import Path

# Load env from Drive
env_path = Path("/home/a/.ouroboros/memory/.env")
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)
else:
    print(f"⚠️ .env not found at {env_path}")
    sys.exit(1)

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_path = os.getenv("TELEGRAM_SESSION_PATH", "/home/a/.ouroboros/memory/telegram.session")

print(f"📱 Using session: {session_path}")

from telethon import TelegramClient

async def main():
    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        # Attempt connection (will use existing session if valid)
        await client.start()
        print("✅ Session is valid, connected!")
        
        me = await client.get_me()
        print(f"👤 You are: {me.first_name} @{me.username or 'no-username'}")
        
        # Send test message to self
        await client.send_message("me", "✅ Telegram user-mode OK (health check).")
        print("✅ Test message sent to 'me'")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n💡 Session file is missing or invalid. Run `python tg_init.py` first.")
        sys.exit(1)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
