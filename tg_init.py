"""
Telegram user-mode initializer.

First run: prompts for phone + SMS code, saves session to TELEGRAM_SESSION_PATH.
Later runs: connects without prompts.

Usage: python tg_init.py
"""

import os
import sys
from pathlib import Path

# Load env from Drive first
env_path = Path("/home/a/.ouroboros/memory/.env")
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)
    print(f"✅ Loaded env from {env_path}")
else:
    print(f"⚠️ .env not found at {env_path}. Creating with provided values...")
    # Fallback: hardcode (only for first run, will be replaced by .env)
    os.environ["TELEGRAM_API_ID"] = "24553863"
    os.environ["TELEGRAM_API_HASH"] = "9364ce0067c945a18425912fb9ab92bb"
    os.environ["TELEGRAM_SESSION_PATH"] = "/home/a/.ouroboros/memory/telegram.session"

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_path = os.getenv("TELEGRAM_SESSION_PATH", "telegram.session")

print(f"📱 Using session: {session_path}")

from telethon import TelegramClient

def get_phone():
    return input("📱 Enter phone (e.g., +77054026507): ").strip()

def get_code():
    return input("🔑 Enter SMS code: ").strip()

def get_password():
    return input("🔐 Enter 2FA password (if any, else empty): ").strip() or None

async def main():
    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        await client.start(
            phone=get_phone,
            password=get_password,
            code_callback=get_code,
        )
        print("✅ Connected! Session saved to", session_path)
        
        me = await client.get_me()
        print(f"👤 You are: {me.first_name} @{me.username or 'no-username'}")
        
        # Send test message to self
        await client.send_message("me", "✅ Telegram user-mode initialized successfully.")
        print("✅ Test message sent to 'me'")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
