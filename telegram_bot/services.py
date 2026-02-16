"""
Services die die Core-Analyse-Module fuer Telegram aufbereiten
"""

import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, date
import os
import base64

logger = logging.getLogger(__name__)


def load_secrets_from_base64():
    """Laedt Streamlit Secrets aus Base64 Environment Variable"""
    
    secrets_b64 = os.getenv("SECRETS_BASE64")
    if not secrets_b64:
        logger.warning("SECRETS_BASE64 nicht gefunden - Google Sheets Integration deaktiviert")
        return None
    
    try:
        import toml
        decoded = base64.b64decode(secrets_b64).decode("utf-8")
        secrets = toml.loads(decoded)
        
        # Simuliere Streamlit Secrets
        import streamlit as st
        st.secrets = secrets
        
        logger.info("Secrets erfolgreich geladen")
        return secrets
    except Exception as e:
        logger.error(f"Fehler beim Laden der Secrets: {e}")
        return None


# Lade Secrets beim Import
_secrets = load_secrets_from_base64()


class AnalysisService:
    """Service fuer Match-Analysen"""
    
    def __init__(self):
        from data import DataParser
        self.parser = DataParser()
    
    async def analyze_match_from_string(self, match_string, timeout=30):
        """Analysiert ein Match basierend auf String-Eingabe"""
        
        logger.info(f"Analyse fuer: {match_string}")
        
        try:
            # Splitte Match-String
            parts = match_string.lower().split(" vs ")
            if len(parts) != 2:
                parts = match_string.lower().split(" - ")
            
            if len(parts) != 2:
                logger.warning(f"Konnte Match nicht parsen: {match_string}")
                return None
            
            home_team = parts[0].strip()
            away_team = parts[1].strip()
            
            # Suche Match in heutigen Matches
            match_service = MatchService()
            todays_matches = await match_service.get_todays_matches()
            
            # Finde passendes Match
            for match in todays_matches:
                if (home_team in match.get("home", "").lower() or 
                    away_team in match.get("away", "").lower()):
                    
                    # TODO: Hole komplette Match-Daten und analysiere
                    # match_data = await self._load_match_data(match["sheet_id"], match["tab"])
                    # result = analyze_match_v47_ml(match_data)
                    
                    return {
                        "home_team": match.get("home"),
                        "away_team": match.get("away"),
                        "predicted_score": "2-1",
                        "probabilities": {
                            "home_win": 54.2,
                            "draw": 23.1,
                            "away_win": 22.7,
                            "over_25": 62.8,
                            "under_25": 37.2
                        },
                        "risk_score": 4,
                        "ml_info": {"applied": True, "confidence": 0.87}
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Fehler bei Analyse: {e}", exc_info=True)
            return None
    
    async def quick_analyze(self, match_id):
        """Schnellanalyse fuer Match-ID"""
        
        logger.info(f"Quick-Analyse fuer Match {match_id}")
        
        # Hole Match aus heutigen Matches
        match_service = MatchService()
        matches = await match_service.get_todays_matches()
        
        if 0 < match_id <= len(matches):
            match = matches[match_id - 1]
            return {
                "home_team": match.get("home"),
                "away_team": match.get("away"),
                "predicted_score": "2-1",
                "risk_score": 4
            }
        
        return None


class MatchService:
    """Service fuer Match-Verwaltung"""
    
    async def get_todays_matches(self):
        """Holt heutige Matches aus Google Sheets"""
        
        if not _secrets:
            logger.warning("Keine Secrets - nutze Demo-Daten")
            return self._get_demo_matches()
        
        try:
            from data import list_daily_sheets_in_folder, list_match_tabs_for_day
            
            # Hole Folder ID
            folder_id = _secrets.get("prematch", {}).get("folder_id")
            if not folder_id:
                logger.warning("Keine folder_id gefunden")
                return self._get_demo_matches()
            
            # Heutiges Datum
            today = datetime.now().strftime("%d.%m.%Y")
            
            # Hole verfuegbare Sheets
            date_to_id = await asyncio.to_thread(
                list_daily_sheets_in_folder, 
                folder_id
            )
            
            if today not in date_to_id:
                logger.info(f"Kein Sheet fuer heute ({today}) gefunden")
                return []
            
            sheet_id = date_to_id[today]
            
            # Hole Match-Tabs
            match_tabs = await asyncio.to_thread(
                list_match_tabs_for_day,
                sheet_id
            )
            
            # Formatiere fuer Telegram
            matches = []
            for i, tab in enumerate(match_tabs, 1):
                tab_name = tab.get("title", "")
                
                # Parse Tab-Name (Format: "Team1 - Team2" oder "Team1 vs Team2")
                if " - " in tab_name:
                    parts = tab_name.split(" - ", 1)
                elif " vs " in tab_name:
                    parts = tab_name.split(" vs ", 1)
                else:
                    parts = [tab_name, ""]
                
                matches.append({
                    "id": i,
                    "home": parts[0].strip() if len(parts) > 0 else "Team A",
                    "away": parts[1].strip() if len(parts) > 1 else "Team B",
                    "time": "",  # TODO: Parse aus Sheet
                    "league": "Bundesliga",  # TODO: Parse aus Sheet
                    "sheet_id": sheet_id,
                    "tab": tab.get("title")
                })
            
            logger.info(f"Gefunden: {len(matches)} Matches fuer heute")
            return matches
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Matches: {e}", exc_info=True)
            return self._get_demo_matches()
    
    def _get_demo_matches(self):
        """Fallback Demo-Matches"""
        return [
            {
                "id": 1,
                "home": "Bayern Muenchen",
                "away": "Borussia Dortmund",
                "time": "20:30",
                "league": "Bundesliga"
            },
            {
                "id": 2,
                "home": "RB Leipzig",
                "away": "Werder Bremen",
                "time": "18:30",
                "league": "Bundesliga"
            }
        ]
    
    async def search_matches(self, search_term):
        """Sucht Matches basierend auf Suchbegriff"""
        
        matches = await self.get_todays_matches()
        
        # Filtere nach Suchbegriff
        search_lower = search_term.lower()
        filtered = [
            m for m in matches
            if search_lower in m.get("home", "").lower() or
               search_lower in m.get("away", "").lower() or
               search_lower in m.get("league", "").lower()
        ]
        
        logger.info(f"Suche '{search_term}': {len(filtered)} Ergebnisse")
        return filtered
    
    def get_today_date(self):
        """Gibt heutiges Datum formatiert zurueck"""
        return datetime.now().strftime("%d.%m.%Y")


class BettingService:
    """Service fuer Wett-Management"""
    
    async def get_recommendations(self, limit=5):
        """Holt Top-Wettempfehlungen"""
        
        logger.info(f"Lade Top-{limit} Empfehlungen")
        
        # Hole heutige Matches und erstelle Demo-Empfehlungen
        match_service = MatchService()
        matches = await match_service.get_todays_matches()
        
        recommendations = []
        for match in matches[:limit]:
            recommendations.append({
                "match_id": match.get("id"),
                "match": f"{match.get('home')} vs {match.get('away')}",
                "market": "Over 2.5",
                "odds": 1.75,
                "stake": 25.0,
                "risk_score": 4,
                "confidence": 0.87
            })
        
        return recommendations
    
    async def get_active_positions(self, user_id):
        """Holt aktive Wetten eines Users"""
        
        logger.info(f"Lade Positionen fuer User {user_id}")
        
        # TODO: Aus Datenbank laden
        return []
    
    async def get_user_stats(self, user_id):
        """Holt Performance-Statistiken eines Users"""
        
        logger.info(f"Lade Stats fuer User {user_id}")
        
        # TODO: Aus Datenbank laden
        return {
            "bankroll": {
                "current": 1247.50,
                "start": 1000.0
            },
            "total_bets": 47,
            "wins": 28,
            "roi": 12.3,
            "best_markets": {
                "Over 2.5": 65.0,
                "BTTS": 58.0
            }
        }


class MLService:
    """Service fuer ML-Modell-Verwaltung"""
    
    def __init__(self):
        try:
            from ml import TablePositionML
            self.model = TablePositionML()
        except Exception as e:
            logger.warning(f"ML-Modell konnte nicht geladen werden: {e}")
            self.model = None
    
    async def train_model(self, timeout=300):
        """Trainiert ML-Modell"""
        
        if not self.model:
            return {
                "success": False,
                "message": "ML-Modell nicht verfuegbar"
            }
        
        logger.info("Starte ML-Training")
        
        try:
            # TODO: Lade historische Matches
            historical_matches = []
            
            if not historical_matches:
                return {
                    "success": False,
                    "message": "Keine historischen Daten verfuegbar"
                }
            
            # Training in separatem Thread
            result = await asyncio.wait_for(
                asyncio.to_thread(self.model.train, historical_matches),
                timeout=timeout
            )
            
            logger.info(f"ML-Training abgeschlossen: {result}")
            return result
            
        except asyncio.TimeoutError:
            logger.error("ML-Training Timeout")
            raise
        except Exception as e:
            logger.error(f"Fehler beim ML-Training: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e)
            }
    
    async def get_model_info(self):
        """Holt Modell-Informationen"""
        
        if not self.model:
            return {
                "is_trained": False,
                "model_type": "N/A",
                "training_data_size": 0,
                "error": "Modell nicht verfuegbar"
            }
        
        try:
            return self.model.get_model_info()
        except Exception as e:
            logger.error(f"Fehler beim Laden der Model-Info: {e}", exc_info=True)
            return {
                "is_trained": False,
                "error": str(e)
            }


class NotificationService:
    """Service fuer Push-Notifications"""
    
    def __init__(self, bot_token):
        self.bot_token = bot_token
    
    async def send_notification(self, chat_id, message, parse_mode="HTML"):
        """Sendet Push-Notification an User"""
        
        try:
            import requests
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            
            response = requests.post(url, data=data)
            
            if response.status_code == 200:
                logger.info(f"Notification gesendet an {chat_id}")
            else:
                logger.error(f"Fehler beim Senden: {response.text}")
                
        except Exception as e:
            logger.error(f"Fehler bei Notification: {e}", exc_info=True)
