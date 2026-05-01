"""
Config Manager for Sebastian AI Companion
Loads and manages configuration from config.toml.
"""

import os
import toml
from pathlib import Path

DEFAULT_CONFIG = {
    "user": {"name": "Elias", "email": "your_email@gmail.com"},
    "paths": {"library": "library", "appointments": "appointments", "memory": "memory", "config": "config"},
    "ollama": {"url": "http://localhost:11434", "model": "phi4", "available_models": ["phi4", "gemma4:26b"]},
    "system": {"proactive_mode": True, "appointment_mode": True, "memory_in_prompt": False, "test_mode": True},
    "user_input": {"combo_trigger_chance": 0.20},
    "timing": {"scheduler_interval_minutes": 10, "proactive_check_seconds": 30, "appointment_check_seconds": 30},
    "vibe": {"day_commentary_chance": 0.10, "weekend_longing_chance": 0.10},
    "combo_weights": {"a_only": 0.20, "b_only": 0.10, "c_only": 0.15, "a_b": 0.15, "a_c": 0.20, "b_c": 0.10, "a_b_c": 0.10},
}

_config = None
_config_path = "config/config.toml"


def load_config(config_path: str = None) -> dict:
    """Load config from TOML file with defaults for missing values."""
    global _config, _config_path
    
    if config_path:
        _config_path = config_path
    
    path = Path(_config_path)
    if path.exists():
        try:
            loaded = toml.load(path)
            _config = _deep_merge(DEFAULT_CONFIG, loaded)
            return _config
        except Exception as e:
            print(f"Error loading config: {e}")
    
    _config = DEFAULT_CONFIG.copy()
    return _config


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_config() -> dict:
    """Get current config, loading if needed."""
    global _config
    if _config is None:
        load_config()
    return _config


def get_user_name() -> str:
    """Get user name from config."""
    return get_config().get("user", {}).get("name", "Elias")


def get_user_email() -> str:
    """Get user email from config."""
    return get_config().get("user", {}).get("email", "")


def get_ollama_url() -> str:
    """Get Ollama URL."""
    return get_config().get("ollama", {}).get("url", "http://localhost:11434")


def get_model() -> str:
    """Get default model."""
    return get_config().get("ollama", {}).get("model", "phi4")


def get_available_models() -> list:
    """Get available models list."""
    return get_config().get("ollama", {}).get("available_models", ["phi4"])


def get_combo_trigger_chance() -> float:
    """Get combo trigger chance for user input.
    
    Returns:
        float: Probability between 0.0 (never) and 1.0 (always)
    """
    chance = get_config().get("user_input", {}).get("combo_trigger_chance", 0.20)
    return max(0.0, min(1.0, chance))  # Clamp to [0.0, 1.0]


def is_combo_on_user_message() -> bool:
    """Check if combo should trigger on user messages.
    
    Returns:
        bool: True if combo can trigger on user input, False otherwise
    """
    return get_config().get("user_input", {}).get("combo_on_user_message", True)


def is_proactive_mode() -> bool:
    """Check if proactive mode is enabled."""
    return get_config().get("system", {}).get("proactive_mode", True)


def is_proactive_on_launch() -> bool:
    """Check if proactive should be ON at launch (system.proactive_on_launch)."""
    return get_config().get("system", {}).get("proactive_on_launch", True)


def is_appointment_mode() -> bool:
    """Check if appointment mode is enabled."""
    return get_config().get("system", {}).get("appointment_mode", True)


def is_memory_in_prompt() -> bool:
    """Check if memory should be included in prompt."""
    return get_config().get("system", {}).get("memory_in_prompt", False)


def is_test_mode() -> bool:
    """Check if test mode is enabled."""
    return get_config().get("system", {}).get("test_mode", True)


def get_ai_timeout() -> int:
    """Get AI timeout in seconds."""
    return get_config().get("system", {}).get("ai_timeout_seconds", 600)


def is_proactive_on_startup() -> bool:
    """Check if proactive should be ON on startup."""
    return get_config().get("startup", {}).get("proactive_on_startup", True)


