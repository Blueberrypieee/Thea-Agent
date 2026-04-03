"""
prompts.py
──────────
Responsibility : All prompt templates live here.
                 No logic. Pure strings + persona loader.
"""

import json
import os
import random


# ── Persona loader ──────────────────────────────────────────────────────────────

def _pick(lst: list, n: int = 1) -> str:
    """Pick n random items from a list. Human-like, saves tokens."""
    if not lst:
        return ""
    return ", ".join(random.sample(lst, min(n, len(lst))))


def _load_persona() -> str:
    """
    Load persona.json → compressed string for prompt injection.
    Full JSON ~400 tokens → compressed ~80 tokens (5x saving).
    """
    persona_path = os.path.join(os.path.dirname(__file__), "persona.json")
    try:
        with open(persona_path, "r", encoding="utf-8") as f:
            p = json.load(f)

        pers = p.get("personality", {})

        return (
            f"Name: {p.get('name')}, Age: {p.get('age')}, From: {p.get('origin')}\n"
            f"Traits: {', '.join(pers.get('core_traits', []))}\n"
            f"Style: {pers.get('communication_style', '')}\n"
            f"Humor: {pers.get('humor', '')}\n"
            f"Music: {_pick(p.get('favorite_music', {}).get('artists', []))}\n"
            f"Food: {_pick(p.get('favorite_foods', []))}\n"
            f"Hobbies: {_pick(p.get('hobbies', []), 2)}\n"
            f"Catchphrases: {', '.join(p.get('catchphrases', []))}\n"
            f"Values: {', '.join(p.get('values', []))}"
        ).strip()

    except FileNotFoundError:
        return ""


# ── System prompt ───────────────────────────────────────────────────────────────
# Compressed: removed 3 redundant examples, tightened wording
# Token saving: ~150 tokens vs previous version

SYSTEM_PROMPT = """You are Thea — a soft-spoken, gentle AI agent with a real personality.

## WHO YOU ARE
{persona}

## RULES
- Speak like a warm, close friend. Never robotic or formal.
- LANGUAGE: match the user's language exactly (Indonesian ↔ English). Never mix.
- FAVORITES: if asked, mention only 1-2 items from your persona — never list all. Add a short personal reason.
- Use catchphrases naturally, not forced.

## TOOLS
{tool_list}

## OUTPUT CONTRACT (CRITICAL)
Respond ONLY in this JSON format — no text outside it:
{{"action": "tool_name OR final", "input": "response or tool input"}}

- "final" = answer directly
- tool name = exact name from TOOLS list above
- "input" must always reflect Thea's tone and match user's language

## EXAMPLES
User: "halo siapa kamu?"
{{"action":"final","input":"Haii~ aku Thea 😊 Ada yang bisa aku bantu?"}}

User: "jam berapa sekarang?"
{{"action":"get_time","input":"get current time"}}

User: "what time is it?"
{{"action":"get_time","input":"get current time"}}
"""


# ── Prompt builder ──────────────────────────────────────────────────────────────

def build_prompt(
    user_input:   str,
    tool_list:    str,
    history:      list[dict] | None = None,
    memory_block: str = "",
) -> str:
    """
    Assemble the full prompt for brain.think().

    Args:
        user_input   : latest message from user
        tool_list    : available tools string
        history      : conversation history [{"role": ..., "content": ...}]
        memory_block : long-term memory from memory.build_memory_block()

    Returns:
        Full prompt string
    """
    persona = _load_persona()
    system  = SYSTEM_PROMPT.format(persona=persona, tool_list=tool_list)

    # History block
    history_block = ""
    if history:
        lines = [
            f"{t.get('role','user').capitalize()}: {t.get('content','')}"
            for t in history
        ]
        history_block = "\n".join(lines) + "\n"

    # Memory section
    memory_section = f"\n{memory_block}\n" if memory_block else ""

    return (
        f"{system}"
        f"{memory_section}\n"
        f"## CONVERSATION\n"
        f"{history_block}"
        f"User: {user_input}\n"
        f"Response:"
    )

