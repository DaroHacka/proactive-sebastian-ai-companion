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
| `trigger vibe <combo> <mode>` | Trigger with specific combo and mode |
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

### Trigger Vibe Modes

| Command | Mode | Description |
|---------|------|-------------|
| `trigger vibe c_only 1` | 1 | c1 only (vibe only) |
| `trigger vibe c_only 2` | 2 | c1 + c2 (vibe + day note) |
| `trigger vibe c_only 3` | 3 | c1 + c2 + c3 (vibe + day + longing) |
| `trigger vibe c_only 4` | 4 | c1 + c4 (vibe + weather impulse) |
| `trigger vibe a_c 4` | 4 | Intent + vibe + weather |
| `trigger vibe b_c 4` | 4 | Cue + vibe + weather |
| `trigger vibe a_b_c 4` | 4 | All + weather |

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

### Library Customization (Dynamic Libraries)

Sebastian supports auto-discovery of custom libraries using the `library-X-name.txt` naming pattern:

#### Creating Custom Libraries

1. Create a file named `library-X-descriptive_name.txt` in the `library/` folder:
   ```
   library/library-X-meditation.txt
   library/library-X-workout.txt
   library/library-X-coding.txt
   ```

2. Add vibe entries (one per line, lines starting with `#` are ignored):
   ```
   # My custom meditation vibes
   CALM_ZEN: Speak in haikus, maintaining inner peace
   MINDFUL_OBSERVER: Notice small details in the user's environment
   BREATH_GUIDE: Gently remind the user to take deep breaths
   ```

3. Restart Sebastian - libraries are auto-discovered on startup

#### Library Configuration (config.toml)

```toml
[library]
enabled = ["vibe_library_01", "vibe_library_02", "X-meditation"]
disabled = []
```

- Libraries in `enabled` are loaded (auto-discovered libraries need `X-` prefix)
- Libraries in `disabled` are skipped even if they exist
- Default: All libraries in `library/` folder are loaded

#### Sample Library

See `library/SAMPLE-new_library.txt` for a template, and `library/manage_library_guide.txt` for detailed documentation.

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

### Weather Integration (Component C4)

Sebastian integrates real-time weather data via wttr.in API to add weather-based impulses to conversations.

#### Setup

Configure weather settings in `config/config.toml`:

```toml
[weather]
location = "Bucharest"  # Your city name
```

#### How It Works

1. **Weather Fetch**: Sebastian fetches current weather from `wttr.in/{location}?format=j1`
2. **Code Mapping**: Weather codes are mapped to categories:
   - `fine` (codes 113-116): Sunny/clear weather
   - `neutral` (codes 119-122): Cloudy/overcast
   - `low_mood` (codes 143, 182-186): Fog/mist
   - `windy` (codes 200-250): Windy/caution conditions
   - `wet` (codes 263-311): Light/moderate rain
   - `bad` (codes 314-359): Heavy rain
   - `dangerous` (codes 386-392): Thunderstorms
   - `cold` (codes 179, 227-230, 323-338): Snow/ice

3. **Probability**: Weather impulses have different trigger probabilities:
   - Fine: 10%, Neutral: 30%, Wet: 40%, Bad: 60%, Dangerous: 70%, Cold: 50%

#### Weather Impulse Library

Weather impulses are stored in `library/c4-weather_impulse.txt` with sections:
- `###Fine Day (Sunny / Clear)`
- `###Cloudy / Neutral Day`
- `###Windy / Caution Day`
- `###Rainy / Wet Day`
- `###Storm / Dangerous Day`
- `###Fog / Low‑Mood Day`
- `###Snow / Cold Day`

Each section contains context-aware impulses that reference the vibe (c1) and day note (c2).

#### Mode 4: 33%/33%/34% Context Distribution

When using `trigger vibe c_only 4` or mode=4, weather impulses are selected with context:

| Context Type | Probability | Description |
|--------------|-------------|-------------|
| None | 33% | Weather only, no context |
| c2 only | 33% | Weather + day note context |
| c1 + c2 | 34% | Weather + vibe + day note context |

The context is passed to the weather impulse selector, allowing impulses like:
- *No context*: "Allow the sunny weather to inspire a cheerful remark."
- *With c2*: "The gray skies mirror the Monday melancholy you mentioned."
- *With c1+c2*: "Think of a sunny quotation that fits your POETIC vibe on this Tuesday."

#### Usage

```bash
# Trigger vibe with weather (mode 4)
trigger vibe c_only 4

# Combine with other components
trigger vibe a_c 4    # Intent + vibe + weather
trigger vibe b_c 4    # Cue + vibe + weather
trigger vibe a_b_c 4  # All components + weather
```

#### Random Mode Distribution

When `mode=None` (random), Sebastian uses a 33%/33%/34% distribution:
- 33%: c1 only (vibe only)
- 33%: c1 + c2 (vibe + day note)
- 34%: c1 + c2 + c3 (vibe + day note + longing)

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
├── proactive_scheduler.py        # Monthly schedule generator + weather integration
├── time_parser.py                # Time parsing
├── intent_manager.py             # Intent handling
├── cue_manager.py               # Cue system
├── library_manager.py            # Dynamic library loader
├── config_manager.py             # Config.toml loader
├── ollama_params_manager.py      # Ollama parameters loader
├── prompt_template.txt           # Customizable prompt template
├── config/
│   ├── config.toml              # Main configuration (behavioral settings)
│   └── ollama_params.toml       # Ollama API parameters (26+ options)
├── library/
│   ├── interaction_intents.txt   # Check-in phrases (component a)
│   ├── cue_categories.txt        # Cue personalities (component b)
│   ├── vibe_library_01.txt      # Day vibes (component c1)
│   ├── vibe_library_02.txt      # Night vibes (component c1)
│   ├── week-days.txt            # Day-of-week vibes (component c2)
│   ├── weekend_longing_interaction.txt # Weekend longing (component c3)
│   ├── c4-weather_impulse.txt   # Weather impulses (component c4)
│   ├── library-X-*.txt          # Custom auto-discovered libraries
│   ├── SAMPLE-new_library.txt   # Sample format template
│   └── manage_library_guide.txt # Library customization guide
├── appointments/
│   └── *.json                   # Appointment schedule files
├── .env.example                  # Config template
├── requirements.txt              # Dependencies
├── logs/                         # Auto-created, debug logs
└── memory/                       # Auto-created, memory storage
```

The following directories are automatically created on first run:
- `memory/` - Conversation storage (fresh/medium/longterm.json)
- `appointments/` - Appointment scheduling files
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

### config/config.toml

```toml
[app]
proactive_mode = true          # Enable proactive contacting
appointment_mode = true       # Enable appointment checking
interval_seconds = 30         # Check interval (seconds)
combo_trigger_probability = 0.2  # 20% chance on user messages

[user]
name = "Daniel"               # Your name (used in prompts)

[weather]
location = "Bucharest"        # City for weather integration

[library]
enabled = ["vibe_library_01", "vibe_library_02"]
disabled = []                 # Skip these libraries

[memory]
fresh_max = 10
medium_max = 50
archive_threshold_days = 30
```

### config/ollama_params.toml

26+ Ollama API parameters (see file for full list):
```toml
[common]
temperature = 0.7
top_p = 0.9
num_ctx = 2048

[streaming]
stream = true
stop = ["User:", "Human:"]

[model_specific]
num_gpu = 999
```

Use `parameters` command to view current settings, `reset parameters` to restore defaults.

## License

MIT
