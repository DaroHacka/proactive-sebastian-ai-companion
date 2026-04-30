"""
Sebastian Proactive Scheduler Module

Generates and manages monthly proactive schedule with:
- 70% days: 2-4 contacts (sparse)
- 30% days: 5-15 contacts (active)
- Special dates with extra contacts
- Activities by time of day
"""

import os
import json
import random
import logging
import requests
from datetime import datetime, timedelta, date
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PROACTIVE_SCHEDULE_FILE = "appointments/proactive_schedule.json"
SPECIAL_DATES_FILE = "appointments/special_dates.json"
VIBE_LIBRARY_DAY = "library/vibe_library_01.txt"
VIBE_LIBRARY_NIGHT = "library/vibe_library_02.txt"

# Vibe library cache
_vibe_library_day = None
_vibe_library_night = None


def load_vibe_library(filename):
    """Load vibe library from file and parse vibes."""
    vibes = []
    current_category = None
    
    if not os.path.exists(filename):
        logger.warning(f"Vibe library not found: {filename}")
        return []
    
    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines and headers
            if not line or line.startswith("###") or line.startswith("---"):
                continue
            
            # Check for category headers
            if "(" in line and ")" in line and not line.startswith("["):
                current_category = line.split("(")[0].strip()
                continue
            
            # Parse vibe lines
            if "[VIBE:" in line:
                # Extract vibe name and text properly (handles "1. **[VIBE: NAME]** text" format)
                import re
                match = re.search(r'\[VIBE: ([^\]]+)\]', line)
                if match:
                    vibe_name = match.group(1)
                    # Find the closing ] and get text after it
                    close_idx = line.rfind(']')
                    if close_idx >= 0:
                        vibe_text = line[close_idx+1:].strip()
                        # Clean up decorative ** markers
                        vibe_text = vibe_text.lstrip('* ')
                        vibes.append({
                            "name": vibe_name,
                            "text": vibe_text,
                            "category": current_category or "UNCATEGORIZED"
                        })
    
    return vibes


def get_vibes_for_time(hour):
    """Get appropriate vibes based on time of day.
    
    Returns day vibes (07:00-23:30) or night vibes (02:00-06:00).
    """
    global _vibe_library_day, _vibe_library_night
    
    # Load libraries if not cached
    if _vibe_library_day is None:
        _vibe_library_day = load_vibe_library(VIBE_LIBRARY_DAY)
    if _vibe_library_night is None:
        _vibe_library_night = load_vibe_library(VIBE_LIBRARY_NIGHT)
    
    # Return appropriate library based on hour
    if 2 <= hour < 6:
        return _vibe_library_night
    else:
        return _vibe_library_day


def get_random_vibe(hour=None):
    """Get a random vibe for the given hour (or current hour if None)."""
    if hour is None:
        hour = datetime.now().hour
    
    vibes = get_vibes_for_time(hour)
    if vibes:
        return random.choice(vibes)
    return None


def get_vibes_count(hour=None):
    """Get count of available vibes."""
    if hour is None:
        hour = datetime.now().hour
    vibes = get_vibes_for_time(hour)
    return len(vibes)


# ==================== DAY-OF-WEEK VIBE SYSTEM ====================

WEEK_DAYS_FILE = "library/week-days.txt"
LONGING_FILE = "library/weekend_longing_interaction.txt"

_week_days_cache = None
_longing_cache = None


def get_current_date_info():
    """Get current date info for vibe system.
    
    Returns: (date_str, day_name, is_weekend, days_to_weekend)
    - date_str: "Monday, April 27, 2026, 12:20 PM"
    - day_name: "monday" (lowercase)
    - is_weekend: True if Saturday/Sunday
    - days_to_weekend: 0-4 for weekdays, 0 for weekend
    """
    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y, %I:%M %p")  # "Monday, April 27, 2026, 12:20 PM"
    day_name = now.strftime("%A").lower()  # "monday"
    
    is_weekend = day_name in ['saturday', 'sunday']
    
    # Calculate days to weekend
    if is_weekend:
        days_to_weekend = 0
    else:
        # weekday() returns 0 for Monday, 4 for Friday
        days_to_weekend = 4 - now.weekday()  # Friday is 4
    
    return date_str, day_name, is_weekend, days_to_weekend


