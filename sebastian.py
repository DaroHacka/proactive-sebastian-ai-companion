#!/usr/bin/env python3
import os
import json
import time
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from webui_client import companion_chat, chat
from email_client import poll_for_new_emails, send_email
from intent_manager import get_intent_for_worry_level, get_worry_template
from memory_manager import add_memory, get_fresh_memory
from appointments import (
    create_appointment,
    schedule_random_check,
    get_pending_appointments,
    mark_appointment_complete,
    should_random_check,
    get_next_due_time,
    clear_old_appointments,
)
from commitment_parser import (
    parse_conversation_for_appointments,
    parse_response_for_appointment,
    calculate_due_time,
)

STATE_FILE = os.getenv("STATE_FILE", "state.json")
WORRY_THRESHOLD_HOURS = float(os.getenv("WORRY_THRESHOLD_HOURS", "3"))
USER_EMAIL = os.getenv("USER_EMAIL", "your_personal_email")

RANDOM_INTERVALS = [2, 3, 4, 5, 6, 7, 8, 12, 24]
INACTIVITY_CHECK_MINUTES = 30


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "last_response_time": None,
        "last_check_time": None,
        "worry_level": 0,
        "last_message_sent": None,
        "last_message_time": None,
        "last_conversation_time": None,
        "last_interaction_time": None,
        "last_appointment_check": None,
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def has_new_response(state):
    last_response_time = state.get("last_response_time")
    if last_response_time is None:
        last_check = state.get("last_check_time")
        if last_check is None:
            return True
        return False

    emails = poll_for_new_emails(since_timestamp=last_check)
    if emails:
        return True
    return False


def check_for_appointments() -> dict:
    """Check conversation for any scheduled appointments.

    Called after INACTIVITY_CHECK_MINUTES of no interaction.
    """
    now = datetime.now()
    now_iso = now.isoformat()
    print(f"[{now_iso}] Checking conversation for appointments...")

    appointment = parse_conversation_for_appointments()

    if appointment.get("has_commitment"):
        due = calculate_due_time(appointment)
        source = appointment.get("source", "ai_proposal")
        description = appointment.get(
            "description", appointment.get("natural_text", "")
        )
        natural = appointment.get("natural_text", description)

        if due:
            appt = create_appointment(source=source, description=description, due=due)
            print(f"[{now_iso}] Appointment created: {appt['id']} - {description}")
            print(f"[{now_iso}] Due: {due}")
            return appt

    print(f"[{now_iso}] No appointment found in conversation")
    return None


