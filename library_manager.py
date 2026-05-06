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
    "f": {
        "name": "appointment_proposal",
        "file": [],  # Will be filled by auto-discovery
        "loader_module": "sebastian_proactive",
        "loader_func": "get_random_appointment_proposal",
        "weight_bias": 0.0,  # Disabled by default (user sets 0.1 in config)
        "max_combo": 3,
        "enabled": False,
        "auto_discovered": False,  # We're manually registering it
    },
}


def discover_new_libraries(library_dir="library"):
    """Auto-discover libraries with pattern: library-X-name.txt
    
    Returns: {letter: {"files": [...], "name": "name", "auto_discovered": True}}
    - Multiple files with same X → grouped as one library
    - Skips files starting with # (comments)
    """
    discovered = {}
    
    # Fix: use absolute path relative to this file
    if not os.path.isabs(library_dir):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        library_dir = os.path.join(base_dir, library_dir)
    
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
    
    # Load config for auto-discovered libraries
    try:
        from config.config_manager import get_config
        config = get_config()
        combo_relevance = config.get("combo_config", {}).get("library_relevance", {})
        lib_configs = config.get("libraries", {})
    except:
        combo_relevance = {}
        lib_configs = {}
    
    # Then, add new OR update existing
    discovered = discover_new_libraries()
    
    for letter, info in discovered.items():
        if letter in LIBRARIES:
            # Already exists - update file paths from auto-discovery
            if info.get("files"):
                LIBRARIES[letter]["file"] = info["files"]
                print(f"[Updated library {letter} with discovered files]")
            
            # Update with config values if available
            if letter in lib_configs:
                lib_config = lib_configs[letter]
                if "weight_bias" in lib_config:
                    LIBRARIES[letter]["weight_bias"] = lib_config["weight_bias"]
                if "enabled" in lib_config:
                    LIBRARIES[letter]["enabled"] = lib_config["enabled"]
                print(f"[Updated library {letter} from config: weight={LIBRARIES[letter]['weight_bias']}, enabled={LIBRARIES[letter]['enabled']}]")
            continue
        
        # New library - add with config-based values
        weight = combo_relevance.get(letter, 1.0)
        lib_config = lib_configs.get(letter, {})
        weight = lib_config.get("weight_bias", weight)
        enabled = lib_config.get("enabled", weight > 0)
        
        LIBRARIES[letter] = {
            "name": info["name"],
            "file": info["files"],
            "loader_module": None,
            "loader_func": None,
            "weight_bias": weight,
            "max_combo": 3,
            "enabled": enabled,
            "auto_discovered": True,
        }
        print(f"[Auto-discovered library {letter}: weight={weight}, enabled={enabled}]")


