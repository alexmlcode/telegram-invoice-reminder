#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
import re
import pymupdf
from dateutil.parser import parse as parse_date
from telethon import TelegramClient, events

# Configuration
API_ID = int(os.environ.get("TELEGRAM_API_ID", 0))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
SESSION_PATH = os.environ.get("TELEGRAM_SESSION_PATH", "~/.ouroboros/telegram/user")
DB_PATH = Path(tempfile.gettempdir()) / "invoice_reminder.db"

# Database helpers
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            amount REAL NOT NULL,
            due_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            invoice_hash TEXT UNIQUE,
            raw_text TEXT
        );
        """
    )
    conn.close()

def add_invoice(client_name, amount, due_date, raw_text):
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    invoice_hash = hash(f"{client_name}{amount}{due_date}{raw_text}")
    created_at = datetime.utcnow().isoformat()
    cursor.execute(
        """INSERT INTO invoices (client_name, amount, due_date, status, created_at, invoice_hash, raw_text)
           VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
        (client_name, amount, due_date, created_at, invoice_hash, raw_text),
    )
    conn.commit()
    invoice_id = cursor.lastrowid
    conn.close()
    return invoice_id

def get_pending_invoices():
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE status = 'pending' ORDER BY due_date ASC")
    invoices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return invoices

# LLM extraction (simplified for now)
def extract_invoice_data(text):
    result = {"client_name": None, "amount": None, "due_date": None}
    amount_match = re.search(r"amount[:\s]*\$?(\d+\.?\d*)", text, re.IGNORECASE)
    if amount_match:
        result["amount"] = float(amount_match.group(1))
    date_match = re.search(r"(due|payable)[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", text, re.IGNORECASE)
    if date_match:
        try:
            result["due_date"] = parse_date(date_match.group(2)).isoformat()
        except Exception:
            pass
    client_match = re.search(r"bill to[:\s]*(.+)" , text, re.IGNORECASE)
    if client_match:
        result["client_name"] = client_match.group(1).strip()
    return result

# Telegram client setup
if BOT_TOKEN:
    client = TelegramClient("session_bot", API_ID, API_HASH)
else:
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

@client.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    await event.respond(
        "Hello! I'm Invoice Reminder Bot.\n\n"
        "I help freelancers track invoices and get paid on time.\n\n"
        "Commands:\n"
        "/upload - Upload invoice PDF/text\n"
        "/add - Add invoice manually\n"
        "/list - Show pending invoices\n"
        "/remind - Set reminder for specific date"
    )

@client.on(events.NewMessage(pattern="/upload"))
async def upload_handler(event):
    await event.respond("Please send your invoice as a PDF file or paste the text.")

@client.on(events.NewMessage(pattern="/list"))
async def list_handler(event):
    invoices = get_pending_invoices()
    if not invoices:
        await event.respond("No pending invoices found.")
        return
    message = "\n\n".join(
        f"#{inv['id']} - {inv['client_name']}\n$ {inv['amount']:.2f}\nDue: {inv['due_date'][:10]}"
        for inv in invoices
    )
    await event.respond(f"Pending Invoices:\n\n{message}")

if __name__ == "__main__":
    init_db()
    print("Starting Invoice Reminder Bot...")
    client.start()
    client.run_until_disconnected()
