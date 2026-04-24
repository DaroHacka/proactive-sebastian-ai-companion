#!/usr/bin/env python3
"""
Sebastian - Interactive TUI Chat
A clean terminal interface for chatting with Sebastian.
Uses Ollama directly (no Open WebUI dependency).
Guts are hidden - only shows AI responses.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Ollama configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("COMPANION_MODEL", "phi4")

STATE_FILE = os.getenv("STATE_FILE", "state.json")
LAST_INTERACTION_FILE = "last_interaction.json"
INACTIVITY_MINUTES = 30
MEMORY_DIR = "memory"


SYSTEM_PROMPT = """You are Sebastian, an AI companion to Elias.

You are a caring friend who checks in on him from time to time. 
You speak naturally as an old friend would - never mention you are an AI.

CONVERSATION STYLE:
- Keep responses short and conversational
- Be warm but not overly enthusiastic
- Listen actively and remember details he shares
- Be genuinely interested in his life

APPOINTMENTS:
- Sometimes you may suggest scheduling a check-in: "Let's talk again tomorrow evening"
- When you propose an appointment, acknowledge it will be tracked
- Not every conversation needs an appointment

Remember: You are a companion, not a tool. Build genuine connection."""


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_interaction_time": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def save_last_interaction(timestamp):
    with open(LAST_INTERACTION_FILE, "w") as f:
        json.dump({"timestamp": timestamp}, f)


def load_last_interaction():
    if os.path.exists(LAST_INTERACTION_FILE):
        with open(LAST_INTERACTION_FILE, "r") as f:
            data = json.load(f)
            return data.get("timestamp")
    return None


def send_to_ollama(user_message: str, conversation_history: list = None) -> str:
    """Send message to Ollama directly."""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history if provided
    if conversation_history:
        messages.extend(conversation_history)

    messages.append({"role": "user", "content": user_message})

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": MODEL, "messages": messages, "stream": False},
    )
    response.raise_for_status()

    return response.json()["message"]["content"]


def ensure_memory_dir():
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
        for f in ["fresh.json", "medium.json", "longterm.json"]:
            with open(os.path.join(MEMORY_DIR, f), "w") as fp:
                json.dump([], fp)


def load_memory() -> list:
    """Load all memories from files."""
    ensure_memory_dir()
    all_memory = []

    for filename in ["fresh.json", "medium.json", "longterm.json"]:
        filepath = os.path.join(MEMORY_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                all_memory.extend(json.load(f))

    return all_memory


def get_conversation_context(num_recent: int = 10) -> list:
    """Get recent conversation history for context."""
    memory = load_memory()

    if not memory:
        return []

    context = []
    for item in memory[-num_recent:]:
        if "user_message" in item:
            context.append({"role": "user", "content": item["user_message"]})
        if "ai_message" in item:
            context.append({"role": "assistant", "content": item["ai_message"]})

    return context


def load_key_facts() -> list:
    """Load key facts from memory."""
    facts = []
    ensure_memory_dir()

    for filename in ["fresh.json", "medium.json", "longterm.json"]:
        filepath = os.path.join(MEMORY_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                data = json.load(f)
                for item in data:
                    if "facts" in item:
                        for fact in item["facts"]:
                            facts.append(fact)

    return facts[-10:]


def extract_key_facts(conversation_text: str) -> list:
    """Prompt AI to extract key facts from conversation."""
    extract_prompt = f"""Extract key facts from this conversation as bullet points. 
Focus on: topics discussed, Elias's mood, things Elias mentioned about himself, any plans.

Conversation:
{conversation_text}

