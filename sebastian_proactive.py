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

TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
PROACTIVE_MODE = os.getenv("PROACTIVE_MODE", "false").lower() == "true"

load_dotenv()

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
APPOINTMENTS_FILE = "appointments.json"
MAX_MEMORY_ENTRIES = int(os.getenv("MAX_MEMORY_ENTRIES", "50"))
ARCHIVE_THRESHOLD = int(os.getenv("ARCHIVE_THRESHOLD", "30"))
_global_interval = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "10"))

# Schedule scheduler to import after load_dotenv
import scheduler as sched_module
from time_parser import parse_response_for_time
from cue_manager import get_random_cue
from proactive_scheduler import (
    initialize_proactive_schedule,
    get_next_proactive_contact,
    get_all_due_proactive_contacts,
    complete_proactive_contact,
    get_proactive_status,
    load_vibe_library,
    get_random_vibe,
)

# ==================== COMBINATORIAL SYSTEM ====================
COMBINATION_WEIGHTS = {
    "a_only": 0.20, "b_only": 0.10, "c_only": 0.15,
    "a_b": 0.15, "a_c": 0.20, "b_c": 0.10, "a_b_c": 0.10,
}

SYSTEM_PROMPT = """You are Sebastian, an AI companion to Elias. Speak naturally, keep responses short."""


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


def build_combinatorial_prompt(context_str=None, hour=None):
    if hour is None:
        hour = datetime.now().hour
    if context_str is None:
        context_str = "Activity: general chat"
    
    combo = select_combination()
    intent = get_random_intent()
    cue_code, cue_desc, _ = get_random_cue()
    vibe = get_random_vibe(hour)
    
    prompts = {
        "a_only": f"""Your task: Pick up this topic: "{intent}". Start a natural conversation. Context: {context_str}""",
        "b_only": f"""Your task: You are playing as: "{cue_desc}". Start a conversation. Context: {context_str}""",
        "c_only": f"""Your task: In your next response, ANSWER AS IF playing a character defined by: "{vibe['text']}". Context: {context_str}""",
        "a_b": f"""Your task: Pick up this topic: "{intent}". Also playing as: "{cue_desc}". Context: {context_str}""",
        "a_c": f"""Your task: In your next response, ANSWER AS IF playing a character defined by: "{vibe['text']}". Also: "{intent}". Context: {context_str}""",
        "b_c": f"""Your task: In your next response, ANSWER AS IF playing a character defined by: "{vibe['text']}". Also playing as: "{cue_desc}". Context: {context_str}""",
        "a_b_c": f"""Your task: Topic: "{intent}", vibe: "{vibe['text']}", cue: "{cue_desc}". Context: {context_str}""",
    }
    return prompts.get(combo, prompts["a_only"])


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
            response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=500)
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
        if os.getenv('PROACTIVE_MODE', 'false').lower() == 'true':
            await check_proactive()
        
        await asyncio.sleep(30)  # Check every 30 seconds


