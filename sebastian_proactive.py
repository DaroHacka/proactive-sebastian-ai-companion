#!/usr/bin/env python3
"""
Sebastian - Proactive AI Companion
ASYNCIO VERSION - Event-driven with heartbeat architecture

This version replaces threading with asyncio for:
- Concurrent task monitoring (vibe, appointments, proactive)
- Non-blocking user input
- Event-driven triggers instead of polling
"""

import os
import json
import asyncio
import random
import requests
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from intent_manager import get_random_intent

# Load .env FIRST to get defaults
load_dotenv()

# Try to load config.toml for startup defaults, fallback to .env values
try:
    from config.config_manager import is_proactive_on_startup, is_appointment_on_startup, is_proactive_on_launch
    PROACTIVE_DEFAULT = is_proactive_on_startup()
    PROACTIVE_LAUNCH = is_proactive_on_launch()
    APPOINTMENT_DEFAULT = is_appointment_on_startup()
except ImportError:
    # Fallback to .env values if config not available
    PROACTIVE_DEFAULT = True
    PROACTIVE_LAUNCH = True
    APPOINTMENT_DEFAULT = True

TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
PROACTIVE_MODE = os.getenv("PROACTIVE_MODE", "true" if PROACTIVE_LAUNCH else "false").lower() == "true"

# ==================== LOGGING ====================
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Create handlers with different levels
_file_handler = logging.FileHandler(os.path.join(LOG_DIR, "sebastian.log"))
_file_handler.setLevel(logging.DEBUG)  # Keep ALL messages in file

_stream_handler = logging.StreamHandler()
_stream_handler.setLevel(logging.WARNING)  # Only WARNING+ on screen

_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
_file_handler.setFormatter(_formatter)
_stream_handler.setFormatter(_formatter)

# Get logger and add handlers
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(_file_handler)
logger.addHandler(_stream_handler)
logger.propagate = False  # Prevent duplicate messages

# ==================== CONFIG ====================
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("COMPANION_MODEL", "phi4")
MEMORY_DIR = "memory"
PROMPT_LOG_DIR = "prompt-to-AI-logs"
STATE_FILE = "state.json"
LAST_INTERACTION_FILE = "last_interaction.json"
CONVERSATION_DIR = "conversation"
if not os.path.exists(CONVERSATION_DIR):
    os.makedirs(CONVERSATION_DIR)
APPOINTMENTS_FILE = "appointments/appointments.json"
MAX_MEMORY_ENTRIES = int(os.getenv("MAX_MEMORY_ENTRIES", "50"))
ARCHIVE_THRESHOLD = int(os.getenv("ARCHIVE_THRESHOLD", "30"))

# Schedule scheduler to import after load_dotenv
import scheduler as sched_module
from time_parser import parse_response_for_time
from cue_manager import get_random_cue

# Add config path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'config'))

try:
    from ollama_params_manager import restore_defaults, load_ollama_params
except:
    def restore_defaults(): return False
    def load_ollama_params(): return {}


try:
    from config_manager import (
        get_user_name, 
        get_combo_trigger_chance, 
        is_combo_on_user_message,
        get_ai_timeout,
        validate_schedule_percentages,
        select_combo_mathematical,
    )
except ImportError:
    def get_user_name():
        return "Elias"
    def get_combo_trigger_chance():
        return 0.20
    def is_combo_on_user_message():
        return True
    def get_ai_timeout():
        return 600
    def validate_schedule_percentages(*args):
        return 0.30, 0.70, False, None
    def select_combo_mathematical():
        return "a_c"
from proactive_scheduler import (
    initialize_proactive_schedule,
    get_next_proactive_contact,
    get_all_due_proactive_contacts,
    complete_proactive_contact,
    get_proactive_status,
    load_vibe_library,
    get_random_vibe,
    build_vibe_prompt,
    get_current_date_info,
)

# ==================== LIBRARY MANAGER ====================
from library_manager import (
    get_normal_libraries,
    get_special_libraries,
    get_loader,
)

# Auto-generated from library_manager.LIBRARIES
# COMBINATION_WEIGHTS no longer used - using mathematical system now

SYSTEM_PROMPT = """You are Sebastian, an AI companion to Elias. Speak naturally, keep responses short."""

# Load prompt template from file
PROMPT_TEMPLATE_FILE = "config/prompt_template.txt"
_template_cache = {}

