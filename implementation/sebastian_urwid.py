#!/usr/bin/env python3
"""
Sebastian - Proactive AI Companion with urwid TUI
A graphical terminal interface using urwid.
"""

import urwid
import os
import json
import time
import random
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from intent_manager import get_random_intent

load_dotenv()

# Configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("COMPANION_MODEL", "phi4")
MEMORY_DIR = "memory"
STATE_FILE = "state.json"
LAST_INTERACTION_FILE = "last_interaction.json"
APPOINTMENTS_FILE = "appointments.json"

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

        text_lower = response.lower()
        if any(
            word in text_lower
            for word in [
                "tonight",
                "tomorrow",
                "later",
                "check in",
                "talk soon",
            ]
        ):
            due = datetime.now() + timedelta(hours=random.choice([2, 4, 24]))
            create_appointment("ai_proposal", response[:50], due.isoformat())

        return response
    except Exception as e:
        return f"I've been thinking about you. How are you doing?"


# ==================== URWID WIDGET ====================


class SebastianWidget:
    def __init__(self):
        self.messages = []

        # Header
        header = urwid.Pile(
            [
                urwid.Text("=" * 50),
                urwid.Text("    SEBASTIAN"),
                urwid.Text("    Your AI Companion"),
                urwid.Text("=" * 50),
                urwid.Divider(),
            ]
        )

        # Message area
        self.message_walker = urwid.SimpleListWalker([])
        self.message_list = urwid.ListBox(self.message_walker)

        # Buttons - single Trigger Conversation button
        btn_trigger = urwid.Button("[Trigger Conversation]", self.on_trigger)
        btn_status = urwid.Button("[Status]", self.on_status)
        btn_clear = urwid.Button("[Clear]", self.on_clear)

        buttons = urwid.Columns([btn_trigger, btn_status, btn_clear], 2)

        # Input
        self.input_edit = urwid.Edit("You: ")

        # Status
        self.status_text = urwid.Text("Ready | Type a message...")

        # Main layout
        self.pile = urwid.Pile(
            [
                header,
                self.message_list,
                urwid.Divider(),
                buttons,
                self.input_edit,
                self.status_text,
            ]
        )

        # Welcome
        self.add_message(
            "Sebastian",
            "Hey! I'm here. Type a message to chat, or use buttons to trigger proactive messages.",
        )

    def add_message(self, sender: str, text: str):
        widget = urwid.Text(f"{sender}: {text}")
        self.message_walker.append(widget)
        try:
            self.message_list.set_focus(len(self.message_walker) - 1)
        except:
            pass

    def set_status(self, text: str):
        self.status_text.set_text(text)

    def on_trigger(self, widget):
        self.set_status("Triggering conversation...")
        self.add_message("System", "[Triggering conversation...]")

        try:
            msg = trigger_conversation()
            self.add_message("Sebastian", msg)
            save_conversation("[Trigger Conversation]", msg)
            schedule_random_check()
            self.set_status(f"Last: {datetime.now().strftime('%H:%M')}")
        except Exception as e:
            self.add_message("System", f"Error: {e}")

    def on_status(self, widget):
        appt = get_pending_appointments()
        data = load_appointments()
        pending = [a for a in data.get("appointments", []) if a["status"] == "pending"]

        status_msg = f"Appointments due: {len(appt)} | Pending: {len(pending)}"
        self.add_message("System", status_msg)

    def on_clear(self, widget):
        self.message_walker[:] = []
        self.add_message("System", "Cleared!")

    def handle_input(self):
        text = self.input_edit.get_edit_text()
        if text.strip():
            self.add_message("You", text)
            self.input_edit.set_edit_text("")

            now = datetime.now().isoformat()
            save_last_interaction(now)

            try:
                context = get_conversation_context()
                response = send_to_ollama(text, context)
                self.add_message("Sebastian", response)

                save_conversation(text, response)

                text_lower = response.lower()
                if any(
                    word in text_lower
                    for word in [
                        "tonight",
                        "tomorrow",
                        "later",
                        "check in",
                        "talk soon",
                    ]
                ):
                    due = datetime.now() + timedelta(hours=random.choice([2, 4, 24]))
                    create_appointment("ai_proposal", response[:50], due.isoformat())
                    self.add_message(
                        "System", f"Appointment scheduled: {due.strftime('%H:%M')}"
                    )

                self.set_status(f"Last: {datetime.now().strftime('%H:%M')}")
            except Exception as e:
                self.add_message("Sebastian", f"Error: {e}")


def handle_key(key):
    if key == "enter":
        widget.handle_input()
        return True
    return False


def main():
    ensure_memory_dir()

    global widget
    widget = SebastianWidget()

    # Wrap properly
    fill = urwid.Filler(widget.pile, "top")

    # Try raw display with simple event handling
    try:
        from urwid import raw_display

        screen = raw_display.Screen()
        loop = urwid.MainLoop(fill, screen=screen, unhandled_input=handle_key)
        loop.run()
    except Exception:
        # Last resort - use curses display
        try:
            from urwid import curses_display

            screen = curses_display.CursesScreen()
            screen.set_terminal_properties(colors=256)
            loop = urwid.MainLoop(fill, screen=screen, unhandled_input=handle_key)
            loop.run()
        except Exception as e2:
            print(f"Cannot initialize terminal: {e2}")
            print("Falling back to simple mode...")
            # Run simple version instead
            import subprocess

            subprocess.run(["python3", "/home/daniel/AI/sebastian_proactive.py"])
    except Exception as e:
        # Fallback: just use basic display
        print("Note: Running in fallback mode")
        screen = urwid.raw_display.Screen()
        loop = urwid.MainLoop(fill, screen=screen, unhandled_input=handle_key)
        loop.run()


if __name__ == "__main__":
    widget = None
    main()
