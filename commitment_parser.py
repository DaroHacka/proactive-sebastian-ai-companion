import json
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


def parse_response_for_appointment(ai_response: str, user_message: str = "") -> dict:
    """Parse AI response AND user message for commitments using regex."""
    text = (ai_response + " " + user_message).lower()
    
    # Pattern 1: Specific time like "12:40 AM", "8 PM", "20:00" (HIGHEST PRIORITY)
    time_pattern = r'(\d{1,2}):?(\d{2})?\s*(am|pm|AM|PM)'
    time_match = re.search(time_pattern, text)
    
    # Pattern 2: "in X hours/minutes"
    hours_pattern = r'in\s+(\d+)\s*(hour|hr|minute)'
    hours_match = re.search(hours_pattern, text)
    
    # Pattern 3: Specific time found (check FIRST before relative terms)
    if time_match:
        time_str = time_match.group(0)
        return {
            "has_commitment": True,
            "commitment_type": "specific_time",
            "time_specified": time_str,
            "description": f"AI will check in at {time_str}"
        }
    
    # Pattern 4: Relative terms
    if re.search(r'in a bit|soon|later|in a while', text):
        return {
            "has_commitment": True,
            "commitment_type": "hours",
            "hours_value": 2,
            "time_specified": "in a bit",
            "description": "AI will check in within 1-2 hours"
        }
    
    if re.search(r'tomorrow|next day', text):
        return {
            "has_commitment": True,
            "commitment_type": "tomorrow",
            "time_specified": "tomorrow",
            "description": "AI will check in tomorrow"
        }
    
    if re.search(r'next week', text):
        return {
            "has_commitment": True,
            "commitment_type": "next_week",
            "description": "AI will check in next week"
        }
    
    return {"has_commitment": False}


def calculate_due_time(appointment: dict) -> str:
    """Calculate the due datetime from an appointment card."""
    if not appointment.get("has_commitment"):
        return None
    
    now = datetime.now()
    commitment_type = appointment.get("commitment_type")
    
    if commitment_type == "hours":
        hours = appointment.get("hours_value", 2)
        return (now + timedelta(hours=hours)).isoformat()
    
    elif commitment_type == "today":
        return now.replace(hour=23, minute=59, second=0).isoformat()
    
    elif commitment_type == "tonight":
        if now.hour < 18:
            return now.replace(hour=20, minute=0, second=0).isoformat()
        else:
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=20, minute=0, second=0).isoformat()
    
    elif commitment_type == "tomorrow":
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=10, minute=0, second=0).isoformat()
    
    elif commitment_type == "specific_time":
        time_str = appointment.get("time_specified", "")
        # Try to parse "12:40 AM" or "8 PM"
        try:
            # Extract hour and minute
            match = re.search(r'(\d{1,2}):?(\d{2})?\s*(am|pm)', time_str, re.IGNORECASE)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if match.group(2) else 0
                ampm = match.group(3).lower()
                
                # Convert to 24-hour format
                if ampm == 'pm' and hour != 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                
                due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if due < now:
                    due += timedelta(days=1)
                return due.isoformat()
        except:
            pass
        
        # Fallback: 3 hours from now
        return (now + timedelta(hours=3)).isoformat()
    
    elif commitment_type == "next_week":
        return (now + timedelta(days=7)).isoformat()
    
    # Default: 3 hours from now
    return (now + timedelta(hours=3)).isoformat()


def create_appointment(response: str, user_message: str = "", source: str = "unknown") -> dict:
    """Parse response and create appointment dict if commitment found."""
    parsed = parse_response_for_appointment(response, user_message)
    
    if not parsed.get("has_commitment"):
        return None
    
    due_iso = calculate_due_time(parsed)
    if not due_iso:
        return None
    
    return {
        "id": f"appt_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "type": "commitment",
        "created_at": datetime.now().isoformat(),
        "source": source,
        "description": parsed.get("description", "No description"),
        "due": due_iso,
        "status": "pending"
    }


if __name__ == "__main__":
    # Test
    test_response = "Hey Daniel, I'll check back in around 12:40 AM. Sebastian"
    result = parse_response_for_appointment(test_response, "trigger library f")
    print(json.dumps(result, indent=2))
    
    if result.get("has_commitment"):
        due = calculate_due_time(result)
        print(f"Due: {due}")
