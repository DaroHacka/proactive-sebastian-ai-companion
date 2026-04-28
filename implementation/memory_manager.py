import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MEMORY_DIR = os.getenv("MEMORY_DIR", "memory")
FRESH_MEMORY_FILE = os.path.join(MEMORY_DIR, "fresh.json")
MEDIUM_MEMORY_FILE = os.path.join(MEMORY_DIR, "medium.json")
LONGTERM_MEMORY_FILE = os.path.join(MEMORY_DIR, "longterm.json")

FRESH_LIMIT = 10
MEDIUM_LIMIT = 50


def ensure_memory_dir():
    if not os.path.exists(MEMORY_DIR):
        os.makedirs(MEMORY_DIR)
        for f in [FRESH_MEMORY_FILE, MEDIUM_MEMORY_FILE, LONGTERM_MEMORY_FILE]:
            with open(f, "w") as fp:
                json.dump([], fp)


def load_memory(file_path: str) -> list:
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return []


def save_memory(file_path: str, memories: list):
    with open(file_path, "w") as f:
        json.dump(memories, f, indent=2)


def add_memory(user_message: str, ai_message: str, has_commitment: bool = False, commitment_time: str = None):
    ensure_memory_dir()
    
    memory_entry = {
        "id": len(load_memory(MEDIUM_MEMORY_FILE)) + len(load_memory(LONGTERM_MEMORY_FILE)) + 1,
        "timestamp": datetime.now().isoformat(),
        "user_message": user_message,
        "ai_message": ai_message,
        "has_commitment": has_commitment,
        "commitment_time": commitment_time
    }
    
    fresh = load_memory(FRESH_MEMORY_FILE)
    medium = load_memory(MEDIUM_MEMORY_FILE)
    
    fresh.append(memory_entry)
    
    if len(fresh) > FRESH_LIMIT:
        moved = fresh[:-FRESH_LIMIT] if len(fresh) > FRESH_LIMIT else fresh
        remaining = fresh[-FRESH_LIMIT:]
        
        medium.extend(moved)
        
        if len(medium) > MEDIUM_LIMIT:
            medium = medium[-MEDIUM_LIMIT:]
        
        save_memory(MEDIUM_MEMORY_FILE, medium)
        fresh = remaining if remaining else []
    
    save_memory(FRESH_MEMORY_FILE, fresh)


def get_fresh_memory() -> list:
    return load_memory(FRESH_MEMORY_FILE)


def get_medium_memory() -> list:
    return load_memory(MEDIUM_MEMORY_FILE)


def get_all_memory() -> list:
    return load_memory(LONGTERM_MEMORY_FILE) + load_memory(MEDIUM_MEMORY_FILE) + load_memory(FRESH_MEMORY_FILE)


def get_context_for_prompt(num_recent: int = 10) -> str:
    fresh = load_memory(FRESH_MEMORY_FILE)
    recent = fresh[-num_recent:] if len(fresh) >= num_recent else fresh
    
    if not recent:
        return ""
    
    context = "Recent conversations:\n"
    for mem in recent:
        dt = datetime.fromisoformat(mem["timestamp"]).strftime("%Y-%m-%d %H:%M")
        context += f"- [{dt}] You: {mem['user_message'][:100]}...\n"
        context += f"  Sebastian: {mem['ai_message'][:100]}...\n"
    
    return context


def search_memory(query: str, limit: int = 5) -> list:
    query_lower = query.lower()
    all_mem = load_memory(LONGTERM_MEMORY_FILE) + load_memory(MEDIUM_MEMORY_FILE)
    
    results = []
    for mem in reversed(all_mem):
        if query_lower in mem["user_message"].lower() or query_lower in mem["ai_message"].lower():
            results.append(mem)
            if len(results) >= limit:
                break
    
    return results


if __name__ == "__main__":
    ensure_memory_dir()
    print("Memory system initialized")
    print(f"Fresh: {len(load_memory(FRESH_MEMORY_FILE))} memories")
    print(f"Medium: {len(load_memory(MEDIUM_MEMORY_FILE))} memories")
    print(f"Long-term: {len(load_memory(LONGTERM_MEMORY_FILE))} memories")