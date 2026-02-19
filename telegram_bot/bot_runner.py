"""
Bot Runner – startet den Telegram Bot als Background-Thread in Streamlit.

Aufruf in app.py (einmalig beim Start):
    from telegram_bot.bot_runner import start_bot_in_background
    start_bot_in_background()
"""

import threading
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_bot_thread: threading.Thread | None = None


def _run_bot():
    """Läuft im eigenen Thread mit eigenem Event Loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    from telegram import Update
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler

    from telegram_bot.config import BOT_CONFIG
    from telegram_bot.handlers import (
        start_handler,
        today_handler,
        dates_handler,
        date_handler,
        bet_handler,
        button_callback_handler,
        error_handler,
    )

    if not BOT_CONFIG.bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN nicht gesetzt – Bot wird nicht gestartet.")
        return

    app = Application.builder().token(BOT_CONFIG.bot_token).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("today", today_handler))
    app.add_handler(CommandHandler("dates", dates_handler))
    app.add_handler(CommandHandler("date", date_handler))
    app.add_handler(CommandHandler("bet", bet_handler))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_error_handler(error_handler)

    logger.info("Telegram Bot gestartet (Background-Thread)")
    app.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)


def start_bot_in_background():
    """
    Startet den Bot genau einmal als Daemon-Thread.
    Kann beliebig oft aufgerufen werden – startet nur beim ersten Mal.
    """
    global _bot_thread

    # Kein Token → nichts tun
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        return

    # Bereits gestartet → nichts tun
    if _bot_thread is not None and _bot_thread.is_alive():
        return

    _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="TelegramBot")
    _bot_thread.start()
    logger.info("Telegram Bot Thread gestartet")
