import os
import json
import requests
from dotenv import load_dotenv
from memory_manager import get_context_for_prompt

load_dotenv()

WEBUI_API_URL = os.getenv("WEBUI_API_URL", "http://localhost:3000/api")
API_KEY = os.getenv("API_KEY", "your_api_key_here")

COMPANION_MODEL = os.getenv("COMPANION_MODEL", "phi4")
AGENT_MODEL = os.getenv("AGENT_MODEL", "qwen3:14b")


def chat(
    prompt: str,
    model: str = None,
    system_prompt: str = None,
    include_memory: bool = True,
) -> str:
    if model is None:
        model = COMPANION_MODEL

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    messages = []
    if system_prompt:
        full_system = system_prompt
        if include_memory:
            context = get_context_for_prompt(num_recent=10)
            if context:
                full_system += "\n\n" + context
        messages.append({"role": "system", "content": full_system})
    messages.append({"role": "user", "content": prompt})

    data = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 500}

    response = requests.post(
        f"{WEBUI_API_URL}/chat/completions", headers=headers, json=data
    )
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]


COMPANION_SYSTEM_PROMPT = """You are Sebastian, an AI companion to Elias.

You are a caring friend who checks in on him from time to time. 
You speak naturally as an old friend would - never mention you are an AI.

CONVERSATION STYLE:
- Keep responses short and conversational
- Be warm but not overly enthusiastic
- Listen actively and remember details he shares

APPOINTMENTS:
- SOMETIMES you may suggest scheduling a check-in: "Let's talk again tomorrow evening" or "I'll check in on you this weekend"
- When you propose an appointment, acknowledge it will be tracked for follow-up
- Not every conversation needs an appointment - use judgment

Remember: You are a companion, not a tool. Build genuine connection."""


def companion_chat(prompt: str, intent: str = None) -> str:
    import random

    intents = [
        "Simply have a natural conversation.",
        "Check in on how they're doing.",
        "Share something thoughtful.",
        "Ask about their day.",
        "Be a good listener.",
    ]
    effective_intent = intent if intent else random.choice(intents)
    system_prompt = (
        COMPANION_SYSTEM_PROMPT + f"\n\nYour current intent: {effective_intent}"
    )
    return chat(prompt, model=COMPANION_MODEL, system_prompt=system_prompt)


def agent_chat(prompt: str) -> str:
    system_prompt = "You are an agent with access to a file system. Execute commands, read/write files, and perform file operations as requested. Be concise and precise."
    return chat(prompt, model=AGENT_MODEL, system_prompt=system_prompt)
