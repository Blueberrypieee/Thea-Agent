"""
agent/__init__.py
─────────────────
Public API for the agent package.

Usage:
    from agent import run           # run the agent
    from agent import think         # call LLM directly
    from agent import execute       # execute a tool directly
    from agent import TOOLS         # inspect registered tools
"""

from agent.agent  import run
from agent.brain  import think
from agent.tools  import execute, TOOLS_REGISTRY as TOOLS

__all__ = ["run", "think", "execute", "TOOLS"]

