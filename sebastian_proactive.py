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

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "sebastian.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
_global_interval = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "10"))

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
        get_ai_timeout,
        validate_schedule_percentages,
        validate_combo_weights,
    )
except ImportError:
    def get_user_name():
        return "Elias"
    def get_combo_trigger_chance():
        return 0.20
    def get_ai_timeout():
        return 600
    def validate_schedule_percentages(*args):
        return 0.30, 0.70, False, None
    def validate_combo_weights(*args):
        return {}, False, None
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
    generate_combo_weights,
    get_normal_libraries,
    get_special_libraries,
    get_loader,
)

# Auto-generated from library_manager.LIBRARIES
COMBINATION_WEIGHTS = generate_combo_weights()

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


def select_combination():
    r = random.random()
    cumulative = 0.0
    for combo, weight in COMBINATION_WEIGHTS.items():
        cumulative += weight
        if r < cumulative:
            return combo
    return "a_c"


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


def build_combinatorial_prompt(context_str=None, hour=None, combo=None, mode=None):
    if hour is None:
        hour = datetime.now().hour
    if context_str is None:
        context_str = "Activity: general chat"
    if combo is None:
        combo = select_combination()
    
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
    
    intent = get_random_intent() if "a" in combo else None
    cue_code, cue_desc, _ = get_random_cue() if "b" in combo else (None, None, None)
    
    # Use new 3-layer vibe system with mode
    vibe_text = build_vibe_prompt(hour, mode) if "c" in combo else None
    
    # Select appropriate instruction based on whether vibe has day note
    if vibe_text and "Day note:" in vibe_text:
        day_note_instruction = day_note_instr
    else:
        day_note_instruction = no_day_note_instr
    
    # Build task instructions dynamically based on combo letters
    task_parts = []
    
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
    
    # Handle additional libraries (d, e, f, etc.)
    # Parse combo to find all library keys
    combo_keys = combo.replace("_only", "").split("_")
    
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
    """Monitors proactive schedule - Sebastian's heartbeat."""
    first_run = True
    while True:
        if first_run:
            await asyncio.sleep(30)  # Grace period
            first_run = False
            continue
        
        # Check PROACTIVE_MODE at RUNTIME, not import time
        if PROACTIVE_MODE:
            await check_proactive()
        
        await asyncio.sleep(30)  # Check every 30 seconds


async def check_proactive():
    """Check and trigger ALL contacts that are due."""
    contacts = get_all_due_proactive_contacts()
    
    for contact in contacts:
        hour = datetime.now().hour
        
        # Get combo and components for display
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
        complete_proactive_contact(contact["id"])


async def vibe_monitor():
    """Monitors time-based vibe changes."""
    last_hour = datetime.now().hour
    while True:
        await asyncio.sleep(60)
        current_hour = datetime.now().hour
        if current_hour != last_hour:
            logger.debug(f"Vibe shift: {last_hour} -> {current_hour}")
            last_hour = current_hour


def get_due_appointments():
    """Get all appointments that are due from appointments.json."""
    try:
        data = sched_module.load_appointments()
        now = datetime.now()
        due = []
        for appt in data.get("appointments", []):
            if appt.get("status") == "pending":
                due_time = datetime.fromisoformat(appt["due"])
                if due_time <= now:
                    due.append(appt)
        return due
    except:
        return []


def complete_appointment(appt_id):
    """Mark an appointment as completed."""
    try:
        data = sched_module.load_appointments()
        for appt in data.get("appointments", []):
            if appt.get("id") == appt_id:
                appt["status"] = "completed"
                break
        sched_module.save_appointments(data)
    except:
        pass


async def appointment_check_loop():
    """Monitors appointments.json for due appointments."""
    while True:
        await asyncio.sleep(30)
        
        # Check APPOINTMENT_MODE at runtime
        if os.getenv('APPOINTMENT_MODE', 'true').lower() != 'true':
            continue
        
        # Check for due appointments
        appts = get_due_appointments()
        
        for appt in appts:
            print(f"\n[Appointment: {appt.get('description', appt.get('activity', 'check-in'))[:50]}...]")
            
            hour = datetime.now().hour
            context = "Activity: " + appt.get("description", appt.get("activity", "check-in"))
            
            if os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true":
                recent = load_conversations()
                if recent:
                    context = "\n".join([f"{m.get('user_message','')}: {m.get('ai_message','')}" for m in recent[-3:]])
            
            prompt = build_combinatorial_prompt(context_str=context, hour=hour)
            save_prompt_to_log(prompt, "appointment")
            
            response = await send_to_ollama(prompt)
            print(f"\nSebastian: {response}")
            complete_appointment(appt.get("id"))


