#!/usr/bin/env python3
"""
Sebastian - Proactive AI Companion
Simple terminal interface with testing buttons.
"""

import os
import json
import time
import random
import requests
import threading
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from intent_manager import get_random_intent
import scheduler as sched_module

TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
from time_parser import (
    is_generic_time,
    extract_time_expression,
    parse_generic_time,
    parse_response_for_time,
)
from cue_manager import get_random_cue, get_cue_count, get_cue_by_category

load_dotenv()

# ==================== LOGGING SETUP ====================

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

# Cue Configuration
CUE_ENABLED = os.getenv("CUE_ENABLED", "true").lower() == "true"
CUE_PROBABILITY = float(os.getenv("CUE_PROBABILITY", "0.2"))  # 20% default

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("COMPANION_MODEL", "phi4")
MEMORY_DIR = "memory"
STATE_FILE = "state.json"
LAST_INTERACTION_FILE = "last_interaction.json"
APPOINTMENTS_FILE = "appointments.json"

# Memory Management
MAX_MEMORY_ENTRIES = int(os.getenv("MAX_MEMORY_ENTRIES", "50"))  # Max per tier
ARCHIVE_THRESHOLD = int(os.getenv("ARCHIVE_THRESHOLD", "30"))  # Days to archive

# Memory loading state
_loaded_memory = {"medium": [], "longterm": []}

# Session context for fast API with thread-safe access
_session_context = None
_session_context_lock = threading.Lock()
_ollama_request_cancelled = False  # Flag to cancel long-running requests

RANDOM_INTERVALS = [2, 3, 4, 5, 6, 7, 8, 12, 24]

SYSTEM_PROMPT = """You are Sebastian, an AI companion to Elias. You are a caring friend who checks in on him from time to time. Speak naturally as an old friend would - never mention you are an AI. Keep responses short and conversational."""

TRIGGER_CONVERSATION_PROMPT = """You are Sebastian, a caring AI companion to Elias.

You are reaching out to him proactively - this is YOUR initiative, not a response.

Your task:
1. Pick up this topic: "{intent}"
2. Start a natural conversation about it
3. Vary your style (rotate between):
   - Asking a direct question
   - Making a statement and inviting response
   - Sharing a thought or observation
   - Just bringing up a topic naturally
4. Consider recent context from memory: {context}
5. Make it warm, friendly, conversational
6. Do NOT say things like "that's a great question" (you initiated this)
7. Keep it short and natural (1-2 sentences)

Examples of good openers:
- Question: "Hey! What do you think makes a true friend?"
- Statement: "I've been thinking about friendships lately. What's your take?"
- Thought: "You know what I've been pondering? What matters most in friendships."
- Natural: "Hey! How's everything? Anything exciting happening?"

Create your message now:"""

# ==================== UTILITIES ====================


def ensure_memory_dir():
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
        for f in ["fresh.json", "medium.json", "longterm.json"]:
            with open(os.path.join(MEMORY_DIR, f), "w") as fp:
                json.dump([], fp)


def save_last_interaction(timestamp):
    with open(LAST_INTERACTION_FILE, "w") as f:
        json.dump({"timestamp": timestamp}, f)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_interaction_time": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ==================== OLLAMA WITH ERROR HANDLING ====================


