# Ouroboros - Local Setup Instructions

## Quick Start (5 minutes)

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/razzant/ouroboros.git
cd ouroboros

# Install dependencies
pip install -r requirements.txt
playwright install  # Install browser drivers
```

### 2. Create `.env` File

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env

# Edit .env with your secrets
nano .env  # or vim, code, etc.
```

### 3. Create Storage Directories

```bash
mkdir -p ~/.ouroboros/{state,logs,memory,index,locks,archive}
```

### 4. Start Ouroboros

```bash
python colab_launcher.py
```

That's it! The bot will start and wait for your first message on Telegram.

---

## Detailed Configuration

### Required Secrets

| Variable | Get From | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys | API key for LLM access |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram | Telegram bot token |
| `GITHUB_TOKEN` | GitHub Settings → Tokens | Personal access token (repo scope) |
| `TOTAL_BUDGET` | Any | Spending limit in USD |

### Optional Secrets

| Variable | Get From | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys | Enables web search |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/settings/keys | Enables Claude Code CLI |

### Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_USER` | `razzant` | Your GitHub username |
| `GITHUB_REPO` | `ouroboros` | Repository name |
| `OUROBOROS_BASE_URL` | (OpenRouter) | Local API endpoint (e.g., `http://localhost:11434/v1`) |
| `OUROBOROS_MODEL` | `anthropic/claude-sonnet-4.6` | Primary LLM model |
| `OUROBOROS_MODEL_CODE` | `anthropic/claude-sonnet-4.6` | Code editing model |
| `OUROBOROS_MODEL_LIGHT` | `google/gemini-3-pro-preview` | Lightweight tasks model |
| `OUROBOROS_WEBSEARCH_MODEL` | `gpt-5` | Web search model |
| `OUROBOROS_MAX_WORKERS` | `5` | Max parallel workers |
| `OUROBOROS_MAX_ROUNDS` | `200` | Max LLM rounds per task |
| `OUROBOROS_BG_BUDGET_PCT` | `10` | Budget % for background consciousness |

**Using Ollama example:**
```bash
OUROBOROS_BASE_URL=http://localhost:11434/v1
OUROBOROS_MODEL=llama3.1:8b
OUROBOROS_MODEL_CODE=llama3.1:8b
OUROBOROS_MODEL_LIGHT=llama3:8b
```

### Storage Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `DRIVE_ROOT` | `/home/username/.ouroboros` | Local storage root |
| `OUROBOROS_REPO_DIR` | `/home/username/ouroboros_repo` | Cloned repo location |

---

## Telegram Commands

Once running, use these commands in your Telegram bot:

| Command | Description |
|---------|-------------|
| `/status` | Shows active workers, task queue, budget |
| `/panic` | Emergency stop |
| `/restart` | Soft restart |
| `/evolve` | Start autonomous evolution mode |
| `/evolve stop` | Stop evolution mode |
| `/review` | Queue a deep review task |
| `/bg start` | Start background consciousness |
| `/bg stop` | Stop background consciousness |

---

## Troubleshooting

### Bot doesn't respond
- Check `~/.ouroboros/logs/supervisor.jsonl` for errors
- Verify all secrets in `.env` are correct
- Test Telegram token: `curl https://api.telegram.org/bot<token>/getMe`

### Budget tracking issues
- Check `~/.ouroboros/state/state.json` for spent amounts
- Verify `TOTAL_BUDGET` is set correctly in `.env`

### Git operations fail
- Ensure `GITHUB_TOKEN` has `repo` scope
- Test token: `curl -H "Authorization: token <token>" https://api.github.com/user/repos`

---

## Data Storage Locations

All data stored locally under `DRIVE_ROOT`:

```
~/.ouroboros/
├── state/state.json          # Persistent state & budget
├── logs/
│   ├── chat.jsonl           # Telegram chat history
│   ├── events.jsonl         # System events
│   ├── progress.jsonl       # Task progress
│   └── supervisor.jsonl     # Supervisor logs
├── memory/
│   ├── scratchpad.md        # Current thoughts
│   ├── identity.md          # Self-identity
│   └── dialogue_summary.md  # Chat summaries
└── locks/                    # File locks
```

---

## Advanced: Running as a Service

### systemd Service

Create `/etc/systemd/system/ouroboros.service`:

```ini
[Unit]
Description=Ouroboros AI Agent
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/home/yourusername/ouroboros
EnvironmentFile=/home/yourusername/ouroboros/.env
ExecStart=/usr/bin/python /home/yourusername/ouroboros/colab_launcher.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ouroboros
sudo systemctl start ouroboros
```

