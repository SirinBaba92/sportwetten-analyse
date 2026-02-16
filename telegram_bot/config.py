"""
Konfiguration fuer den Telegram Bot
"""

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class BotConfig:
    """Bot-Konfiguration"""
    
    # Telegram
    bot_token: str
    admin_chat_ids: List[int]
    
    # Features
    enable_notifications: bool = True
    enable_ml_commands: bool = True
    enable_betting: bool = True
    
    # Limits
    max_analyses_per_day: int = 50
    max_bet_amount: float = 100.0
    rate_limit_requests: int = 10
    rate_limit_period: int = 60  # Sekunden
    
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
            "❌ TELEGRAM_BOT_TOKEN nicht gefunden!\n\n"
            "Setze Environment-Variable:\n"
            "export TELEGRAM_BOT_TOKEN='dein_token'\n\n"
            "Oder füge zu .streamlit/secrets.toml hinzu:\n"
            "[telegram]\n"
            "bot_token = 'dein_token'\n"
            "admin_chat_ids = '123456789,987654321'"
        )
    
    # Parse Admin IDs
    admin_ids = []
    if admin_ids_str:
        try:
            admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
        except ValueError:
            print("⚠️ TELEGRAM_ADMIN_CHAT_IDS enthält ungültige Werte - Admin-Funktionen deaktiviert")
    
    # Füge default Admin hinzu (dich selbst) falls keine konfiguriert
    if not admin_ids:
        print("⚠️ Keine Admins konfiguriert - Admin-Funktionen nur für Bot-Besitzer?")
        # Versuche aus Umgebung zu laden
        default_admin = os.getenv("TELEGRAM_DEFAULT_ADMIN")
        if default_admin:
            try:
                admin_ids = [int(default_admin)]
            except:
                pass
    
    return BotConfig(
        bot_token=bot_token,
        admin_chat_ids=admin_ids
    )


# Globale Config-Instanz
BOT_CONFIG = load_bot_config()


def is_admin(chat_id: int) -> bool:
    """Prueft ob User Admin ist"""
    return chat_id in BOT_CONFIG.admin_chat_ids


def get_user_rate_limit_key(chat_id: int) -> str:
    """Erstellt Rate-Limit Key fuer User"""
    return f"rate_limit:{chat_id}"