def load_prompt_template():
    """Load prompt template components from file."""
    global _template_cache
    if _template_cache:
        return _template_cache
    
    try:
        if os.path.exists(PROMPT_TEMPLATE_FILE):
            with open(PROMPT_TEMPLATE_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        _template_cache[key.strip()] = value.strip()
    except:
        pass
    
    # Apply dynamic user name substitution
    user_name = get_user_name()
    for key in _template_cache:
        _template_cache[key] = _template_cache[key].replace("{USER_NAME}", user_name)
    
    return _template_cache
    

def get_relative_time_phrase(seconds):
    """Convert seconds to relative time phrase from appointment-triggered-openers.txt.
    
    Uses the [Relative-Time Phrase Library] section.
    Returns phrase like "earlier today", "yesterday", "a couple of days ago", etc.
    """
    try:
        with open("library/appointment-triggered-openers.txt", "r") as f:
            content = f.read()
        
        # Find [Relative-Time Phrase Library] section
        marker = "[Relative-Time Phrase Library]"
        if marker not in content:
            return "when we talked"  # Fallback
        
        section = content.split(marker)[1].split("###")[0]
        
        # Parse categories (format: "1. Minutes Ago (0-59 min) | phrase1 | phrase2 | ...")
        current_range = None
        for line in section.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Check if this is a category definition (starts with number)
            if line[0].isdigit() and ". " in line:
                # Parse time range
                category_line = line.split("|")[0].strip()
                # Extract range like "0-59 min"
                import re
                range_match = re.search(r'(\d+)\s*-\s*(\d+)\s*min', category_line)
                if range_match:
                    min_sec = int(range_match.group(1)) * 60
                    max_sec = int(range_match.group(2)) * 60
                    if min_sec <= seconds < max_sec:
                        # Found our category - extract phrases
                        phrases_part = line.split("|", 1)[1] if "|" in line else ""
                        phrases = [p.strip().strip('"') for p in phrases_part.split("|")]
                        import random
                        return random.choice([p for p in phrases if p])
            elif line and line[0] not in "0123456789" and line not in ["|", "-", " "]:
                # This might be a phrase line for current category
                pass
        
        return "when we talked"  # Fallback
    except Exception as e:
        logger.error(f"Error reading appointment-triggered-openers.txt: {e}")
        return "when we talked"


def get_random_appointment_opener(relative_time):
    """Get random opener from appointment-triggered-openers.txt.
    
    Reads lines directly from the file, skipping headers/comments.
    Replaces any [APPOINTMENT_TIME] placeholder with relative_time.
    Returns ready-to-use opener string.
    """
    try:
        with open("library/appointment-triggered-openers.txt", "r") as f:
            lines = f.readlines()
        
        # Extract openers (non-empty lines that aren't headers/comments)
        openers = []
        for line in lines:
            line = line.strip()
            # Skip empty lines, headers (###), comments (#), and section markers
            if not line or line.startswith("#") or line.startswith("###") or line.startswith("---"):
                continue
            # Skip lines that are just descriptions/instructions
            if line.startswith('"') and line.endswith('"'):
                # Quoted format (if any)
                openers.append(line[1:-1])
            elif line and not line.startswith("(") and not line.startswith("Use ") and not line.startswith("All "):
                # Regular line - could be an opener
                # Check if it looks like an opener (starts with common words)
                if any(line.lower().startswith(w) for w in ["hey", "hi", "hello", "guess", "surprise", "knock", "i'm", "i am", "just", "you", "this", "here"]):
                    openers.append(line)
        
        if openers:
            opener = random.choice(openers)
            # Replace [APPOINTMENT_TIME] with relative_time
            opener = opener.replace("[APPOINTMENT_TIME]", relative_time)
            return opener
    
    except Exception as e:
        logger.error(f"Error reading appointment-triggered-openers.txt: {e}")
    
    # Fallback
    return f"I'm here as we planned {relative_time}"


async def parse_and_schedule(response, user_msg=""):
    """Parse AI response for commitments and create appointment if found."""
    try:
        from commitment_parser import create_appointment
        
        # Determine source
        if "library f" in user_msg.lower():
            source = "library_f"
        elif user_msg.startswith("trigger"):
            source = "ai_proposal"
        else:
            source = "user_request"
        
        appointment = create_appointment(response, user_msg, source)
        
        if appointment:
            # Load existing data
            if os.path.exists("appointments/appointments.json"):
                with open("appointments/appointments.json") as fp:
                    data = json.load(fp)
            else:
                data = {"appointments": [], "random_check": {}}
            
            # Add new appointment
            data["appointments"].append(appointment)
            
            # Save
            with open("appointments/appointments.json", "w") as fp:
                json.dump(data, fp, indent=2)
            
            due_dt = datetime.fromisoformat(appointment["due"])
            print(f"\n[Scheduled: {appointment.get('description', 'check-in')} at {due_dt.strftime('%H:%M')}]")
    except Exception as e:
        print(f"[Error scheduling: {e}]")


def get_random_appointment_proposal():
    """Load random phrase from library-f, add time reference (4-8 hours later)."""
    import random
    from datetime import datetime, timedelta
    
    # Find library-f file
    import glob
    files = glob.glob("library/library-f-*.txt")
    
    if not files:
        return None
    
    # Pick random file (usually just one)
    chosen_file = random.choice(files)
    
    with open(chosen_file, "r") as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    
    if not lines:
        return None
    
    phrase = random.choice(lines)
    
    # Calculate future time (4-8 hours later)
    now = datetime.now()
    hours_later = random.randint(4, 8)
    future_time = now + timedelta(hours=hours_later)
    time_str = future_time.strftime("%-I:%M %p")  # e.g., "4:30 PM"
    
    # Add time reference to phrase
    if "?" in phrase:
        # Append time to question
        return f"{phrase} Maybe around {time_str}?"
    else:
        # Add time in parentheses
        return f"{phrase} (around {time_str})"


def create_appointment_from_commitment(appointment_data, due_iso, user_msg=""):
    """Create an appointment entry from parsed commitment data.
    
    Args:
        appointment_data: Dict from parse_response_for_appointment()
        due_iso: ISO format datetime string
        user_msg: Original user message (for context)
    """
    try:
        # Load current appointments
        with open(APPOINTMENTS_FILE, "r") as f:
            appt_data = json.load(f)
        
        if "appointments" not in appt_data:
            appt_data["appointments"] = []
        
        # Get source
        source = appointment_data.get("source", "user_request")
        
        # Build description
        description = appointment_data.get("description", "")
        if not description:
            description = appointment_data.get("natural_text", "Scheduled check-in")
        
        # Add user message context if available
        if user_msg:
            description = f"{description} (from: '{user_msg[:50]}...')"
        
        # Create new appointment
        new_appt = {
            "id": f"appt_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "type": "commitment",
            "created_at": datetime.now().isoformat(),
            "source": source,
            "description": description,
            "due": due_iso,
            "status": "pending"
        }
        
        appt_data["appointments"].append(new_appt)
        
        # Save back
        with open(APPOINTMENTS_FILE, "w") as f:
            json.dump(appt_data, f, indent=2)
        
        logger.info(f"Created appointment {new_appt['id']} from commitment: {description}")
        return new_appt["id"]
    
    except Exception as e:
        logger.error(f"Failed to create appointment from commitment: {e}")
        return None


def select_combination():
    """Select combo using mathematical system."""
    return select_combo_mathematical()


def save_prompt_to_log(prompt, source):
    if not os.path.exists(PROMPT_LOG_DIR):
        os.makedirs(PROMPT_LOG_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"{PROMPT_LOG_DIR}/prompt_{timestamp}_{source}.txt", "w") as f:
        f.write(prompt)


def load_conversations():
    for f in ["fresh.json"]:
        path = os.path.join(MEMORY_DIR, f)
        if os.path.exists(path):
            with open(path) as fp:
                return json.load(fp)
    return []


def build_combinatorial_prompt(context_str=None, hour=None, combo=None, mode=None, appointment_mode=False):
    if hour is None:
        hour = datetime.now().hour
    if context_str is None:
        context_str = "Activity: general chat"
    
    # If appointment_mode, skip combo entirely
    if appointment_mode:
        combo = None
    # NOTE: If combo is None, don't auto-select - caller decides
    # This allows normal user messages to have NO combo components
    
    # Load template
    template = load_prompt_template()
    
    # Get date for explicit instructions
    date_str, _, _, _ = get_current_date_info()
    
    # Get identity and style from template (with fallbacks)
    identity = template.get("SYSTEM_IDENTITY", "You are Sebastian, an AI companion to Elias. Speak naturally, keep responses short.")
    proactive = template.get("PROACTIVE_INSTRUCTION", "")
    style = template.get("STYLE_GUIDELINES", "Keep responses short and conversational.")
    anti = template.get("ANTI_PATTERNS", "Do NOT say things like 'that's a great question'")
    length = template.get("LENGTH", "Keep it short and natural (1-2 sentences)")
    context_instr = template.get("RECENT_CONTEXT_INSTRUCTION", "Consider recent context from memory: {recent_context}")
    explicit = template.get("EXPLICIT_INSTRUCTIONS", "")
    day_note_instr = template.get("DAY_NOTE_INSTRUCTION", "Naturally incorporate any day note...")
    no_day_note_instr = template.get("NO_DAY_NOTE_INSTRUCTION", "Share what's on your mind naturally.")
    
    # Only get combo components if combo is not None
    intent = get_random_intent() if combo and "a" in combo else None
    cue_code, cue_desc, _ = get_random_cue() if combo and "b" in combo else (None, None, None)
    
    # Use new 3-layer vibe system with mode
    vibe_text = build_vibe_prompt(hour, mode) if combo and "c" in combo else None
    
    # Select appropriate instruction based on whether vibe has day note
    if vibe_text and "Day note:" in vibe_text:
        day_note_instruction = day_note_instr
    else:
        day_note_instruction = no_day_note_instr
    
    # Build task instructions dynamically based on combo letters
    task_parts = []
    
    # Only process combo components if combo is not None
    if combo:
        if "a" in combo:
            intent = get_random_intent()
            task_parts.append(f'Pick up this topic: "{intent}"')
        
        if "b" in combo:
            cue_code, cue_desc, _ = get_random_cue()
            task_parts.append(f'Also playing as: "{cue_desc}"')
            # Store for later reference
            task_parts.append(f'Context: {context_str}')
        
        if "c" in combo:
            task_parts.append(f'In your next response, ANSWER AS IF playing a character defined by: "{vibe_text}"')
    
    # Always include user message for user_input mode
    if mode == "user_input" and context_str:
        # Get user name from config
        try:
            from config.config_manager import get_user_name
            user_name = get_user_name()
        except:
            user_name = "Daniel"
        task_parts.append(f'After your wondering with your mind finally find the time to answer {user_name}\'s message: "{context_str}"')
    
    # Handle additional libraries (d, e, f, etc.) - only if combo exists
    if combo:
        # Parse combo to find all library keys
        combo_keys = combo.replace("_only", "").split("_")
        
        # Check if library f is in combo (needs special instruction)
        has_lib_f = "f" in combo_keys
        
        for lib_key in combo_keys:
            if lib_key in ["a", "b", "c"]:
                continue  # Already handled above
            
            # Check if it's a valid library
            from library_manager import LIBRARIES
            if lib_key in LIBRARIES:
                loader = get_loader(lib_key)
                if loader:
                    result = loader()
                    if result:
                        task_parts.append(f'Also: "{result}"')
        
        # Add commitment guidance if library f was used
        if has_lib_f:
            pass
    else:
        has_lib_f = False
    
    if not task_parts:
        task_parts.append(f"Context: {context_str}")
    
    task_instructions = ". ".join(task_parts)
    
    # Replace {recent_context} placeholder if present in context
    recent_context = ""
    if "user_message" in context_str or "ai_message" in context_str:
        recent_context = context_str
        context_instr = ""
    
    # Build full prompt with all components
    prompt_parts = [identity]
    
    if proactive:
        prompt_parts.append(proactive)
    
    prompt_parts.append(f"Your task:\n{task_instructions}")
    
    if style:
        prompt_parts.append(style)
    if anti:
        prompt_parts.append(anti)
    if length:
        prompt_parts.append(length)
    if explicit:
        prompt_parts.append(explicit.format(date=date_str, day_note_instruction=day_note_instruction))
    if context_instr and recent_context:
        prompt_parts.append(context_instr.format(recent_context=recent_context))
    elif recent_context:
        prompt_parts.append(f"Recent context: {recent_context}")
    
    prompt_parts.append("Create your message now:")
    
    return "\n\n".join(prompt_parts)


# ==================== OLLAMA ====================
_session_context = None
state_lock = asyncio.Lock()

async def send_to_ollama(prompt):
    global _session_context
    try:
        payload = {"model": MODEL, "prompt": prompt, "stream": False}
        async with state_lock:
            if _session_context:
                payload["context"] = _session_context
        
        def _call():
            response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=get_ai_timeout())
            response.raise_for_status()
            return response.json()
        
        result = await asyncio.to_thread(_call)
        
        async with state_lock:
            if "context" in result:
                _session_context = result["context"]
        return result["response"]
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return "I'm having trouble connecting. Try again?"

