# Sebastian - Proactive AI Companion

A proactive AI companion powered by local LLMs (phi4 via Ollama) that reaches out to check in on you.

## Features

- **Proactive Contact**: Sebastian initiates conversations based on scheduled intervals or appointments
- **Memory System**: Fresh, medium, and long-term memory storage
- **Time-aware Scheduling**: Understands natural time expressions ("tonight", "later", "morning", etc.)
- **Auto-pause**: Pauses automatic scheduling when appointments are set, resumes when they fire
- **TUI Interface**: Terminal-based UI with urwid (sebastian_urwid.py)

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
nano .env
```

Required settings in `.env`:
```env
OLLAMA_URL=http://localhost:11434
COMPANION_MODEL=phi4
SCHEDULER_INTERVAL_MINUTES=5
AUTOMATIC_ENABLED=true
```

### 3. Run

```bash
# Simple terminal version
python sebastian_proactive.py

# TUI version (requires urwid)
python sebastian_urwid.py
```

## Commands

| Command | Description |
|---------|-----------|
| `trigger` | Ask Sebastian to initiate a conversation |
| `pause` | Pause automatic scheduler |
| `resume` | Resume automatic scheduler |
| `interval X` | Set check interval to X minutes |
| `status` | Show appointments status |
| `clear-schedule` | Clear all appointments |
| `clear-all` | Clear all data |
| `memory status` | Show memory statistics |
| `medium memory` | Load medium-term memory |
| `long memory` | Load long-term memory |
| `quit` | Exit |

## How It Works

1. **Initialization**: On startup, checks for pending appointments
2. **Proactive Mode**: Every X minutes (default: 5), triggers conversation
3. **Time Detection**: Parses "tonight", "later", "8 PM", etc. from Sebastian's responses
4. **Auto-schedule**: Pauses when appointment created, resumes when it fires

## Project Structure

```
sebastian/
├── sebastian_proactive.py   # Main script
├── sebastian_urwid.py       # TUI version
├── scheduler.py            # Scheduling module
├── time_parser.py          # Time parsing
├── intent_manager.py       # Intent handling
├── interaction_intents.py # Check-in phrases
├── .env.example           # Config template
└── requirements.txt       # Dependencies
```

The following directories are automatically created on first run:
- `memory/` - Conversation storage
- `appointments.json` - Appointment scheduling

These are excluded from git (see .gitignore).

## License

MIT