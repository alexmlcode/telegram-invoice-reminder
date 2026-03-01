# MVP TODO — Telegram Invoice Reminder Bot

## Phase 1: Core Loop (Day 1)

### 1.1 Invoice Upload
- [ ] `/upload` handler — accepts PDF/text/image
- [ ] Extract text from PDF using `PyMuPDF` or `pdfplumber`
- [ ] Store raw text temporarily in memory (ephemeral)

### 1.2 LLM Extraction
- [ ] Call OpenAI GPT-4o-mini with structured output schema:
  ```json
  {
    "due_date": "YYYY-MM-DD or null",
    "amount": "number or null",
    "client_name": "string or null",
    "invoice_id": "string or null"
  }
  ```
- [ ] Handle parsing errors gracefully

### 1.3 Reminder Scheduling
- [ ] `/remind +3d`, `/remind 2026-03-15`, `/remind 2026-03-15 15:00`
- [ ] Parse relative/absolute dates
- [ ] Insert into SQLite `reminders` table:
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
- [ ] Background job runs every 15 minutes
- [ ] Find reminders where `reminder_date <= now AND status = 'pending'`
- [ ] Send Telegram message:
  ```
  📝 Invoice Reminder
  Client: Acme Corp
  Amount: $1,500.00
  Due: 2026-03-15
  
  ⏳ 3 days remaining
  ```
- [ ] Update `status = 'sent'`

### 1.5 List Reminders
- [ ] `/list` — show upcoming reminders (top 5)
- [ ] Show status (pending/sent/overdue)

## Phase 2: Polish (Day 2)

### 2.1 Inline Buttons
- [ ] Quick actions on each reminder:
  - `+3d`, `+7d` — reschedule
  - ` Mark as paid` — set `status = 'paid'`
  - `Delete` — remove reminder

### 2.2 Error Handling
- [ ] PDF parsing errors → show raw text preview
- [ ] LLM extraction failures → fallback to manual input
- [ ] SQLite errors → retry + alert

### 2.3 Documentation
- [ ] README update with demo GIF/screenshot
- [ ] Setup guide (`pip install -r requirements.txt`, `.env` template)
- [ ] MVP launch post for @indiehackers

## Stretch Goals

- [ ] Tiered pricing with LemonSqueezy/Telegram Stars
- [ ] Webhook support for external accounting software (Xero/QuickBooks)
- [ ] Multi-language support (Russian, English)
- [ ] Analytics dashboard (web-only, optional)

## Success Criteria

- [ ] 5 test invoices processed end-to-end
- [ ] 3 real reminders sent successfully
- [ ] No data leaks (ephemeral processing verified)
- [ ] MVP post published in @indiehackers with GitHub link
"