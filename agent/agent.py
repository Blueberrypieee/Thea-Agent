"""
agent.py
────────
Responsibility : The agent loop.
                 - Build prompt (with memory + persona)
                 - Call brain.think()
                 - Parse JSON response (robust)
                 - Validate + execute tools
                 - Extract + save memory
                 - Return final answer

Rules          : No LLM calls here. No tool logic here.
                 Only orchestration.
"""

import re
import json
import logging
from datetime import datetime

from agent import brain, prompts, tools, memory, config

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


# ── JSON parser (robust) ────────────────────────────────────────────────────────

def _parse_llm_response(raw: str) -> dict | None:
    """
    Robust JSON parser — handles LLM output imperfections.

    Attempts in order:
      1. Direct parse
      2. Strip code fences (```json ... ```)
      3. Extract first {...} block via regex (handles trailing text)
      4. Give up → return None
    """
    if not raw or not raw.strip():
        logger.warning("LLM returned empty response")
        return None

    cleaned = raw.strip()

    # Attempt 1: direct parse
    try:
        parsed = json.loads(cleaned)
        return _validate_contract(parsed)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip code fences
    if "```" in cleaned:
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if fence_match:
            try:
                parsed = json.loads(fence_match.group(1).strip())
                return _validate_contract(parsed)
            except json.JSONDecodeError:
                pass

    # Attempt 3: extract first {...} block (handles trailing text)
    brace_match = re.search(r"\{[\s\S]*?\}", cleaned)
    if brace_match:
        try:
            parsed = json.loads(brace_match.group(0))
            return _validate_contract(parsed)
        except json.JSONDecodeError:
            pass

    logger.warning("All JSON parse attempts failed | raw: %s", raw[:300])
    return None


def _validate_contract(parsed: dict) -> dict | None:
    """Validate JSON contract: must have 'action' and 'input' keys."""
    if not isinstance(parsed, dict):
        return None
    if "action" not in parsed or "input" not in parsed:
        logger.warning("LLM response missing required keys: %s", parsed)
        return None
    return parsed


# ── Tool validation ─────────────────────────────────────────────────────────────

def _validate_tool(action: str) -> bool:
    """
    Check if tool exists before executing.
    Prevents crashes from LLM hallucinating tool names.
    """
    from agent.tools import TOOLS_REGISTRY
    return action in TOOLS_REGISTRY or action == "final"


# ── Memory extractor ────────────────────────────────────────────────────────────

def _extract_and_save_memory(user_input: str) -> None:
    """Extract basic facts from user input and save to long-term memory."""
    text = user_input.lower().strip()

    name_triggers = [
        "nama aku ", "nama saya ", "panggil aku ", "panggil saya ",
        "my name is ", "call me ", "i'm ", "i am ",
    ]
    for trigger in name_triggers:
        if trigger in text:
            idx  = text.index(trigger) + len(trigger)
            name = user_input[idx:].split()[0].strip(".,!?")
            if name:
                memory.update("user.name", name.capitalize())
                logger.info("Memory: captured name = %s", name)
            break

    location_triggers = [
        "aku tinggal di ", "saya tinggal di ", "aku dari ", "saya dari ",
        "i live in ", "i'm from ", "i am from ", "based in ",
    ]
    for trigger in location_triggers:
        if trigger in text:
            idx      = text.index(trigger) + len(trigger)
            location = user_input[idx:].split()[0].strip(".,!?")
            if location:
                memory.update("user.location", location.capitalize())
                logger.info("Memory: captured location = %s", location)
            break

    memory.update("context.last_seen", datetime.now().strftime("%Y-%m-%d %H:%M"))


def _update_last_topic(user_input: str) -> None:
    topic = user_input[:60].strip()
    memory.update("context.last_topic", topic)


# ── Agent loop ──────────────────────────────────────────────────────────────────

def run(user_input: str, history: list[dict] | None = None) -> str:
    """
    Main agent entry point.

    Args:
        user_input : message from the user
        history    : optional conversation history

    Returns:
        str → final answer to show the user
    """
    logger.info("Agent received input: %s", user_input)

    _extract_and_save_memory(user_input)
    _update_last_topic(user_input)

    tool_list     = tools.get_tool_list_for_prompt()
    iteration     = 0
    current_input = user_input

    while iteration < MAX_ITERATIONS:
        iteration += 1
        logger.info("── Iteration %d/%d ──", iteration, MAX_ITERATIONS)

        # Refresh memory each iteration — picks up facts extracted mid-loop
        memory_block = memory.build_memory_block()

        # Step 1: Build prompt
        prompt = prompts.build_prompt(
            user_input=current_input,
            tool_list=tool_list,
            history=history,
            memory_block=memory_block,
        )

        # Step 2: Think
        llm_result = brain.think(prompt)

        if isinstance(llm_result, dict) and "error" in llm_result:
            logger.error("Brain returned error: %s", llm_result)
            return llm_result["message"]

        # Step 3: Parse JSON (robust — 3 attempts)
        parsed = _parse_llm_response(llm_result)

        if parsed is None:
            logger.warning("JSON parse failed on iteration %d — retrying with correction", iteration)
            current_input = (
                f"{user_input}\n\n"
                f"IMPORTANT: Respond ONLY with valid JSON:\n"
                f'{{ "action": "final", "input": "your response" }}'
            )
            continue

        action     = parsed["action"]
        tool_input = parsed["input"]

        logger.info("Action: %s | Input: %s", action, str(tool_input)[:100])

        # Step 4: Final answer
        if action == "final":
            logger.info("Agent reached final answer at iteration %d", iteration)
            return tool_input

        # Step 5: Validate tool exists
        if not _validate_tool(action):
            logger.warning("Unknown tool: '%s' — asking LLM to retry", action)
            current_input = (
                f"{user_input}\n\n"
                f"Note: Tool '{action}' does not exist.\n"
                f"Available tools:\n{tool_list}\n"
                f"Use a valid tool name or 'final'."
            )
            continue

        # Step 6: Execute tool
        tool_result = tools.execute(action, tool_input)
        logger.info("Tool '%s' result: %s", action, str(tool_result)[:100])

        # Step 7: Feed result back cleanly
        current_input = (
            f"Original request: {user_input}\n"
            f"Tool used: {action}\n"
            f"Tool result: {tool_result}\n"
            f"Task: Give a final answer to the user based on this result."
        )

    # Graceful max iteration message
    logger.error("Agent exceeded MAX_ITERATIONS (%d)", MAX_ITERATIONS)
    return "Hmm, aku butuh waktu lebih buat mikirin ini… coba tanya lagi ya 🙏"


