"""
memory.py
─────────
Responsibility : Manage Thea's long-term memory.
                 - Load/save memory from JSON file
                 - Update specific keys via dot-notation
                 - Inject memory context into prompt

Storage        : agent/memory.json (auto-created on first save)

Memory types:
    long_term  → persistent facts about user (survives across sessions)
    short_term → conversation history (lives in main.py / telegram_bot.py)
"""

import json
import os
import copy
import logging

logger = logging.getLogger(__name__)

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "memory.json")

DEFAULT_MEMORY: dict = {
    "user": {
        "name":        None,
        "location":    None,
        "preferences": [],
        "facts":       []
    },
    "context": {
        "last_topic": None,
        "last_seen":  None,
    }
}


# ── Core operations ─────────────────────────────────────────────────────────────

def load() -> dict:
    """
    Load memory from file.
    Returns deep copy of DEFAULT_MEMORY if file doesn't exist or is corrupted.
    """
    if not os.path.exists(MEMORY_PATH):
        logger.info("No memory file found, starting fresh")
        return copy.deepcopy(DEFAULT_MEMORY)

    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Ensure all default keys exist (handles schema additions over time)
        _fill_missing_keys(data, DEFAULT_MEMORY)
        return data

    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load memory: %s — using default", e)
        return copy.deepcopy(DEFAULT_MEMORY)


def save(mem: dict) -> bool:
    """
    Save memory dict to file.
    Returns True on success, False on failure.
    """
    try:
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2, ensure_ascii=False)
        return True
    except IOError as e:
        logger.error("Failed to save memory: %s", e)
        return False


def update(key_path: str, value) -> bool:
    """
    Update a specific key in memory using dot-notation and save.

    Args:
        key_path : e.g. "user.name" or "context.last_topic"
        value    : value to set

    Returns:
        True on success, False on failure

    Example:
        update("user.name", "Rian")
        update("context.last_topic", "crypto")
    """
    try:
        mem  = load()
        keys = key_path.split(".")

        target = mem
        for key in keys[:-1]:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
            target = target[key]

        target[keys[-1]] = value
        saved = save(mem)

        if saved:
            logger.info("Memory updated: %s = %s", key_path, value)
        return saved

    except Exception as e:
        logger.error("Memory update failed for '%s': %s", key_path, e)
        return False


def append_fact(fact: str) -> bool:
    """
    Append a unique fact about the user.
    Skips silently if fact already exists.

    Example:
        append_fact("suka dengerin musik malem-malem")
    """
    if not fact or not fact.strip():
        return False

    mem   = load()
    facts = mem.get("user", {}).get("facts", [])

    if fact in facts:
        return True  # already exists, not an error

    facts.append(fact.strip())
    mem["user"]["facts"] = facts
    return save(mem)


def append_preference(preference: str) -> bool:
    """
    Append a unique user preference.
    Skips silently if preference already exists.

    Example:
        append_preference("prefer jawaban singkat")
    """
    if not preference or not preference.strip():
        return False

    mem   = load()
    prefs = mem.get("user", {}).get("preferences", [])

    if preference in prefs:
        return True

    prefs.append(preference.strip())
    mem["user"]["preferences"] = prefs
    return save(mem)


def clear() -> bool:
    """Reset memory to default. Irreversible."""
    logger.warning("Memory cleared — all user data reset")
    return save(copy.deepcopy(DEFAULT_MEMORY))


# ── Schema helper ───────────────────────────────────────────────────────────────

def _fill_missing_keys(data: dict, default: dict) -> None:
    """
    Recursively fill missing keys from default into data.
    Handles cases where memory.json is from an older schema version.
    """
    for key, val in default.items():
        if key not in data:
            data[key] = copy.deepcopy(val)
        elif isinstance(val, dict) and isinstance(data[key], dict):
            _fill_missing_keys(data[key], val)


# ── Prompt injection ────────────────────────────────────────────────────────────

def build_memory_block() -> str:
    """
    Build a compact memory context string to inject into the prompt.
    Returns empty string if nothing meaningful is stored.

    Injected as ## WHAT YOU REMEMBER ABOUT THE USER in the prompt.
    """
    mem  = load()
    user = mem.get("user", {})
    ctx  = mem.get("context", {})

    lines = []

    if user.get("name"):
        lines.append(f"- User's name: {user['name']}")

    if user.get("location"):
        lines.append(f"- User's location: {user['location']}")

    if user.get("preferences"):
        lines.append(f"- User's preferences: {', '.join(user['preferences'])}")

    if user.get("facts"):
        for fact in user["facts"]:
            lines.append(f"- {fact}")

    if ctx.get("last_topic"):
        lines.append(f"- Last topic: {ctx['last_topic']}")

    if not lines:
        return ""

    return "## WHAT YOU REMEMBER ABOUT THE USER\n" + "\n".join(lines)