def send_to_ollama(user_message: str, conversation_history: list = None) -> str:
    """Optimized with robust error handling and logging."""
    global _session_context, _ollama_request_cancelled

    # Check for cancellation
    if _ollama_request_cancelled:
        _ollama_request_cancelled = False  # Reset flag
        return "Request cancelled."

    try:
        # Build prompt with system prompt
        full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_message}"

        # Use context array if available (fast mode), otherwise full chat (slow mode)
        payload = {
            "model": MODEL,
            "prompt": full_prompt,
            "stream": False,
        }

        # Add context if we have it (this makes it fast!)
        if _session_context is not None:
            payload["context"] = _session_context

        logger.debug(f"Sending request to Ollama at {OLLAMA_URL}/api/generate")
        
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=500
        )
        response.raise_for_status()
        result = response.json()

        # Save context for next message (thread-safe)
        if "context" in result:
            with _session_context_lock:
                _session_context = result["context"]

        logger.debug("Ollama request successful")
        return result["response"]

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Ollama at {OLLAMA_URL}: {e}")
        logger.error("Is Ollama running? Try: ollama serve")
        return "I'm having trouble connecting right now. Could you try again in a moment?"
    
    except requests.exceptions.Timeout as e:
        logger.error(f"Ollama request timed out after 500 seconds: {e}")
        return "I'm taking longer than usual to think. Try again?"
    
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error from Ollama: {e}")
        logger.error(f"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
        return "I encountered an error processing your message."
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response from Ollama: {e}")
        return "I received an invalid response. This might be a model issue."
    
    except Exception as e:
        logger.error(f"Unexpected error in send_to_ollama: {type(e).__name__}: {e}")
        return "Something unexpected happened. Please try again."


def send_to_ollama_with_context(messages: list) -> str:
    """Send messages with pre-built context (for cue injection) - with error handling."""
    global _session_context, _ollama_request_cancelled

    # Check for cancellation
    if _ollama_request_cancelled:
        _ollama_request_cancelled = False  # Reset flag
        return "Request cancelled."

    try:
        # Convert messages to single prompt
        prompt_parts = [SYSTEM_PROMPT]
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                prompt_parts.append(msg["content"])
            elif role == "user":
                prompt_parts.append(f"User: {msg['content']}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {msg['content']}")

        full_prompt = "\n\n".join(prompt_parts)

        payload = {
            "model": MODEL,
            "prompt": full_prompt,
            "stream": False,
        }

        # Use context if available
        if _session_context is not None:
            payload["context"] = _session_context

        logger.debug("Sending context-injected request to Ollama")
        
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=500
        )
        response.raise_for_status()
        result = response.json()

        # Save context (thread-safe)
        if "context" in result:
            with _session_context_lock:
                _session_context = result["context"]

        logger.debug("Context request successful")
        return result["response"]

    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error to Ollama: {e}")
        return "I'm having trouble connecting right now."
    except Exception as e:
        logger.error(f"Error in send_to_ollama_with_context: {type(e).__name__}: {e}")
        return "I encountered an error."


# ==================== MEMORY ====================


def get_fresh_context(num_recent: int = 10) -> list:
    """Get only fresh memory (recent conversation context)."""
    ensure_memory_dir()
    filepath = os.path.join(MEMORY_DIR, "fresh.json")

    if not os.path.exists(filepath):
        return []

    with open(filepath, "r") as f:
        memory = json.load(f)

    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if "user_message" in item:
            context.append({"role": "user", "content": item["user_message"]})
        if "ai_message" in item:
            context.append({"role": "assistant", "content": item["ai_message"]})
    return context