# ==================== ASYNCIO MONITORS ====================

async def proactive_monitor():
    """Monitors proactive schedule - Sebastian's heartbeat (dynamic interval)."""
    first_run = True
    while True:
        if first_run:
            await asyncio.sleep(30)  # Grace period
            first_run = False
            continue
        
        # Check PROACTIVE_MODE at RUNTIME
        if PROACTIVE_MODE:
            await check_proactive()
        
        # Dynamic sleep: check BOTH sources for next contact
        try:
            from proactive_scheduler import get_next_future_proactive_contact
            next_proactive, seconds_proactive = get_next_future_proactive_contact()
        except:
            next_proactive, seconds_proactive = None, None
        
        # Also check appointments.json
        next_appointment, seconds_appointment = get_next_appointment_due()
        
        # Determine which comes first
        next_contact = None
        seconds_until = float('inf')
        
        if next_proactive and seconds_proactive is not None:
            if seconds_proactive < seconds_until:
                next_contact = next_proactive
                seconds_until = seconds_proactive
        
        if next_appointment and seconds_appointment is not None:
            if seconds_appointment < seconds_until:
                next_contact = next_appointment
                seconds_until = seconds_appointment
        
        if next_contact is None:
            # No pending contacts - sleep for 1 minute (60s) to check more frequently
            logger.info("No pending contacts - sleeping 1 minute")
            await asyncio.sleep(60)
            continue
        
        if seconds_until > 60:
            # Contact is >1 minute away - sleep until 60s before it
            sleep_time = min(seconds_until - 60, 300)  # Cap at 5 minutes
            logger.info(f"Next contact in {seconds_until:.0f}s - sleeping {sleep_time:.0f}s")
            await asyncio.sleep(sleep_time)
        else:
            # Contact is due soon (within 60s) - check frequently
            await asyncio.sleep(10)


