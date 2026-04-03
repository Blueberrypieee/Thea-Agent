"""
main.py
───────
Entry point. Nothing else lives here.

Usage:
    python main.py          → CLI mode
    python main.py telegram → Telegram bot mode
"""

import sys
import logging
import logging.handlers
import os

from agent import config


# ── Logging setup ───────────────────────────────────────────────────────────────

def setup_logging():
    os.makedirs(config.LOG_DIR, exist_ok=True)

    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    fmt       = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(log_level)

    # Console
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # General log
    file_handler = logging.handlers.RotatingFileHandler(
        config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Error log
    error_handler = logging.handlers.RotatingFileHandler(
        config.ERROR_LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(fmt)
    root.addHandler(error_handler)


# ── CLI mode ────────────────────────────────────────────────────────────────────

def run_cli():
    from agent import agent

    logger = logging.getLogger(__name__)
    logger.info("Thea Agent starting — CLI mode")
    print("\n🤖 Thea Agent is ready. Type 'exit' to quit.\n")

    history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nThea: Dadah! 👋")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "bye"):
            print("Thea: Dadah! 👋")
            break

        response = agent.run(user_input, history=history)
        print(f"Thea: {response}\n")

        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": response})


# ── Entry point ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    setup_logging()

    mode = sys.argv[1] if len(sys.argv) > 1 else "cli"

    if mode == "telegram":
        from telegram_bot import run_bot
        run_bot()
    else:
        run_cli()


