"""
Sebastian Scheduler Module
Background scheduler using Python's sched module.
"""

import os
import sched
import time
import json
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

APPOINTMENTS_FILE = "appointments.json"

RANDOM_INTERVALS = [2, 3, 4, 5, 6, 7, 8, 12, 24]

scheduler = sched.scheduler(time.time, time.sleep)
_auto_enabled = True
_last_trigger_time = None


def load_appointments():
    if os.path.exists(APPOINTMENTS_FILE):
        with open(APPOINTMENTS_FILE, "r") as f:
            return json.load(f)
    return {"appointments": [], "random_check": None}


def save_appointments(data):
    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_pending_appointments():
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


def check_and_trigger(on_trigger_callback):
    """
    Check if any appointments or random checks are due.
    If so, call the callback with the trigger reason.
    Respects minimum 60-second gap between triggers.
    """
    global _auto_enabled, _last_trigger_time

    if not _auto_enabled:
        return

    # Check minimum gap
    if _last_trigger_time and (time.time() - _last_trigger_time) < 60:
        return

    now = datetime.now()

    pending = get_pending_appointments()
    if pending:
        reason = "appointment"
        on_trigger_callback(reason)
        _last_trigger_time = time.time()

        # Mark appointment as completed
        data = load_appointments()
        for appt in data.get("appointments", []):
            if (
                appt["status"] == "pending"
                and datetime.fromisoformat(appt["due"]) <= now
            ):
                appt["status"] = "completed"
        save_appointments(data)

        # Check if more appointments pending - resume only if none left
        remaining = get_pending_appointments()
        if not remaining:
            resume_scheduler(on_trigger_callback)
            print("[Scheduler resumed - no more appointments]")

        schedule_random_check()
        reschedule_auto(on_trigger_callback)
        return

    data = load_appointments()
    random_check = data.get("random_check", {})
    if random_check and random_check.get("next_due"):
        next_due = datetime.fromisoformat(random_check["next_due"])
        if now >= next_due:
            reason = "random"
            on_trigger_callback(reason)
            _last_trigger_time = time.time()
            schedule_random_check()
            reschedule_auto(on_trigger_callback)
            return


def reschedule_auto(on_trigger_callback):
    """Schedule the next automatic check."""
    interval = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", 5)) * 60
    scheduler.enter(interval, 1, _tick, (on_trigger_callback,))


def _tick(on_trigger_callback):
    """Internal tick handler."""
    check_and_trigger(on_trigger_callback)
    reschedule_auto(on_trigger_callback)


def start_scheduler(on_trigger_callback):
    """Start the automatic scheduler."""
    reschedule_auto(on_trigger_callback)


def pause_scheduler():
    """Pause automatic scheduling."""
    global _auto_enabled
    _auto_enabled = False
    return True


def resume_scheduler(on_trigger_callback):
    """Resume automatic scheduling."""
    global _auto_enabled
    _auto_enabled = True
    reschedule_auto(on_trigger_callback)
    return True


def set_interval(minutes, on_trigger_callback):
    """Change the check interval."""
    os.environ["SCHEDULER_INTERVAL_MINUTES"] = str(minutes)
    if _auto_enabled:
        # Cancel all pending events
        for event in scheduler.queue[:]:
            scheduler.cancel(event)
        reschedule_auto(on_trigger_callback)
    return minutes


def is_enabled():
    """Check if auto-scheduling is enabled."""
    return _auto_enabled


def run_pending(blocking=False):
    """Run any pending scheduler events."""
    scheduler.run(blocking=blocking)