def is_appointment_on_startup() -> bool:
    """Check if appointment mode should be ON on startup."""
    return get_config().get("startup", {}).get("appointment_on_startup", True)


def get_timing(key: str) -> int:
    """Get a timing value in seconds."""
    return get_config().get("timing", {}).get(key, 30)


def get_vibe_chance(key: str) -> float:
    """Get a vibe probability."""
    return get_config().get("vibe", {}).get(key, 0.10)


def get_combo_weight(combo: str) -> float:
    """Get combo weight probability."""
    return get_config().get("combo_weights", {}).get(combo, 0.10)


def validate_schedule_percentages(config: dict = None) -> tuple:
    """Validate and normalize schedule percentages.
    
    Returns (active_percentage, sparse_percentage, was_normalized, warning_message)
    """
    if config is None:
        config = get_config()
    
    schedule = config.get("schedule", {})
    active = schedule.get("active_day_percentage", 0.30)
    
    # Check if user provided sparse percentage
    user_sparse = schedule.get("sparse_day_percentage")
    
    normalized = False
    warning = None
    
    if user_sparse is not None:
        total = active + user_sparse
        if abs(total - 1.0) > 0.001:
            # Normalize
            normalized_sparse = 1.0 - active
            normalized = True
            warning = (
                f"Schedule percentages (active={active:.2f}, sparse={user_sparse:.2f}) "
                f"don't sum to 100%. Normalized: sparse = {normalized_sparse:.2f}"
            )
            return active, normalized_sparse, normalized, warning
        else:
            return active, user_sparse, False, None
    
    # No user_sparse provided, calculate implied
    sparse = 1.0 - active
    return active, sparse, False, None


def get_schedule_config(key: str = None, default: any = None) -> any:
    """Get schedule configuration."""
    cfg = get_config().get("schedule", {
        "contacts_sparse_min": 2,
        "contacts_sparse_max": 4,
        "contacts_active_min": 5,
        "contacts_active_max": 15,
        "active_day_percentage": 0.30
    })
    
    if key:
        return cfg.get(key, default)
    return cfg


def validate_combo_weights(config: dict = None) -> tuple:
    """Validate combo weights sum to 1.0.
    
    Returns (weights_dict, was_normalized, warning_message)
    """
    if config is None:
        config = get_config()
    
    weights = config.get("combo_weights", {})
    
    # Calculate sum
    total = sum(weights.values())
    
    normalized = False
    warning = None
    
    if abs(total - 1.0) > 0.001:
        # Normalize weights
        factor = 1.0 / total if total > 0 else 1.0
        weights = {k: v * factor for k, v in weights.items()}
        normalized = True
        warning = (
            f"Combo weights don't sum to 100% (got {total:.2f}). "
            f"Normalized to sum to 1.0"
        )
    
    return weights, normalized, warning


def get_library_config(lib_key=None):
    """Get library configuration from config.toml, merged with LIBRARIES defaults."""
    config = get_config().get("libraries", {})
    
    if lib_key:
        # Return config for specific library
        return config.get(lib_key, {})
    
    return config


def validate_libraries():
    """Validate library configuration."""
    warnings = []
    
    # Check all enabled libraries have valid files
    from library_manager import LIBRARIES
    import os
    
    for key, lib in LIBRARIES.items():
        if not lib.get("enabled", True):
            continue
        
        # Check weight_bias is positive
        bias = lib.get("weight_bias", 1.0)
        if bias <= 0:
            warnings.append(f"Library {key}: weight_bias must be positive (got {bias})")
        
        # Check file exists
        file_path = lib.get("file")
        if isinstance(file_path, list):
            for f in file_path:
                if not os.path.exists(f):
                    warnings.append(f"Library {key}: file not found: {f}")
        elif not os.path.exists(file_path):
            warnings.append(f"Library {key}: file not found: {file_path}")
    
    return warnings


def save_config(config_path: str = None):
    """Save current config to file."""
    global _config
    path = config_path or _config_path
    with open(path, "w") as f:
        toml.dump(_config, f)