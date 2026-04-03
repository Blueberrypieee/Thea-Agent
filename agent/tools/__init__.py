"""
tools/__init__.py
─────────────────
Responsibility : Aggregate all tool registries into one.
                 Expose unified execute() and get_tool_list_for_prompt().

How to add a new tool module:
    1. Create agent/tools/your_module.py with a TOOLS dict
    2. Import it here and merge into TOOLS_REGISTRY
"""

import logging

from agent.tools.base   import TOOLS as BASE_TOOLS
from agent.tools.sheets import TOOLS as SHEETS_TOOLS
from agent.tools.email  import TOOLS as EMAIL_TOOLS

logger = logging.getLogger(__name__)

# ── Single unified registry ─────────────────────────────────────────────────────

TOOLS_REGISTRY: dict[str, dict] = {
    **BASE_TOOLS,
    **SHEETS_TOOLS,
    **EMAIL_TOOLS,
}


# ── Helpers ─────────────────────────────────────────────────────────────────────

def get_tool_list_for_prompt() -> str:
    """Returns formatted tool list string for LLM prompt."""
    lines = [f"- {name}: {meta['description']}" for name, meta in TOOLS_REGISTRY.items()]
    return "\n".join(lines)


def execute(tool_name: str, tool_input: str) -> str:
    """
    Execute a registered tool by name.
    Never crashes — always returns a string.

    Returns:
        str → JSON string with {"status": "success"|"error", ...}
    """
    import json

    tool = TOOLS_REGISTRY.get(tool_name)

    if tool is None:
        logger.warning("execute: unknown tool requested: '%s'", tool_name)
        return json.dumps({
            "status":  "error",
            "message": f"Tool '{tool_name}' not found. Available: {', '.join(TOOLS_REGISTRY.keys())}"
        })

    try:
        logger.info("execute: running tool '%s'", tool_name)
        result = tool["fn"](tool_input)
        logger.info("execute: tool '%s' completed", tool_name)
        return result

    except Exception as e:
        logger.error("execute: tool '%s' raised exception: %s", tool_name, e)
        return json.dumps({
            "status":  "error",
            "message": f"Tool '{tool_name}' failed unexpectedly: {str(e)}"
        })