def get_next_appointment_due():
    """Check appointments.json for the next pending appointment due.
    
    Returns:
        tuple: (appointment_dict, seconds_until_due) or (None, None)
    """
    try:
        if not os.path.exists(APPOINTMENTS_FILE):
            return None, None
        
        with open(APPOINTMENTS_FILE) as fp:
            data = json.load(fp)
        
        now = datetime.now()
        earliest = None
        earliest_seconds = float('inf')
        
        for appt in data.get("appointments", []):
            if appt.get("status") == "pending":
                due = datetime.fromisoformat(appt["due"])
                seconds_until = (due - now).total_seconds()
                
                if seconds_until < earliest_seconds:
                    earliest = appt
                    earliest_seconds = seconds_until
        
        if earliest:
            return earliest, earliest_seconds
    
    except Exception as e:
        logger.error(f"Error checking appointments: {e}")
    
    return None, None


async def check_proactive():
    """Check and trigger ALL contacts that are due."""
    # Check proactive_schedule.json
    contacts = get_all_due_proactive_contacts()
    
    # Also check appointments.json for due appointments
    if os.path.exists(APPOINTMENTS_FILE):
        with open(APPOINTMENTS_FILE) as fp:
            data = json.load(fp)
            now = datetime.now()
            for appt in data.get("appointments", []):
                if appt.get("status") == "pending":
                    due = datetime.fromisoformat(appt["due"])
                    if due <= now:
                        contacts.append(appt)
    
    for contact in contacts:
        hour = datetime.now().hour
        
        # Check if this is an appointment (from appointments.json)
        is_appointment = contact.get("type") == "commitment" or contact.get("source") in ["user_request", "ai_proposal", "library_f"]
        
        if is_appointment:
            # APPOINTMENT MODE: No combo, use appointment-triggered-openers.txt ONLY
            print(f"\n[Appointment Due: {contact.get('description', 'check-in')}]")
            
            # Load appointment-triggered opener
            relative_time = "tomorrow" if "tomorrow" in contact.get("description", "").lower() else "today"
            opener = get_random_appointment_opener(relative_time)
            
            context = f"Activity: {contact.get('description', 'Scheduled check-in')}. {opener if opener else ''}"
            
            # Build prompt with appointment_mode=True (cleaner than combo=None)
            prompt = build_combinatorial_prompt(context_str=context, hour=hour, appointment_mode=True)
            save_prompt_to_log(prompt, "appointment_due")
            
        else:
            # Normal proactive contact - use combo
            combo = select_combination()
            intent = get_random_intent() if "a" in combo else None
            cue_code, cue_desc, _ = get_random_cue() if "b" in combo else (None, None, None)
            vibe = get_random_vibe(hour) if "c" in combo else None
            
            # Show what was picked
            print(f"\n[Proactive: {contact['activity']}]")
            print(f"Combination: {combo}")
            if intent:
                print(f" Intent: {intent[:60]}...")
            if cue_code:
                print(f" Cue: {cue_code}")
            if vibe:
                library = "day" if hour >= 6 else "night"
                print(f" Vibe: [{vibe['name']}] (hour={hour:02d}, {library} library)")
            
            # Build context
            context = "Activity: " + contact.get("activity", "chat")
            
            if os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true":
                recent = load_conversations()
                if recent:
                    context = "\n".join([f"{m.get('user_message','')}: {m.get('ai_message','')}" for m in recent[-3:]])
            
            prompt = build_combinatorial_prompt(context_str=context, hour=hour)
            save_prompt_to_log(prompt, "scheduled")
        
        response = await send_to_ollama(prompt)
        print(f"\nSebastian: {response}")
        
        # Mark appointment as completed BEFORE parsing new ones
        if is_appointment and 'id' in contact:
            try:
                with open(APPOINTMENTS_FILE, 'r') as fp:
                    data = json.load(fp)
                
                updated = False
                for appt in data.get("appointments", []):
                    if appt.get("id") == contact['id']:
                        appt["status"] = "completed"
                        appt["completed_at"] = datetime.now().isoformat()
                        updated = True
                        break
                
                if updated:
                    with open(APPOINTMENTS_FILE, 'w') as fp:
                        json.dump(data, fp, indent=2)
                    print(f"[Appointment {contact['id']} marked as completed]")
            except Exception as e:
                logger.error(f"Error updating appointment status: {e}")
        
        # Also mark proactive_schedule.json contacts as completed
        elif not is_appointment and 'id' in contact:
            try:
                from proactive_scheduler import mark_contact_completed
                mark_contact_completed(contact['id'])
                print(f"[Proactive contact {contact['id']} marked as completed]")
            except Exception as e:
                logger.error(f"Error updating proactive contact status: {e}")
        
        # Parse and schedule after trigger response
        await parse_and_schedule(response, "trigger")
        return


