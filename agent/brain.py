"""
brain.py
────────
Responsibility : LLM communication ONLY.
                 - Call OpenRouter primary with retry
                 - Fallback to OpenRouter secondary
                 - Return raw text or structured error dict

Rules          : MUST NOT know about tools, agent logic, or memory.
"""

import time
import logging
import requests

from agent import config

logger = logging.getLogger(__name__)


# ── Structured error helpers ────────────────────────────────────────────────────

def _rate_limit_error() -> dict:
    return {"error": "rate_limit", "message": config.MSG_RATE_LIMIT}

def _general_error(detail: str = "") -> dict:
    logger.error("LLM general error: %s", detail)
    return {"error": "general", "message": config.MSG_GENERAL_ERROR}


# ── Response validator ──────────────────────────────────────────────────────────

def _extract_content(data: dict) -> str | None:
    """
    Safely extract text content from OpenRouter response.
    Returns None if response structure is unexpected.
    """
    try:
        content = data["choices"][0]["message"]["content"]
        if not content or not content.strip():
            logger.warning("OpenRouter returned empty content")
            return None
        return content
    except (KeyError, IndexError, TypeError) as e:
        logger.warning("Unexpected response structure: %s | data: %s", e, str(data)[:200])
        return None


# ── OpenRouter caller ───────────────────────────────────────────────────────────

def _call_openrouter(prompt: str, api_key: str, model: str) -> str:
    """
    Send prompt to OpenRouter and return raw text response.
    Raises:
        requests.HTTPError  → non-2xx status
        ValueError          → empty or malformed response
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    resp = requests.post(
        config.OPENROUTER_API_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    data    = resp.json()
    content = _extract_content(data)

    if content is None:
        raise ValueError(f"Empty or malformed response from {model}")

    return content


# ── Provider with retry ─────────────────────────────────────────────────────────

def _try_provider(prompt: str, api_key: str, model: str, label: str) -> str | None:
    """
    Try a single OpenRouter provider with retry logic.

    Returns:
        str  → response text on success
        None → all retries exhausted (non-rate-limit errors)

    Raises:
        requests.HTTPError with 429 → caller decides to fallback
    """
    # Mask API key for safe logging (show last 6 chars only)
    key_hint = f"...{api_key[-6:]}" if len(api_key) > 6 else "***"
    max_retries = config.OPENROUTER_MAX_RETRIES

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "%s attempt %d/%d | model: %s | key: %s",
                label, attempt, max_retries, model, key_hint
            )
            result = _call_openrouter(prompt, api_key, model)
            logger.info("%s OK | model: %s | key: %s", label, model, key_hint)
            return result

        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            logger.warning(
                "%s HTTP %d on attempt %d | model: %s | key: %s",
                label, status, attempt, model, key_hint
            )

            if status == 429:
                logger.warning("%s rate-limited — bubbling up for fallback", label)
                raise  # let think() handle fallback

            if status in (401, 403):
                logger.error("%s auth error (HTTP %d) — skipping retries", label, status)
                return None  # no point retrying auth errors

            if attempt < max_retries:
                logger.info("%s retrying in %.1fs...", label, config.RETRY_DELAY_SECONDS)
                time.sleep(config.RETRY_DELAY_SECONDS)

        except (requests.ConnectionError, requests.Timeout) as e:
            logger.warning("%s network error on attempt %d: %s", label, attempt, e)
            if attempt < max_retries:
                time.sleep(config.RETRY_DELAY_SECONDS)

        except requests.RequestException as e:
            logger.warning("%s request error on attempt %d: %s", label, attempt, e)
            if attempt < max_retries:
                time.sleep(config.RETRY_DELAY_SECONDS)

        except ValueError as e:
            # Empty/malformed response
            logger.warning("%s invalid response on attempt %d: %s", label, attempt, e)
            if attempt < max_retries:
                time.sleep(config.RETRY_DELAY_SECONDS)

    logger.error("%s exhausted all %d retries", label, max_retries)
    return None


# ── Public interface ─────────────────────────────────────────────────────────────

def think(prompt: str) -> str | dict:
    """
    Primary entry point for agent.py.

    Returns:
        str   → raw LLM text
        dict  → structured error {"error": "rate_limit"|"general", "message": "..."}

    Flow:
        1. Try primary   (OPENROUTER_API_KEY + OPENROUTER_MODEL)
        2. If fails      → try fallback (OPENROUTER_API_KEY_2 + OPENROUTER_MODEL_2)
        3. If both fail  → return structured error
    """

    # ── Primary ──
    try:
        result = _try_provider(
            prompt,
            api_key=config.OPENROUTER_API_KEY,
            model=config.OPENROUTER_MODEL,
            label="OpenRouter[primary]",
        )
        if result is not None:
            return result
        logger.warning("OpenRouter[primary] exhausted — switching to fallback")

    except requests.HTTPError:
        logger.warning("OpenRouter[primary] rate-limited — switching to fallback")

    # ── Fallback ──
    if not config.OPENROUTER_API_KEY_2:
        logger.error("No fallback configured (OPENROUTER_API_KEY_2 missing)")
        return _general_error("No fallback available")

    logger.info("OpenRouter[fallback] activating | model: %s", config.OPENROUTER_MODEL_2)

    try:
        result = _try_provider(
            prompt,
            api_key=config.OPENROUTER_API_KEY_2,
            model=config.OPENROUTER_MODEL_2,
            label="OpenRouter[fallback]",
        )
        if result is not None:
            return result
        logger.error("OpenRouter[fallback] also exhausted")
        return _general_error("Both providers exhausted")

    except requests.HTTPError:
        logger.error("OpenRouter[fallback] also rate-limited")
        return _rate_limit_error()