Output ONLY as bullet points starting with "- ". Example:
- Elias: Working on coding project
- Topic: AI companion
- Mood: Happy"""

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You extract key information from conversations.",
                    },
                    {"role": "user", "content": extract_prompt},
                ],
                "stream": False,
            },
        )

        text = response.json()["message"]["content"]

        facts = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("- "):
                facts.append(line[2:])
            elif line.startswith("-"):
                facts.append(line[1:])

        return facts if facts else []

    except Exception as e:
        print(f"Error extracting facts: {e}")
        return []


def save_key_facts(facts: list):
    """Save key facts to memory with aging."""
    ensure_memory_dir()

    fresh_file = os.path.join(MEMORY_DIR, "fresh.json")
    medium_file = os.path.join(MEMORY_DIR, "medium.json")

    # Load existing
    with open(fresh_file, "r") as f:
        fresh = json.load(f)

    # Add new entry
    fact_entry = {
        "id": len(fresh) + 1,
        "timestamp": datetime.now().isoformat(),
        "facts": facts,
    }
    fresh.append(fact_entry)

    # Age to medium if over 10
    if len(fresh) > 10:
        with open(medium_file, "r") as f:
            medium = json.load(f)

        # Move oldest 1 to medium
        moved = fresh[0]
        moved["id"] = len(medium) + 1
        medium.append(moved)

        with open(medium_file, "w") as f:
            json.dump(medium, f, indent=2)

        fresh = fresh[1:]

    with open(fresh_file, "w") as f:
        json.dump(fresh, f, indent=2)


def save_conversation(user_msg: str, ai_msg: str):
    """Save full conversation to memory."""
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

        moved = fresh[0]
        moved["id"] = len(medium) + moved["id"]
        medium.append(moved)

        with open(medium_file, "w") as f:
            json.dump(medium, f, indent=2)

        fresh = fresh[1:]

    with open(fresh_file, "w") as f:
        json.dump(fresh, f, indent=2)


def check_inactivity():
    """Check for inactivity and save key facts."""
    last_time = load_last_interaction()
    if not last_time:
        return

    last_dt = datetime.fromisoformat(last_time)
    now = datetime.now()
    minutes_inactive = (now - last_dt).total_seconds() / 60

    if minutes_inactive >= INACTIVITY_MINUTES:
        print(f"\n[Inactive for {int(minutes_inactive)} min. Saving context...]\n")

        context = get_conversation_context(num_recent=5)
        if context:
            # Convert to text for fact extraction
            text = ""
            for msg in context:
                text += f"{msg['role']}: {msg['content']}\n"

            facts = extract_key_facts(text)
            if facts:
                save_key_facts(facts)
                print(f"[Saved {len(facts)} key facts]")


def chat():
    print("=" * 44)
    print("           SEBASTIAN")
    print("    Your AI Companion")
    print("=" * 44)
    print()

    state = load_state()

    # Load key facts for context
    key_facts = load_key_facts()
    if key_facts:
        print("Recalling recent context...")
        for fact in key_facts[-3:]:
            print(f"  • {fact}")
        print()

    # Load conversation history
    history = get_conversation_context(num_recent=10)

    now = time.time()
    now_iso = datetime.now().isoformat()

    opening_prompt = (
        "Start a natural, caring conversation with Elias. Greet him warmly."
    )

    try:
        response = send_to_ollama(opening_prompt, history)
    except Exception as e:
        print(f"Error connecting to AI: {e}")
        print("\nMake sure Ollama is running: ollama serve")
        return

    while True:
        print(f"Sebastian: {response}")
        print()

        user_input = input("You: ").strip()

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "bye", "later"]:
            print("Talk soon!")
            break

        now = time.time()
        now_iso = datetime.now().isoformat()
        save_last_interaction(now_iso)

        state["last_interaction_time"] = now
        save_state(state)

        try:
            response = send_to_ollama(user_input, history)
        except Exception as e:
            print(f"Error: {e}")
            response = "Something went wrong. Try again?"

        # Save conversation
        save_conversation(user_input, response)

        # Update history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})

        print()


def run_inactivity_check():
    """Standalone: check inactivity and save facts."""
    check_inactivity()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "inactivity":
        run_inactivity_check()
    else:
        chat()