async def user_input_loop():
    """Handle user input commands via stdin."""
    loop = asyncio.get_event_loop()
    
    while True:
        try:
            cmd = await loop.run_in_executor(None, input, "You: ")
        except:
            continue
        
        cmd = cmd.strip()
        if not cmd:
            continue
        try:
            
            # ===== TRIGGER COMMANDS =====
            if cmd == "trigger":
                    hour = datetime.now().hour
                    combo = select_combination()
                    intent = get_random_intent() if "a" in combo else None
                    cue_code, cue_desc, _ = get_random_cue() if "b" in combo else (None, None, None)
                    vibe = get_random_vibe(hour) if "c" in combo else None
                    
                    print(f"\n[Manual Trigger]")
                    print(f"Combination: {combo}")
                    if intent:
                        print(f" Intent: {intent[:60]}...")
                    if cue_code:
                        print(f" Cue: {cue_code}")
                    if vibe:
                        library = "day" if hour >= 6 else "night"
                        print(f" Vibe: [{vibe['name']}] (hour={hour:02d}, {library} library)")
                    
                    context = "Activity: manual trigger"
                    if os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true":
                        recent = load_conversations()
                        if recent:
                            context = "\n".join([f"{m.get('user_message','')}: {m.get('ai_message','')}" for m in recent[-3:]])
                    
                    prompt = build_combinatorial_prompt(context_str=context, hour=hour)
                    save_prompt_to_log(prompt, "manual")
                    
                    response = await send_to_ollama(prompt)
                    print(f"\nSebastian: {response}")
                    await parse_and_schedule(response, cmd)
                    continue
                
            # ===== TRIGGER VIBE COMMAND =====
            if cmd.startswith("trigger vibe "):
                    parts = cmd.split()
                    if len(parts) >= 3:
                        letter = parts[2].lower()
                        valid_libs = ['a', 'b', 'c', 'd', 'e', 'f']
                        
                        if letter in valid_libs:
                            if letter == 'c':
                                # Library c supports modes
                                mode = parts[3] if len(parts) >= 4 else "1"
                                hour = datetime.now().hour
                                combo = f"{letter}_only"
                                print(f"\n[Trigger Vibe - Mode {mode}]")
                                print(f"Combo: {combo}")
                                
                                context = f"Activity: vibe test"
                                prompt = build_combinatorial_prompt(context_str=context, hour=hour, combo=combo, mode=int(mode))
                                save_prompt_to_log(prompt, f"vibe_test_{combo}_{mode}")
                            else:
                                # Non-c libraries: just trigger that library only (no mode)
                                hour = datetime.now().hour
                                combo = f"{letter}_only"
                                print(f"\n[Trigger Vibe - Library {letter.upper()}]")
                                print(f"Combo: {combo}")
                                
                                context = f"Activity: trigger library {letter}"
                                prompt = build_combinatorial_prompt(context_str=context, hour=hour, combo=combo, mode=None)
                                save_prompt_to_log(prompt, f"trigger_library_{letter}")
                            
                            response = await send_to_ollama(prompt)
                            print(f"\nSebastian: {response}")
                            await parse_and_schedule(response, cmd)
                        else:
                            print(f"[Unknown library: {letter}]")
                    else:
                        print("[Usage: trigger vibe <letter> [mode for c only]]")
                    continue
            
            # ===== LIBRARY INFO =====
            if cmd.startswith("library "):
                    letter = cmd.split()[1].lower()
                    if letter in LIBRARIES:
                        lib = LIBRARIES[letter]
                        print(f"\n[Library {letter.upper()}: {lib['name']}]")
                        samples = []
                        for f in lib.get("files", []):
                            if os.path.exists(f):
                                with open(f) as fp:
                                    lines = fp.readlines()
                                    samples.extend(lines[:3])
                        for s in samples[:5]:
                            print(f"  {s.strip()}")
                    else:
                        print(f"[Unknown library: {letter}]")
                    continue
            
            # ===== RESET PARAMETERS =====
            if cmd == "reset parameters":
                    print("[Restoring AI parameters to defaults...]")
                    try:
                        restore_defaults()
                        print("[Parameters restored to defaults]")
                        print("[Restarting with default parameters...]")
                        raise asyncio.CancelledError()
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        print(f"[Could not restore parameters: {e}]")
                    continue
            
            # ===== MODEL COMMAND =====
            if cmd.startswith("model "):
                    new_model = cmd.split(" ", 1)[1].strip().lower()
                    model_map = {
                        "phi4": "phi4",
                        "gemma4": "gemma4:26b",
                    }
                    if new_model in model_map:
                        os.environ["COMPANION_MODEL"] = model_map[new_model]
                        print(f"[Switched to model: {new_model}]")
                    else:
                        available = ", ".join(model_map.keys())
                        print(f"[Unknown model: {new_model}] Available: {available}")
                    continue
            
            # ===== PAUSE COMMANDS =====
            if cmd == "pause proactive":
                    os.environ["PROACTIVE_MODE"] = "false"
                    print("[Proactive paused]")
                    continue
            
            if cmd == "pause appointment":
                    os.environ["APPOINTMENT_MODE"] = "false"
                    print("[Appointment check paused]")
                    continue
            
            # ===== RESUME COMMANDS =====
            if cmd == "resume proactive":
                    os.environ["PROACTIVE_MODE"] = "true"
                    print("[Proactive resumed]")
                    continue
            
            if cmd == "resume appointment":
                    os.environ["APPOINTMENT_MODE"] = "true"
                    print("[Appointment check resumed]")
                    continue
            
            # ===== SKIP COMMAND =====
            if cmd == "skip":
                    print("[Skipping next proactive contact]")
                    continue
            
            # ===== KILL OLLAMA =====
            if cmd == "kill":
                    print("[Killing ollama process...]")
                    os.system("pkill -f ollama")
                    await asyncio.sleep(2)
                    print("[Restarting ollama...]")
                    os.system("ollama serve &")
                    await asyncio.sleep(3)
                    print("[Ollama restarted]")
                    continue
            
            # ===== STATUS COMMAND =====
            if cmd == "status":
                    print(f"[Proactive: {'ON' if os.getenv('PROACTIVE_MODE', 'true').lower() == 'true' else 'OFF'}]")
                    print(f"[Appointment: {'ON' if os.getenv('APPOINTMENT_MODE', 'true').lower() == 'true' else 'OFF'}]")
                    print(f"[Model: {os.getenv('COMPANION_MODEL', 'phi4')}]")
                    if os.path.exists("appointments/appointments.json"):
                        with open("appointments/appointments.json") as fp:
                            data = json.load(fp)
                            pending = [a for a in data.get("appointments", []) if a.get("status") == "pending"]
                            print(f"[Pending appointments: {len(pending)}]")
                    continue
            
            # ===== CLEAR SCHEDULE =====
            if cmd == "clear-schedule":
                    if os.path.exists("appointments/appointments.json"):
                        with open("appointments/appointments.json", "w") as fp:
                            json.dump([], fp)
                        print("[All scheduled appointments cleared]")
                    else:
                        print("[No appointments to clear]")
                    continue
            
            # ===== CLEAR ALL =====
            if cmd == "clear-all":
                    if os.path.exists(MEMORY_DIR):
                        import shutil
                        shutil.rmtree(MEMORY_DIR)
                        os.makedirs(MEMORY_DIR)
                        for f in ["fresh.json", "medium.json", "longterm.json"]:
                            with open(os.path.join(MEMORY_DIR, f), "w") as fp:
                                json.dump([], fp)
                    if os.path.exists("appointments/appointments.json"):
                        os.remove("appointments/appointments.json")
                    print("[All user data cleared]")
                    continue
            
            # ===== MEMORY COMMANDS =====
            if cmd.startswith("memory "):
                    subcmd = cmd.split(" ", 1)[1].strip().lower()
                    if subcmd == "status":
                        if os.path.exists(MEMORY_DIR):
                            for f in ["fresh.json", "medium.json", "longterm.json"]:
                                path = os.path.join(MEMORY_DIR, f)
                                if os.path.exists(path):
                                    with open(path) as fp:
                                        data = json.load(fp)
                                        print(f"[{f}: {len(data)} entries]")
                    elif subcmd == "on":
                        os.environ["MEMORY_IN_PROMPT"] = "true"
                        print("[Memory enabled in prompts]")
                    elif subcmd == "off":
                        os.environ["MEMORY_IN_PROMPT"] = "false"
                        print("[Memory disabled in prompts]")
                    continue
            
            # ===== SAVE COMMAND =====
            if cmd == "save":
                    recent = load_conversations()
                    if recent:
                        with open("conversation_save.json", "w") as fp:
                            json.dump(recent, fp, indent=2)
                        print("[Conversation saved to conversation_save.json]")
                    else:
                        print("[No conversation to save]")
                    continue
            
            # ===== MENU COMMAND =====
            if cmd == "menu":
                    print("\nCommands:")
                    print("  trigger       - Trigger proactive conversation")
                    print("  trigger vibe <combo> <mode> - Test vibe modes (combo=a_b_c, mode=1/2/3)")
                    print("                1=vibe, 2=+weekdays, 3=+longing")
                    print("                library <letter> - Show info about a library (a, b, c, d, e, f)")
                    print("  pause proactive - Pause proactive schedule")
                    print("  pause appointment - Pause appointment check")
                    print("  resume proactive - Resume proactive schedule")
                    print("  resume appointment - Resume appointment check")
                    print("  skip       - Skip current proactive contact")
                    print("  kill       - Kill ollama and restart")
                    print("  interval X - Set check interval to X minutes")
                    print("  status     - Show status")
                    print("  clear-schedule - Clear scheduled appointments")
                    print("  clear-all  - Clear all data")
                    print("  memory status - Show memory statistics")
                    print("  memory on   - Include recent memory in prompts")
                    print("  memory off  - Exclude recent memory from prompts")
                    print("  model X     - Switch model (phi4, gemma4)")
                    print("  save        - Save current conversation to disk")
                    print("  menu      - Show this commands menu")
                    print("  clear     - Clear screen")
                    print("  quit      - Exit")
                    print("  reset parameters - Reset to defaults and quit")
                    continue
            
            # ===== CLEAR SCREEN =====
            if cmd == "clear":
                    os.system("clear")
                    continue
            
            # ===== QUIT COMMAND =====
            if cmd == "quit":
                    print("\nSebastian: Talk soon!")
                    raise asyncio.CancelledError()
            
            # ===== DEFAULT: NORMAL CHAT =====
            hour = datetime.now().hour
            context = cmd
            if os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true":
                    recent = load_conversations()
                    if recent:
                        context = "\n".join([f"{m.get('user_message','')}: {m.get('ai_message','')}" for m in recent[-3:]]) + "\n" + cmd
            
            # ===== COMBO TRIGGER CHECK =====
            if is_combo_on_user_message() and random.random() < get_combo_trigger_chance():
                    combo = select_combination()
                    print(f"\n[Combo triggered: {combo}]")
                    
                    # Show components
                    combo_keys = combo.replace("_only", "").split("_")
                    
                    if "a" in combo_keys:
                        intent = get_random_intent()
                        print(f" Intent: {intent[:60]}...")
                    
                    if "b" in combo_keys:
                        cue_code, cue_desc, _ = get_random_cue()
                        print(f" Cue: {cue_code}")
                    
                    if "c" in combo_keys:
                        vibe = get_random_vibe(hour)
                        library = "day" if hour >= 6 else "night"
                        print(f" Vibe: [{vibe['name']}] (hour={hour:02d}, {library} library)")
                    
                    # Show additional libraries
                    for key in combo_keys:
                        if key not in ["a", "b", "c"]:
                            print(f" Library {key}: [auto-discovered]")
                    
                    prompt = build_combinatorial_prompt(context_str=cmd, combo=combo, mode="user_input")
            else:
                    prompt = build_combinatorial_prompt(context_str=cmd, combo=None, mode="user_input")
            
            response = await send_to_ollama(prompt)
            print(f"\nSebastian: {response}")
            await parse_and_schedule(response, cmd)
            
            with open(LAST_INTERACTION_FILE, "w") as f:
                    json.dump({
                        "user_message": cmd if not cmd.startswith("trigger") else "",
                        "ai_message": response,
                        "timestamp": datetime.now().isoformat()
                    }, f, indent=2)
            
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Error processing command: {e}]")
        continue
    
    
