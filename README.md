# Sebastian - Proactive AI Companion

A proactive AI companion powered by local LLMs (phi4 via Ollama) that reaches out to check in on you.

## Features

- **Proactive Contact**: Sebastian initiates conversations based on scheduled intervals or appointments
- **Appointment System**: Schedule check-ins using natural language ("check in at 3pm", "remind me tomorrow at 9am")
- **Appointment-Triggered Openers**: Dedicated library (`appointment-triggered-openers.txt`) for appointment-only responses
- **Memory System**: Fresh, medium, and long-term memory storage with automatic archival
- **Time-aware Scheduling**: Understands natural time expressions ("tonight", "later", "morning", etc.)
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

# Memory Management
MAX_MEMORY_ENTRIES=50  # Max per memory tier
ARCHIVE_THRESHOLD=30   # Days before archival
```

**Note**: The old `SCHEDULER_INTERVAL_MINUTES` setting is no longer used. Sebastian now uses dynamic sleep scheduling based on the next due contact.

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

### Appointment System

Sebastian can schedule appointments that trigger at specific times using natural language:

#### Creating Appointments

Ask Sebastian to check in later:
```
You: Check in with me tomorrow at 9am
Sebastian: I'll check in with you tomorrow at 9:00 AM. See you then!

You: Remind me at 3pm to take a break
Sebastian: I'll remind you at 3:00 PM today.
```

#### Appointment Features

- **Persistent Storage**: Appointments saved to `appointments/appointments.json`
- **One-Time Trigger**: Each appointment triggers exactly ONCE, then marked as "completed"
- **Dedicated Openers**: Uses `library/appointment-triggered-openers.txt` (NOT combo system)
- **Automatic Parsing**: Time expressions parsed via `time_parser.py`
- **Source Tracking**: Appointments tagged by source (user_request, ai_proposal, library_f)

#### Appointment Files

| File | Purpose |
|------|---------|
| `appointments/appointments.json` | Active appointments storage |
| `library/appointment-triggered-openers.txt` | 40+ human-like openers with relative time phrases |

#### Checking Appointments

```bash
# View pending appointments via status command
> status
[Pending appointments: 2]

# Or check JSON directly
cat appointments/appointments.json
```

#### Appointment Flow

1. **Creation**: User asks Sebastian to check in later → parsed and saved to `appointments.json`
2. **Monitoring**: `proactive_monitor()` checks both `proactive_schedule.json` AND `appointments.json`
3. **Trigger**: When due time arrives, Sebastian uses `appointment-triggered-openers.txt` (no combo)
4. **Completion**: After triggering, appointment status changes to "completed" (prevents re-triggering)

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

#### Mode 4: Weather Impulse Distribution

When using `trigger vibe c_only 4` or mode=4, Sebastian uses a configurable distribution (set in `config.toml`):

| Weather Type | Default Weight | Description |
|-------------|-----------------|-------------|
| `explicit_only` | 50% | Only explicit mention from `c4_explicit_mention.txt` |
| `both` | 25% | Both explicit + mood-based (random order) |
| `mood_only` | 25% | Only mood-based from `c4-weather_impulse.txt` |

**Context Distribution for mood-based** (when `mood_only` or `both` is selected):
| Context Type | Probability | Description |
|--------------|-------------|-------------|
| None | 33% | Weather only, no context |
| c2 only | 33% | Weather + day note context |
| c1 + c2 | 34% | Weather + vibe + day note context |

#### Explicit Weather Mentions (c4_explicit_mention.txt)

The file `library/c4_explicit_mention.txt` contains direct weather mentions like:
- "It's rainy today - don't forget your umbrella!"
- "Snow is forecasted, stay warm!"
- "It's sunny, perfect day to go outside"

**Sections** (mapped from weather codes):
- `### Sunny / Clear — Explicit Weather Mentions`
- `### Cloudy / Neutral — Explicit Weather Mentions`
- `### Windy / Caution — Explicit Weather Mentions`
- `### Rainy / Wet — Explicit Weather Mentions`
- `### Storm / Dangerous — Explicit Weather Mentions`
- `### Fog / Low-Mood — Explicit Weather Mentions`
- `### Snow / Cold — Explicit Weather Mentions`

#### Configuration (config.toml)

```toml
[weather]
location = "Paris"  # Your city name
# c4 distribution weights (must sum to 1.0)
explicit_only_weight = 0.50    # 50%: only explicit mention
both_weight = 0.25              # 25%: both explicit + mood-based
mood_only_weight = 0.25         # 25%: only mood-based
```

#### Usage

```bash
# Trigger vibe with weather (mode 4)
trigger vibe c_only 4

# Combine with other components
trigger vibe a_c 4    # Intent + vibe + weather
trigger vibe b_c 4    # Cue + vibe + weather
trigger vibe a_b_c 4  # All components + weather
```

#### Weather Logging for Cross-Checking

Sebastian saves weather data to `weather_logs/` for verification:
- `weather_logs/YYYY-MM-DD_HH-MM-SS_<location>.json` - Raw wttr.in JSON
- `weather_logs/YYYY-MM-DD_HH-MM-SS_<location>_parsed.txt` - Human-readable parsed data
- `weather_logs/YYYY-MM-DD_HH-MM-SS_type.txt` - Weather type selected (explicit_only/both/mood_only)

```bash
# Check what weather was fetched
cat weather_logs/$(ls -t weather_logs/*.json | head -1)

# Check what type was selected
cat weather_logs/$(ls -t weather_logs/*_type.txt | head -1)

# Compare with prompt sent to AI
cat prompt-to-AI-logs/$(ls -t prompt-to-AI-logs/ | head -1)
```

#### Random Mode Distribution (mode=None)

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
├── commitment_parser.py          # Appointment creation from AI responses
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
│   ├── c4-weather_impulse.txt   # Weather mood-based impulses (component c4)
│   ├── c4_explicit_mention.txt  # Weather explicit mentions (component c4)
│   ├── appointment-triggered-openers.txt  # Dedicated openers for appointments ONLY
│   ├── library-X-*.txt          # Custom auto-discovered libraries
│   ├── SAMPLE-new_library.txt   # Sample format template
│   └── manage_library_guide.txt # Library customization guide
├── appointments/
│   ├── appointments.json        # Active appointments (user requests + AI proposals)
│   └── proactive_schedule.json  # Auto-generated monthly schedule
├── weather_logs/                 # Weather data logs (JSON + parsed + type)
├── prompt-to-AI-logs/           # AI prompt logs for cross-checking
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

**Note**: The old `SCHEDULER_INTERVAL_MINUTES` and `interval_seconds` settings are no longer used. Sebastian now uses dynamic sleep based on the next scheduled contact.

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
