"""
Sebastian Scheduler Module
Simple appointment storage for Sebastian AI Companion.

Used by asyncio version for:
- load_appointments()
- save_appointments()

NOT used for auto-scheduling (removed).
"""

import os
import json
from datetime import datetime

APPOINTMENTS_FILE = "appointments/appointments.json"


def load_appointments():
    """Load appointments from JSON file."""
    if os.path.exists(APPOINTMENTS_FILE):
        with open(APPOINTMENTS_FILE, "r") as f:
            return json.load(f)
    return {"appointments": []}


def save_appointments(data):
    """Save appointments to JSON file."""
    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(data, f, indent=2)