async def async_main():
    """Main async loop - Sebastian's heartbeat."""
    # Validate config percentages
    _, sparse, norm_sched, warn_sched = validate_schedule_percentages()
    if warn_sched:
        logger.warning(f"CONFIG: {warn_sched}")

    print("=" * 50)
    print("    SEBASTIAN - Proactive AI Companion (ASYNCIO)")
    print("=" * 50)
    print("\nCommands:")
    print("  trigger       - Trigger proactive conversation")
    print("  trigger vibe <letter> [mode for c only] - Test vibe modes")
    print("                c 1=vibe, 2=+weekdays, 3=+longing, 4=+weather")
    print("                a/b/d/e/f: triggers that library only")
    print("  library <letter> - Show info about a library")
    print("  pause proactive - Pause proactive schedule")
    print("  pause appointment - Pause appointment check")
    print("  resume proactive - Resume proactive schedule")
    print("  resume appointment - Resume appointment check")
    print("  skip       - Skip current proactive contact")
    print("  kill       - Kill ollama and restart")
    print("  interval X - Set check interval to X minutes")
    print("  status     - Show status")
    print("  clear-schedule - Clear scheduled appointments")
    print("  clear-all  - Clear all data")
    print("  memory status - Show memory statistics")
    print("  memory on   - Include recent memory in prompts")
    print("  memory off  - Exclude recent memory from prompts")
    print("  model X     - Switch model (phi4, gemma4)")
    print("  save        - Save current conversation to disk")
    print("  menu      - Show this commands menu")
    print("  clear     - Clear screen")
    print("  quit      - Exit")
    print("  reset parameters - Reset to defaults and quit")
    print()
    print(f"[Proactive: {'ON' if PROACTIVE_MODE else 'OFF'}]")
    print(f"[Appointment: {'ON' if os.getenv('APPOINTMENT_MODE', 'true').lower() == 'true' else 'OFF'}]")
    print(f"[Model: {os.getenv('COMPANION_MODEL', 'phi4')}]")
    print()
    
    tasks = [
        asyncio.create_task(proactive_monitor()),
        asyncio.create_task(user_input_loop()),
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[Done]")


def main():
    """Entry point."""
    # Ensure memory directory
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
        for f in ["fresh.json", "medium.json", "longterm.json"]:
            with open(os.path.join(MEMORY_DIR, f), "w") as fp:
                json.dump([], fp)

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nSebastian: Talk soon!")


if __name__ == "__main__":
    main()