async def user_input_loop():
    """Non-blocking user input."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            user_input = await loop.run_in_executor(None, lambda: input("\nYou: "))
            if not user_input:
                continue
            user_input = user_input.strip()
            await handle_command(user_input)
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as e:
            # Skip other input errors silently
            pass


async def handle_command(cmd):
    """Handle user commands - async."""
    global _global_interval
    
    if cmd in ["quit", "exit", "q"]:
        print("\nSebastian: Talk soon!")
        raise asyncio.CancelledError()
    
    # ===== KILL COMMAND =====
    if cmd == "kill":
        print("[Killing ollama process...]")
        import subprocess
        subprocess.run(["pkill", "-9", "-f", "ollama"], check=False)
        print("[Waiting 2 minutes for ollama to restart...]")
        await asyncio.sleep(120)
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[Ollama restarted]")
        return
    
    
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
        return

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
        return
    
    # ===== PAUSE COMMANDS =====
    if cmd == "pause proactive":
        os.environ["PROACTIVE_MODE"] = "false"
        print("[Proactive paused]")
        return
    
    if cmd == "pause appointment":
        os.environ["APPOINTMENT_MODE"] = "false"
        print("[Appointment paused]")
        return
    
    # ===== RESUME COMMANDS =====
    if cmd == "resume proactive":
        os.environ["PROACTIVE_MODE"] = "true"
        print("[Proactive resumed]")
        return
    
    if cmd == "resume appointment":
        os.environ["APPOINTMENT_MODE"] = "true"
        print("[Appointment resumed]")
        return
    
    # ===== MEMORY COMMANDS =====
    if cmd == "memory on":
        os.environ["MEMORY_IN_PROMPT"] = "true"
        print("[Memory in prompts: ON]")
        print("[Recent: includes last 5 user messages]")
        return
    
    if cmd == "memory off":
        os.environ["MEMORY_IN_PROMPT"] = "false"
        print("[Memory in prompts: OFF]")
        print("[Recent: not included in prompts]")
        return
    
    if cmd == "memory status":
        memory_on = os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true"
        print(f"\n[Memory Status]")
        print(f"  In prompts: {'ON' if memory_on else 'OFF'}")
        return
    
    # ===== TRIGGER =====
    if cmd == "trigger":
        print("\n[Triggering...]")
        hour = datetime.now().hour
        
        # Get combo and components for display
        combo = select_combination()
        intent = get_random_intent() if "a" in combo else None
        cue_code, cue_desc, _ = get_random_cue() if "b" in combo else (None, None, None)
        vibe = get_random_vibe(hour) if "c" in combo else None
        
        # Show what was picked
        print(f"Combination: {combo}")
        print(f" Model: {os.getenv('COMPANION_MODEL', 'phi4')}")
        if intent:
            print(f" Intent: {intent[:60]}...")
        if cue_code:
            print(f" Cue: {cue_code}")
        if vibe:
            library = "day" if hour >= 6 else "night"
            print(f" Vibe: [{vibe['name']}] (hour={hour:02d}, {library} library)")
        
        # Build context and prompt - pass combo to ensure same combo used
        context = "Activity: manual trigger"
        if os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true":
            recent = load_conversations()
            if recent:
                context = "\n".join([f"{m.get('user_message','')}: {m.get('ai_message','')}" for m in recent[-3:]])
        
        prompt = build_combinatorial_prompt(context_str=context, hour=hour, combo=combo)
        save_prompt_to_log(prompt, "trigger")
        
        response = await send_to_ollama(prompt)
        print(f"\nSebastian: {response}")
        return
    
    # ===== TRIGGER VIBE (testing combos + modes) =====
    if cmd.startswith("trigger vibe "):
        parts = cmd.split()
        
        # Parse: trigger vibe [combo] [mode]
        if len(parts) < 3:
            print("[Usage: trigger vibe <combo> <mode>]")
            print("  combo: a_only, b_only, a_b, a_c, b_c, a_b_c, f_g_c, etc.")
            print("  mode: 1=vibe only, 2=+weekdays, 3=+longing")
            return
        
        combo_arg = parts[2]
        mode = int(parts[3]) if len(parts) >= 4 else 1
        
        if mode not in [1, 2, 3, 4]:
            print("[Mode must be 1, 2, 3, or 4]")
            return
        
        # Convert single letter to _only format
        if "_" not in combo_arg and len(combo_arg) == 1:
            combo = combo_arg + "_only"
        else:
            combo = combo_arg
        
        print(f"\n[Triggering combo {combo} with vibe mode {mode}...]")
        hour = datetime.now().hour
        
        # Show what was picked
        print(f"Combination: {combo}")
        print(f" Mode: {mode}")
        print(f" Model: {os.getenv('COMPANION_MODEL', 'phi4')}")
        
        # Dynamically load components based on combo
        intent = get_random_intent() if "a" in combo else None
        cue_code, cue_desc, _ = get_random_cue() if "b" in combo else (None, None, None)
        
        if intent:
            print(f" Intent: {intent[:60]}...")
        if cue_code:
            print(f" Cue: {cue_code}")
        
        # Build and show vibe (if c in combo)
        if "c" in combo:
            vibe_text = build_vibe_prompt(hour, mode)
            print(f" Vibe: {vibe_text[:100]}...")
        
        # Build context and prompt
        context = "Activity: manual trigger"
        if os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true":
            recent = load_conversations()
            if recent:
                context = "\n".join([f"{m.get('user_message','')}: {m.get('ai_message','')}" for m in recent[-3:]])
        
        prompt = build_combinatorial_prompt(context_str=context, hour=hour, combo=combo, mode=mode)
        save_prompt_to_log(prompt, f"trigger_vibe_{mode}")
        
        response = await send_to_ollama(prompt)
        print(f"\nSebastian: {response}")
        return
    
    # ===== SKIP =====
    if cmd == "skip":
        contact = get_next_proactive_contact()
        if contact:
            print(f"[Skipped: {contact['activity']}]")
        return
    
    # ===== CLEAR COMMANDS =====
    if cmd == "clear":
        print("\033[2J\033[H")
        print("=" * 50)
        print("    SEBASTIAN - Proactive AI Companion (ASYNCIO)")
        print("=" * 50)
        return
    
    if cmd == "clear-schedule":
        # Import scheduler module
        import scheduler as auto_sched
        auto_sched.save_appointments({"appointments": [], "random_check": None})
        print("[All appointments cleared]")
        return
    
    if cmd == "clear-all":
        import scheduler as auto_sched
        # Clear appointments
        auto_sched.save_appointments({"appointments": [], "random_check": None})
        # Clear memory
        for f in ["fresh.json", "medium.json", "longterm.json"]:
            with open(os.path.join(MEMORY_DIR, f), "w") as fp:
                json.dump([], fp)
        print("[All data cleared]")
        return
    
    # ===== SAVE CONVERSATION =====
    if cmd == "save":
        # Load last interaction (user message + AI response)
        try:
            with open(LAST_INTERACTION_FILE) as f:
                data = json.load(f)
                user_msg = data.get("user_message", "")
                ai_msg = data.get("ai_message", "")
        except:
            print("[No conversation to save]")
            return
        
        if not user_msg and not ai_msg:
            print("[No conversation to save]")
            return
        
        # Create filename: YYYY-MM-DD_HH-MM-SS_first_60_chars.txt
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Clean user message for filename
        clean_msg = user_msg[:60].replace("/", "_").replace("\\", "_").replace(" ", "_")
        clean_msg = "".join(c for c in clean_msg if c.isalnum() or c in "_-")
        filename = f"{timestamp}_{clean_msg}.txt"
        filepath = os.path.join(CONVERSATION_DIR, filename)
        
        # Save conversation
        with open(filepath, "w") as f:
            f.write(f"Timestamp: {datetime.now().isoformat()}\n\n")
            f.write(f"User: {user_msg}\n\n")
            f.write(f"Sebastian: {ai_msg}\n")
        
        print(f"[Conversation saved to {filepath}]")
        return
    
    # ===== STATUS =====
    if cmd == "status":
        print(f"\n[Status]")
        print(f"  Proactive: {'ON' if PROACTIVE_MODE else 'OFF'}")
        
        # Appointment check status
        appt_mode = os.getenv('APPOINTMENT_MODE', 'true').lower() == 'true'
        print(f"  Appointment: {'ON' if appt_mode else 'OFF'}")
        
        # Next from proactive_schedule.json
        proactive = get_proactive_status()
        if proactive:
            stats = proactive.get("stats", {})
            print(f"  Proactive: {proactive.get('month')} - {stats.get('pending',0)} pending, {stats.get('completed',0)} done")
        
        # Next from appointments.json
        try:
            data = sched_module.load_appointments()
            now = datetime.now()
            upcoming = []
            for appt in data.get("appointments", []):
                if appt.get("status") == "pending":
                    due = datetime.fromisoformat(appt["due"])
                    if due > now:
                        upcoming.append({"id": appt["id"], "due": appt["due"], "activity": appt.get("description", appt.get("activity", "check-in"))[:30]})
            if upcoming:
                upcoming.sort(key=lambda x: x["due"])
                next_appt = upcoming[0]
                due_dt = datetime.fromisoformat(next_appt["due"])
                print(f"  Next Appointment: {due_dt.strftime('%Y-%m-%d %H:%M')} (id={next_appt['id']}, {next_appt['activity'][:30]}...)")
        except Exception as e:
            pass
        return
    
    # ===== INTERVAL =====
    if cmd.startswith("interval "):
        try:
            new_interval = int(cmd.split()[1])
            _global_interval = new_interval
            print(f"[Interval set to {new_interval} minutes]")
        except:
            print("[Usage: interval X]")
        return
    
    # ===== MENU =====
    if cmd == "menu":
        print("\nCommands:")
        print("  trigger       - Trigger proactive conversation")
        print("  trigger vibe <combo> <mode> - Test vibe modes (combo=a_b_c, mode=1/2/3)")
        print("                1=vibe, 2=+weekdays, 3=+longing")
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
        return
    
    # Combo trigger chance on normal user message
    if random.random() < get_combo_trigger_chance():
        combo = select_combination()
        print(f"\n[Combo triggered: {combo}]")
        prompt = build_combinatorial_prompt(context_str=cmd, combo=combo, mode="user_input")
        response = await send_to_ollama(prompt)
    else:
        # Unknown command: send to AI as free text
        response = await send_to_ollama(cmd)
        print(f"\nSebastian: {response}")
    
    # Save last interaction for "save" command
    try:
        with open(LAST_INTERACTION_FILE, "w") as f:
            json.dump({
                "user_message": cmd if not cmd.startswith("trigger") else "",
                "ai_message": response,
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)
    except:
        pass


async def async_main():
    """Main async loop - Sebastian's heartbeat."""
    # Validate config percentages
    _, sparse, norm_sched, warn_sched = validate_schedule_percentages()
    if warn_sched:
        logger.warning(f"CONFIG: {warn_sched}")
    
    _, norm_combo, warn_combo = validate_combo_weights()
    if warn_combo:
        logger.warning(f"CONFIG: {warn_combo}")
    
    print("=" * 50)
    print("    SEBASTIAN - Proactive AI Companion (ASYNCIO)")
    print("=" * 50)
    print("\nCommands:")
    print("  trigger       - Trigger proactive conversation")
    print("  trigger vibe <combo> <mode> - Test vibe modes (combo=a_b_c, mode=1/2/3)")
    print("                1=vibe, 2=+weekdays, 3=+longing")
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
    print(f"[Interval: {_global_interval}min]")
    print()
    
    tasks = [
        asyncio.create_task(proactive_monitor()),
        asyncio.create_task(vibe_monitor()),
        asyncio.create_task(appointment_check_loop()),
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
