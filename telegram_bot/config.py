"""
Konfiguration fuer den Telegram Bot
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class BotConfig:
    """Bot-Konfiguration"""
    
    # Telegram
    bot_token: str
    admin_chat_ids: list
    
    # Features
    enable_notifications: bool = True
    enable_ml_commands: bool = True
    enable_betting: bool = True
    
    # Limits
    max_analyses_per_day: int = 50
    max_bet_amount: float = 100.0
    
    # Timeouts
    analysis_timeout: int = 30
    ml_training_timeout: int = 300


def load_bot_config():
    """
    Laedt Bot-Konfiguration aus Environment-Variablen oder secrets
    """
    
    # Versuche aus Environment-Variablen zu laden
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_ids_str = os.getenv("TELEGRAM_ADMIN_CHAT_IDS", "")
    
    # Fallback: Versuche aus Streamlit Secrets zu laden
    if not bot_token:
        try:
            import streamlit as st
            bot_token = st.secrets.get("telegram", {}).get("bot_token")
            admin_ids_str = st.secrets.get("telegram", {}).get("admin_chat_ids", "")
        except Exception:
            pass
    
    if not bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN nicht gefunden!\n"
            "Setze Environment-Variable oder fuege zu .streamlit/secrets.toml hinzu"
        )
    
    # Parse Admin IDs
    admin_ids = []
    if admin_ids_str:
        try:
            admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        except ValueError:
            raise ValueError("TELEGRAM_ADMIN_CHAT_IDS muss komma-separierte Integers sein")
    
    return BotConfig(
        bot_token=bot_token,
        admin_chat_ids=admin_ids
    )


# Globale Config-Instanz
BOT_CONFIG = load_bot_config()


# Helper-Funktionen
def is_admin(chat_id):
    """Prueft ob User Admin ist"""
    return chat_id in BOT_CONFIG.admin_chat_ids


def get_user_rate_limit_key(chat_id):
    """Erstellt Rate-Limit Key fuer User"""
    return f"rate_limit:{chat_id}"
