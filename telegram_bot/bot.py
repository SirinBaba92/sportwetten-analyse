"""
Telegram Bot fuer Sportwetten-Analyse
Hauptdatei - startet den Bot und registriert alle Handler
"""

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

from telegram_bot.config import BOT_CONFIG
from telegram_bot.handlers import (
    start_handler,
    help_handler,
    analyze_handler,
    today_handler,
    quick_handler,
    live_handler,
    search_handler,
    bet_handler,
    place_handler,
    positions_handler,
    stats_handler,
    history_handler,
    train_handler,
    model_handler,
    settings_handler,
    bankroll_handler,
    alerts_handler,
    export_handler,
    button_callback_handler,
    error_handler
)

# Logging konfigurieren
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Startet den Telegram Bot"""
    logger.info("Bot startet...")
    
    # Bot-Application erstellen
    application = Application.builder().token(BOT_CONFIG.bot_token).build()
    
    # Start & Help
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    
    # Analyse Commands
    application.add_handler(CommandHandler("analyze", analyze_handler))
    application.add_handler(CommandHandler("today", today_handler))
    application.add_handler(CommandHandler("quick", quick_handler))
    application.add_handler(CommandHandler("live", live_handler))
    application.add_handler(CommandHandler("search", search_handler))
    
    # Wett-Management
    application.add_handler(CommandHandler("bet", bet_handler))
    application.add_handler(CommandHandler("place", place_handler))
    application.add_handler(CommandHandler("positions", positions_handler))
    
    # Performance & Stats
    application.add_handler(CommandHandler("stats", stats_handler))
    application.add_handler(CommandHandler("history", history_handler))
    
    # ML Commands
    application.add_handler(CommandHandler("train", train_handler))
    application.add_handler(CommandHandler("model", model_handler))
    
    # Settings
    application.add_handler(CommandHandler("settings", settings_handler))
    application.add_handler(CommandHandler("bankroll", bankroll_handler))
    application.add_handler(CommandHandler("alerts", alerts_handler))
    
    # Utilities
    application.add_handler(CommandHandler("export", export_handler))
    
    # Callback Query Handler
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    # Error Handler
    application.add_error_handler(error_handler)
    
    logger.info("Bot konfiguriert - starte Polling...")
    
    # Bot starten
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot gestoppt")
    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        sys.exit(1)
