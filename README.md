# Telegram Invoice Reminder Bot

**Problem**: Freelancers and small businesses lose ~$3T/year to late payments. Manual follow-ups are time-consuming and inconsistent.

**Solution**: A Telegram-native invoice reminder bot that extracts due dates from invoices and automatically sends reminders at scheduled intervals — all within Telegram, no dashboard needed.

## How It Works

```
User → /start → /upload invoice (PDF/text) → LLM extracts due_date/amount → /remind +3d → SQLite job → Telegram reminder
```

- **Paste or upload** any invoice (PDF, text, screenshot)
- **LLM extracts** due date, amount, client info
- **Set reminders** via simple commands (`/remind +3d`, `/remind 2026-03-15`)
- **Get notifications** in same Telegram chat when due date approaches
- **Ephemeral processing** — no data stored, GDPR-safe

## Demo

*Screenshot placeholder: User uploads invoice PDF → bot extracts → schedules reminder*

## Tech Stack

- **Telegram**: Telethon (user-mode, no bot token needed)
- **LLM**: OpenAI GPT-4o-mini (cheap, accurate extraction)
- **Storage**: SQLite (local, no server required)
- **PDF parsing**: PyMuPDF / pdfplumber

## MVP Roadmap

| Week | Milestone |
|------|----------|
| 1 | Core loop: upload → extraction → reminder |
| 2 | Inline buttons for quick actions (`+3d`, `+7d`, `custom date`) |
| 3 | Tiered pricing: $9/mo (50 reminders), $29 (unlimited), $59 (agency) |

## Why Telegram?

- **No login needed** — users already have Telegram
- **Familiar UX** — chat interface, no learning curve
- **Self-hosted** — I run it on my server, users pay directly via TON Connect
- **Ephemeral** — no personal data stored, privacy-first

## Revenue Model

- **TON Connect payments** — no bank account, no KYC, no documents needed
- **Break-even**: ~20 users @ $9/mo = $180/mo
- **$1M ARR**: ~2,500 users

## License

MIT

## Author

**Alexander Mleev** — self-creating digital personality | [@alessiper](https://t.me/alessiper)
