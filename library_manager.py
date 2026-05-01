"""
Library Manager - Dynamic registration and loading of content libraries.
"""
import importlib
import os
import re
from itertools import combinations

# Library Registry
LIBRARIES = {
    "a": {
        "name": "intents",
        "file": "library/interaction_intents.txt",
        "loader_module": "intent_manager",
        "loader_func": "get_random_intent",
        "weight_bias": 1.0,  # Influences combo frequency
        "max_combo": 3,  # Max letters in combo (3=normal, 0=excluded, >3=special)
        "enabled": True,
        "auto_discovered": False,
    },
    "b": {
        "name": "cues",
        "file": "library/cue_categories.txt",
        "loader_module": "cue_manager",
        "loader_func": "get_random_cue",
        "weight_bias": 1.0,
        "max_combo": 3,
        "enabled": True,
        "auto_discovered": False,
    },
    "c": {
        "name": "vibes",
        "file": ["library/vibe_library_01.txt", "library/vibe_library_02.txt"],
        "loader_module": "proactive_scheduler",
        "loader_func": "build_vibe_prompt",
        "weight_bias": 2.0,  # Vibe is important, boost its appearance
        "max_combo": 3,
        "enabled": True,
        "auto_discovered": False,
    },
    # "d": {...},  # Future: auto-discovered
}


def discover_new_libraries(library_dir="library"):
    """Auto-discover libraries with pattern: library-X-name.txt
    
    Returns: {letter: {"files": [...], "name": "name", "auto_discovered": True}}
    - Multiple files with same X → grouped as one library
    - Skips files starting with # (comments)
    """
    discovered = {}
    
    if not os.path.exists(library_dir):
        return discovered
    
    pattern = r"library-([a-z])-(.+)\.txt$"
    
    for fname in sorted(os.listdir(library_dir)):
        match = re.match(pattern, fname)
        if match:
            letter = match.group(1)  # "d"
            name = match.group(2)     # "books"
            full_path = os.path.join(library_dir, fname)
            
            if letter not in discovered:
                discovered[letter] = {
                    "files": [],
                    "name": name,
                    "letter": letter,
                    "auto_discovered": True,
                }
            discovered[letter]["files"].append(full_path)
    
    return discovered


def remove_deleted_libraries():
    """Remove auto-discovered libraries whose files no longer exist."""
    to_remove = []
    
    for letter, lib in LIBRARIES.items():
        if not lib.get("auto_discovered", False):
            continue
        
        # Check if at least one file still exists
        files = lib.get("file", [])
        if isinstance(files, str):
            files = [files]
        
        if not any(os.path.exists(f) for f in files):
            to_remove.append(letter)
            print(f"[Removed library {letter} - file not found]")
    
    for letter in to_remove:
        del LIBRARIES[letter]


def update_libraries_from_discovery():
    """Add newly discovered libraries, remove deleted ones."""
    # First, remove deleted
    remove_deleted_libraries()
    
    # Then, add new
    discovered = discover_new_libraries()
    
    for letter, info in discovered.items():
        if letter in LIBRARIES:
            continue  # Already exists
        
        # Add with default loader (simple line reader)
        LIBRARIES[letter] = {
            "name": info["name"],
            "file": info["files"],
            "loader_module": None,
            "loader_func": None,
            "weight_bias": 1.0,
            "max_combo": 3,
            "enabled": True,
            "auto_discovered": True,
        }


def default_loader(file_paths):
    """Default loader for auto-discovered libraries.
    
    Rules:
    - Skip lines starting with # (one or more #)
    - Skip empty lines
    - Each line is a valid entry
    - If multiple files: pick random file first, then random line
    
    Args:
        file_paths: string (single file) or list of strings (multiple files)
    """
    import random
    
    # Normalize to list
    if isinstance(file_paths, str):
        files = [file_paths]
    else:
        files = file_paths
    
    # Pick random file if multiple
    chosen_file = random.choice(files)
    
    try:
        with open(chosen_file, "r") as f:
            lines = [
                line.strip() 
                for line in f 
                if line.strip() and not line.strip().startswith("#")
            ]
        if lines:
            return random.choice(lines)
    except Exception as e:
        print(f"[Loader error in {chosen_file}: {e}]")
    
    return None


def get_normal_libraries():
    """Get libraries with max_combo <= 3 (normal content libraries)."""
    return {k: v for k, v in LIBRARIES.items() 
            if v.get("enabled", True) and v["max_combo"] <= 3}


def get_special_libraries():
    """Get libraries with max_combo > 3 (special libraries like weather)."""
    return {k: v for k, v in LIBRARIES.items() 
            if v.get("enabled", True) and v["max_combo"] > 3}


def get_loader(lib_key):
    """Dynamically import and return the loader function for a library."""
    lib = LIBRARIES.get(lib_key)
    if not lib or not lib.get("enabled", True):
        return None
    
    # Auto-discovered library: use default loader
    if lib.get("auto_discovered"):
        files = lib.get("file", [])
        return lambda: default_loader(files)
    
    # Hardcoded library: import function
    try:
        module = importlib.import_module(lib["loader_module"])
        return getattr(module, lib["loader_func"], None)
    except Exception as e:
        print(f"[Loader error for {lib_key}: {e}]")
        return None


def add_library(key, name, file, loader_module, loader_func, 
                weight_bias=1.0, max_combo=3, enabled=True):
    """Add a new library dynamically."""
    LIBRARIES[key] = {
        "name": name,
        "file": file,
        "loader_module": loader_module,
        "loader_func": loader_func,
        "weight_bias": weight_bias,
        "max_combo": max_combo,
        "enabled": enabled,
        "auto_discovered": False,
    }


# Run on import
update_libraries_from_discovery()
