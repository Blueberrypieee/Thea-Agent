import os
from dotenv import load_dotenv

load_dotenv()


# ── LLM Provider: OpenRouter ────────────────────────────────────────────────────

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Primary
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")

# Fallback
OPENROUTER_API_KEY_2 = os.getenv("OPENROUTER_API_KEY_2", "")
OPENROUTER_MODEL_2   = os.getenv("OPENROUTER_MODEL_2", "google/gemma-3-4b-it:free")

# ── Retry ────────────────────────────────────────────────────────────────────────

OPENROUTER_MAX_RETRIES = int(os.getenv("OPENROUTER_MAX_RETRIES", 3))
RETRY_DELAY_SECONDS    = float(os.getenv("RETRY_DELAY_SECONDS", 2.0))

# ── Persona Error Messages ──────────────────────────────────────────────────────

MSG_RATE_LIMIT   = "Tunggu bentar, Thea kecapean 😮‍💨"
MSG_GENERAL_ERROR = "Thea...pusing, istirahat bentar yaa :("

# ── Google Sheets ───────────────────────────────────────────────────────────────

SHEETS_CREDENTIALS_PATH = os.getenv(
    "SHEETS_CREDENTIALS_PATH",
    "credentials/sheets_service_account.json"
)

# ── Gmail SMTP ───────────────────────────────────────────────────────────────────

GMAIL_SENDER       = os.getenv("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# ── Telegram ────────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", 0))

# ── Logging ─────────────────────────────────────────────────────────────────────

LOG_DIR        = os.getenv("LOG_DIR", "logs")
LOG_FILE       = os.path.join(LOG_DIR, "agent.log")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "error.log")
LOG_LEVEL      = os.getenv("LOG_LEVEL", "INFO")

