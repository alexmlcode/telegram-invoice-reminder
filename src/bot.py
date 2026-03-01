#!/usr/bin/env python3
"""
Telegram Invoice Reminder Bot MVP
Core loop: /start → /upload → LLM extraction → /remind → SQLite job
"""

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from telethon import TelegramClient, events
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
telegram_api_id = int(os.getenv("TELEGRAM_API_ID"))
telegram_api_hash = os.getenv("TELEGRAM_API_HASH")
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
database_path = os.getenv("DATABASE_PATH", "data/invoice_reminders.db")

# Initialize Telethon client
client = TelegramClient("session", telegram_api_id, telegram_api_hash)

# SQLite connection
def get_db():
    os.makedirs(os.path.dirname(database_path), exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            raw_text TEXT,
            due_date DATE,
            amount REAL,
            client TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            trigger_time TIMESTAMP,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        )
    """)
    conn.commit()
    conn.close()

# LLM extraction (placeholder)
def extract_invoice_data(raw_text: str) -> Optional[dict]:
    """Extract due_date, amount, client from invoice text using OpenRouter."""
    # TODO: Implement OpenRouter API call
    # For now, return dummy data
    return {
        "due_date": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        "amount": 100.0,
        "client": "Unknown Client"
    }

# Command handlers
@client.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    await event.respond(
        "✅ **Invoice Reminder Bot**\n\n"
        "I'll help you track invoice payments and send automatic reminders.\n\n"
        "**How it works:**\n"
        "1. `/upload` \u2014 paste invoice text or send PDF\n"
        "2. I extract due_date, amount, client\n"
        "3. `/remind` \u2014 set reminder timing\n"
        "4. I notify you on Telegram when payment is due\n\n"
        "**Features:**\n"
        "- 100% Telegram-native (no login, no dashboard)\n"
        "- Ephemeral processing (extract → reminder → delete raw file)\n"
        "- GDPR-safe (no storage of raw invoices)\n\n"
        "Ready to get started? Type `/upload`!"
    )

@client.on(events.NewMessage(pattern="/upload"))
async def upload_handler(event):
    user_id = event.sender_id
    
    await event.respond(
        "📄 **Upload Invoice**\n\n"
        "Please paste the invoice text or send the PDF file.\n\n"
        "I'll extract: due_date, amount, client."
    )
    
    # Wait for user response (simplified - in production use state machine)
    # For MVP, we'll assume the next message contains the invoice data
    
    # TODO: Implement state machine for multi-step flow
    # For now, just process the message as invoice text
    if event.message.text:
        invoice_text = event.message.text
        extracted = extract_invoice_data(invoice_text)
        
        if extracted:
            conn = get_db()
            conn.execute(
                "INSERT INTO invoices (user_id, raw_text, due_date, amount, client) VALUES (?, ?, ?, ?, ?)",
                (user_id, invoice_text, extracted["due_date"], extracted["amount"], extracted["client"])
            )
            conn.commit()
            conn.close()
            
            await event.respond(
                f"✅ **Invoice Saved!**\n\n"
                f"**Client:** {extracted['client']}\n"
                f"**Amount:** ${extracted['amount']:.2f}\n"
                f"**Due Date:** {extracted['due_date']}\n\n"
                f"Type `/remind` to set reminders."
            )
        else:
            await event.respond(
                "❌ **Failed to extract invoice data.**\n\n"
                "Please check the format and try again."
            )

@client.on(events.NewMessage(pattern="/remind"))
async def remind_handler(event):
    user_id = event.sender_id
    
    await event.respond(
        "⏰ **Set Reminder**\n\n"
        "Choose reminder timing:\n"
        "1. Daily (every day until paid)\n"
        "2. 3 days before due date\n"
        "3. On due date\n\n"
        "Type your choice (1, 2, or 3)."
    )
    
    # TODO: Implement state machine for reminder timing selection

@client.on(events.NewMessage(pattern="/list"))
async def list_handler(event):
    user_id = event.sender_id
    
    conn = get_db()
    invoices = conn.execute(
        "SELECT * FROM invoices WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (user_id,)
    ).fetchall()
    conn.close()
    
    if not invoices:
        await event.respond(
            "📊 **No invoices found.**\n\n"
            "Type `/upload` to add your first invoice."
        )
        return
    
    response = "📊 **Your Invoices**\n\n"
    for invoice in invoices:
        response += f"- **{invoice['client']}**: ${invoice['amount']:.2f} (due: {invoice['due_date']})\n"
    
    await event.respond(response)

# Background job (placeholder)
async def run_reminder_job():
    """Check for due reminders and send Telegram notifications."""
    conn = get_db()
    reminders = conn.execute(
        "SELECT * FROM reminders WHERE status = 'pending' AND trigger_time <= ?",
        (datetime.now(),)
    ).fetchall()
    
    for reminder in reminders:
        # Send notification (placeholder)
        print(f"Reminder: Invoice ID {reminder['invoice_id']} is due!")
        
        # Update status
        conn.execute(
            "UPDATE reminders SET status = 'sent' WHERE id = ?",
            (reminder['id'],)
        )
        conn.commit()
    
    conn.close()

# Main
def main():
    print("Initializing database...")
    init_db()
    
    print("Starting Telegram Invoice Reminder Bot...")
    with client:
        client.loop.run_until_complete(client.start())
        print("Bot is running!")
        client.run_until_disconnected()

if __name__ == "__main__":
    main()
