import json
import os
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

APPOINTMENTS_FILE = os.getenv("APPOINTMENTS_FILE", "appointments.json")

MIN_INTERVAL_HOURS = 2
RANDOM_INTERVALS = [2, 3, 4, 5, 6, 7, 8, 12, 24]


def load_appointments() -> dict:
    if os.path.exists(APPOINTMENTS_FILE):
        with open(APPOINTMENTS_FILE, "r") as f:
            return json.load(f)
    return {
        "appointments": [],
        "random_check": {
            "last_scheduled": None,
            "next_due": None,
            "interval_hours": None,
        },
    }


def save_appointments(data: dict):
    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def create_appointment(
    source: str, description: str, due: str, expires_at: str = None
) -> dict:
    """Create a new appointment card.

    Args:
        source: "ai_proposal" or "user_request"
        description: What was agreed (e.g., "Talk this evening around 8pm")
        due: ISO datetime when due (e.g., "2025-01-20T20:00:00")
        expires_at: When the commitment expires (defaults to due + 2 hours)
    """
    data = load_appointments()

    if expires_at is None:
        due_dt = datetime.fromisoformat(due)
        expires_at = (due_dt + timedelta(hours=2)).isoformat()

    appointment_id = f"appt_{len(data['appointments']) + 1:03d}"

    appointment = {
        "id": appointment_id,
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


def schedule_random_check() -> datetime:
    """Schedule the next random check-in."""
    data = load_appointments()
    hours = random.choice(RANDOM_INTERVALS)
    due = datetime.now() + timedelta(hours=hours)

    data["random_check"] = {
        "last_scheduled": datetime.now().isoformat(),
        "next_due": due.isoformat(),
        "interval_hours": hours,
    }

    save_appointments(data)
    return due


def get_pending_appointments() -> list:
    """Get appointments that are due now."""
    data = load_appointments()
    now = datetime.now()

    pending = []
    for appt in data["appointments"]:
        if appt["status"] == "pending":
            due = datetime.fromisoformat(appt["due"])
            if due <= now:
                pending.append(appt)

    return pending


def get_upcoming_appointments() -> list:
    """Get all pending appointments sorted by due date."""
    data = load_appointments()
    pending = [a for a in data["appointments"] if a["status"] == "pending"]
    return sorted(pending, key=lambda a: a["due"])


def mark_appointment_complete(appointment_id: str):
    """Mark an appointment as completed."""
    data = load_appointments()

    for appt in data["appointments"]:
        if appt["id"] == appointment_id:
            appt["status"] = "completed"
            appt["completed_at"] = datetime.now().isoformat()
            break

    save_appointments(data)


def mark_appointment_cancelled(appointment_id: str):
    """Mark an appointment as cancelled."""
    data = load_appointments()

    for appt in data["appointments"]:
        if appt["id"] == appointment_id:
            appt["status"] = "cancelled"
            appt["cancelled_at"] = datetime.now().isoformat()
            break

    save_appointments(data)


def should_random_check(last_interaction_time: float) -> bool:
    """Check if we should do a random check.

    Args:
        last_interaction_time: Unix timestamp of last user interaction
    """
    data = load_appointments()

    random_check = data.get("random_check", {})
    if not random_check.get("next_due"):
        return True

    last_check = datetime.fromisoformat(random_check["next_due"])
    now = datetime.now()

    hours_since_last_msg = (
        now - datetime.fromtimestamp(last_interaction_time)
    ).total_seconds() / 3600

    if hours_since_last_msg < MIN_INTERVAL_HOURS:
        return False

    if now < last_check:
        return False

    return True


def get_next_due_time() -> datetime:
    """Get the next due appointment or random check."""
    data = load_appointments()

    pending_commitments = [
        a
        for a in data["appointments"]
        if a["type"] == "commitment" and a["status"] == "pending"
    ]

    if pending_commitments:
        next_commitment = min(
            pending_commitments, key=lambda a: datetime.fromisoformat(a["due"])
        )
        return datetime.fromisoformat(next_commitment["due"])

    if data.get("random_check", {}).get("next_due"):
        return datetime.fromisoformat(data["random_check"]["next_due"])

    return datetime.now() + timedelta(hours=random.choice(RANDOM_INTERVALS))


def clear_old_appointments(days: int = 7):
    """Remove completed/cancelled appointments older than N days."""
    data = load_appointments()
    cutoff = datetime.now() - timedelta(days=days)

    kept = []
    for appt in data["appointments"]:
        if appt["status"] == "pending":
            kept.append(appt)
        else:
            completed_at = appt.get("completed_at") or appt.get("cancelled_at")
            if completed_at:
                if datetime.fromisoformat(completed_at) > cutoff:
                    kept.append(appt)

    data["appointments"] = kept
    save_appointments(data)


if __name__ == "__main__":
    print("Appointments system ready")
    print(f"Next due: {get_next_due_time()}")