def parse_library_content(file_path):
    """Parse library file and extract instructions + data.
    
    Supports Python code format:
        prompt = "single instruction"  # Single instruction
        random_prompts = [...]   # List of random prompts
    
    Returns dict with:
        - "data": list of data lines (for random selection)
        - "instruction": single prompt value (or None)
        - "random_prompts": list of random prompt instructions
    """
    data_lines = []
    instruction = None
    random_prompts = []
    in_list_block = False
    list_lines = []
    
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                i += 1
                continue
            
            # Check for Python assignment: prompt = "..."
            if line.startswith("prompt ="):
                # Extract string value
                val = line[8:].strip()
                if val.startswith('"') or val.startswith("'"):
                    # Remove quotes
                    if val.endswith('"') or val.endswith("'"):
                        instruction = val[1:-1]
                    else:
                        instruction = val[1:]
                i += 1
                continue
            
            # Check for Python assignment: random_prompts = [...]
            if line.startswith("random_prompts ="):
                in_list_block = True
                list_lines = []
                
                # Get content after = 
                val = line[16:].strip()
                if val.startswith('['):
                    # Might be single line: random_prompts = ["a", "b"]
                    if val.endswith(']'):
                        # Single line list
                        list_str = val[1:-1]  # Remove [ and ]
                        # Parse items
                        for item in list_str.split(','):
                            item = item.strip()
                            if item.startswith('"') or item.startswith("'"):
                                item = item[1:]
                            if item.endswith('"') or item.endswith("'"):
                                item = item[:-1]
                            if item.endswith(','):
                                item = item[:-1]
                            if item:
                                random_prompts.append(item)
                        in_list_block = False
                i += 1
                continue
            
            # Check for end of multi-line list
            if line == "]" and in_list_block:
                in_list_block = False
                # Process collected lines
                for item in list_lines:
                    item = item.strip()
                    if item.startswith("-"):
                        item = item[1:].strip()  # Remove "-"
                    # Remove surrounding quotes (handle cases like "text", or "text")
                    if len(item) >= 2:
                        # Check for matching quotes at start and end
                        if (item.startswith('"') and item.endswith('"')) or \
                           (item.startswith("'") and item.endswith("'")):
                            item = item[1:-1]
                        # Handle case where item ends with quote + comma: "text",
                        elif item.startswith('"') and item.endswith('",'):
                            item = item[1:-2]  # Remove ", from end
                        elif item.startswith("'") and item.endswith("',"):
                            item = item[1:-2]  # Remove ', from end
                    if item.endswith(','):
                        item = item[:-1]
                    if item:
                        random_prompts.append(item)
                list_lines = []
                i += 1
                continue
            
            # Inside multi-line list
            if in_list_block:
                list_lines.append(lines[i])  # Keep original with newline
                i += 1
                continue
            
            # Regular data line (clean it)
            line = lines[i].strip()
            # Remove matched quotes from start and end of line
            # e.g., "item" - description -> item" - description (wrong)
            # e.g., "item - description" -> item - description (right)
            if line.startswith('"') and '"' in line[1:]:
                # Find matching end quote
                end_quote = line.rfind('"')
                if end_quote > 0:
                    line = line[1:end_quote] + line[end_quote+1:]
            elif line.startswith("'") and "'" in line[1:]:
                end_quote = line.rfind("'")
                if end_quote > 0:
                    line = line[1:end_quote] + line[end_quote+1:]
            data_lines.append(line)
            i += 1
            
    except Exception as e:
        print(f"[Parse error in {file_path}: {e}]")
    
    return {
        "data": data_lines,
        "instruction": instruction,
        "random_prompts": random_prompts,
    }


def default_loader(file_paths, lib_key=None):
    """Default loader for auto-discovered libraries.
    
    Rules:
    - Skip lines starting with # (one or more #)
    - Skip empty lines
    - Each line is a valid entry
    - If multiple files: pick random file first, then random line
    - Extracts [prompt]: and [random][prompt]: tags if present
    
    Args:
        file_paths: string (single file) or list of strings (multiple files)
        lib_key: library key (to store instructions in LIBRARIES)
    """
    import random
    
    # Normalize to list
    if isinstance(file_paths, str):
        files = [file_paths]
    else:
        files = file_paths
    
    # Pick random file if multiple
    chosen_file = random.choice(files)
    
    # Parse the file (extract instructions + data)
    parsed = parse_library_content(chosen_file)
    
    # Store instructions in LIBRARIES if lib_key provided
    if lib_key and lib_key in LIBRARIES:
        if parsed["instruction"]:
            LIBRARIES[lib_key]["instruction"] = parsed["instruction"]
        if parsed["random_prompts"]:
            LIBRARIES[lib_key]["random_prompts"] = parsed["random_prompts"]
    
    # Return random data line (cleaned)
    if parsed["data"]:
        data = random.choice(parsed["data"])
        # Clean up: strip quotes and newlines
        data = data.strip().strip('"').strip("'")
        return data
    
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
    
    # FIRST: Check if custom loader is defined (even for auto-discovered)
    if lib.get("loader_module") and lib.get("loader_func"):
        try:
            module = importlib.import_module(lib["loader_module"])
            return getattr(module, lib["loader_func"], None)
        except Exception as e:
            print(f"[Loader error for {lib_key}: {e}]")
            # Fall through to default loader if available
    
    # Auto-discovered library with no custom loader: use default loader
    if lib.get("auto_discovered"):
        files = lib.get("file", [])
        return lambda: default_loader(files, lib_key)
    
    # No loader found
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
