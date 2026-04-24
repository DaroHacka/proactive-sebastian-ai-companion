import json
import os
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TASKS_FILE = os.getenv("TASKS_FILE", "scheduled_tasks.json")

MIN_INTERVAL_HOURS = 2
RANDOM_INTERVALS = [2, 3, 4, 5, 6, 7, 8, 12, 24]


def load_tasks() -> dict:
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r") as f:
            return json.load(f)
    return {"tasks": [], "last_random_check": None}


def save_tasks(data: dict):
    with open(TASKS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_commitment_task(commitment: str, due_time: str):
    data = load_tasks()
    
    task = {
        "id": len(data["tasks"]) + 1,
        "type": "commitment",
        "commitment_text": commitment,
        "due": due_time,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    
    data["tasks"].append(task)
    save_tasks(data)
    return task


def schedule_random_check() -> datetime:
    data = load_tasks()
    hours = random.choice(RANDOM_INTERVALS)
    due = datetime.now() + timedelta(hours=hours)
    
    data["last_random_check"] = {
        "due": due.isoformat(),
        "interval_planned": hours
    }
    
    save_tasks(data)
    return due


def get_pending_tasks() -> list:
    data = load_tasks()
    now = datetime.now()
    
    pending = []
    for task in data["tasks"]:
        if task["status"] == "pending":
            due = datetime.fromisoformat(task["due"])
            if due <= now:
                pending.append(task)
    
    return pending


def mark_task_complete(task_id: int):
    data = load_tasks()
    
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat()
            break
    
    save_tasks(data)


def should_random_check(last_message_time: float) -> bool:
    data = load_tasks()
    
    if not data.get("last_random_check"):
        return True
    
    last_check = datetime.fromisoformat(data["last_random_check"]["due"])
    now = datetime.now()
    
    hours_since_last_msg = (datetime.fromtimestamp(last_message_time) - datetime.fromtimestamp(0)).total_seconds() / 3600
    
    if hours_since_last_msg < MIN_INTERVAL_HOURS:
        return False
    
    if now < last_check:
        return False
    
    return True


def get_next_check_time() -> datetime:
    data = load_tasks()
    
    commitments = [t for t in data["tasks"] if t["type"] == "commitment" and t["status"] == "pending"]
    
    if commitments:
        next_commitment = min(commitments, key=lambda t: datetime.fromisoformat(t["due"]))
        return datetime.fromisoformat(next_commitment["due"])
    
    if data.get("last_random_check"):
        return datetime.fromisoformat(data["last_random_check"]["due"])
    
    return datetime.now() + timedelta(hours=random.choice(RANDOM_INTERVALS))


def clear_completed_tasks():
    data = load_tasks()
    data["tasks"] = [t for t in data["tasks"] if t["status"] == "pending"]
    save_tasks(data)


if __name__ == "__main__":
    print("Scheduled tasks system ready")
    print(f"Next check: {get_next_check_time()}")