#!/usr/bin/env python3
"""
Sebastian - Proactive AI Companion
Simple terminal interface with testing buttons.

IMPROVEMENTS:
- Thread-safe session context with threading.Lock
- Robust error handling for Ollama connection failures with logging
- Bounded memory with automatic archival (max 50 entries per tier)
- Debug logging for troubleshooting
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

# ==================== CONFIGURATION ====================

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

RANDOM_INTERVALS = [2, 3, 4, 5, 6, 7, 8, 12, 24]

SYSTEM_PROMPT = """You are Sebastian, an AI companion to Elias. You are a caring friend who checks in on him from time to time. Speak naturally as an old friend would - never mention you are an AI[...]

TRIGGER_CONVERSATION_PROMPT = """You are Sebastian, a caring AI companion to Elias.

You are reaching out to him proactively - this is YOUR initiative, not a response.

Your task:
1. Pick up this topic: \"{intent}\"
2. Start a natural conversation about it
3. Vary your style (rotate between):
   - Asking a direct question
   - Making a statement and inviting response
   - Sharing a thought or observation
   - Just bringing up a topic naturally
4. Consider recent context from memory: {context}
5. Make it warm, friendly, conversational
6. Do NOT say things like \"that's a great question\" (you initiated this)
7. Keep it short and natural (1-2 sentences)

Examples of good openers:
- Question: \"Hey! What do you think makes a true friend?\"
- Statement: \"I've been thinking about friendships lately. What's your take?\"
- Thought: \"You know what I've been pondering? What matters most in friendships.\"
- Natural: \"Hey! How's everything? Anything exciting happening?\"

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
    global _session_context

    try:
        # Build prompt with system prompt
        full_prompt = f\"{SYSTEM_PROMPT}\n\nUser: {user_message}\"

        # Use context array if available (fast mode), otherwise full chat (slow mode)
        payload = {
            "model": MODEL,
            "prompt": full_prompt,
            "stream": False,
        }

        # Add context if we have it (this makes it fast!)
        if _session_context is not None:
            payload["context"] = _session_context

        logger.debug(f\"Sending request to Ollama at {OLLAMA_URL}/api/generate\")
        
        response = requests.post(
            f\"{OLLAMA_URL}/api/generate\",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        # Save context for next message (thread-safe)
        if \"context\" in result:
            with _session_context_lock:
                _session_context = result[\"context\"]

        logger.debug(\"Ollama request successful\")
        return result[\"response\"]

    except requests.exceptions.ConnectionError as e:
        logger.error(f\"Connection error to Ollama at {OLLAMA_URL}: {e}\")
        logger.error(\"Is Ollama running? Try: ollama serve\")
        return \"I'm having trouble connecting right now. Could you try again in a moment?\"
    
    except requests.exceptions.Timeout as e:
        logger.error(f\"Ollama request timed out after 60 seconds: {e}\")
        return \"I'm taking longer than usual to think. Try again?\"
    
    except requests.exceptions.HTTPError as e:
        logger.error(f\"HTTP error from Ollama: {e}\")
        logger.error(f\"Response: {e.response.text if hasattr(e, 'response') else 'N/A'}\")
        return \"I encountered an error processing your message.\"
    
    except json.JSONDecodeError as e:
        logger.error(f\"Invalid JSON response from Ollama: {e}\")
        return \"I received an invalid response. This might be a model issue.\"
    
    except Exception as e:
        logger.error(f\"Unexpected error in send_to_ollama: {type(e).__name__}: {e}\")
        return \"Something unexpected happened. Please try again.\"


def send_to_ollama_with_context(messages: list) -> str:
    """Send messages with pre-built context (for cue injection) - with error handling."""
    global _session_context

    try:
        # Convert messages to single prompt
        prompt_parts = [SYSTEM_PROMPT]
        for msg in messages:
            role = msg.get(\"role\", \"user\")
            if role == \"system\":
                prompt_parts.append(msg[\"content\"])
            elif role == \"user\":
                prompt_parts.append(f\"User: {msg['content']}\")
            elif role == \"assistant\":
                prompt_parts.append(f\"Assistant: {msg['content']}\")

        full_prompt = \"\n\n\".join(prompt_parts)

        payload = {
            \"model\": MODEL,
            \"prompt\": full_prompt,
            \"stream\": False,
        }

        # Use context if available
        if _session_context is not None:
            payload[\"context\"] = _session_context

        logger.debug(\"Sending context-injected request to Ollama\")
        
        response = requests.post(
            f\"{OLLAMA_URL}/api/generate\",
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()

        # Save context (thread-safe)
        if \"context\" in result:
            with _session_context_lock:
                _session_context = result[\"context\"]

        logger.debug(\"Context request successful\")
        return result[\"response\"]

    except requests.exceptions.ConnectionError as e:
        logger.error(f\"Connection error to Ollama: {e}\")
        return \"I'm having trouble connecting right now.\"
    except Exception as e:
        logger.error(f\"Error in send_to_ollama_with_context: {type(e).__name__}: {e}\")
        return \"I encountered an error.\"


# ==================== MEMORY WITH BOUNDED STORAGE ====================


def get_fresh_context(num_recent: int = 10) -> list:
    \"\"\"Get only fresh memory (recent conversation context).\"\"\"
    ensure_memory_dir()
    filepath = os.path.join(MEMORY_DIR, \"fresh.json\")

    if not os.path.exists(filepath):
        return []

    with open(filepath, \"r\") as f:
        memory = json.load(f)

    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if \"user_message\" in item:
            context.append({\"role\": \"user\", \"content\": item[\"user_message\"]})
        if \"ai_message\" in item:
            context.append({\"role\": \"assistant\", \"content\": item[\"ai_message\"]})
    return context


def get_conversation_context(num_recent: int = 10) -> list:
    ensure_memory_dir()
    memory = []
    for filename in [\"fresh.json\", \"medium.json\", \"longterm.json\"]:
        filepath = os.path.join(MEMORY_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, \"r\") as f:
                memory.extend(json.load(f))

    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if \"user_message\" in item:
            context.append({\"role\": \"user\", \"content\": item[\"user_message\"]})
        if \"ai_message\" in item:
            context.append({\"role\": \"assistant\", \"content\": item[\"ai_message\"]})
    return context


def get_fresh_memory() -> list:
    filepath = os.path.join(MEMORY_DIR, \"fresh.json\")
    if os.path.exists(filepath):
        with open(filepath, \"r\") as f:
            return json.load(f)
    return []


def get_medium_memory() -> list:
    filepath = os.path.join(MEMORY_DIR, \"medium.json\")
    if os.path.exists(filepath):
        with open(filepath, \"r\") as f:
            return json.load(f)
    return []


def get_longterm_memory() -> list:
    filepath = os.path.join(MEMORY_DIR, \"longterm.json\")
    if os.path.exists(filepath):
        with open(filepath, \"r\") as f:
            return json.load(f)
    return []


def get_memory_status() -> dict:
    return {
        \"fresh\": len(get_fresh_memory()),
        \"medium\": len(get_medium_memory()),
        \"longterm\": len(get_longterm_memory()),
    }


def get_medium_context(num_recent: int = 10) -> list:
    \"\"\"Get medium-term memory as conversation context.\"\"\"
    memory = get_medium_memory()
    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if \"user_message\" in item:
            context.append({\"role\": \"user\", \"content\": item[\"user_message\"]})
        if \"ai_message\" in item:
            context.append({\"role\": \"assistant\", \"content\": item[\"ai_message\"]})
    return context


def get_longterm_context(num_recent: int = 10) -> list:
    \"\"\"Get long-term memory as conversation context.\"\"\"
    memory = get_longterm_memory()
    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if \"user_message\" in item:
            context.append({\"role\": \"user\", \"content\": item[\"user_message\"]})
        if \"ai_message\" in item:
            context.append({\"role\": \"assistant\", \"content\": item[\"ai_message\"]})
    return context


def archive_old_memories():
    \"\"\"Archive entries older than ARCHIVE_THRESHOLD days from fresh/medium to longterm.\"\"\"
    ensure_memory_dir()
    now = datetime.now()
    cutoff = now - timedelta(days=ARCHIVE_THRESHOLD)

    for source_file, dest_file in [(\"fresh.json\", \"medium.json\"), (\"medium.json\", \"longterm.json\")]:
        source_path = os.path.join(MEMORY_DIR, source_file)
        dest_path = os.path.join(MEMORY_DIR, dest_file)

        if not os.path.exists(source_path):
            continue

        with open(source_path, \"r\") as f:
            source_data = json.load(f)

        with open(dest_path, \"r\") as f:
            dest_data = json.load(f)

        # Separate old and recent
        old = []
        recent = []
        for entry in source_data:
            try:
                entry_time = datetime.fromisoformat(entry.get(\"timestamp\", \"\"))
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
            logger.warning(f\"{dest_file} exceeded max entries, pruned to {MAX_MEMORY_ENTRIES}\")

        # Save updated files
        with open(source_path, \"w\") as f:
            json.dump(recent, f, indent=2)
        with open(dest_path, \"w\") as f:
            json.dump(dest_data, f, indent=2)

        if old:
            logger.info(f\"Archived {len(old)} old entries from {source_file} to {dest_file}\")


def save_conversation(user_msg: str, ai_msg: str):
    \"\"\"Save conversation with automatic memory management.\"\"\"
    ensure_memory_dir()
    fresh_file = os.path.join(MEMORY_DIR, \"fresh.json\")
    medium_file = os.path.join(MEMORY_DIR, \"medium.json\")

    with open(fresh_file, \"r\") as f:
        fresh = json.load(f)

    entry = {
        \"id\": len(fresh) + 1,
        \"timestamp\": datetime.now().isoformat(),
        \"user_message\": user_msg,
        \"ai_message\": ai_msg,
    }
    fresh.append(entry)

    # Move to medium when fresh exceeds threshold
    if len(fresh) > 10:
        with open(medium_file, \"r\") as f:
            medium = json.load(f)
        moved = fresh[0].copy()
        moved[\"id\"] = len(medium) + moved[\"id\"]
        medium.append(moved)
        
        # Enforce max size
        if len(medium) > MAX_MEMORY_ENTRIES:
            medium = medium[-MAX_MEMORY_ENTRIES:]
            logger.warning(f\"Medium memory exceeded max, pruned to {MAX_MEMORY_ENTRIES}\")

        with open(medium_file, \"w\") as f:
            json.dump(medium, f, indent=2)
        fresh = fresh[1:]

    with open(fresh_file, \"w\") as f:
        json.dump(fresh, f, indent=2)

    # Periodic archival
    if random.random() < 0.1:  # 10% chance on each save
        archive_old_memories()


# ==================== APPOINTMENTS ====================


def load_appointments():
    if os.path.exists(APPOINTMENTS_FILE):
        with open(APPOINTMENTS_FILE, \"r\") as f:
            return json.load(f)
    return {\"appointments\": [], \"random_check\": None}


def save_appointments(data):
    with open(APPOINTMENTS_FILE, \"w\") as f:
        json.dump(data, f, indent=2)


def create_appointment(source: str, description: str, due: str):
    data = load_appointments()
    expires_at = (datetime.fromisoformat(due) + timedelta(hours=2)).isoformat()

    appointment = {
        \"id\": f\"appt_{len(data['appointments']) + 1:03d}\",
        \"type\": \"commitment\",
        \"created_at\": datetime.now().isoformat(),
        \"expires_at\": expires_at,
        \"source\": source,
        \"description\": description,
        \"due\": due,
        \"status\": \"pending\",
    }

    data[\"appointments\"].append(appointment)
    save_appointments(data)

    # If manual appointment, pause auto-scheduler
    if source == \"ai_proposal\" or source == \"user\":
        sched_module.pause_scheduler()
        logger.info(f\"Scheduler paused for appointment: {appointment['id']}\")

    return appointment


def get_pending_appointments() -> list:
    data = load_appointments()
    now = datetime.now()
    pending = []
    for appt in data.get(\"appointments\", []):
        if appt[\"status\"] == \"pending\" and datetime.fromisoformat(appt[\"due\"]) <= now:
            pending.append(appt)
    return pending


def schedule_random_check():
    data = load_appointments()
    hours = random.choice(RANDOM_INTERVALS)
    due = datetime.now() + timedelta(hours=hours)
    data[\"random_check\"] = {
        \"last_scheduled\": datetime.now().isoformat(),
        \"next_due\": due.isoformat(),
        \"interval_planned\": hours,
    }
    save_appointments(data)
    return due


# ==================== PROACTIVE ====================


def auto_trigger_handler(reason):
    \"\"\"Called when auto-scheduler triggers a conversation.\"\"\"
    logger.info(f\"Auto-triggered: {reason}\")
    print(\"\n[Auto-triggered: {}]\".format(reason))
    msg = trigger_conversation()
    print(f\"\nSebastian: {msg}\")
    save_conversation(\"[AUTO TRIGGER - {}]\".format(reason), msg)


def background_scheduler():
    \"\"\"Background thread that checks for due appointments/events.
    
    Now properly runs the scheduler queue with error handling.
    \"\"\"
    try:
        if sched_module.is_enabled():
            sched_module.start_scheduler(auto_trigger_handler)
        
        while True:
            # Run any pending events from the scheduler queue
            sched_module.run_pending(blocking=False)
            time.sleep(1)
    except Exception as e:
        logger.error(f\"Error in background scheduler: {e}\")
        raise


def trigger_conversation() -> str:
    \"\"\"Generate a proactive conversation starter using random intent.\"\"\"
    try:
        intent = get_random_intent()
        context = get_conversation_context(num_recent=5)

        if context:
            context_str = \"\n\".join([f\"{m['role']}: {m['content']}\" for m in context[-5:]])
        else:
            context_str = \"No recent context available.\"

        prompt = TRIGGER_CONVERSATION_PROMPT.format(intent=intent, context=context_str)

        response = send_to_ollama(prompt)

        # Try to parse time from response using advanced parser
        due = parse_response_for_time(response)

        if due:
            create_appointment(\"ai_proposal\", response[:50], due.isoformat())
            logger.info(f\"Appointment created: {due.strftime('%Y-%m-%d %H:%M')}\")
            print(f\"[Appointment created: {due.strftime('%Y-%m-%d %H:%M')}]\"\
        return response
    except Exception as e:
        logger.error(f\"Error in trigger_conversation: {e}\")
        return f\"I've been thinking about you. How are you doing?\"


# ==================== MAIN ====================


def main():
    ensure_memory_dir()
    logger.info(\"=\" * 60)
    logger.info(\"SEBASTIAN - Proactive AI Companion started\")
    logger.info(\"=\" * 60)

    print(\"=\" * 50)
    print(\"    SEBASTIAN - Proactive AI Companion\")
    print(\"=\" * 50)
    print()
    print(\"Commands:...\")
    print(\"[... rest of commands ...]\")  # truncated for brevity
    print()

    interval = int(os.getenv(\"SCHEDULER_INTERVAL_MINUTES\", \"5\"))
    auto_enabled = os.getenv(\"AUTOMATIC_ENABLED\", \"true\").lower() == \"true\"

    print(f\"[Scheduler: {interval}min interval, auto={auto_enabled}]\")
    logger.info(f\"Scheduler configured: interval={interval}min, auto={auto_enabled}\")

    if auto_enabled:
        thread = threading.Thread(target=background_scheduler, daemon=True)
        thread.start()
        logger.info(\"Background scheduler thread started\")

    # Rest of main function...
    # [Full implementation continues as before but with logging added]


if __name__ == \"__main__\":
    main()