def run_proactive_check(state):
    now = time.time()
    now_iso = datetime.now().isoformat()

    last_check = state.get("last_check_time") or now
    state["last_check_time"] = now

    if has_new_response(state):
        state["last_response_time"] = now
        state["worry_level"] = 0
        save_state(state)
        print(f"[{now_iso}] User responded. Worry level reset.")
        return

    if state["last_response_time"] is None:
        save_state(state)
        print(f"[{now_iso}] No prior response time. Skipping.")
        return

    elapsed_hours = (now - state["last_response_time"]) / 3600

    if elapsed_hours < 2:
        save_state(state)
        print(f"[{now_iso}] Recent conversation {elapsed_hours:.1f}h ago. Skipping.")
        return

    pending_appointments = get_pending_appointments()
    if pending_appointments:
        for appt in pending_appointments:
            state["last_message_time"] = now
            state["last_message_sent"] = (
                f"Scheduled check: {appt.get('description', 'Check-in')}"
            )
            print(f"[{now_iso}] Fulfilling appointment: {appt['id']}")
            mark_appointment_complete(appt["id"])
            save_state(state)
            return

    if not should_random_check(state.get("last_message_time", now - 7200)):
        next_check = get_next_due_time()
        save_state(state)
        print(f"[{now_iso}] Next check scheduled: {next_check}")
        return

    next_interval = random.choice(RANDOM_INTERVALS)
    if state.get("last_message_time"):
        hours_since_msg = (now - state["last_message_time"]) / 3600
        if hours_since_msg < next_interval:
            next_check = datetime.fromtimestamp(state["last_message_time"]) + timedelta(
                hours=next_interval
            )
            save_state(state)
            print(f"[{now_iso}] Waiting for interval. Next: {next_check}")
            return

    worry_level = state.get("worry_level", 0)
    elapsed_hours_since_msg = None
    if state.get("last_message_time"):
        elapsed_hours_since_msg = (now - state["last_message_time"]) / 3600
        if elapsed_hours_since_msg < 2:
            save_state(state)
            print(
                f"[{now_iso}] Recent message sent ({elapsed_hours_since_msg:.1f}h ago). Skipping."
            )
            return

    worry_level = worry_level + 1
    state["worry_level"] = worry_level

    intent = get_intent_for_worry_level(worry_level)

    try:
        message = companion_chat(prompt=f"Current intent: {intent}", intent=intent)
    except Exception as e:
        message = get_worry_template(worry_level)
        print(f"[{now_iso}] Using fallback template: {e}")

    try:
        appointment_data = parse_response_for_appointment(message)
        has_appointment = appointment_data.get("has_commitment", False)

        if has_appointment:
            due = calculate_due_time(appointment_data)
            source = appointment_data.get("source", "ai_proposal")
            description = appointment_data.get(
                "description", appointment_data.get("natural_text", "")
            )

            if due:
                create_appointment(source=source, description=description, due=due)
                print(f"[{now_iso}] Appointment from proactive message: {due}")
    except Exception as e:
        print(f"[{now_iso}] Appointment parsing error (non-fatal): {e}")
        has_appointment = False

    if send_email(subject="Sebastian", body=message, to_address=USER_EMAIL):
        state["last_message_sent"] = message
        state["last_message_time"] = now
        print(
            f"[{now_iso}] Message sent (worry_level={worry_level}): {message[:50]}..."
        )

        appointment_data = parse_response_for_appointment(message)
        has_appointment = appointment_data.get("has_commitment", False)

        if not has_appointment:
            next_check_time = schedule_random_check()
            print(f"[{now_iso}] Random check scheduled: {next_check_time}")
    else:
        print(f"[{now_iso}] Failed to send email")

    save_state(state)


def run_conversation(user_message: str) -> str:
    now = time.time()
    now_iso = datetime.now().isoformat()

    state = load_state()
    state["last_interaction_time"] = now
    save_state(state)

    intent = get_intent_for_worry_level(0)

    try:
        ai_message = companion_chat(prompt=user_message, intent=intent)
    except Exception as e:
        print(f"[{now_iso}] Chat error: {e}")
        return get_worry_template(0)

    try:
        appointment = parse_response_for_appointment(ai_message)

        if appointment.get("has_commitment"):
            due = calculate_due_time(appointment)
            source = appointment.get("source", "ai_proposal")
            description = appointment.get(
                "description", appointment.get("natural_text", "")
            )

            if due:
                create_appointment(source=source, description=description, due=due)
                print(f"[{now_iso}] Appointment created from conversation: {due}")
    except Exception as e:
        print(f"[{now_iso}] Appointment parse error: {e}")

    add_memory(user_message=user_message, ai_message=ai_message)

    state["last_conversation_time"] = now
    state["last_message_time"] = now
    state["worry_level"] = 0
    save_state(state)

    return ai_message


def run_inactivity_check():
    """Check for appointments after inactivity period."""
    state = load_state()
    now = time.time()
    now_iso = datetime.now().isoformat()

    last_interaction = state.get("last_interaction_time")
    if last_interaction is None:
        print(f"[{now_iso}] No prior interaction. Skipping.")
        return

    minutes_inactive = (now - last_interaction) / 60

    if minutes_inactive < INACTIVITY_CHECK_MINUTES:
        print(f"[{now_iso}] Only {minutes_inactive:.1f} min inactive. Skipping.")
        return

    print(
        f"[{now_iso}] {minutes_inactive:.1f} min inactive. Checking for appointments..."
    )

    state["last_appointment_check"] = now

    check_for_appointments()

    if not should_random_check(last_interaction):
        next_check = get_next_due_time()
        print(f"[{now_iso}] Random check not due yet: {next_check}")
    else:
        next_check_time = schedule_random_check()
        print(f"[{now_iso}] Random check scheduled: {next_check_time}")

    save_state(state)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "conversation":
            user_msg = " ".join(sys.argv[2:])
            response = run_conversation(user_msg)
            print(f"Sebastian: {response}")
        elif sys.argv[1] == "inactivity":
            run_inactivity_check()
        else:
            run_proactive_check(load_state())
    else:
        run_proactive_check(load_state())
