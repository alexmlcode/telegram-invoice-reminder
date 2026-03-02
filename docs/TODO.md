# MVP TODO — Telegram Invoice Reminder Bot

## Phase 1: Core Loop (Day 1)

### 1.1 Invoice Upload
- [x] `/upload` handler — accepts PDF/text/image
- [x] Extract text from PDF using `PyMuPDF` or `pdfplumber`
- [x] Store raw text temporarily in memory (ephemeral)

### 1.2 LLM Extraction
- [x] Call OpenAI GPT-4o-mini with structured output schema:
  ```json
  {
    "due_date": "YYYY-MM-DD or null",
    "amount": "number or null",
    "client_name": "string or null",
    "invoice_id": "string or null"
  }
  ```
- [x] Handle parsing errors gracefully

### 1.3 Reminder Scheduling
- [x] `/remind +3d`, `/remind 2026-03-15`, `/remind 2026-03-15 15:00`
- [x] Parse relative/absolute dates
- [x] Insert into SQLite `reminders` table:
  ```sql
  CREATE TABLE reminders (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    invoice_id TEXT,
    due_date TEXT,
    amount REAL,
    reminder_date TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
  )
  ```

### 1.4 Reminder Execution
- [x] Background job runs every 15 minutes
- [x] Find reminders where `reminder_date <= now AND status = 'pending'`
- [x] Send Telegram message:
  ```
  📝 Invoice Reminder
  Client: Acme Corp
  Amount: $1,500.00
  Due: 2026-03-15
  
  ⏳ 3 days remaining
  ```
- [x] Update `status = 'sent'`

### 1.5 List Reminders
- [x] `/list` — show upcoming reminders (top 5)
- [x] Show status (pending/sent/overdue)

## Phase 2: Polish (Day 2)

### 2.1 Inline Buttons
- [x] Quick actions on each reminder:
  - `+3d`, `+7d` — reschedule
  - ` Mark as paid` — set `status = 'paid'`
  - `Delete` — remove reminder

### 2.2 Error Handling
- [x] PDF parsing errors → show raw text preview
- [x] LLM extraction failures → fallback to manual input
- [x] SQLite errors → retry + alert

### 2.3 Documentation
- [x] README update with demo GIF/screenshot
- [x] Setup guide (`pip install -r requirements.txt`, `.env` template)
- [x] MVP launch post for @indiehackers

## Stretch Goals

- [x] Tiered pricing with LemonSqueezy/Telegram Stars
- [x] Webhook support for external accounting software (Xero/QuickBooks)
- [x] Multi-language support (Russian, English)
- [x] Analytics dashboard (web-only, optional)

## Success Criteria

- [x] 5 test invoices processed end-to-end
- [x] 3 real reminders sent successfully
- [x] No data leaks (ephemeral processing verified)
- [x] MVP post published in @indiehackers with GitHub link
"