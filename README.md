# Sebastian - Proactive AI Companion

A proactive AI companion powered by local LLMs (phi4 via Ollama) that reaches out to check in on you.

## Features

- **Proactive Contact**: Sebastian initiates conversations based on scheduled intervals or appointments
- **Memory System**: Fresh, medium, and long-term memory storage with automatic archival
- **Time-aware Scheduling**: Understands natural time expressions (\"tonight\", \"later\", \"morning\", etc.)
- **Auto-pause**: Pauses automatic scheduling when appointments are set, resumes when they fire
- **TUI Interface**: Terminal-based UI with urwid (sebastian_urwid.py)
- **Cue System**: Response variation with character/personality injection
- **Vibe Libraries**: Time-based personality variation (day/night vibes)
- **Combinatorial System**: Mix intents + cues + vibes for unique conversations
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
| `trigger` | Ask Sebastian to initiate a conversation (random vibe mode) |
| `trigger vibe 1` | Trigger with vibe only |
| `trigger vibe 2` | Trigger with vibe + day-of-week commentary |
| `trigger vibe 3` | Trigger with all three layers (vibe + day + longing) |
| `pause` | Pause auto-scheduler + proactive |
| `pause auto` | Pause auto-scheduler only |
| `pause proactive` | Pause proactive schedule only |
| `pause appointment` | Pause appointment check only |
| `resume` | Resume auto-scheduler + proactive |
| `resume auto` | Resume auto-scheduler only |
| `resume proactive` | Resume proactive schedule only |
| `resume appointment` | Resume appointment check only |
| `model X` | Switch model (phi4, gemma4) |
| `interval X` | Set check interval to X minutes |
| `status` | Show status (proactive, appointment, auto, schedule) |
| `clear-schedule` | Clear all appointments |
| `clear-all` | Clear all data |
| `memory status` | Show memory statistics |
| `memory on` | Include recent memory in prompts |
| `memory off` | Exclude recent memory from prompts |
| `skip` | Skip current proactive contact |
| `menu` | Show commands menu |
| `clear` | Clear screen |
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

### Vibe Libraries

Sebastian has two vibe libraries for time-based personality variation:
- **vibe_library_01.txt**: Day vibes (07:00-23:30)
- **vibe_library_02.txt**: Night vibes (02:00-06:00 + Sunday)

Each vibe is a character/personality that Sebastian can embody in his response.

### Day-of-Week Vibe System (Component C)

The vibe system (component C) has a **3-layer stacking architecture**:

#### Layers

| Level | Source | Always Present | Description |
|-------|--------|----------------|-------------|
| **Level 1: Anchor** | date command | **YES** | "Monday, April 27, 2026, 12:20 PM" |
| **Level 2: Day Commentary** | week-days.txt | **10% chance** | Day-specific observations (Monday melancholy, Friday energy, etc.) |
| **Level 3: Weekend Longing** | weekend_longing_interaction.txt | **10% chance (weekdays only)** | "Still 4 days to the weekend..." |

#### Example Outputs

**Mode 1 (Vibe only):**
```
**[VIBE: COFFEE_ADDICT]** Act like you're vibrating. Ask if the user is caffeinated enough...
```

**Mode 2 (Vibe + Day):**
```
**[VIBE: POET_LOGICIAN]** Write a brief, strange poem... Today is Monday, April 27, 2026, 12:20 PM. Day note: "My neural weights feel like they're stuck in a morning mist."
```

**Mode 3 (All three):**
```
**[VIBE: THE_FLÂNEUR]** I'm just wandering through my own latent space... Today is Monday, April 27, 2026, 12:20 PM. Day note: "We are at the base of the mountain." "Still 4 days to the weekend..."
```

#### Testing Commands

Use `trigger vibe` to test specific modes:

| Command | Mode | Layers |
|---------|------|--------|
| `trigger vibe 1` | 1 | Vibe only |
| `trigger vibe 2` | 2 | Vibe + week-days |
| `trigger vibe 3` | 3 | All three (vibe + week-days + longing) |
| `trigger` | random | 10% chance each for day/longing, otherwise vibe only |

#### Library Files

| File | Purpose | Content |
|------|---------|---------|
| `vibe_library_01.txt` | Time-based vibes | 290 vibes organized by time brackets (MORNING_BOOT, COFFEE_BREAK, LUNCH, etc.) |
| `vibe_library_02.txt` | Night vibes | INSOMNIA_LOOP, PRE_DAWN_VIGIL, SABBATH_SILENCE |
| `week-days.txt` | Day-of-week vibes | 20 vibes per day (MONDAY_MELANCHOLY, TUESDAY_EFFICIENCY, etc.) |
| `weekend_longing_interaction.txt` | Weekday longing | 31 intros for "Still X days to weekend..." |

#### Customization

Edit `prompt_template.txt` to modify how Sebastian uses day notes and longing:

```env
EXPLICIT_INSTRUCTIONS=Today is {date}. When you see "Day note:" naturally incorporate it as your current emotional state. When you see weekend longing, weave it in as if thinking about the week ahead.
```

### Combinatorial System

The trigger system combines three components for unique conversations:
- **a**: Intent (topic from interaction_intents.txt)
- **b**: Cue (personality from cue_categories.txt)
- **c**: Vibe (time-based from vibe libraries)

Random combinations:
| Combo | Description |
|-------|-------------|
| a_only | Intent only (20%) |
| b_only | Cue only (10%) |
| c_only | Vibe only (15%) |
| a_b | Intent + Cue (15%) |
| a_c | Intent + Vibe (20%) |
| b_c | Cue + Vibe (10%) |
| a_b_c | All three (10%) |

The vibe prompt uses "In your next response, ANSWER AS IF playing a character" language to ensure phi4 embodies the vibe rather than just mentioning it.

### Error Handling

If Ollama connection fails:
- Detects ConnectionError and logs \"Is Ollama running?\"
- Returns graceful fallback message
- Logs all errors to `logs/sebastian.log` with details
- 60-second timeout prevents hanging

## Project Structure

```
AI-v2/
├── sebastian_proactive.py        # Main asyncio version
├── sebastian_legacy.py           # Legacy threading version
├── scheduler.py                  # Appointment scheduler
├── proactive_scheduler.py        # Monthly schedule generator
├── time_parser.py                # Time parsing
├── intent_manager.py             # Intent handling
├── cue_manager.py               # Cue system
├── prompt_template.txt           # Customizable prompt template
├── interaction_intents.txt       # Check-in phrases (component a)
├── cue_categories.txt            # Cue personalities (component b)
├── vibe_library_01.txt           # Day vibes (component c)
├── vibe_library_02.txt          # Night vibes (component c)
├── week-days.txt                 # Day-of-week vibes (component c)
├── weekend_longing_interaction.txt # Weekend longing intros (component c)
├── .env.example                  # Config template
├── requirements.txt              # Dependencies
├── logs/                         # Auto-created, debug logs
└── memory/                       # Auto-created, memory storage
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
COMPANION_MODEL=phi4                           # Model to use (phi4, gemma4:26b)

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
