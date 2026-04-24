"""
Time Parser for Generic Time Expressions
Maps generic time expressions to specific time ranges.
"""

import re
import random
from datetime import datetime, timedelta


TIME_RANGES = {
    "early morning": (5, 7),  # 5:00 - 7:00
    "morning": (8, 11),  # 8:00 - 11:00
    "noon": (12, 12),  # 12:00
    "lunch": (12, 13),  # 12:00 - 13:00
    "afternoon": (13, 17),  # 13:00 - 17:00
    "evening": (18, 20),  # 18:00 - 20:00
    "night": (21, 23),  # 21:00 - 23:00
    "midnight": (0, 1),  # 00:00 - 01:00
}


def parse_generic_time(time_expr: str) -> datetime:
    """Parse a generic time expression to a specific datetime.

    Args:
        time_expr: Generic time like "morning", "evening", "tomorrow afternoon"

    Returns:
        datetime object with the parsed time
    """
    now = datetime.now()
    time_expr_lower = time_expr.lower().strip()

    # Check for "tomorrow" prefix
    is_tomorrow = "tomorrow" in time_expr_lower
    if is_tomorrow:
        time_expr_lower = time_expr_lower.replace("tomorrow", "").strip()
        base_date = now + timedelta(days=1)
    else:
        base_date = now

    # Map to time range
    for generic, (start_hour, end_hour) in TIME_RANGES.items():
        if generic in time_expr_lower:
            # Pick random hour in range
            hour = random.randint(start_hour, end_hour)
            minute = random.randint(0, 59)
            return base_date.replace(hour=hour, minute=minute, second=0)

    # Handle relative expressions
    if "soon" in time_expr_lower:
        # 15-30 minutes from now
        minutes = random.randint(15, 30)
        return now + timedelta(minutes=minutes)

    if "later" in time_expr_lower:
        # 1-2 hours from now
        hours = random.randint(1, 2)
        return now + timedelta(hours=hours)

    # Default: return current time + 1 hour
    return now + timedelta(hours=1)


def is_generic_time(text: str) -> bool:
    """Check if text contains generic time expression."""
    text_lower = text.lower()

    # Check all generic time keys
    for generic in TIME_RANGES.keys():
        if generic in text_lower:
            return True

    # Check relative expressions
    for rel in ["soon", "later", "tomorrow"]:
        if rel in text_lower:
            return True

    return False


def extract_time_expression(text: str) -> str:
    """Extract the first generic time expression from text."""
    text_lower = text.lower()

    for generic in TIME_RANGES.keys():
        if generic in text_lower:
            return generic

    for rel in ["soon", "later"]:
        if rel in text_lower:
            return rel

    if "tomorrow" in text_lower:
        # Check what follows tomorrow
        if "morning" in text_lower:
            return "tomorrow morning"
        if "afternoon" in text_lower:
            return "tomorrow afternoon"
        if "evening" in text_lower:
            return "tomorrow evening"
        if "night" in text_lower:
            return "tomorrow night"
        return "tomorrow"

    return None


def parse_response_for_time(response: str) -> datetime | None:
    """Parse AI response for time expressions and return a due datetime.

    Handles:
    - Explicit times: "8 PM", "9:30", "at 8", "at 9pm"
    - Generic times: "morning", "evening", "tonight"
    - Relative: "soon", "later tonight"

    Returns:
        datetime object if time found, None otherwise
    """
    text_lower = response.lower()
    now = datetime.now()

    # Try explicit time patterns first (more specific)
    # Pattern 1: "8 PM", "9pm", "8pm", "9 PM"
    explicit_pattern = re.search(r"(\d{1,2})\s*(am|pm|AM|PM)", text_lower)
    if explicit_pattern:
        hour = int(explicit_pattern.group(1))
        period = explicit_pattern.group(2).lower()

        # Convert to 24-hour
        if period == "am":
            if hour == 12:
                hour = 0  # 12 AM = midnight
        else:  # pm
            if hour != 12:
                hour += 12  # 1 PM = 13

        # Pick a random minute for natural feel
        minute = random.randint(0, 59)

        # Handle "tomorrow" in response
        base_date = now
        if "tomorrow" in text_lower:
            base_date = now + timedelta(days=1)

        return base_date.replace(hour=hour, minute=minute, second=0)

    # Pattern 2: "8 or 9 PM", "between 8 and 9"
    range_pattern = re.search(
        r"(\d{1,2})\s*(?:or|to|-)\s*(\d{1,2})\s*(am|pm|AM|PM)", text_lower
    )
    if range_pattern:
        start_hour = int(range_pattern.group(1))
        end_hour = int(range_pattern.group(2))
        period = range_pattern.group(3).lower()

        # Pick random hour in range
        hour = random.randint(start_hour, end_hour)

        # Convert to 24-hour
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0

        minute = random.randint(0, 59)

        base_date = now + timedelta(days=1) if "tomorrow" in text_lower else now
        return base_date.replace(hour=hour, minute=minute, second=0)

    # Try generic time expressions
    time_expr = extract_time_expression(text_lower)
    if time_expr:
        return parse_generic_time(time_expr)

    # Try relative keywords (later tonight, later, soon)
    relative_keywords = {
        "later tonight": (18, 22),
        "later today": (18, 22),
        "tonight": (18, 22),
        "later": (None, 1),  # 1-2 hours from now
        "soon": (0, 30),  # 0-30 minutes
    }

    for keyword, time_range in relative_keywords.items():
        if keyword in text_lower:
            if time_range[0] is None:
                # Relative: X hours from now
                hours = (
                    random.randint(1, 2)
                    if time_range[1] == 1
                    else random.randint(1, time_range[1])
                )
                return now + timedelta(hours=hours)
            elif time_range[1] == 0:
                # Minutes from now
                minutes = random.randint(15, 30)
                return now + timedelta(minutes=minutes)
            else:
                # Time range for today/tomorrow
                hour = random.randint(time_range[0], time_range[1])
                minute = random.randint(0, 59)
                base_date = now + timedelta(days=1) if "tomorrow" in text_lower else now
                return base_date.replace(hour=hour, minute=minute, second=0)

    # Try keyword detection (less specific)
    keywords = {
        "evening": (18, 20),
        "evenings": (18, 20),
        "morning": (8, 11),
        "afternoon": (13, 17),
        "night": (21, 23),
        "midnight": (0, 1),
    }

    for keyword, (start, end) in keywords.items():
        if keyword in text_lower:
            hour = random.randint(start, end)
            minute = random.randint(0, 59)
            base_date = now + timedelta(days=1) if "tomorrow" in text_lower else now
            return base_date.replace(hour=hour, minute=minute, second=0)

    return None
