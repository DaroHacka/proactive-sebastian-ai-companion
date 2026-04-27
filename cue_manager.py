"""
Cue Manager for Sebastian AI Companion
Handles loading and selecting trigger cues for response variation.
"""

import random
import os

CUE_FILE = os.getenv("CUE_FILE", "library/cue_categories.txt")


def load_cues() -> dict:
    """Load all cues from cue_categories.txt.

    Returns:
        dict: {category: [(cue_code, cue_text), ...]}
    """
    cues = {}
    current_category = None

    try:
        with open(CUE_FILE, "r") as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    # Check for category header
                    if line.startswith("# Category"):
                        # Extract category after "Category X:"
                        if ":" in line:
                            current_category = line.split(":", 1)[1].strip()
                        else:
                            # Handle "Category X:" format with number
                            parts = line.split()
                            if len(parts) >= 2:
                                current_category = " ".join(parts[1:]).strip()
                        if current_category and current_category not in cues:
                            cues[current_category] = []
                    continue

                # Parse cue line: [CUE: CODE],-description
                if line.startswith("[") and "]" in line:
                    # Extract code and description
                    code_part = line.split("]")[0] + "]"
                    desc_part = line.split("]", 1)[1].lstrip(" -").strip()

                    if current_category and code_part and desc_part:
                        cues[current_category].append((code_part, desc_part))

    except FileNotFoundError:
        return {}

    return cues


def get_random_cue(single_only: bool = False) -> tuple:
    """Get a random cue.

    Args:
        single_only: If True, return only single cue (50% chance)

    Returns:
        tuple: (cue_code, cue_text, is_combo)
    """
    cues = load_cues()
    if not cues:
        return ("", "", False)

    all_cues = []
    for category, cue_list in cues.items():
        all_cues.extend(cue_list)

    if not all_cues:
        return ("", "", False)

    # 50% combo, 50% single
    if not single_only and random.random() < 0.5:
        # Return combo (2 different cues)
        selected = random.sample(all_cues, 2)
        combo_code = (
            selected[0][0].replace("[", "").replace("]", "")
            + " + "
            + selected[1][0].replace("[", "").replace("]", "")
        )
        combo_desc = f"{selected[0][1]} | {selected[1][1]}"
        return (combo_code, combo_desc, True)

    # Return single cue
    selected = random.choice(all_cues)
    return (selected[0], selected[1], False)


def get_cue_by_category(category: str) -> tuple:
    """Get a random cue from a specific category.

    Args:
        category: Category name (e.g., "Emotional Volatiles")

    Returns:
        tuple: (cue_code, cue_text)
    """
    cues = load_cues()

    # Normalize category name
    category_normalized = category.lower()

    # Find matching category
    for cat, cue_list in cues.items():
        if category_normalized in cat.lower():
            if cue_list:
                selected = random.choice(cue_list)
                return (selected[0], selected[1])

    return ("", "")


def list_categories() -> list:
    """List all available categories.

    Returns:
        list: Category names
    """
    cues = load_cues()
    return list(cues.keys())


def get_cue_count() -> int:
    """Get total number of cues.

    Returns:
        int: Total cue count
    """
    cues = load_cues()
    total = 0
    for cue_list in cues.values():
        total += len(cue_list)
    return total


if __name__ == "__main__":
    # Test
    print(f"Loaded {get_cue_count()} cues")
    print(f"Categories: {list_categories()}")
    print()

    # Test single
    code, text, is_combo = get_random_cue(single_only=True)
    print(f"Single: {code} - {text}")

    print()

    # Test combo
    code, text, is_combo = get_random_cue(single_only=False)
    print(f"Combo: {code}")
    print(f"Text: {text}")
    print(f"Is combo: {is_combo}")
