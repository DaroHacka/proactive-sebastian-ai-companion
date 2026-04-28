"""
Ollama Parameters Manager
Loads and manages Ollama API parameters from ollama_params.toml
"""

import os
import toml
from pathlib import Path

DEFAULT_PARAMS = {
    "temperature": 0.8,
    "top_p": 0.9,
    "top_k": 20,
    "max_tokens": 500,
    "repeat_penalty": 1.2,
    "seed": -1,
    "stream": False,
    "num_ctx": 1024,
    "num_gpu": 0,
    "num_thread": 0,
    "keep_alive": "5m",
    "min_p": 0.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "repeat_last_n": 64,
    "tfs_z": 1.0,
    "typical_p": 0.7,
    "mirostat": 0,
    "mirostat_tau": 0.8,
    "mirostat_eta": 0.6,
    "use_mmap": True,
    "use_mlock": False,
    "num_keep": 5,
    "num_batch": 2,
    "stop": [],
    "logit_bias": {},
    "reasoning_effort": "medium",
    "think": False,
    "format": "",
}

_params = None
_params_path = "config/ollama_params.toml"


def load_ollama_params(params_path: str = None) -> dict:
    """Load Ollama parameters from TOML file, fall back to defaults."""
    global _params, _params_path
    
    if params_path:
        _params_path = params_path
    
    path = Path(_params_path)
    if path.exists():
        try:
            loaded = toml.load(path)
            params = {}
            
            # Parse each top-level key that has 'value' (our current structure)
            for key, value in loaded.items():
                if isinstance(value, dict) and 'value' in value:
                    params[key] = value.get("value")
            
            # If no params loaded (different structure), try [common] sections
            if not params:
                for section in ["common", "streaming", "model", "advanced"]:
                    if section in loaded:
                        for key, val in loaded[section].items():
                            if key != "description":
                                params[key] = val.get("value", DEFAULT_PARAMS.get(key))
            
            _params = params
            return _params
        except Exception as e:
            print(f"Error loading ollama_params: {e}")
    
    _params = DEFAULT_PARAMS.copy()
    return _params


def get_ollama_params() -> dict:
    """Get current parameters, loading if needed."""
    global _params
    if _params is None:
        load_ollama_params()
    return _params


def get_ollama_param(name: str, default=None):
    """Get single parameter value."""
    params = get_ollama_params()
    return params.get(name, DEFAULT_PARAMS.get(name, default))


def build_options_payload(model_name: str = None) -> dict:
    """Build the options dict for Ollama API payload based on current parameters."""
    params = get_ollama_params()
    
    # Check for model-specific overrides
    if model_name:
        model_overrides = get_model_params(model_name)
        if model_overrides:
            params.update(model_overrides)
    
    # Build options dict (exclude non-option fields)
    options = {}
    for key, value in params.items():
        if key not in ["description", "group", "value"]:
            if value is not None and value != "" and value != {}:
                options[key] = value
    
    return options


def get_model_params(model_name: str) -> dict:
    """Get model-specific parameters if defined."""
    path = Path(_params_path)
    if not path.exists():
        return {}
    
    try:
        config = toml.load(path)
        model_name = model_name.lower()
        
        for section in config:
            if section.startswith("model_"):
                if model_name.startswith(section.replace("model_", "")):
                    model_config = config[section]
                    params = {}
                    for key in ["temperature", "top_p", "top_k", "max_tokens", "repeat_penalty", "seed"]:
                        if key in model_config:
                            params[key] = model_config[key]
                    return params
    except:
        pass
    
    return {}


def validate_params(config: dict = None) -> list:
    """Validate parameters and return list of warnings."""
    warnings = []
    
    if config is None:
        config = {}
    
    # Check common parameters
    common = config.get("common", {})
    if common:
        temp = common.get("temperature", {}).get("value", 0.8)
        if temp < 0.0 or temp > 2.0:
            warnings.append(f"temperature {temp} out of range (0.0-2.0)")
    
    tp = common.get("top_p", {}).get("value", 0.9)
    if tp < 0.0 or tp > 1.0:
        warnings.append(f"top_p {tp} out of range (0.0-1.0)")
    
    tk = common.get("top_k", {}).get("value", 20)
    if tk < 1 or tk > 100:
        warnings.append(f"top_k {tk} out of range (1-100)")
    
    return warnings


def get_groups() -> list:
    """Get groups in priority order."""
    return ["common", "streaming", "model", "advanced"]


def get_params_by_group(group: str) -> dict:
    """Get parameters for a specific group."""
    path = Path(_params_path)
    if not path.exists():
        return {}
    
    try:
        config = toml.load(path)
        params = {}
        
        # Search each key for matching group
        for key, value in config.items():
            if isinstance(value, dict):
                if value.get("group") == group and "value" in value:
                    params[key] = value.get("value")
        
        return params
    except:
        pass
    
    return {}


def restore_defaults() -> bool:
    """Restore all parameters to Ollama defaults. Returns True on success."""
    global _params
    _params = DEFAULT_PARAMS.copy()
    
    path = Path(_params_path)
    if path.exists():
        try:
            with open(_params_path, "r") as f:
                lines = f.readlines()
            
            param_defaults = {}
            for key, value in DEFAULT_PARAMS.items():
                if key in ["stop"]:
                    param_defaults[key] = "[]"
                elif key in ["logit_bias"]:
                    param_defaults[key] = "{}"
                elif key in ["format"]:
                    param_defaults[key] = '""'
                elif key in ["keep_alive"]:
                    param_defaults[key] = f'"{value}"'
                elif isinstance(value, bool):
                    param_defaults[key] = "true" if value else "false"
                elif isinstance(value, int):
                    param_defaults[key] = str(value)
                elif isinstance(value, float):
                    param_defaults[key] = str(value)
                else:
                    param_defaults[key] = str(value)
            
            new_lines = []
            i = 0
            while i < len(lines):
                line = lines[i]
                stripped = line.strip()
                
                if stripped.startswith("[") and stripped.endswith("]"):
                    param_name = stripped[1:-1]
                    if param_name in param_defaults:
                        new_lines.append(line)
                        i += 1
                        if i < len(lines):
                            next_line = lines[i].strip()
                            # Only replace value if it exists
                            if next_line.startswith("value ="):
                                i += 1
                                default_val = param_defaults[param_name]
                                if default_val not in ["[]", "{}"] and not default_val.startswith('"'):
                                    default_val = f'"{default_val}"'
                                new_lines.append(f"value = {default_val}\n")
                            else:
                                pass  # No value line found, skip this param
                        continue
                
                new_lines.append(line)
                i += 1
            
            with open(_params_path, "w") as f:
                f.writelines(new_lines)
            
            return True
        except Exception as e:
            print(f"Error restoring defaults: {e}")
            return False
    
    return True


def display_parameters():
    """Display current parameters in a formatted way."""
    params = get_ollama_params()
    groups = get_groups()
    
    output = ["\n[Current Ollama Parameters]"]
    
    for group in groups:
        group_params = get_params_by_group(group)
        if group_params:
            output.append(f"\n--- {group.upper()} ---")
            for key, value in group_params.items():
                output.append(f"  {key}: {value}")
    
    return "\n".join(output)