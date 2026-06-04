# Calendar PA

A production-grade Google Calendar MCP server with a Telegram bot interface. Manage your calendar in plain English — schedule meetings, find free slots, set up recurring events, and get reminders — all through Claude or Telegram.

---

## Features

- **Natural language scheduling** — "Schedule a team sync tomorrow at 3pm for an hour"
- **Conflict detection** — automatically checks for clashes before creating events
- **Smart slot finder** — "Find me a 2 hour deep work block this week" (AI-powered reasoning)
- **Complex recurring events** — "Every second Tuesday of the month", "Every weekday until December"
- **Reminders** — configurable popup and email reminders on any event
- **Session memory** — remembers context and preferences across sessions
- **Two interfaces** — Claude Desktop (MCP) and Telegram bot

---

## Architecture

```
Google Calendar API
        ↑
MCP Server (Python)
        ↑
   ┌────┴────┐
Claude    Telegram Bot
Desktop   (Claude API + MCP tools)
```

The MCP server exposes tools that any MCP-compatible client can use. The Telegram bot calls the same tool handlers directly, giving you a mobile-friendly interface with the same intelligence.

---

## Quick Start

### Requirements

- Python 3.12+
- A Google Cloud project with the Calendar API enabled
- An Anthropic API key (for the Telegram bot)
- A Telegram bot token (for the Telegram bot)

### 1. Clone and set up

```bash
git clone https://github.com/Richardilemon/calendar-pa.git
cd calendar-pa

python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Google Calendar OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Google Calendar API**
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop app**
6. Download the JSON file, rename it to `credentials.json`, place it in the project root
7. Add your Google account as a test user under **OAuth consent screen → Test users**

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Google Calendar
CALENDAR_ID=primary
CREDENTIALS_FILE=/absolute/path/to/calendar-pa/credentials.json
TOKEN_FILE=/absolute/path/to/calendar-pa/token.json

# Session context storage
CONTEXT_FILE=/absolute/path/to/calendar-pa/data/session_context.json

# Telegram bot (required for bot interface)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### 4. Authenticate with Google

```bash
python -c "from src.auth import get_calendar_service; get_calendar_service(); print('authenticated')"
```

This opens your browser for OAuth authorization. A `token.json` file is saved for future sessions.

### 5. Run the MCP server

```bash
python -m src.server
```

### 6. Connect to Claude Desktop

Add to your `claude_desktop_config.json`:

**MacOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "calendar-pa": {
      "command": "/absolute/path/to/calendar-pa/venv/bin/python",
      "args": ["/absolute/path/to/calendar-pa/src/server.py"],
      "cwd": "/absolute/path/to/calendar-pa"
    }
  }
}
```

Restart Claude Desktop. You should see `calendar-pa` in the connectors list.

### 7. Run the Telegram bot (optional)

Create a Telegram bot via [@BotFather](https://t.me/BotFather) and add the token to `.env`, then:

```bash
python src/bot.py
```

---

## MCP Tools

| Tool | Description |
|---|---|
| `get_events` | Fetch events by date, date range, or keyword |
| `create_event` | Create event with automatic conflict detection |
| `update_event` | Reschedule, rename, or update any event |
| `delete_event` | Delete with confirmation step |
| `find_free_slot` | AI-powered free slot finder |
| `create_recurring_event` | Natural language recurring events |
| `set_reminder` | Add popup or email reminders |
| `get_session_context` | Load persistent session state |
| `update_session_context` | Save state across sessions |

## Resources

| Resource | URI | Description |
|---|---|---|
| Today's schedule | `calendar://today` | Live events for today |
| This week's schedule | `calendar://week` | Live events for the week |
| Tool statistics | `system://tool-stats` | Tool call metrics |

---

## Usage Examples

**Claude Desktop:**
- *"What's on my calendar this week?"*
- *"Schedule a FANAP planning session tomorrow at 10am for 2 hours"*
- *"Find me a free 90 minute slot on Thursday"*
- *"Create a recurring team standup every Monday at 9am"*
- *"Move my 3pm meeting to Friday"*

**Telegram bot:**
- `/today` — today's schedule
- `/week` — this week at a glance
- Or just type naturally — the bot understands plain English

---

## Self-Hosting Notes

This is a self-hosted tool — you run your own instance with your own credentials. There is no shared hosted service.

Each user needs:
- Their own Google OAuth credentials (`credentials.json`)
- Their own Anthropic API key (for the Telegram bot)
- Their own Telegram bot token (for the Telegram bot)

None of these are included in the repo — they stay on your machine only.

---

## Deployment

To run the Telegram bot as an always-on service, deploy `src/bot.py` to any Python-compatible host:

- **Railway** — recommended, generous free tier
- **Render** — Background Worker, $7/month
- **Fly.io** — free tier available
- **Any VPS** — run with `python src/bot.py` or set up as a systemd service

For cloud deployment, store `credentials.json` and `token.json` as base64-encoded environment variables:

```bash
base64 -i credentials.json | tr -d '\n'  # → GOOGLE_CREDENTIALS_B64
base64 -i token.json | tr -d '\n'        # → GOOGLE_TOKEN_B64
```

The server decodes these at startup via `src/setup.py`.

---

## Project Structure

```
calendar-pa/
├── src/
│   ├── server.py          # MCP server — tools, resources, routing
│   ├── auth.py            # Google OAuth flow
│   ├── bot.py             # Telegram bot
│   ├── setup.py           # Cloud deployment credential setup
│   └── tools/
│       ├── calendar.py    # All calendar tool handlers
│       └── context.py     # Session context tools
├── data/                  # Session context storage (gitignored)
├── credentials.json       # Google OAuth credentials (gitignored)
├── token.json             # Google OAuth token (gitignored)
├── .env                   # Environment variables (gitignored)
├── .env.example           # Environment variable template
├── requirements.txt
└── Procfile               # For cloud deployment
```

---

## Roadmap

**v1 (current)**
- Core calendar operations with conflict detection
- Smart slot finder with AI reasoning
- Complex recurring events
- Session memory
- Telegram bot interface

**v2 (planned)**
- Multi-calendar support
- Per-user OAuth for hosted deployment
- React Native app for alarm-based notifications
- Meeting suggestions with attendee availability

---

## Built With

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Google Calendar API](https://developers.google.com/calendar)
- [python-telegram-bot](https://python-telegram-bot.org)
- [Anthropic Claude API](https://anthropic.com)

---

## License

MIT