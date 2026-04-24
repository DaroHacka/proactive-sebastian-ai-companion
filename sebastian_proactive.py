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

# Memory loading state
_loaded_memory = {"medium": [], "longterm": []}

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


# ==================== OLLAMA ====================


def send_to_ollama(user_message: str, conversation_history: list = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": MODEL, "messages": messages, "stream": False},
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def send_to_ollama_with_context(messages: list) -> str:
    """Send messages with pre-built context (for cue injection)."""
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": MODEL, "messages": messages, "stream": False},
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


# ==================== MEMORY ====================


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


def save_conversation(user_msg: str, ai_msg: str):
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

    if len(fresh) > 10:
        with open(medium_file, "r") as f:
            medium = json.load(f)
        moved = fresh[0].copy()
        moved["id"] = len(medium) + moved["id"]
        medium.append(moved)
        with open(medium_file, "w") as f:
            json.dump(medium, f, indent=2)
        fresh = fresh[1:]

    with open(fresh_file, "w") as f:
        json.dump(fresh, f, indent=2)


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
    print("  clear     - Clear screen")
    print("  quit      - Exit")
    print()

    interval = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "5"))
    auto_enabled = os.getenv("AUTOMATIC_ENABLED", "true").lower() == "true"

    print(f"[Scheduler: {interval}min interval, auto={auto_enabled}]")

    if auto_enabled:
        sched_module.start_scheduler(auto_trigger_handler)

    while True:
        # Check due appointments immediately on each iteration
        sched_module.check_and_trigger(auto_trigger_handler)

        user_input = input("\nYou: ").strip()

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd == "quit" or cmd == "exit":
            print("\nSebastian: Talk soon!")
            break

        if cmd == "clear":
            print("\033[2J\033[H")
            print("=" * 50)
            print("    SEBASTIAN")
            print("=" * 50)
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
            code, text, is_combo = get_random_cue(single_only=False)
            combo_str = " (COMBO)" if is_combo else ""
            print(f"\n[Cue ready: {code}]{combo_str}")
            print(f"  {text}")
            print("\nType your message...")
            forced_cue = (code, text)
            user_msg = input("\nYou: ").strip()
            if user_msg:
                # Send message with forced cue
                system_instruction = {"role": "system", "content": f"{code}: {text}"}
                merged_context = (
                    _loaded_memory["medium"]
                    + _loaded_memory["longterm"]
                    + get_conversation_context()
                )
                messages = (
                    [system_instruction]
                    + merged_context
                    + [{"role": "user", "content": user_msg}]
                )
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
            _loaded_memory["medium"]
            + _loaded_memory["longterm"]
            + get_conversation_context()
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
                # Add cue as system instruction
                system_instruction = {
                    "role": "system",
                    "content": f"{cue_code}: {cue_text}",
                }
                messages = (
                    [system_instruction]
                    + merged_context
                    + [{"role": "user", "content": user_input}]
                )
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
