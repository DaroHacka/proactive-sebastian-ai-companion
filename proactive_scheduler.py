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
    now = datetime.now()  # This line MUST be indented
    date_str = now.strftime("%A, %B %d, %Y, %I:%M %p")
    day_name = now.strftime("%A").lower()
    
    is_weekend = day_name in ['saturday', 'sunday']
    
    # Calculate days to weekend
    if is_weekend:
        days_to_weekend = 0
    else:
        # weekday() returns 0 for Monday, 4 for Friday
        days_to_weekend = 4 - now.weekday()
    
    return date_str, day_name, is_weekend, days_to_weekend

def initialize_proactive_schedule():
    """Initialize new monthly schedule if needed."""
    now = datetime.now()
    
    try:
        import toml
        with open("config/config.toml") as f:
            config = toml.load(f)
            current_freq = config.get("schedule", {}).get("frequency", 3)
    except:
        current_freq = 3
    
    existing = load_proactive_schedule()
    
    if existing:
        current_month = f"{now.year}-{now.month:02d}"
        existing_month = existing.get("month")
        existing_freq = existing.get("config", {}).get("frequency", 3)
        
        if existing_month == current_month and existing_freq == current_freq:
            return existing
    
    new_schedule = generate_monthly_schedule(now.year, now.month)
    new_schedule["config"] = {"frequency": current_freq}
    save_proactive_schedule(new_schedule)
    return new_schedule

def get_next_proactive_contact():
    """Get the next scheduled contact that hasn't happened yet."""
    schedule = load_proactive_schedule()
    if not schedule or "contacts" not in schedule:
        return None
        
    now = datetime.now()
    contacts = schedule.get("contacts", [])
    
    for contact in contacts:
        if not contact.get("completed"):
            contact_time = datetime.fromisoformat(contact["scheduled_at"])
            if now >= contact_time:
                return contact
    return None

def get_vibe_check_instruction():
    """Return the system instruction for a proactive vibe check."""
    return "This is a proactive vibe check. Reach out to the user naturally."

def get_all_due_proactive_contacts():
    """Get all scheduled contacts that are due or overdue."""
    schedule = load_proactive_schedule()
    if not schedule or "contacts" not in schedule:
        return []
        
    now = datetime.now()
    due_contacts = []
    
    for contact in schedule.get("contacts", []):
        if not contact.get("completed"):
            contact_time = datetime.fromisoformat(contact["scheduled_at"])
            if now >= contact_time:
                due_contacts.append(contact)
                
    return due_contacts

def complete_proactive_contact(contact_id):
    """Mark a specific contact as completed in the schedule."""
    schedule = load_proactive_schedule()
    if not schedule or "contacts" not in schedule:
        return False
        
    updated = False
    for contact in schedule.get("contacts", []):
        if contact.get("id") == contact_id:
            contact["completed"] = True
            contact["completed_at"] = datetime.now().isoformat()
            updated = True
            break
            
    if updated:
        save_proactive_schedule(schedule)
        logger.info(f"Marked proactive contact {contact_id} as completed")
        return True
        
    return False
