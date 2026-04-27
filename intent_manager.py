import random
import os

INTENT_FILE = os.getenv("INTENT_FILE", "library/interaction_intents.txt")

WORRY_TEMPLATES = {
    0: "Hey, thinking of you. How's your day going?",
    1: "Hi! Just checking in - how are you doing?",
    2: "Hey, haven't heard from you in a while. Everything alright?",
    3: "Hey, just wanted to make sure you're okay. Been a while since we talked.",
    4: "[Just checking in - let me know when you're free.]",
}


def load_intents() -> list:
    intents = []
    try:
        with open(INTENT_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    intents.append(line)
    except FileNotFoundError:
        intents = [WORRY_TEMPLATES[0]]
    return intents


def get_intent_for_worry_level(worry_level: int) -> str:
    intents = load_intents()

    if worry_level >= 4:
        return WORRY_TEMPLATES[4]

    if worry_level <= 1:
        return (
            random.choice(intents[:10])
            if len(intents) >= 10
            else random.choice(intents)
        )
    elif worry_level == 2:
        return (
            random.choice(intents[10:25])
            if len(intents) > 25
            else random.choice(intents)
        )
    else:
        return (
            random.choice(intents[25:]) if len(intents) > 25 else random.choice(intents)
        )


def get_worry_template(worry_level: int) -> str:
    level = min(worry_level, 4)
    return WORRY_TEMPLATES[level]


def get_random_intent() -> str:
    intents = load_intents()
    return random.choice(intents) if intents else WORRY_TEMPLATES[0]
