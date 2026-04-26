"""
Sebastian Scheduler Module
Background scheduler using Python's sched module.

IMPROVEMENTS:
- Thread-safe appointment status updates
- Race condition fixes for concurrent access
- Test mode for faster triggering during development
"""

import os
import sched
import time
import json
import random
import threading
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

APPOINTMENTS_FILE = "appointments.json"

# Test mode: rapid triggering (every 5 min) vs production (2-24 hours)
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"

# Production: longer intervals for sparse proactive contacts
RANDOM_INTERVALS = [2, 3, 4, 5, 6, 7, 8, 12, 24]  # hours
# Test mode: shorter intervals
TEST_INTERVALS = [5, 5, 5, 10, 10, 15]  # minutes

scheduler = sched.scheduler(time.time, time.sleep)
_auto_enabled = True
_last_trigger_time = None
_appointments_lock = threading.Lock()  # Prevent race conditions


def initialize_automatic_schedule():
    """Initialize/reset automatic schedule on launch.
    
    Clears ONLY the automatic schedule (random_check), preserving:
    - Appointment reminders (created during chat)
    - Proactive schedule (in separate file)
    
    Then schedules a fresh check for immediate first trigger.
    """
    global _auto_enabled
    
    try:
        # Load current appointments file
        data = load_appointments()
        
        # Check if random_check exists and is stale
        random_check = data.get("random_check", {})
        
        cleared = False
        if random_check:
            # Clear ONLY random_check (automatic schedule)
            data["random_check"] = None
            cleared = True
        
        # Save back (without random_check)
        save_appointments(data)
        
        # Read AUTOMATIC_ENABLED from .env
        _auto_enabled = os.getenv("AUTOMATIC_ENABLED", "false").lower() == "true"
        
        if cleared:
            logger.info("Cleared stale automatic schedule")
        
        logger.info(f"Automatic scheduler initialized: enabled={_auto_enabled}")
        
        # Schedule fresh initial check (will fire on next background loop check)
        if _auto_enabled:
            schedule_random_check()
            logger.info(f"Scheduled initial check")
        
    except Exception as e:
        logger.error(f"Error initializing automatic schedule: {e}")


def load_appointments():
    if os.path.exists(APPOINTMENTS_FILE):
        with open(APPOINTMENTS_FILE, "r") as f:
            return json.load(f)
    return {"appointments": [], "random_check": None}


def save_appointments(data):
    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_pending_appointments():
    """Get pending appointments that are due.
    
    Auto-completes old pending appointments that are past due.
    Tracks completed count for info display.
    """
    data = load_appointments()
    now = datetime.now()
    pending = []
    completed_total = data.get("completed_count", 0)
    
    updated = False
    for appt in data.get("appointments", []):
        if appt["status"] == "pending":
            due_time = datetime.fromisoformat(appt["due"])
            if due_time <= now:
                # Auto-complete old pending appointments
                appt["status"] = "completed"
                completed_total += 1
                updated = True
            else:
                pending.append(appt)
    
    if updated:
        data["completed_count"] = completed_total
        save_appointments(data)
        logger.debug(f"Auto-completed old appointments. Total completed: {completed_total}")
    
    return pending


def get_completed_count():
    """Get total count of completed appointments."""
    data = load_appointments()
    return data.get("completed_count", 0)


def schedule_random_check():
    """Schedule the next random check.
    
    Test mode: short intervals (5-15 minutes)
    Production: longer intervals (2-24 hours)
    """
    data = load_appointments()
    
    if TEST_MODE:
        # Test mode: short intervals in minutes
        interval = random.choice(TEST_INTERVALS)
        due = datetime.now() + timedelta(minutes=interval)
        data["random_check"] = {
            "last_scheduled": datetime.now().isoformat(),
            "next_due": due.isoformat(),
            "interval_planned": interval,
            "interval_unit": "minutes",
            "mode": "test"
        }
        logger.info(f"Next random check scheduled: {due.strftime('%H:%M')} ({interval} min TEST mode)")
    else:
        # Production: longer intervals in hours
        interval = random.choice(RANDOM_INTERVALS)
        due = datetime.now() + timedelta(hours=interval)
        data["random_check"] = {
            "last_scheduled": datetime.now().isoformat(),
            "next_due": due.isoformat(),
            "interval_planned": interval,
            "interval_unit": "hours",
            "mode": "production"
        }
        logger.info(f"Next random check scheduled: {due.strftime('%H:%M')} ({interval}h)")
    
    save_appointments(data)
    return due


def check_and_trigger(on_trigger_callback):
    """
    Check if any appointments or random checks are due.
    If so, call the callback with the trigger reason.
    Respects minimum 60-second gap between triggers.
    
    FIXED: Uses lock to prevent race conditions on appointment status.
    """
    global _auto_enabled, _last_trigger_time

    if not _auto_enabled:
        return

    # Check minimum gap
    if _last_trigger_time and (time.time() - _last_trigger_time) < 60:
        return

    now = datetime.now()

    # FIXED: Atomic appointment check/mark with lock
    with _appointments_lock:
        pending = get_pending_appointments()
        if pending:
            reason = "appointment"
            on_trigger_callback(reason)
            _last_trigger_time = time.time()

            # Mark appointment as completed (atomic operation)
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
                logger.info("[Scheduler resumed - no more appointments]")

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
    """Schedule the next automatic check.
    
    For test mode: use short intervals
    For production: use configured interval (default 5 min) for the polling loop
    """
    if TEST_MODE:
        interval = 30  # Check every 30 seconds in test mode
    else:
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
    logger.info("Scheduler paused")
    return True


def resume_scheduler(on_trigger_callback):
    """Resume automatic scheduling."""
    global _auto_enabled
    _auto_enabled = True
    reschedule_auto(on_trigger_callback)
    logger.info("Scheduler resumed")
    return True


def set_interval(minutes, on_trigger_callback):
    """Change the check interval."""
    os.environ["SCHEDULER_INTERVAL_MINUTES"] = str(minutes)
    if _auto_enabled:
        # Cancel all pending events
        for event in scheduler.queue[:]:
            scheduler.cancel(event)
        reschedule_auto(on_trigger_callback)
    logger.info(f"Scheduler interval set to {minutes} minutes")
    return minutes


def is_enabled():
    """Check if auto-scheduling is enabled."""
    return _auto_enabled


def run_pending(blocking=False):
    """Run any pending scheduler events."""
    scheduler.run(blocking=blocking)
