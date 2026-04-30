"""
Library Manager - Dynamic registration and loading of content libraries.
"""
import importlib
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
    },
    "b": {
        "name": "cues",
        "file": "library/cue_categories.txt",
        "loader_module": "cue_manager",
        "loader_func": "get_random_cue",
        "weight_bias": 1.0,
        "max_combo": 3,
        "enabled": True,
    },
    "c": {
        "name": "vibes",
        "file": ["library/vibe_library_01.txt", "library/vibe_library_02.txt"],
        "loader_module": "proactive_scheduler",
        "loader_func": "build_vibe_prompt",
        "weight_bias": 2.0,  # Vibe is important, boost its appearance
        "max_combo": 3,
        "enabled": True,
    },
    # "d": {...},  # Future library - just add here!
}


def get_normal_libraries():
    """Get libraries with max_combo <= 3 (normal content libraries)."""
    return {k: v for k, v in LIBRARIES.items() 
            if v["enabled"] and v["max_combo"] <= 3}


def get_special_libraries():
    """Get libraries with max_combo > 3 (special libraries like weather)."""
    return {k: v for k, v in LIBRARIES.items() 
            if v["enabled"] and v["max_combo"] > 3}


def generate_combo_weights():
    """Auto-generate combo weights from normal libraries.
    
    Generates: a_only, b_only, c_only, a_b, a_c, b_c, a_b_c
    Weights = product of weight_bias values, then normalized to sum=1.0
    """
    normal_libs = get_normal_libraries()
    keys = sorted(normal_libs.keys())
    
    weights = {}
    
    # Generate combos of size 1, 2, 3
    for r in [1, 2, 3]:
        for combo_tuple in combinations(keys, r):
            if r == 1:
                combo_str = combo_tuple[0] + "_only"
            else:
                combo_str = "_".join(combo_tuple)
            
            # Weight = product of weight_bias values
            weight = 1.0
            for k in combo_tuple:
                weight *= normal_libs[k]["weight_bias"]
            weights[combo_str] = weight
    
    # Normalize to sum = 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    return weights


def get_loader(lib_key):
    """Dynamically import and return the loader function for a library."""
    lib = LIBRARIES.get(lib_key)
    if not lib or not lib["enabled"]:
        return None
    
    try:
        module = importlib.import_module(lib["loader_module"])
        return getattr(module, lib["loader_func"], None)
    except:
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
    }