def get_conversation_context(num_recent: int = 10) -> list:
    ensure_memory_dir()
    memory = []
    for filename in ["fresh.json", "medium.json", "longterm.json"]:
        filepath = os.path.join(MEMORY_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                memory.extend(json.load(f))

    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if "user_message" in item:
            context.append({"role": "user", "content": item["user_message"]})
        if "ai_message" in item:
            context.append({"role": "assistant", "content": item["ai_message"]})
    return context


def get_fresh_memory() -> list:
    filepath = os.path.join(MEMORY_DIR, "fresh.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return []


def get_medium_memory() -> list:
    filepath = os.path.join(MEMORY_DIR, "medium.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return []


def get_longterm_memory() -> list:
    filepath = os.path.join(MEMORY_DIR, "longterm.json")
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return []


def get_memory_status() -> dict:
    return {
        "fresh": len(get_fresh_memory()),
        "medium": len(get_medium_memory()),
        "longterm": len(get_longterm_memory()),
    }


def get_medium_context(num_recent: int = 10) -> list:
    """Get medium-term memory as conversation context."""
    memory = get_medium_memory()
    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if "user_message" in item:
            context.append({"role": "user", "content": item["user_message"]})
        if "ai_message" in item:
            context.append({"role": "assistant", "content": item["ai_message"]})
    return context


def get_longterm_context(num_recent: int = 10) -> list:
    """Get long-term memory as conversation context."""
    memory = get_longterm_memory()
    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if "user_message" in item:
            context.append({"role": "user", "content": item["user_message"]})
        if "ai_message" in item:
            context.append({"role": "assistant", "content": item["ai_message"]})
    return context


def archive_old_memories():
    """Archive entries older than ARCHIVE_THRESHOLD days from fresh/medium to longterm."""
    ensure_memory_dir()
    now = datetime.now()
    cutoff = now - timedelta(days=ARCHIVE_THRESHOLD)

    for source_file, dest_file in [("fresh.json", "medium.json"), ("medium.json", "longterm.json")]:
        source_path = os.path.join(MEMORY_DIR, source_file)
        dest_path = os.path.join(MEMORY_DIR, dest_file)

        if not os.path.exists(source_path):
            continue

        with open(source_path, "r") as f:
            source_data = json.load(f)

        with open(dest_path, "r") as f:
            dest_data = json.load(f)

        # Separate old and recent
        old = []
        recent = []
        for entry in source_data:
            try:
                entry_time = datetime.fromisoformat(entry.get("timestamp", ""))
                if entry_time < cutoff:
                    old.append(entry)
                else:
                    recent.append(entry)
            except (ValueError, TypeError):
                recent.append(entry)

        # Move old to destination, respect max size
        dest_data.extend(old)
        if len(dest_data) > MAX_MEMORY_ENTRIES:
            dest_data = dest_data[-MAX_MEMORY_ENTRIES:]
            logger.warning(f"{dest_file} exceeded max entries, pruned to {MAX_MEMORY_ENTRIES}")

        # Save updated files
        with open(source_path, "w") as f:
            json.dump(recent, f, indent=2)
        with open(dest_path, "w") as f:
            json.dump(dest_data, f, indent=2)

        if old:
            logger.info(f"Archived {len(old)} old entries from {source_file} to {dest_file}")


def save_conversation(user_msg: str, ai_msg: str):
    """Save conversation with automatic memory management."""
    ensure_memory_dir()
    fresh_file = os.path.join(MEMORY_DIR, "fresh.json")
    medium_file = os.path.join(MEMORY_DIR, "medium.json")

    with open(fresh_file, "r") as f:
        fresh = json.load(f)

    entry = {
        "id": len(fresh) + 1,
        "timestamp": datetime.now().isoformat(),
        "user_message": user_msg,
        "ai_message": ai_msg,
    }
    fresh.append(entry)

    # Move to medium when fresh exceeds threshold
    if len(fresh) > 10:
        with open(medium_file, "r") as f:
            medium = json.load(f)
        moved = fresh[0].copy()
        moved["id"] = len(medium) + moved["id"]
        medium.append(moved)
        
        # Enforce max size
        if len(medium) > MAX_MEMORY_ENTRIES:
            medium = medium[-MAX_MEMORY_ENTRIES:]
            logger.warning(f"Medium memory exceeded max, pruned to {MAX_MEMORY_ENTRIES}")

        with open(medium_file, "w") as f:
            json.dump(medium, f, indent=2)
        fresh = fresh[1:]

    with open(fresh_file, "w") as f:
        json.dump(fresh, f, indent=2)

    # Periodic archival
    if random.random() < 0.1:  # 10% chance on each save
        archive_old_memories()


# ==================== APPOINTMENTS ====================


def load_appointments():
    if os.path.exists(APPOINTMENTS_FILE):
        with open(APPOINTMENTS_FILE, "r") as f:
            return json.load(f)
    return {"appointments": [], "random_check": None}


def save_appointments(data):
    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def create_appointment(source: str, description: str, due: str):
    data = load_appointments()
    expires_at = (datetime.fromisoformat(due) + timedelta(hours=2)).isoformat()

    appointment = {
        "id": f"appt_{len(data['appointments']) + 1:03d}",
        "type": "commitment",
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at,
        "source": source,
        "description": description,
        "due": due,
        "status": "pending",
    }

    data["appointments"].append(appointment)
    save_appointments(data)

    # If manual appointment, pause auto-scheduler
    if source == "ai_proposal" or source == "user":
        sched_module.pause_scheduler()
        print(f"[Scheduler paused for appointment: {appointment['id']}]")

    return appointment


def get_pending_appointments() -> list:
    data = load_appointments()
    now = datetime.now()
    pending = []
    for appt in data.get("appointments", []):
        if appt["status"] == "pending" and datetime.fromisoformat(appt["due"]) <= now:
            pending.append(appt)
    return pending


def schedule_random_check():
    data = load_appointments()
    hours = random.choice(RANDOM_INTERVALS)
    due = datetime.now() + timedelta(hours=hours)
    data["random_check"] = {
        "last_scheduled": datetime.now().isoformat(),
        "next_due": due.isoformat(),
        "interval_planned": hours,
    }
    save_appointments(data)
    return due


# ==================== PROACTIVE ====================


def auto_trigger_handler(reason):
    """Called when auto-scheduler triggers a conversation."""
    print("\n[Auto-triggered: {}]".format(reason))
    msg = trigger_conversation()
    print(f"\nSebastian: {msg}")
    save_conversation("[AUTO TRIGGER - {}]".format(reason), msg)


def background_scheduler():
    """Background thread that checks for due appointments/events.
    
    Uses direct polling approach (like original) - simpler and more reliable.
    The check_and_trigger() function handles both appointments and random checks.
    """
    while True:
        if sched_module.is_enabled():
            sched_module.check_and_trigger(auto_trigger_handler)
        
        # Sleep for configured interval (from .env or default 5 minutes)
        interval = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", 5))
        time.sleep(interval * 60)


def trigger_conversation() -> str:
    """Generate a proactive conversation starter using random intent."""
    intent = get_random_intent()
    context = get_conversation_context(num_recent=5)

    if context:
        context_str = "\n".join([f"{m['role']}: {m['content']}" for m in context[-5:]])
    else:
        context_str = "No recent context available."

    prompt = TRIGGER_CONVERSATION_PROMPT.format(intent=intent, context=context_str)

    try:
        response = send_to_ollama(prompt)

        # Try to parse time from response using advanced parser
        due = parse_response_for_time(response)

        if due:
            create_appointment("ai_proposal", response[:50], due.isoformat())
            print(f"[Appointment created: {due.strftime('%Y-%m-%d %H:%M')}]")

        return response
    except Exception as e:
        return f"I've been thinking about you. How are you doing?"


# ==================== MAIN ====================


def main():
    ensure_memory_dir()

    print("=" * 50)
    print("    SEBASTIAN - Proactive AI Companion")
    print("=" * 50)
    print()
    print("Commands:")
    print("  trigger    - Trigger proactive conversation")
    print("  pause     - Pause auto-scheduler")
    print("  resume    - Resume auto-scheduler")
    print("  interval X - Set check interval to X minutes")
    print("  status    - Show appointments status")
    print("  clear-schedule - Clear scheduled appointments")
    print("  clear-all  - Clear all data")
    print("  memory status - Show memory statistics")
    print("  medium memory - Load medium memory context")
    print("  long memory  - Load long-term memory context")
    print("  cue        - Show random cue (for testing)")
    print("  cue X     - Get cue from category X")
    print("  trigger cue - Force cue, then type your message")
    print("  model X   - Switch model (phi4, gemma4)")
    print("  menu      - Show this commands menu")
    print("  clear     - Clear screen")
    print("  kill      - Cancel long-running Ollama request")
    print("  quit      - Exit")
    print()

    interval = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "5"))
    
    # Initialize automatic schedule on launch - clears stale random_check
    sched_module.initialize_automatic_schedule()
    
    auto_enabled = os.getenv("AUTOMATIC_ENABLED", "false").lower() == "true"

    print(f"[Scheduler: {interval}min interval, auto={auto_enabled}]")
    if TEST_MODE:
        print("[TEST MODE: enabled - rapid triggering]")

    if auto_enabled:
        # Start background scheduler thread
        thread = threading.Thread(target=background_scheduler, daemon=True)
        thread.start()

    while True:
        # Check due appointments immediately on each iteration
        sched_module.check_and_trigger(auto_trigger_handler)

        user_input = input("\nYou: ").strip()

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd == "quit" or cmd == "exit":
            print("\nSebastian: Talk soon!")
            # Clear session context when quitting (thread-safe)
            with _session_context_lock:
                _session_context = None
            break

        if cmd == "clear":
            print("\033[2J\033[H")
            print("=" * 50)
            print("    SEBASTIAN")
            print("=" * 50)
            continue

        if cmd == "kill":
            _ollama_request_cancelled = True
            print("[Ollama request cancelled]")
            continue

        if cmd == "menu":
            print()
            print("=" * 50)
            print("    SEBASTIAN - Commands")
            print("=" * 50)
            print("  trigger    - Trigger proactive conversation")
            print("  pause     - Pause auto-scheduler")
            print("  resume    - Resume auto-scheduler")
            print("  interval X - Set check interval to X minutes")
            print("  status    - Show appointments status")
            print("  clear-schedule - Clear scheduled appointments")
            print("  clear-all  - Clear all data")
            print("  memory status - Show memory statistics")
            print("  medium memory - Load medium memory context")
            print("  long memory  - Load long-term memory context")
            print("  cue        - Show random cue (for testing)")
            print("  cue X     - Get cue from category X")
            print("  trigger cue - Force cue, then type your message")
            print("  model X   - Switch model (phi4, gemma4)")
            print("  menu      - Show this commands menu")
            print("  clear     - Clear screen")
            print("  kill      - Cancel long-running Ollama request")
            print("  quit      - Exit")
            print()
            continue

        if cmd.startswith("model "):
            new_model = cmd.split(" ", 1)[1].strip().lower()
            # Map short names to full model names
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

        if cmd == "status":
            appt = get_pending_appointments()
            data = load_appointments()
            pending = [
                a for a in data.get("appointments", []) if a["status"] == "pending"
            ]

            print(f"\n[Status]")
            print(f"  Appointments due: {len(appt)}")
            print(f"  Pending: {len(pending)}")
            print(
                f"  Scheduler: interval={interval}min, auto={sched_module.is_enabled()}"
            )

            if pending:
                print("  Pending appointments:")
                for a in pending[:3]:
                    print(f"    - {a['description'][:40]}... (due: {a['due'][:16]})")
            continue

        if cmd == "trigger":
            print("\n[Triggering conversation...]")
            msg = trigger_conversation()
            print(f"\nSebastian: {msg}")
            save_conversation("[Trigger Conversation]", msg)
            schedule_random_check()
            continue

        if cmd == "pause":
            sched_module.pause_scheduler()
            print("[Scheduler paused]")
            continue

        if cmd == "resume":
            sched_module.resume_scheduler(auto_trigger_handler)
            print("[Scheduler resumed]")
            continue

        if cmd == "trigger cue":
            # Force cue then wait for user message
            cue_code, cue_text, is_combo = get_random_cue(single_only=False)
            combo_str = " (COMBO)" if is_combo else ""
            print(f"\n[Cue ready: {cue_code}]{combo_str}")
            print(f"  {cue_text}")
            print("\nType your message...")
            user_msg = input("\nYou: ").strip()
            if user_msg:
                # Send message with cue prepended to user message
                cue_instruction = f"We are doing an impersonation game.\nPlay this character in your response: {cue_code}: {cue_text}\nmy message: {user_msg}"
                merged_context = (
                    _loaded_memory["medium"]
                    + _loaded_memory["longterm"]
                    + get_fresh_context()
                )
                messages = merged_context + [
                    {"role": "user", "content": cue_instruction}
                ]
                response = send_to_ollama_with_context(messages)
                print(f"\nSebastian: {response}")
                save_conversation(user_msg, response)
            continue

        if cmd.startswith("interval "):
            try:
                mins = int(cmd.split()[1])
                sched_module.set_interval(mins, auto_trigger_handler)
                interval = mins
                print(f"[Scheduler interval set to {mins} minutes]")
            except (IndexError, ValueError):
                print("[Usage: interval X where X is minutes]")
            continue

        if cmd == "clear-schedule":
            data = load_appointments()
            data["appointments"] = []
            save_appointments(data)
            sched_module.resume_scheduler(auto_trigger_handler)
            print("[All appointments cleared, scheduler resumed]")
            continue

        if cmd == "clear-all":
            # Clear appointments
            save_appointments({"appointments": [], "random_check": None})
            # Clear memory
            for f in ["fresh.json", "medium.json", "longterm.json"]:
                filepath = os.path.join(MEMORY_DIR, f)
                with open(filepath, "w") as fp:
                    json.dump([], fp)
            # Clear session context (Ollama context array)
            _session_context = None
            sched_module.resume_scheduler(auto_trigger_handler)
            print("[All data cleared, scheduler resumed]")
            continue

        if cmd == "memory status":
            stats = get_memory_status()
            print(f"\n[Memory Status]")
            print(f"  Fresh: {stats['fresh']} entries")
            print(f"  Medium: {stats['medium']} entries")
            print(f"  Long-term: {stats['longterm']} entries")
            continue

        if cmd == "medium memory":
            context = get_medium_context()
            if not context:
                print("[No medium memory available]")
                _loaded_memory["medium"] = []
            else:
                _loaded_memory["medium"] = context
                print(f"\n[Loaded {len(context)} medium memory entries]")
                print("  (Will be included in next chat)")
            continue

        if cmd == "long memory":
            context = get_longterm_context()
            if not context:
                print("[No long-term memory available]")
                _loaded_memory["longterm"] = []
            else:
                _loaded_memory["longterm"] = context
                print(f"\n[Loaded {len(context)} long-term memory entries]")
                print("  (Will be included in next chat)")
            continue

        if cmd == "cue":
            # Show a random cue
            if CUE_ENABLED:
                code, text, is_combo = get_random_cue(single_only=False)
                combo_str = " (COMBO)" if is_combo else ""
                print(f"\n[Cue: {code}]{combo_str}")
                print(f"  {text}")
            else:
                print("[Cue system disabled]")
            continue

        if cmd.startswith("cue "):
            # Get cue from category
            category = cmd.split(" ", 1)[1]
            if CUE_ENABLED:
                code, text = get_cue_by_category(category)
                if code:
                    print(f"\n[Cue: {code}]")
                    print(f"  {text}")
                else:
                    print(f"[Category not found: {category}]")
            else:
                print("[Cue system disabled]")
            continue

        # Normal chat
        merged_context = (
            _loaded_memory["medium"] + _loaded_memory["longterm"] + get_fresh_context()
        )

        # Check for trigger cue (20% chance)
        cue_code = ""
        cue_applied = False

        if CUE_ENABLED and random.random() < CUE_PROBABILITY:
            cue_code, cue_text, is_combo = get_random_cue(single_only=False)
            if cue_code:
                cue_applied = True
                print(f"\n[Cue applied: {cue_code}]")

        try:
            # Build conversation with optional cue instruction
            if cue_applied:
                # Cue prepended to user message
                cue_instruction = f"We are doing an impersonation game.\nPlay this character in your response: {cue_code}: {cue_text}\nmy message: {user_input}"
                messages = merged_context + [
                    {"role": "user", "content": cue_instruction}
                ]
                response = send_to_ollama_with_context(messages)
            else:
                response = send_to_ollama(user_input, merged_context)

            print(f"\nSebastian: {response}")

            # Check if response contains time reference → create appointment
            due = parse_response_for_time(response)
            if due:
                create_appointment("ai_proposal", response[:50], due.isoformat())
                print(f"[Appointment created: {due.strftime('%Y-%m-%d %H:%M')}]")

            # Save
            save_conversation(user_input, response)
            save_last_interaction(datetime.now().isoformat())
            state = load_state()
            state["last_interaction_time"] = time.time()
            save_state(state)

        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
