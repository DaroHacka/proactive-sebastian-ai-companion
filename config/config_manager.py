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
    """Get combo trigger chance for user input."""
    return get_config().get("user_input", {}).get("combo_trigger_chance", 0.20)


def is_proactive_mode() -> bool:
    """Check if proactive mode is enabled."""
    return get_config().get("system", {}).get("proactive_mode", True)


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


def save_config(config_path: str = None):
    """Save current config to file."""
    global _config
    path = config_path or _config_path
    with open(path, "w") as f:
        toml.dump(_config, f)