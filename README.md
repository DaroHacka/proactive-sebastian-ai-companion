# Sebastian - Proactive AI Companion

A proactive AI companion powered by local LLMs (phi4 via Ollama) that reaches out to check in on you.

## Features

- **Proactive Contact**: Sebastian initiates conversations based on scheduled intervals or appointments
- **Memory System**: Fresh, medium, and long-term memory storage with automatic archival
- **Time-aware Scheduling**: Understands natural time expressions (\"tonight\", \"later\", \"morning\", etc.)
- **Auto-pause**: Pauses automatic scheduling when appointments are set, resumes when they fire
- **TUI Interface**: Terminal-based UI with urwid (sebastian_urwid.py)
- **Cue System**: Response variation with character/personality injection
- **Robust Error Handling**: Graceful fallbacks when Ollama is unavailable
- **Comprehensive Logging**: Full debug logging to `logs/sebastian.log`

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

# Cue System (response variation)
CUE_ENABLED=true
CUE_PROBABILITY=0.2  # 20% chance

# Memory Management
MAX_MEMORY_ENTRIES=50  # Max per memory tier
ARCHIVE_THRESHOLD=30   # Days before archival
```

### 3. Run

```bash
# Simple terminal version
python sebastian_proactive.py

# TUI version (requires urwid)
python sebastian_urwid.py
```

Logs are saved to `logs/sebastian.log` automatically.

## Commands

| Command | Description |
|---------|-------------|
| `trigger` | Ask Sebastian to initiate a conversation |
| `pause` | Pause automatic scheduler |
| `resume` | Resume automatic scheduler |
| `interval X` | Set check interval to X minutes |
| `status` | Show appointments status |
| `clear-schedule` | Clear all appointments |
| `clear-all` | Clear all data |
| `memory status` | Show memory statistics (with max limits) |
| `medium memory` | Load medium-term memory |
| `long memory` | Load long-term memory |
| `cue` | Show random cue |
| `cue X` | Get cue from category X |
| `trigger cue` | Apply cue then type your message |
| `quit` | Exit |

## How It Works

### Proactive Scheduling

1. **Initialization**: On startup, checks for pending appointments
2. **Proactive Mode**: Every X minutes (default: 5), triggers conversation via background scheduler
3. **Time Detection**: Parses \"tonight\", \"later\", \"8 PM\", etc. from Sebastian's responses
4. **Auto-schedule**: Pauses when appointment created, resumes when it fires

### Memory Management

Sebastian maintains three memory tiers:
- **Fresh**: Last 10 entries (recent conversation)
- **Medium**: Older entries (up to 50, archived after 30 days)
- **Long-term**: Historical entries (up to 50, archived from medium)

Memory automatically archives:
- When fresh exceeds 10 entries → moves to medium
- When entries are >30 days old → moves to next tier
- When tier exceeds MAX_MEMORY_ENTRIES → older entries pruned

### Cue System

The cue system adds personality variation to responses:
- **Automatic**: 20% chance (configurable) on each message
- **Manual**: Use `cue` or `trigger cue` commands to preview/apply
- **Categories**: Organize personality types/characters

Example:
```
You: trigger cue
[Cue ready: MENTOR]
Play this character in your response: MENTOR: A wise, patient teacher
You: How do I learn Python?
Sebastian: [responds as MENTOR]
```

### Error Handling

If Ollama connection fails:
- Detects ConnectionError and logs \"Is Ollama running?\"
- Returns graceful fallback message
- Logs all errors to `logs/sebastian.log` with details
- 60-second timeout prevents hanging

## Project Structure

```
sebastian/
├── sebastian_proactive.py   # Main script
├── sebastian_urwid.py       # TUI version
├── scheduler.py             # Scheduling module (thread-safe)
├── time_parser.py           # Time parsing
├── intent_manager.py        # Intent handling
├── cue_manager.py           # Cue system
├── interaction_intents.py   # Check-in phrases
├── .env.example             # Config template
├── requirements.txt         # Dependencies
└── logs/                    # Auto-created, debug logs
```

The following directories are automatically created on first run:
- `memory/` - Conversation storage (fresh/medium/longterm.json)
- `appointments.json` - Appointment scheduling
- `logs/sebastian.log` - Debug and error logs

These are excluded from git (see .gitignore).

## Debugging

Check `logs/sebastian.log` for:
- Connection errors (\"Is Ollama running?\")
- Memory archival operations
- Scheduler events
- All exceptions with full stack traces

```bash
# Watch logs in real-time
tail -f logs/sebastian.log

# Or grep for errors
grep ERROR logs/sebastian.log
```

## Configuration Reference

```env
# Ollama
OLLAMA_URL=http://localhost:11434              # Ollama server URL
COMPANION_MODEL=phi4                           # Model to use

# Scheduler
SCHEDULER_INTERVAL_MINUTES=5                   # Check interval (minutes)
AUTOMATIC_ENABLED=true                         # Auto-start scheduler

# Cues
CUE_ENABLED=true                               # Enable cue system
CUE_PROBABILITY=0.2                            # Probability per message (0.0-1.0)

# Memory
MAX_MEMORY_ENTRIES=50                          # Max entries per tier
ARCHIVE_THRESHOLD=30                           # Days before archival
```

## License

MIT
