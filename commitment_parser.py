import json
import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from webui_client import chat, COMPANION_MODEL
from memory_manager import get_fresh_memory


APPOINTMENT_EXTRACTION_PROMPT = """You are analyzing a conversation between Sebastian (AI companion) and the user.

Your task is to check if EITHER:
1. You (the AI) made a commitment to contact the user at a specific time, OR
2. The user mentioned wanting to be contacted at a specific time

IMPORTANT: Only extract REAL commitments. Ignore:
- Fictional references ("In the story, they met tomorrow")
- General wishes ("I wish we could talk more")
- Casual expressions without specific intent

Output ONLY a JSON appointment card. If no commitment exists:
{"has_commitment": false}

If a commitment exists, output:
{
  "has_commitment": true,
  "source": "ai_proposal" | "user_request",
  "commitment_type": "today" | "tonight" | "tomorrow" | "hours" | "specific_time",
  "hours_value": number (if commitment_type is "hours"),
  "specific_time": "HH:MM" or "YYYY-MM-DDTHH:MM:SS" (if commitment_type is "specific_time"),
  "natural_text": "What was said about the next conversation",
  "description": "A short summary for the appointment card"
}

Examples:
- "I'll check in on you this evening around 8pm" -> 
  {"has_commitment": true, "source": "ai_proposal", "commitment_type": "tonight", "specific_time": "20:00", "natural_text": "I'll check in on you this evening", "description": "Check in this evening"}

- "Can you text me tomorrow morning?" -> 
  {"has_commitment": true, "source": "user_request", "commitment_type": "tomorrow", "specific_time": "10:00", "natural_text": "Can you text me tomorrow morning?", "description": "User wants contact tomorrow morning"}

- "Talk in 2 hours" -> 
  {"has_commitment": true, "source": "ai_proposal", "commitment_type": "hours", "hours_value": 2, "natural_text": "Talk in 2 hours", "description": "Talk in 2 hours"}

Output ONLY the JSON, no other text."""


def parse_conversation_for_appointments() -> dict:
    """Analyze the recent conversation for appointment/commitment.

    This is called after 30 min inactivity OR at end of conversation.
    Returns a structured appointment card if one is found.
    """
    conversation = get_fresh_memory()

    if not conversation:
        return {"has_commitment": False}

    prompt = f"""Analyze the recent conversation below for any time-related commitments:

Recent messages:
{chr(10).join([f"- {m['user_message'][:200]}... | Response: {m['ai_message'][:200]}..." for m in conversation[-5:]])}

{f"{len(conversation)} messages in conversation history" if len(conversation) > 5 else ""}

Did either you or the user mention a specific time for the next conversation? Output the appointment card JSON."""

    try:
        response = chat(
            prompt=prompt,
            model=COMPANION_MODEL,
            system_prompt=APPOINTMENT_EXTRACTION_PROMPT,
            include_memory=False,
        )

        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            appointment = json.loads(json_match.group())
            return appointment
        else:
            return {"has_commitment": False}

    except Exception as e:
        print(f"Error parsing appointment: {e}")
        return {"has_commitment": False}


def parse_response_for_appointment(ai_response: str) -> dict:
    """Parse a single response for commitments (legacy support)."""
    prompt = f"""Analyze this response you gave:
"{ai_response}"

Did you make a specific time-based commitment to contact the user? Output appointment card JSON."""

    try:
        response = chat(
            prompt=prompt,
            model=COMPANION_MODEL,
            system_prompt=APPOINTMENT_EXTRACTION_PROMPT,
            include_memory=False,
        )

        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            appointment = json.loads(json_match.group())
            return appointment
        else:
            return {"has_commitment": False}

    except Exception as e:
        print(f"Error parsing appointment: {e}")
        return {"has_commitment": False}


def calculate_due_time(appointment: dict) -> str:
    """Calculate the due datetime from an appointment card."""
    if not appointment.get("has_commitment"):
        return None

    now = datetime.now()
    commitment_type = appointment.get("commitment_type")

    if commitment_type == "hours":
        hours = appointment.get("hours_value", 2)
        due = now + timedelta(hours=hours)
        return due.isoformat()

    elif commitment_type == "today":
        due = now.replace(hour=23, minute=59, second=0, microsecond=0)
        return due.isoformat()

    elif commitment_type == "tonight":
        if now.hour < 18:
            due = now.replace(hour=20, minute=0, second=0, microsecond=0)
        else:
            due = now + timedelta(days=1)
            due = due.replace(hour=20, minute=0, second=0, microsecond=0)
        return due.isoformat()

    elif commitment_type == "tomorrow":
        due = now + timedelta(days=1)
        due = due.replace(hour=10, minute=0, second=0, microsecond=0)
        return due.isoformat()

    elif commitment_type == "specific_time":
        specific = appointment.get("specific_time", "")
        if "T" in specific:
            return specific
        if ":" in specific:
            try:
                time_parts = specific.split(":")
                hour = int(time_parts[0])
                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if due < now:
                    due = due + timedelta(days=1)
                return due.isoformat()
            except:
                pass
        return (now + timedelta(hours=24)).isoformat()

    return None


if __name__ == "__main__":
    result = parse_conversation_for_appointments()
    print(f"Appointment found: {result}")
    if result.get("has_commitment"):
        due = calculate_due_time(result)
        print(f"Due: {due}")
