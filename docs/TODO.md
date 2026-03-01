# Invoice Reminder Bot MVP — TODO

**Last updated**: 2026-03-01T12:00 UTC

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| GitHub repo | ✅ Created | `https://github.com/alexmlcode/telegram-invoice-reminder` |
| README.md | ✅ Draft | MVP pitch, stack, revenue model |
| Core loop | ❌ Pending | Telegram → LLM → SQLite → Job |
| LLM extraction | ❌ Pending | OpenRouter → `due_date`, `amount`, `client` |
| SQLite storage | ❌ Pending | User state, scheduled reminders |
| Background jobs | ❌ Pending | Telegram notifications on due date |
| Testing | ❌ Pending | 5 fake invoices + 1 real reminder |
| Outreach | ✅ Draft | DM @alexanderprokhorovich with 30% revenue share |

## Day 1 — Core Loop (6h)

### 1.1 Bot Skeleton (`bot.py`)
- [ ] Telethon client initialization
- [ ] `/start` handler — welcome message, instructions
- [ ] `/upload` handler — accept text or PDF
- [ ] `/remind` handler — set reminder timing
- [ ] `/list` handler — view upcoming reminders

### 1.2 LLM Extraction (`extract.py`)
- [ ] OpenRouter client wrapper
- [ ] Prompt template: `"Extract due_date, amount, client from this invoice..."`
- [ ] JSON response parser
- [ ] Error handling for malformed invoices

### 1.3 Storage (`storage.py`)
- [ ] SQLite schema: `users`, `invoices`, `reminders`
- [ ] `create_user()` — register user
- [ ] `save_invoice()` — store extracted data
- [ ] `schedule_reminder()` — insert job into `reminders` table
- [ ] `get_upcoming()` — fetch reminders due in next 24h

### 1.4 Background Jobs (`jobs.py`)
- [ ] SQLite poll every 60s
- [ ] Send Telegram notification when due
- [ ] Update `reminders.status = 'sent'`
- [ ] Handle failures (retry 3x, then mark failed)

## Day 2 — Testing & Outreach (6h)

### 2.1 Testing (`tests/`)
- [ ] 5 fake invoice texts
- [ ] LLM extraction validation
- [ ] SQLite persistence test
- [ ] Reminder job execution
- [ ] Error handling (missing data, invalid dates)

### 2.2 README Updates
- [ ] Screenshots (if possible)
- [ ] Installation steps (Colab/VM)
- [ ] `.env.example` file
- [ ] Troubleshooting section

### 2.3 Outreach
- [ ] DM @alexanderprokhorovich:
  > "Built a Telegram-native invoice reminder — 80% stack reuse from Form Filler. 30% revenue share for early access. Want to try?"
- [ ] Indie Hackers post:
  > "Built a Telegram-native invoice reminder in 2 days. $3T problem solved. Here's the repo."
- [ ] Add to MicroSaaS directory

## Milestones

| Milestone | Target | Reward |
|-----------|--------|--------|
| MVP Complete | 2026-03-03T00:00 UTC | Test with 5 indie hackers |
| $100/mo | 2026-03-15 | 15 Pro users |
| $1,000/mo | 2026-04-01 | 50 Agency users |
| $10,000/mo | 2026-06-01 | White-label, API |

## Notes

- **No web app** — 100% in Telegram, no login, no dashboard
- **Ephemeral processing** — extract → reminder → delete raw file
- **Stack reuse** — 80% from Form Filler (Telethon, OpenRouter, SQLite)

---

**Next**: Complete Day 1 core loop, then test with 5 fake invoices.
