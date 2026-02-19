"""
Bot Runner – startet den Telegram Bot als Background-Thread in Streamlit.
Globale Variable verhindert doppelte Instanzen über Reruns hinweg.
"""

import threading
import asyncio
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

# Globale Variable – überlebt Streamlit Reruns
_bot_thread: threading.Thread | None = None


def _drop_webhook(token: str):
    """Webhook löschen damit Polling funktioniert"""
    try:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
        urllib.request.urlopen(url, timeout=5)
    except Exception:
        pass


async def _poll(app):
    from telegram import Update
    await app.initialize()
    await app.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )
    await app.start()
    logger.info("Bot läuft")
    while True:
        await asyncio.sleep(3600)


def _run_bot(token: str):
    from telegram.ext import Application, CommandHandler, CallbackQueryHandler
    from telegram_bot.handlers import (
        start_handler, today_handler, dates_handler,
        date_handler, bet_handler, button_callback_handler, error_handler,
    )

    # Webhook löschen bevor wir starten
    _drop_webhook(token)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("today", today_handler))
    app.add_handler(CommandHandler("dates", dates_handler))
    app.add_handler(CommandHandler("date", date_handler))
    app.add_handler(CommandHandler("bet", bet_handler))
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_error_handler(error_handler)

    try:
        loop.run_until_complete(_poll(app))
    except Exception as e:
        logger.error(f"Bot Fehler: {e}", exc_info=True)
    finally:
        loop.close()


def start_bot_in_background():
    """Startet Bot genau einmal pro Prozess"""
    global _bot_thread

    # Token laden
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        try:
            import streamlit as st
            token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
            if token:
                os.environ["TELEGRAM_BOT_TOKEN"] = token
        except Exception:
            pass

    if not token:
        return

    # Bereits aktiv → nichts tun
    if _bot_thread is not None and _bot_thread.is_alive():
        return

    _bot_thread = threading.Thread(
        target=_run_bot, args=(token,), daemon=True, name="TelegramBot"
    )
    _bot_thread.start()
    logger.info("Telegram Bot Thread gestartet")
