"""
tools/base.py
─────────────
Responsibility : Built-in utility tools.
                 No external dependencies.
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Output helpers ──────────────────────────────────────────────────────────────

def _ok(data: str) -> str:
    return json.dumps({"status": "success", "data": data}, ensure_ascii=False)

def _err(message: str) -> str:
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


# ── Tool functions ──────────────────────────────────────────────────────────────

def echo(input: str) -> str:
    """Echoes back whatever input is given. Used for testing."""
    logger.info("echo: input=%s", input[:100])
    result = input.strip() or "(empty)"
    logger.info("echo: success")
    return _ok(result)


def get_time(input: str) -> str:
    """Returns the current date and time."""
    logger.info("get_time: called")
    now = datetime.now().strftime("%A, %d %B %Y — %H:%M:%S")
    logger.info("get_time: success")
    return _ok(now)


# ── Registry fragment ───────────────────────────────────────────────────────────

TOOLS = {
    "echo": {
        "fn":          echo,
        "description": "Echoes back whatever input is given. Use for testing.",
    },
    "get_time": {
        "fn":          get_time,
        "description": "Returns the current date and time.",
    },
}