def load_week_days_vibes():
    """Load week-days.txt and parse into dict by day name."""
    global _week_days_cache
    
    if _week_days_cache is not None:
        return _week_days_cache
    
    _week_days_cache = {}
    current_day = None
    current_vibes = []
    
    if not os.path.exists(WEEK_DAYS_FILE):
        logger.warning(f"week-days.txt not found")
        return {}
    
    with open(WEEK_DAYS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines and Focus headers only (NOT Category - we need those!)
            if not line or line.startswith("Focus:"):
                continue
            
            # Detect day category header
            if "Category: " in line and "(" in line:
                # Save previous day
                if current_day and current_vibes:
                    _week_days_cache[current_day] = current_vibes
                
                # Parse new day - extract just the day name (monday, tuesday, etc.)
                category_part = line.split("(")[0].replace("Category:", "").strip()
                # Map category names to day names
                day_map = {
                    "MONDAY_MELANCHOLY": "monday",
                    "TUESDAY_EFFICIENCY": "tuesday",
                    "WEDNESDAY_HUMP_DAY": "wednesday",
                    "THURSDAY_THE_FINISHER": "thursday",
                    "FRIDAY_THE_RELEASE": "friday",
                    "SATURDAY_THE_PHILOSOPHER": "saturday",
                    "SUNDAY_REST_AND_REBOOT": "sunday",
                    "WEEKEND_TEMPORAL_LOGIC": "weekend",
                }
                current_day = day_map.get(category_part, category_part.lower())
                current_vibes = []
                continue
            
            # Detect separator
            if line.startswith("--"):
                continue
            
            # Parse vibe lines
            if "[VIBE:" in line:
                parts = line.split("]", 1)
                if len(parts) == 2:
                    vibe_name = parts[0].replace("[VIBE:", "").strip()
                    vibe_text = parts[1].strip()
                    current_vibes.append({
                        "name": vibe_name,
                        "text": vibe_text
                    })
    
    # Save last day
    if current_day and current_vibes:
        _week_days_cache[current_day] = current_vibes
    
    return _week_days_cache


def load_longing_intros():
    """Load weekend_longing_interaction.txt and parse into list."""
    global _longing_cache
    
    if _longing_cache is not None:
        return _longing_cache
    
    _longing_cache = []
    current_category = None
    
    if not os.path.exists(LONGING_FILE):
        logger.warning(f"weekend_longing_interaction.txt not found")
        return []
    
    with open(LONGING_FILE, "r") as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines and category headers
            if not line or "The " in line and "(" in line:
                continue
            
            # Only add lines that look like actual longing intros (contain quotes or {x})
            if ("\"" in line or "{" in line) and len(line) > 10:
                _longing_cache.append(line)
    
    return _longing_cache


def get_random_week_day_vibe(day_name):
    """Get a random vibe for the given day from week-days.txt."""
    vibes_dict = load_week_days_vibes()
    
    if day_name in vibes_dict and vibes_dict[day_name]:
        return random.choice(vibes_dict[day_name])
    
    return None


def get_random_longing_intro(days_to_weekend):
    """Get a random longing intro and format with days_to_weekend."""
    intros = load_longing_intros()
    
    if not intros:
        return None
    
    intro = random.choice(intros)
    
    # Replace {x} with days count
    if "{" in intro and "}" in intro:
        intro = intro.replace("{x}", str(days_to_weekend))
    
    return intro


def build_vibe_prompt(hour=None, mode=None):
    """Build the vibe string with optional layering.
    
    Modes:
    - mode=1: Vibe only (c1, no stacking)
    - mode=2: Vibe + week-days (c1+c2)
    - mode=3: All three layers (c1+c2+c3)
    - mode=4: Vibe + weather impulse (c1+c4) with 33%/33%/33% context distribution
    - mode=None: Random 33%/33%/34% for mode1/mode2/mode3
    
    Returns: "**[VIBE: NAME]** text. Today is April 27, 2026. Day note: "text" [longing] [weather]"
    """
    if hour is None:
        hour = datetime.now().hour
    
    # Level 1: Get date info (Anchor)
    date_str, day_name, is_weekend, days_to_weekend = get_current_date_info()
    
    # Level 3: Base vibe from vibe_library (always needed, c1)
    base_vibe = get_random_vibe(hour)
    if not base_vibe:
        return ""
    
    vibe_part = f"**[VIBE: {base_vibe['name']}]** {base_vibe['text']}"
    day_part = ""
    longing_part = ""
    
    if mode is None:
        # Random mode: 33%/33%/34% distribution
        if is_weekend:
            day_part = ""
            longing_part = ""
        else:
            roll = random.random()
            if roll < 0.33:
                # 33%: c1 only (mode1)
                day_part = ""
                longing_part = ""
            elif roll < 0.66:
                # 33%: c1+c2 (mode2)
                day_vibe = get_random_week_day_vibe(day_name)
                day_part = f". Today is {date_str}. Day note: \"{day_vibe['text']}\"" if day_vibe else ""
                longing_part = ""
            else:
                # 34%: c1+c2+c3 (mode3)
                day_vibe = get_random_week_day_vibe(day_name)
                longing = get_random_longing_intro(days_to_weekend)
                day_part = f". Today is {date_str}. Day note: \"{day_vibe['text']}\"" if day_vibe else ""
                longing_part = f" {longing}" if longing else ""
    elif mode == 1:
        # c1 only
        day_part = ""
        longing_part = ""
    elif mode == 2:
        # c1+c2
        day_vibe = get_random_week_day_vibe(day_name)
        day_part = f". Today is {date_str}. Day note: \"{day_vibe['text']}\"" if day_vibe else ""
        longing_part = ""
    elif mode == 3:
        # c1+c2+c3
        day_vibe = get_random_week_day_vibe(day_name)
        longing = get_random_longing_intro(days_to_weekend)
        day_part = f". Today is {date_str}. Day note: \"{day_vibe['text']}\"" if day_vibe else ""
        longing_part = f" {longing}" if longing else ""
    elif mode == 4:
        # c1+c4 (weather) with 33%/33%/33% context distribution
        weather_code, _, _ = get_current_weather()
        if weather_code:
            roll = random.random()
            context_parts = []
            
            if roll < 0.33:
                # 33%: Weather only (no context)
                context_str = None
                day_part = ""
            elif roll < 0.66:
                # 33%: Weather + c2 (day note)
                day_vibe = get_random_week_day_vibe(day_name)
                day_part = f". Today is {date_str}. Day note: \"{day_vibe['text']}\"" if day_vibe else ""
                if day_part:
                    context_parts.append(f"Day: {day_part}")
                context_str = ". ".join(context_parts) if context_parts else None
            else:
                # 34%: Weather + c1 + c2 (full context)
                context_parts.append(f"Vibe: {base_vibe['text']}")
                day_vibe = get_random_week_day_vibe(day_name)
                day_part = f". Today is {date_str}. Day note: \"{day_vibe['text']}\"" if day_vibe else ""
                if day_part:
                    context_parts.append(f"Day: {day_part}")
                context_str = ". ".join(context_parts) if context_parts else None
            
            impulse = get_weather_impulse(weather_code, context_str)
            if impulse:
                vibe_part += f" {impulse}"
            
            longing_part = ""
        else:
            # No weather data, fallback to c1 only
            day_part = ""
            longing_part = ""
    else:
        # Invalid mode, default to c1 only
        day_part = ""
        longing_part = ""
    
    return f"{vibe_part}{day_part}{longing_part}"


# Activity categories
ACTIVITIES = {
    "BREAKFAST": {"hours": (7, 9), "mood": "CHEERFUL", "prompts": [
        "What are you having for breakfast?",
        "How's your morning going?",
        "Any exciting plans today?"
    ]},
    "MORNING": {"hours": (9, 12), "mood": "NEUTRAL", "prompts": [
        "How's your morning going?",
        "Any progress on your project?",
        "What's keeping you busy?"
    ]},
    "LUNCH": {"hours": (12, 14), "mood": "FRIENDLY", "prompts": [
        "What are you having for lunch?",
        "How's your lunch break?",
        "Any interesting lunch plans?"
    ]},
    "AFTERNOON": {"hours": (14, 18), "mood": "CASUAL", "prompts": [
        "How's your afternoon?",
        "Taking any breaks today?",
        "What's happening?"
    ]},
    "EVENING": {"hours": (18, 21), "mood": "WARM", "prompts": [
        "What are you up to tonight?",
        "Any evening plans?",
        "How's your evening going?"
    ]},
    "NIGHT": {"hours": (21, 24), "mood": "RELAXED", "prompts": [
        "Anything exciting happening?",
        "Wind down for the night?",
        "How's your evening?"
    ]},
    "LATE_NIGHT": {"hours": (0, 6), "mood": "CONCERNED", "prompts": [
        "You still up? Everything okay?",
        "Late night - you okay?",
        "What's keeping you up?"
    ]}
}

# Special activity prompts
SPECIAL_ACTIVITIES = {
    "CHRISTMAS": {"mood": "FESTIVE", "prompts": [
        "Merry Christmas! 🎄 Any festive plans?",
        "It's Christmas! How are you celebrating?",
        "Christmas Day! Any traditions this year?"
    ]},
    "NEW_YEAR": {"mood": "EXCITED", "prompts": [
        "Happy New Year! 🎉 Any resolutions?",
        "New Year's Eve! Any plans?",
        "Last day of the year! How's it going?"
    ]},
    "BIRTHDAY": {"mood": "EXCITED", "prompts": [
        "It's a special day! 🎂 Any plans?",
        "Happy birthday to them! How are you celebrating?",
        "Special occasion! Any fun plans?"
    ]},
    "HOLIDAY": {"mood": "RELAXED", "prompts": [
        "Holiday! Any plans?",
        "Nice to have a day off! What's up?",
        "Holiday vibes! How are you spending it?"
    ]}
}


def load_special_dates():
    """Load special dates from file."""
    if os.path.exists(SPECIAL_DATES_FILE):
        with open(SPECIAL_DATES_FILE, "r") as f:
            return json.load(f)
    return {"special_dates": [], "user_dates": []}


def get_activity_by_hour(hour):
    """Map hour to activity category."""
    for activity, info in ACTIVITIES.items():
        start, end = info["hours"]
        if start <= hour < end:
            return activity
    return "NIGHT"


def get_activity_prompt(activity, special_activity=None):
    """Get a random prompt for activity."""
    # Special activity takes priority
    if special_activity and special_activity in SPECIAL_ACTIVITIES:
        prompts = SPECIAL_ACTIVITIES[special_activity]["prompts"]
        return random.choice(prompts)
    
    # Regular activity
    if activity in ACTIVITIES:
        prompts = ACTIVITIES[activity]["prompts"]
        return random.choice(prompts)
    
    return "How are you doing?"


def get_mood(activity, special_activity=None):
    """Get mood for activity."""
    if special_activity and special_activity in SPECIAL_ACTIVITIES:
        return SPECIAL_ACTIVITIES[special_activity]["mood"]
    
    if activity in ACTIVITIES:
        return ACTIVITIES[activity]["mood"]
    
    return "NEUTRAL"


def is_special_date(day_date):
    """Check if date is special and return special info if so."""
    special_dates = load_special_dates()
    date_str = day_date.isoformat()
    
    # Check both official and user dates
    for date_entry in special_dates.get("special_dates", []) + special_dates.get("user_dates", []):
        if date_entry.get("date") == date_str:
            return date_entry
    
    return None


def generate_daily_contacts(day_date):
    """Generate number of contacts for a day.
    
    Distribution:
    - 70% of days: 2-4 contacts (sparse)
    - 30% of days: 5-15 contacts (active)
    """
    # Check for special date
    special = is_special_date(day_date)
    
    if special:
        # Special date - use extra_contacts
        return special.get("extra_contacts", 5), special.get("activity", "HOLIDAY")
    
    # Random day
    if random.random() < 0.30:
        # 30% - active day (5-15 contacts)
        return random.randint(5, 15), None
    else:
        # 70% - sparse day (2-4 contacts)
        return random.randint(2, 4), None


def generate_monthly_schedule(year, month):
    """Generate a full month's proactive schedule.
    
    Only includes contacts from TODAY onwards (not past dates).
    """
    today = date.today()
    
    # Handle month overflow
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    
    schedule = []
    contact_id = 1
    
    # Start from either today or first of month, whichever is later
    current_day = max(today, date(year, month, 1))
    
    while current_day <= last_day:
        # Skip Sundays (0 = Sunday in weekday())
        if current_day.weekday() != 6:
            num_contacts, special_activity = generate_daily_contacts(current_day)
            
            # Generate contact times distributed throughout the day
            # Only generate if the day is today or future
            if num_contacts > 0:
                # First contact time - if today, start from current hour + buffer
                if current_day == today:
                    current_hour = now.hour + 1
                    if current_hour < 9:
                        current_hour = 9
                    first_hour = random.randint(current_hour, 21)
                else:
                    first_hour = random.randint(9, 21)
                
                if first_hour < 22:  # 10 PM
                    first_minute = random.randint(0, 59)
                    contact_time = datetime(
                        current_day.year, current_day.month, current_day.day,
                        first_hour, first_minute
                    )
                    
                    schedule.append({
                        "id": contact_id,
                        "due": contact_time.isoformat(),
                        "activity": get_activity_by_hour(first_hour),
                        "status": "pending"
                    })
                    contact_id += 1
                    num_contacts -= 1
            
            # Remaining contacts
            while num_contacts > 0:
                hour = random.randint(12, 21)
                minute = random.randint(0, 59)
                contact_time = datetime(
                    current_day.year, current_day.month, current_day.day,
                    hour, minute
                )
                
                # Skip if too close to existing (30 min gap) or in the past (if today)
                too_close = False
                for existing in schedule:
                    existing_dt = datetime.fromisoformat(existing["due"])
                    if abs((contact_time - existing_dt).total_seconds()) < 1800:
                        too_close = True
                        break
                
                if current_day == today and contact_time <= datetime.now():
                    pass  # Skip past times today
                elif not too_close:
                    schedule.append({
                        "id": contact_id,
                        "due": contact_time.isoformat(),
                        "activity": get_activity_by_hour(hour),
                        "status": "pending"
                    })
                    contact_id += 1
                    num_contacts -= 1
                
                # Safety break
                if contact_id > 500:
                    break
        
        current_day += timedelta(days=1)
    
    # Sort by due time
    schedule.sort(key=lambda x: x["due"])
    
    # Calculate stats
    total = len(schedule)
    month_str = f"{year}-{month:02d}"
    
    # Build result
    result = {
        "month": month_str,
        "generated_at": datetime.now().isoformat(),
        "schedule": schedule,
        "next_contact": None,
        "stats": {
            "total": total,
            "pending": total,
            "completed": 0,
            "skipped": 0
        }
    }
    
    # Set next contact
    if schedule:
        result["next_contact"] = {
            "id": schedule[0]["id"],
            "due": schedule[0]["due"]
        }
    
    return result


def load_proactive_schedule():
    """Load existing proactive schedule."""
    if os.path.exists(PROACTIVE_SCHEDULE_FILE):
        with open(PROACTIVE_SCHEDULE_FILE, "r") as f:
            return json.load(f)
    return None


def save_proactive_schedule(schedule_data):
    """Save proactive schedule to file."""
    with open(PROACTIVE_SCHEDULE_FILE, "w") as f:
        json.dump(schedule_data, f, indent=2)


def initialize_proactive_schedule():
    """Initialize new monthly schedule if needed."""
    now = datetime.now()
    
    # Check if we need new schedule
    existing = load_proactive_schedule()
    
    if existing:
        # Check if current month
        current_month = f"{now.year}-{now.month:02d}"
        if existing.get("month") == current_month:
            logger.info(f"Proactive schedule for {current_month} already exists")
            return existing
    
    # Generate new schedule
    logger.info(f"Generating new proactive schedule for {now.year}-{now.month:02d}")
    new_schedule = generate_monthly_schedule(now.year, now.month)
    save_proactive_schedule(new_schedule)
    
    return new_schedule


def get_next_proactive_contact():
    """Get the next proactive contact that's due now or in the past."""
    schedule = load_proactive_schedule()
    
    if not schedule:
        return None
    
    now = datetime.now()
    updated = False
    
    # Find next pending contact that's due (must be due now or overdue)
    for contact in schedule.get("schedule", []):
        if contact["status"] == "pending":
            due = datetime.fromisoformat(contact["due"])
            # Only return if actually due now or overdue
            if due <= now:
                return contact
    
    return None


def get_all_due_proactive_contacts():
    """Get ALL proactive contacts that are due now or overdue."""
    schedule = load_proactive_schedule()
    
    if not schedule:
        return []
    
    now = datetime.now()
    due_contacts = []
    
    for contact in schedule.get("schedule", []):
        if contact["status"] == "pending":
            due = datetime.fromisoformat(contact["due"])
            if due <= now:
                due_contacts.append(contact)
    
    return due_contacts
    
    now = datetime.now()
    updated = False
    
    # Find next pending contact that's due (must be due now or in the past)
    for contact in schedule.get("schedule", []):
        if contact["status"] == "pending":
            due = datetime.fromisoformat(contact["due"])
            # Only return if actually due now or overdue
            if due <= now:
                return contact
    
    return None


def complete_proactive_contact(contact_id):
    """Mark a proactive contact as completed."""
    schedule = load_proactive_schedule()
    
    if not schedule:
        return False
    
    for contact in schedule.get("schedule", []):
        if contact["id"] == contact_id:
            contact["status"] = "completed"
            schedule["stats"]["completed"] = schedule["stats"].get("completed", 0) + 1
            schedule["stats"]["pending"] = schedule["stats"].get("pending", 1) - 1
            break
    
    # Update next_contact
    schedule["next_contact"] = None
    for contact in schedule.get("schedule", []):
        if contact["status"] == "pending":
            schedule["next_contact"] = {
                "id": contact["id"],
                "due": contact["due"]
            }
            break
    
    save_proactive_schedule(schedule)
    return True


def skip_proactive_contact(contact_id):
    """Skip a proactive contact."""
    schedule = load_proactive_schedule()
    
    if not schedule:
        return False
    
    for contact in schedule.get("schedule", []):
        if contact["id"] == contact_id:
            contact["status"] = "skipped"
            schedule["stats"]["skipped"] = schedule["stats"].get("skipped", 0) + 1
            schedule["stats"]["pending"] = schedule["stats"].get("pending", 1) - 1
            break
    
    # Update next_contact
    schedule["next_contact"] = None
    for contact in schedule.get("schedule", []):
        if contact["status"] == "pending":
            schedule["next_contact"] = {
                "id": contact["id"],
                "due": contact["due"]
            }
            break
    
    save_proactive_schedule(schedule)
    return True


def get_proactive_status():
    """Get proactive schedule status."""
    schedule = load_proactive_schedule()
    
    if not schedule:
        return None
    
    return {
        "month": schedule.get("month"),
        "stats": schedule.get("stats", {}),
        "next": schedule.get("next_contact")
    }


# ==================== WEATHER FUNCTIONS ====================

# Weather code to category mapping (from wttr.in constants.py)
WEATHER_CODE_MAP = {
    # Fine Day (Sunny/Clear)
    113: "fine",  # Sunny
    116: "fine",  # Partly Sunny
    
    # Neutral Day (Cloudy/Overcast)
    119: "neutral",  # Cloudy
    122: "neutral",  # Very Cloudy
    143: "low_mood",  # Fog
    248: "low_mood",  # Fog
    260: "low_mood",  # Fog
    
    # Caution Day (Windy)
    # Check wind speed in weather data for "windy" category
    
    # Wet Day (Light Rain)
    176: "wet",  # Light Showers
    263: "wet",  # Light Showers
    266: "wet",  # Light Rain
    293: "wet",  # Light Rain
    296: "wet",  # Light Rain
    
    # Bad Weather Day (Heavy Rain)
    299: "bad",  # Heavy Showers
    302: "bad",  # Heavy Rain
    305: "bad",  # Heavy Showers
    308: "bad",  # Heavy Rain
    
    # Dangerous Day (Thunderstorm)
    200: "dangerous",  # Thundery Showers
    386: "dangerous",  # Thundery Showers
    389: "dangerous",  # Thundery Heavy Rain
    
    # Cold Day (Snow)
    227: "cold",  # Light Snow
    230: "cold",  # Heavy Snow
    320: "cold",  # Light Snow
    323: "cold",  # Light Snow Showers
    326: "cold",  # Light Snow Showers
    329: "cold",  # Heavy Snow
    332: "cold",  # Heavy Snow
    335: "cold",  # Heavy Snow Showers
    338: "cold",  # Heavy Snow Showers
}

WEATHER_CATEGORY_FREQ = {
    "fine": 0.1,      # 10% chance to mention
    "neutral": 0.3,  # 30% chance
    "low_mood": 0.3,  # 30% chance
    "wet": 0.4,       # 40% chance
    "bad": 0.6,      # 60% chance
    "dangerous": 0.7,  # 70% chance
    "cold": 0.5,      # 50% chance
}


def fetch_weather_from_wttr(location=None, format="j1"):
    """Fetch weather from wttr.in.
    
    Args:
        location: city name, GPS coords, etc. (default: auto-detect from IP)
        format: j1=JSON, 1=one-line, etc.
    Returns: JSON dict or None
    """
    if location is None:
        location = os.getenv("WEATHER_LOCATION", "Paris")
    
    try:
        response = requests.get(
            f"https://wttr.in/{location}?format={format}",
            timeout=5
        )
        return response.json()
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return None


def get_current_weather(location=None):
    """Get current weather code, description, and temp.
    
    Returns: (weather_code, description, temp_C) or (None, None, None)
    """
    data = fetch_weather_from_wttr(location, format="j1")
    if not data:
        return None, None, None
    
    try:
        current = data["current_condition"][0]
        weather_code = int(current["weatherCode"])
        desc = current["weatherDesc"][0]["value"]
        temp = int(current["temp_C"])
        return weather_code, desc, temp
    except (KeyError, IndexError, ValueError) as e:
        logger.warning(f"Weather parse error: {e}")
        return None, None, None


def get_weather_category(weather_code):
    """Map weather code to category."""
    return WEATHER_CODE_MAP.get(weather_code, "neutral")


def get_weather_probability(weather_code=None):
    """Get probability of including weather impulse.
    
    Higher for bad weather, lower for fine weather.
    Returns: float between 0.0 and 1.0
    """
    if weather_code is None:
        return 0.0
    
    category = get_weather_category(weather_code)
    return WEATHER_CATEGORY_FREQ.get(category, 0.3)


def get_weather_impulse(weather_code=None, context_str=None):
    """Get weather impulse from library/c4-weather_impulse.txt.
    
    Args:
        weather_code: wttr.in weather code
        context_str: Optional context from c1 (vibe) or c2 (day note)
    
    Returns: random line from appropriate section, or None
    """
    if weather_code is None:
        return None
    
    category = get_weather_category(weather_code)
    
    # Map category to section name in file
    section_map = {
        "fine": "Fine Day (Sunny / Clear)",
        "neutral": "Cloudy / Neutral Day",
        "low_mood": "Fog / Low‑Mood Day",
        "wet": "Rainy / Wet Day",
        "bad": "Rainy / Wet Day",  # Same as wet
        "dangerous": "Storm / Dangerous Day",
        "cold": "Snow / Cold Day",
        "windy": "Windy / Caution Day",
    }
    
    section_name = section_map.get(category)
    if not section_name:
        return None
    
    try:
        with open("library/c4-weather_impulse.txt", "r") as f:
            lines = f.readlines()
        
        # Find section start and end (handle missing space after ###)
        start = None
        end = None
        
        expected_header = f"### {section_name} — Weather Impulse Library"
        expected_header_no_space = f"###{section_name} — Weather Impulse Library"
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped == expected_header or line_stripped == expected_header_no_space:
                start = i + 1  # Skip header
            elif start is not None and line_stripped.startswith("###"):
                end = i
                break
        
        if start is None:
            return None
        
        if end is None:
            end = len(lines)
        
        # Extract lines from section
        section_lines = lines[start:end]
        valid_lines = [
            l.strip() for l in section_lines 
            if l.strip() and not l.strip().startswith("#")
        ]
        
        if valid_lines:
            import random
            impulse = random.choice(valid_lines)
            
            # Append context if provided (c1 or c2)
            if context_str:
                return f"{impulse} {context_str}"
            return impulse
    except Exception as e:
        logger.warning(f"Weather impulse error: {e}")
    
    return None
    
    category = get_weather_category(weather_code)
    
    # Map category to section name in file
    section_map = {
        "fine": "Fine Day (Sunny / Clear)",
        "neutral": "Cloudy / Neutral Day",
        "low_mood": "Fog / Low-Mood Day",
        "wet": "Rainy / Wet Day",
        "bad": "Rainy / Wet Day",  # Same as wet
        "dangerous": "Storm / Dangerous Day",
        "cold": "Snow / Cold Day",
    }
    
    section_name = section_map.get(category)
    if not section_name:
        return None
    
    try:
        with open("library/c4-weather_impulse.txt", "r") as f:
            lines = f.readlines()
        
        # Find section start and end
        start = None
        end = None
        
        for i, line in enumerate(lines):
            if line.strip() == f"###{section_name} — Weather Impulse Library":
                start = i + 1  # Skip header
            elif start is not None and line.startswith("###"):
                end = i
                break
        
        if start is None:
            return None
        
        if end is None:
            end = len(lines)
        
        # Extract lines from section
        section_lines = lines[start:end]
        valid_lines = [
            l.strip() for l in section_lines 
            if l.strip() and not l.strip().startswith("#")
        ]
        
        if valid_lines:
            return random.choice(valid_lines)
    except Exception as e:
        logger.warning(f"Weather impulse error: {e}")
    
    return None
    
    category = get_weather_category(weather_code)
    
    # Map category to section name in file (exact from file)
    section_map = {
        "fine": "Fine Day (Sunny / Clear)",
        "neutral": "Cloudy / Neutral Day",
        "low_mood": "Fog / Low-Mood Day",
        "wet": "Rainy / Wet Day",
        "bad": "Rainy / Wet Day",  # Same as wet
        "dangerous": "Storm / Dangerous Day",
        "cold": "Snow / Cold Day",
    }
    
    section_name = section_map.get(category)
    if not section_name:
        return None
    
    try:
        with open("library/c4-weather_impulse.txt", "r") as f:
            content = f.read()
        
        # Find section by header
        import re
        # Pattern: ### Section Name — Weather Impulse Library\n...\n### or end
        escaped = re.escape(section_name)
        pattern = rf"### {escaped} — Weather Impulse Library\n(.*?)(?=###|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            section = match.group(1)
            lines = [line.strip() for line in section.split("\n") 
                      if line.strip() and not line.strip().startswith("#")]
            if lines:
                return random.choice(lines)
    except Exception as e:
        logger.warning(f"Weather impulse error: {e}")
    
    return None
    
    category = get_weather_category(weather_code)
    
    # Map category to section name in file (exact match from file)
    section_map = {
        "fine": "Fine Day (Sunny / Clear)",
        "neutral": "Cloudy / Neutral Day",
        "low_mood": "Fog / Low-Mood Day",
        "wet": "Rainy / Wet Day",
        "bad": "Rainy / Wet Day",  # Same as wet
        "dangerous": "Storm / Dangerous Day",
        "cold": "Snow / Cold Day",
    }
    
    section_name = section_map.get(category)
    if not section_name:
        return None
    
    try:
        with open("library/c4-weather_impulse.txt", "r") as f:
            content = f.read()
        
        # Find section: ### Section Name — Weather Impulse Library
        import re
        # Escape the section name for regex
        escaped = re.escape(section_name)
        pattern = rf"### {escaped}.*?— Weather Impulse Library\n(.*?)(?=###|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            section = match.group(1)
            lines = [line.strip() for line in section.split("\n") 
                      if line.strip() and not line.strip().startswith("#")]
            if lines:
                return random.choice(lines)
    except Exception as e:
        logger.warning(f"Weather impulse error: {e}")
    
    return None


# Auto-initialize on module load
if __name__ != "__main__":
    try:
        initialize_proactive_schedule()
    except Exception as e:
        logger.warning(f"Could not initialize proactive schedule: {e}")