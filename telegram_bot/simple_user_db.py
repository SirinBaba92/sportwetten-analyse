"""
Einfache JSON-basierte User-Datenbank für Telegram Bot
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
import time

USER_DB_FILE = "telegram_users.json"
COMMAND_STATS_FILE = "command_stats.json"
RATE_LIMIT_FILE = "rate_limits.json"


class UserDatabase:
    """User-Datenbank mit JSON-Speicherung"""
    
    def __init__(self):
        self.users = self._load_users()
        self.command_stats = self._load_command_stats()
        self.rate_limits = self._load_rate_limits()
    
    def _load_users(self) -> Dict:
        """Lade User aus JSON"""
        if os.path.exists(USER_DB_FILE):
            try:
                with open(USER_DB_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _load_command_stats(self) -> Dict:
        """Lade Command-Statistiken"""
        if os.path.exists(COMMAND_STATS_FILE):
            try:
                with open(COMMAND_STATS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"total_commands": 0, "commands": {}, "daily": {}}
        return {"total_commands": 0, "commands": {}, "daily": {}}
    
    def _load_rate_limits(self) -> Dict:
        """Lade Rate-Limit Daten"""
        if os.path.exists(RATE_LIMIT_FILE):
            try:
                with open(RATE_LIMIT_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_users(self):
        """Speichere User"""
        with open(USER_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.users, f, indent=2, ensure_ascii=False)
    
    def _save_command_stats(self):
        """Speichere Command-Statistiken"""
        with open(COMMAND_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.command_stats, f, indent=2, ensure_ascii=False)
    
    def _save_rate_limits(self):
        """Speichere Rate-Limit Daten"""
        with open(RATE_LIMIT_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.rate_limits, f, indent=2, ensure_ascii=False)
    
    def register_user(self, user_id: int, username: str = "", first_name: str = "", last_name: str = ""):
        """Registriere neuen User oder aktualisiere existierenden"""
        user_id_str = str(user_id)
        now = datetime.now().isoformat()
        
        if user_id_str not in self.users:
            self.users[user_id_str] = {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "joined_at": now,
                "last_active": now,
                "total_commands": 0,
                "settings": {
                    "notifications": True,
                    "bankroll": 1000.0,
                    "risk_profile": "moderat",
                    "language": "de"
                },
                "stats": {
                    "analyzes": 0,
                    "bets_placed": 0,
                    "wins": 0,
                    "losses": 0
                }
            }
            print(f"✅ Neuer User registriert: {first_name} (@{username})")
            return True
        else:
            # Update existing
            self.users[user_id_str]["last_active"] = now
            if username:
                self.users[user_id_str]["username"] = username
            if first_name:
                self.users[user_id_str]["first_name"] = first_name
            return False
    
    def update_activity(self, user_id: int, command: str = ""):
        """Aktualisiere User-Aktivität"""
        user_id_str = str(user_id)
        if user_id_str in self.users:
            self.users[user_id_str]["last_active"] = datetime.now().isoformat()
            self.users[user_id_str]["total_commands"] = self.users[user_id_str].get("total_commands", 0) + 1
            
            # Update command-specific stats
            if command:
                if command == "analyze":
                    self.users[user_id_str]["stats"]["analyzes"] = self.users[user_id_str]["stats"].get("analyzes", 0) + 1
            
            self._save_users()
        
        # Track command globally
        self.track_command(command, user_id)
    
    def track_command(self, command: str, user_id: int):
        """Tracke Command-Nutzung global"""
        self.command_stats["total_commands"] = self.command_stats.get("total_commands", 0) + 1
        
        # Per command
        if command:
            self.command_stats["commands"][command] = self.command_stats["commands"].get(command, 0) + 1
        
        # Daily stats
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.command_stats["daily"]:
            self.command_stats["daily"][today] = {}
        
        if command:
            self.command_stats["daily"][today][command] = self.command_stats["daily"][today].get(command, 0) + 1
        
        # User daily stats
        user_key = f"user_{user_id}"
        if user_key not in self.command_stats["daily"][today]:
            self.command_stats["daily"][today][user_key] = 0
        self.command_stats["daily"][today][user_key] += 1
        
        self._save_command_stats()
    
    def check_rate_limit(self, user_id: int, max_requests: int = 10, per_seconds: int = 60) -> bool:
        """
        Prüft Rate Limit für User
        Returns: True wenn erlaubt, False wenn limitiert
        """
        user_id_str = str(user_id)
        now = time.time()
        
        # Clean old entries
        if user_id_str in self.rate_limits:
            self.rate_limits[user_id_str] = [
                t for t in self.rate_limits[user_id_str] 
                if now - t < per_seconds
            ]
        else:
            self.rate_limits[user_id_str] = []
        
        # Check limit
        if len(self.rate_limits[user_id_str]) >= max_requests:
            return False
        
        # Add new request
        self.rate_limits[user_id_str].append(now)
        self._save_rate_limits()
        return True
    
    def get_user_settings(self, user_id: int) -> Dict:
        """Hole User-Einstellungen"""
        user_id_str = str(user_id)
        if user_id_str in self.users:
            return self.users[user_id_str].get("settings", {})
        return {}
    
    def update_user_settings(self, user_id: int, settings: Dict):
        """Aktualisiere User-Einstellungen"""
        user_id_str = str(user_id)
        if user_id_str in self.users:
            self.users[user_id_str]["settings"].update(settings)
            self._save_users()
            return True
        return False
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Hole User-Statistiken"""
        user_id_str = str(user_id)
        if user_id_str in self.users:
            return {
                "user": self.users[user_id_str],
                "stats": self.users[user_id_str].get("stats", {})
            }
        return {}
    
    def get_bot_stats(self) -> Dict:
        """Hole globale Bot-Statistiken"""
        total_users = len(self.users)
        
        # Aktive heute
        today = datetime.now().date()
        active_today = 0
        for user in self.users.values():
            last_active = datetime.fromisoformat(user["last_active"]).date()
            if last_active == today:
                active_today += 1
        
        # Aktive diese Woche
        week_ago = today - timedelta(days=7)
        active_week = 0
        for user in self.users.values():
            last_active = datetime.fromisoformat(user["last_active"]).date()
            if last_active >= week_ago:
                active_week += 1
        
        # Meistgenutzte Commands
        top_commands = sorted(
            self.command_stats["commands"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        return {
            "total_users": total_users,
            "active_today": active_today,
            "active_week": active_week,
            "total_commands": self.command_stats.get("total_commands", 0),
            "top_commands": top_commands,
            "users": self.users
        }


# Globale Instanz
db = UserDatabase()
