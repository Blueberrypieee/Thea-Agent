import json
import logging
import time
import telebot

from telebot.apihelper import ApiTelegramException
from agent import config
from agent import agent
from agent.tools import execute as tools_execute

logger = logging.getLogger(__name__)

# ── Per-user state ─────────────────────────────────────────────────────────────
user_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 6

# ── Pending confirmations ──────────────────────────────────────────────────────
pending_confirmations: dict[int, dict] = {}

# Tools yang butuh konfirmasi
TOOLS_REQUIRING_CONFIRM = {"send_email", "write_sheet", "append_sheet"}

# Keyword konfirmasi
CONFIRM_YES = {"ya", "yes", "yep", "iya", "ok", "oke", "lanjut", "kirim", "send", "y"}
CONFIRM_NO  = {"tidak", "no", "nope", "batal", "cancel", "jangan", "stop", "n"}

# ── Typing throttle ────────────────────────────────────────────────────────────
last_typing_time = {}

def safe_typing(bot, chat_id):
    now = time.time()
    if chat_id not in last_typing_time or now - last_typing_time[chat_id] > 2:
        try:
            bot.send_chat_action(chat_id, "typing", timeout=5)
            last_typing_time[chat_id] = now
        except Exception:
            pass  # typing indicator non-critical, skip semua error


# ── Confirmation message builder ───────────────────────────────────────────────

def _build_confirm_message(tool: str, tool_input: str) -> str:
    try:
        params = json.loads(tool_input)
    except (json.JSONDecodeError, TypeError):
        params = {}

    if tool == "send_email":
        to      = params.get("to", "?")
        subject = params.get("subject", "?")
        body    = params.get("body", "")
        preview = body[:80] + ("..." if len(body) > 80 else "")
        return (
            f"📧 Aku mau kirim email:\n"
            f"• Ke: {to}\n"
            f"• Subject: {subject}\n"
            f"• Isi: {preview}\n\n"
            f"Lanjut kirim? (ya/tidak)"
        )
    if tool == "write_sheet":
        sheet  = params.get("sheet", "Sheet1")
        range_ = params.get("range", "?")
        rows   = len(params.get("values", []))
        return (
            f"📊 Aku mau nulis ke Google Sheets:\n"
            f"• Sheet: {sheet}, Range: {range_}\n"
            f"• Jumlah baris: {rows}\n\n"
            f"Lanjut? (ya/tidak)"
        )
    if tool == "append_sheet":
        sheet = params.get("sheet", "Sheet1")
        rows  = len(params.get("values", []))
        return (
            f"📊 Aku mau nambahin {rows} baris ke sheet '{sheet}'.\n\n"
            f"Lanjut? (ya/tidak)"
        )
    return f"Aku mau jalankan '{tool}'. Lanjut? (ya/tidak)"


# ── Bot init & auth ────────────────────────────────────────────────────────────

def _make_bot() -> telebot.TeleBot:
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")
    return telebot.TeleBot(token)

def _is_allowed(user_id: int) -> bool:
    return user_id == config.TELEGRAM_ALLOWED_USER_ID

def _send(bot, message, text: str):
    try:
        bot.reply_to(message, text, timeout=15)
    except ApiTelegramException as e:
        if e.error_code == 429:
            time.sleep(getattr(e, "retry_after", 2))
            try:
                bot.reply_to(message, text, timeout=15)
            except Exception as retry_err:
                logger.error("Send retry failed: %s", retry_err)
        else:
            logger.error("Send message error: %s", e)
    except Exception as e:
        logger.error("Send message unexpected error: %s", e)

def _update_history(user_id: int, user_input: str, response: str):
    if user_id not in user_histories:
        user_histories[user_id] = []
    history = user_histories[user_id]
    history.append({"role": "user",      "content": user_input})
    history.append({"role": "assistant", "content": response})
    if len(history) > MAX_HISTORY * 2:
        user_histories[user_id] = history[-(MAX_HISTORY * 2):]


# ── Agent run dengan intercept ─────────────────────────────────────────────────

def _run_agent_with_intercept(user_id: int, user_input: str) -> tuple[str, dict | None]:
    """
    Run agent loop tapi intercept sebelum execute confirmable tool.

    Returns:
        (response, pending) dimana:
        - pending = None  → agent selesai normal, response = final answer
        - pending = dict  → butuh konfirmasi, response = confirm message
    """
    import re
    from agent import brain, prompts, memory
    from agent.tools import get_tool_list_for_prompt, TOOLS_REGISTRY, execute as tex
    from agent import agent as ag

    history    = user_histories.get(user_id, [])
    tool_list  = get_tool_list_for_prompt()
    iteration  = 0
    current_input = user_input

    ag._extract_and_save_memory(user_input)
    ag._update_last_topic(user_input)

    MAX_ITER = 5

    while iteration < MAX_ITER:
        iteration += 1
        memory_block = memory.build_memory_block()

        prompt = prompts.build_prompt(
            user_input=current_input,
            tool_list=tool_list,
            history=history,
            memory_block=memory_block,
        )

        llm_result = brain.think(prompt)

        if isinstance(llm_result, dict) and "error" in llm_result:
            return llm_result["message"], None

        parsed = ag._parse_llm_response(llm_result)

        if parsed is None:
            current_input = (
                f"{user_input}\n\nIMPORTANT: Respond ONLY with valid JSON:\n"
                f'{{ "action": "final", "input": "your response" }}'
            )
            continue

        action     = parsed["action"]
        tool_input = parsed["input"]

        if action == "final":
            return str(tool_input), None

        if not ag._validate_tool(action):
            current_input = (
                f"{user_input}\n\nNote: Tool '{action}' does not exist.\n"
                f"Available tools:\n{tool_list}\nUse a valid tool or 'final'."
            )
            continue

        # ── Intercept confirmable tool ──
        if action in TOOLS_REQUIRING_CONFIRM:
            input_str = json.dumps(tool_input, ensure_ascii=False) if isinstance(tool_input, dict) else str(tool_input)
            pending = {"tool": action, "input": input_str}
            confirm_msg = _build_confirm_message(action, input_str)
            logger.info("Intercepted confirmable tool: %s for user %d", action, user_id)
            return confirm_msg, pending

        # ── Execute non-confirmable tool normally ──
        tool_result = tex(action, str(tool_input))
        logger.info("Tool '%s' result: %s", action, str(tool_result)[:100])

        current_input = (
            f"Original request: {user_input}\n"
            f"Tool used: {action}\n"
            f"Tool result: {tool_result}\n"
            f"Task: Give a final answer to the user based on this result."
        )

    return "Hmm, aku butuh waktu lebih buat mikirin ini… coba tanya lagi ya 🙏", None


