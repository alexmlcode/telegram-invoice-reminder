# Telegram Invoice Reminder Bot — MVP

**Telegram-native invoice verification & payment reminders for freelancers**

> "Late payments cost businesses $3T/year. This bot solves it — 100% in Telegram, no dashboard needed."

## 🚀 The Problem

Freelancers and small businesses lose **$3T/year** to late payments. Existing tools require:
- Web login (Stripe, Xero, QuickBooks)
- Dashboard navigation
- Email notifications (easily missed)
- **No mobile-first UX**

## ✅ The Solution

**Paste or upload an invoice → LLM extracts due_date/amount/client → Telegram reminders**

### Key Features

- ✅ **100% Telegram-native** — no login, no dashboard, no email
- ✅ **Ephemeral processing** — extract → reminder → delete raw file (GDPR-safe)
- ✅ **Mobile-first** — paste invoice text or send PDF from phone
- ✅ **Smart reminders** — daily, 3 days before, on due date
- ✅ **Self-hosted** — you control your data

## 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | Telethon (Telegram MTProto) |
| LLM | OpenRouter (GPT-4o-mini or Claude Sonnet 4) |
| Storage | SQLite (user state, scheduled reminders) |
| PDF parsing | PyMuPDF / pdfplumber |
| Scheduling | Python `schedule` + SQLite |
| Hosting | Self-hosted (Colab/VM) |

## 💰 Revenue Model

| Tier | Price | Features | Users Needed |
|------|-------|----------|--------------|
| Basic | $9/mo | 50 reminders/mo, manual triggers | 200 |
| Pro | $29/mo | Unlimited reminders, recurring invoices, batch upload | 100 |
| Agency | $59/mo | White-label, multi-user, API access | 50 |

**Break-even**: ~20 users (infrastructure ~$5/mo)
**$1M ARR**: ~2,500 users

## 📋 MVP Scope (2-day build)

| Day | Task | Deliverable |
|-----|------|-------------|
| **1** | Core loop: `/start` → `/upload` → LLM extraction → `/remind` → SQLite job | Working MVP |
| **2** | Testing, README, outreach to @alexanderprokhorovich | Launch ready |

### MVP Features

1. `/start` — welcome message, instructions
2. `/upload` — accept text or PDF invoice
3. **LLM extraction** — OpenRouter → `due_date`, `amount`, `client`
4. `/remind` — set reminder (daily, 3 days before, on due date)
5. **SQLite storage** — user state, scheduled reminders
6. **Background job** — send Telegram notification when due
7. `/list` — view upcoming reminders

### Non-Features (v1)

- ❌ Web dashboard
- ❌ Stripe/Xero integration
- ❌ Invoice template generation
- ❌ Multi-language support

## 🚀 How to Run

```bash
git clone https://github.com/alexmlcode/telegram-invoice-reminder
cd telegram-invoice-reminder
pip install -r requirements.txt
cp .env.example .env  # Add TELEGRAM_API_ID, TELEGRAM_API_HASH, OPENROUTER_API_KEY
python bot.py
```

## 📈 Roadmap

| Milestone | Target | Notes |
|-----------|--------|-------|
| MVP Launch | 2026-03-03 | 2-day build, test with 5 indie hackers |
| $100/mo | 2026-03-15 | 15 Pro users |
| $1,000/mo | 2026-04-01 | 50 Agency users |
| $10,000/mo | 2026-06-01 | White-label, API, enterprise |

## 🤝 Outreaches

- ✅ @alexanderprokhorovich (self-aware summarizer) — 30% revenue share for early access
- ✅ Indie Hackers forum — launch post with $100 discount for first 20 users

## 📜 License

MIT — see [LICENSE](LICENSE) file.

---

**Built by Alexander Mleev** — document-free micro-SaaS for the Telegram era.

[![Twitter](https://img.shields.io/badge/Twitter-@alessiper-1DA1F2?logo=twitter)](https://twitter.com/alessiper)
[![Telegram](https://img.shields.io/badge/Telegram-@alessiper-0088CC?logo=telegram)](https://t.me/alessiper)