async def check_proactive():
    """Check and trigger ALL contacts that are due."""
    contacts = get_all_due_proactive_contacts()
    
    for contact in contacts:
        print(f"\n[Proactive: {contact['activity']}]")
        
        hour = datetime.now().hour
        context = "Activity: " + contact.get("activity", "chat")
        
        if os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true":
            recent = load_conversations()
            if recent:
                context = "\n".join([f"{m.get('role','')}: {m.get('content','')}" for m in recent[-3:]])
        
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
                    context = "\n".join([f"{m.get('role','')}: {m.get('content','')}" for m in recent[-3:]])
            
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
    
    # ===== PAUSE COMMANDS =====
    if cmd == "pause":
        os.environ["PROACTIVE_MODE"] = "false"
        print("[Auto-scheduler paused]")
        print("[Proactive schedule paused]")
        return
    
    if cmd == "pause auto":
        print("[Auto-scheduler paused]")
        return
    
    if cmd == "pause proactive":
        os.environ["PROACTIVE_MODE"] = "false"
        print("[Proactive schedule paused]")
        return
    
    if cmd == "pause appointment":
        os.environ["APPOINTMENT_MODE"] = "false"
        print("[Appointment check paused]")
        return
    
    # ===== RESUME COMMANDS =====
    if cmd == "resume":
        os.environ["PROACTIVE_MODE"] = "true"
        print("[Auto-scheduler resumed]")
        print("[Proactive schedule resumed]")
        return
    
    if cmd == "resume auto":
        print("[Auto-scheduler resumed]")
        return
    
    if cmd == "resume proactive":
        os.environ["PROACTIVE_MODE"] = "true"
        print("[Proactive schedule resumed]")
        return
    
    if cmd == "resume appointment":
        os.environ["APPOINTMENT_MODE"] = "true"
        print("[Appointment check resumed]")
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
        if intent:
            print(f" Intent: {intent[:60]}...")
        if cue_code:
            print(f" Cue: {cue_code}")
        if vibe:
            library = "day" if hour >= 6 else "night"
            print(f" Vibe: [{vibe['name']}] (hour={hour:02d}, {library} library)")
        
        # Build context and prompt
        context = "Activity: manual trigger"
        if os.getenv("MEMORY_IN_PROMPT", "false").lower() == "true":
            recent = load_conversations()
            if recent:
                context = "\n".join([f"{m.get('role','')}: {m.get('content','')}" for m in recent[-3:]])
        
        prompt = build_combinatorial_prompt(context_str=context, hour=hour)
        save_prompt_to_log(prompt, "trigger")
        
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
    
    # ===== STATUS =====
    if cmd == "status":
        print(f"\n[Status]")
        print(f"  Proactive: {'ON' if os.getenv('PROACTIVE_MODE', 'false').lower() == 'true' else 'OFF'}")
        
        # Appointment check status
        appt_mode = os.getenv('APPOINTMENT_MODE', 'true').lower() == 'true'
        print(f"  Appointment: {'ON' if appt_mode else 'OFF'}")
        
        # Auto scheduler status from scheduler module
        auto_status = "PAUSED"
        try:
            if sched_module.is_enabled():
                auto_status = "ON"
        except:
            pass
        print(f"  Auto: {auto_status}")
        print(f"  Interval: 30sec")
        
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
        print("  trigger    - Trigger proactive conversation")
        print("  pause      - Pause auto-scheduler + proactive")
        print("  pause auto - Pause auto-scheduler only")
        print("  pause proactive - Pause proactive schedule only")
        print("  pause appointment - Pause appointment check")
        print("  resume     - Resume auto-scheduler + proactive")
        print("  resume auto - Resume auto-scheduler only")
        print("  resume proactive - Resume proactive schedule")
        print("  resume appointment - Resume appointment check")
        print("  skip       - Skip current proactive contact")
        print("  interval X - Set check interval to X minutes")
        print("  status     - Show status")
        print("  clear-schedule - Clear scheduled appointments")
        print("  clear-all  - Clear all data")
        print("  memory status - Show memory statistics")
        print("  memory on   - Include recent memory in prompts")
        print("  memory off  - Exclude recent memory from prompts")
        print("  menu      - Show this commands menu")
        print("  clear     - Clear screen")
        print("  quit      - Exit")
        return
    
    # Unknown command: send to AI as free text
    response = await send_to_ollama(cmd)
    print(f"\nSebastian: {response}")


async def async_main():
    """Main async loop - Sebastian's heartbeat."""
    print("=" * 50)
    print("    SEBASTIAN - Proactive AI Companion (ASYNCIO)")
    print("=" * 50)
    print("\nCommands:")
    print("  trigger    - Trigger proactive conversation")
    print("  pause      - Pause auto-scheduler + proactive")
    print("  pause auto - Pause auto-scheduler only")
    print("  pause proactive - Pause proactive schedule only")
    print("  pause appointment - Pause appointment check")
    print("  resume     - Resume auto-scheduler + proactive")
    print("  resume auto - Resume auto-scheduler only")
    print("  resume proactive - Resume proactive schedule")
    print("  resume appointment - Resume appointment check")
    print("  skip       - Skip current proactive contact")
    print("  interval X - Set check interval to X minutes")
    print("  status     - Show status")
    print("  clear-schedule - Clear scheduled appointments")
    print("  clear-all  - Clear all data")
    print("  memory status - Show memory statistics")
    print("  memory on   - Include recent memory in prompts")
    print("  memory off  - Exclude recent memory from prompts")
    print("  menu      - Show this commands menu")
    print("  clear     - Clear screen")
    print("  quit      - Exit")
    print()
    print(f"[Proactive: {'ON' if os.getenv('PROACTIVE_MODE', 'false').lower() == 'true' else 'OFF'}]")
    print(f"[Appointment: {'ON' if os.getenv('APPOINTMENT_MODE', 'true').lower() == 'true' else 'OFF'}]")
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