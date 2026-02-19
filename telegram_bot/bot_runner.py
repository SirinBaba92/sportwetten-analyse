"""
Bot Runner – startet den Telegram Bot als Background-Thread in Streamlit.
Verwendet asyncio direkt (ohne Signal-Handler) für Thread-Kompatibilität.
"""

import threading
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

_bot_thread = None


async def _start_polling(app):
    """Startet Polling ohne Signal-Handler (Thread-kompatibel)"""
    from telegram import Update
    await app.initialize()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    await app.start()
    logger.info("Telegram Bot Polling läuft...")
    while True:
        await asyncio.sleep(3600)


def _run_bot():
    """Läuft im eigenen Thread mit eigenem Event Loop"""
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

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Application.builder().token(BOT_CONFIG.bot_token).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("today", today_handler))
    app.add_handler(CommandHandler("dates", dates_handler))
    app.add_handler(CommandHandler("date", date_handler))
    app.add_handler(CommandHandler("bet", bet_handler))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_error_handler(error_handler)

    try:
        loop.run_until_complete(_start_polling(app))
    except Exception as e:
        logger.error(f"Bot Fehler: {e}", exc_info=True)
    finally:
        loop.close()


def start_bot_in_background():
    """
    Startet den Bot genau einmal als Daemon-Thread.
    Kann beliebig oft aufgerufen werden – startet nur beim ersten Mal.
    """
    global _bot_thread

    # Token aus Env oder Streamlit Secrets laden
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        try:
            import streamlit as st
            token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
            if not token:
                return
            os.environ["TELEGRAM_BOT_TOKEN"] = token
        except Exception:
            return

    if _bot_thread is not None and _bot_thread.is_alive():
        return

    _bot_thread = threading.Thread(target=_run_bot, daemon=True, name="TelegramBot")
    _bot_thread.start()
    logger.info("Telegram Bot Thread gestartet")