# ── Bot runner ─────────────────────────────────────────────────────────────────

def run_bot() -> None:
    bot = _make_bot()

    @bot.message_handler(commands=["start"])
    def start_handler(message):
        user_id = message.from_user.id
        if not _is_allowed(user_id):
            _send(bot, message, "Maaf, aku cuma bisa ngobrol sama orang tertentu aja 🙏")
            return
        user_histories[user_id] = []
        pending_confirmations.pop(user_id, None)
        _send(bot, message,
            "Haii~ aku Thea! 😊\n"
            "Seneng bisa ketemu kamu di sini.\n"
            "Ada yang bisa aku bantu hari ini?"
        )

    @bot.message_handler(commands=["clear"])
    def clear_handler(message):
        user_id = message.from_user.id
        if not _is_allowed(user_id):
            return
        user_histories[user_id] = []
        pending_confirmations.pop(user_id, None)
        _send(bot, message, "Memory sesi ini udah aku bersihkan~ mulai fresh lagi ya 🌿")

    @bot.message_handler(commands=["cancel"])
    def cancel_handler(message):
        user_id = message.from_user.id
        if not _is_allowed(user_id):
            return
        if user_id in pending_confirmations:
            pending_confirmations.pop(user_id)
            _send(bot, message, "Oke, dibatalin ya~ Ada yang lain? 😊")
        else:
            _send(bot, message, "Ga ada yang perlu dibatalin kok~")

    @bot.message_handler(func=lambda m: True, content_types=["text"])
    def message_handler(message):
        user_id    = message.from_user.id
        user_input = message.text.strip()

        if not _is_allowed(user_id):
            _send(bot, message, "Maaf, aku cuma bisa ngobrol sama orang tertentu aja 🙏")
            return

        if not user_input:
            return

        logger.info("Telegram message from %d: %s", user_id, user_input)
        safe_typing(bot, message.chat.id)

        # ── Handle pending confirmation ──
        if user_id in pending_confirmations:
            pending = pending_confirmations[user_id]
            answer  = user_input.lower().strip().rstrip("!.")

            if answer in CONFIRM_YES:
                pending_confirmations.pop(user_id)
                logger.info("User %d confirmed: %s", user_id, pending["tool"])
                safe_typing(bot, message.chat.id)

                try:
                    result = tools_execute(pending["tool"], pending["input"])
                    # Format result jadi jawaban Thea yang natural
                    final = agent.run(
                        f"Tool '{pending['tool']}' sudah dieksekusi. "
                        f"Hasil: {result}. "
                        f"Beritahu user dengan ramah bahwa aksinya berhasil atau gagal.",
                        history=user_histories.get(user_id, []),
                    )
                except Exception as e:
                    logger.error("Tool execution error: %s", e)
                    final = config.MSG_GENERAL_ERROR

                _send(bot, message, final)
                _update_history(user_id, user_input, final)
                return

            elif answer in CONFIRM_NO:
                pending_confirmations.pop(user_id)
                logger.info("User %d cancelled: %s", user_id, pending["tool"])
                _send(bot, message, "Oke, dibatalin ya~ Ada yang lain yang bisa aku bantu? 😊")
                _update_history(user_id, user_input, "Dibatalin.")
                return

            else:
                _send(bot, message,
                    "Hmm, aku kurang nangkep~ Ketik ya untuk lanjut atau tidak untuk batal 😊"
                )
                return

        # ── Normal flow dengan intercept ──
        if user_id not in user_histories:
            user_histories[user_id] = []

        try:
            response, pending = _run_agent_with_intercept(user_id, user_input)
        except Exception as e:
            logger.error("Agent error for user %d: %s", user_id, e)
            response, pending = config.MSG_GENERAL_ERROR, None

        if pending:
            pending_confirmations[user_id] = pending

        _send(bot, message, response)

        if not pending:
            _update_history(user_id, user_input, response)

        logger.info("Thea replied to %d", user_id)

    logger.info("Thea Telegram bot is running...")
    print("\n🤖 Thea Telegram Bot is running. Press Ctrl+C to stop.\n")
    bot.infinity_polling(skip_pending=True, interval=1, timeout=20)


