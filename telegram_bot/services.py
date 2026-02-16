"""
Services die die Core-Analyse-Module für Telegram aufbereiten
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, date

# Import Core-Module
from analysis import analyze_match_v47_ml, validate_match_data
from data import DataParser, list_daily_sheets_in_folder, list_match_tabs_for_day, read_worksheet_text_by_id
from data.models import MatchData
from ml import TablePositionML

logger = logging.getLogger(__name__)

class AnalysisService:
    """Service für Match-Analysen"""
    
    def __init__(self):
        self.parser = DataParser()
    
    async def analyze_match_from_string(self, match_string: str, timeout: int = 30) -> Optional[Dict]:
        """
        Analysiert ein Match basierend auf String-Eingabe
        
        Args:
            match_string: z.B. "Bayern München vs Dortmund"
            timeout: Timeout in Sekunden
            
        Returns:
            Analyse-Ergebnis Dictionary oder None
        """
        
        try:
            # Parse match_string in MatchData
            # TODO: Implementiere intelligentes Parsing
            # Für jetzt: Dummy-Implementation
            
            parts = match_string.lower().split(" vs ")
            if len(parts) != 2:
                parts = match_string.lower().split(" - ")
            
            if len(parts) != 2:
                logger.warning(f"Konnte Match-String nicht parsen: {match_string}")
                return None
            
            home_team = parts[0].strip()
            away_team = parts[1].strip()
            
            # Versuche Match in Google Sheets zu finden
            match_data = await self._find_match_in_sheets(home_team, away_team)
            
            if not match_data:
                logger.warning(f"Match nicht gefunden: {match_string}")
                return None
            
            # Analysiere mit Core-Logik
            result = await asyncio.wait_for(
                asyncio.to_thread(analyze_match_v47_ml, match_data),
                timeout=timeout
            )
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout bei Analyse: {match_string}")
            raise
        except Exception as e:
            logger.error(f"Fehler bei Analyse: {e}", exc_info=True)
            return None
    
    async def _find_match_in_sheets(self, home_team: str, away_team: str) -> Optional[MatchData]:
        """
        Sucht Match in Google Sheets
        
        Args:
            home_team: Name des Heimteams
            away_team: Name des Auswärtsteams
            
        Returns:
            MatchData oder None
        """
        
        try:
            # TODO: Implementiere Sheet-Suche
            # Für jetzt: Dummy-MatchData zurückgeben
            logger.info(f"Suche Match: {home_team} vs {away_team}")
            
            # Dummy-Daten für Testing
            return None  # Placeholder
            
        except Exception as e:
            logger.error(f"Fehler bei Sheet-Suche: {e}", exc_info=True)
            return None
    
    async def quick_analyze(self, match_id: int) -> Optional[Dict]:
        """
        Schnellanalyse für Match-ID
        
        Args:
            match_id: ID des Matches
            
        Returns:
            Verkürzte Analyse
        """
        
        # TODO: Implementiere Quick-Analyse
        logger.info(f"Quick-Analyse für Match {match_id}")
        return None

class MatchService:
    """Service für Match-Verwaltung"""
    
    async def get_todays_matches(self) -> List[Dict]:
        """
        Holt heutige Matches
        
        Returns:
            Liste von Match-Dictionaries
        """
        
        try:
            # TODO: Implementiere mit Google Sheets
            logger.info("Lade heutige Matches")
            
            # Dummy-Daten
            return [
                {
                    'id': 1,
                    'home': 'Bayern München',
                    'away': 'Borussia Dortmund',
                    'time': '20:30',
                    'league': 'Bundesliga'
                },
                {
                    'id': 2,
                    'home': 'RB Leipzig',
                    'away': 'Werder Bremen',
                    'time': '18:30',
                    'league': 'Bundesliga'
                }
            ]
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Matches: {e}", exc_info=True)
            return []
    
    async def search_matches(self, search_term: str) -> List[Dict]:
        """
        Sucht Matches basierend auf Suchbegriff
        
        Args:
            search_term: Suchbegriff (Team oder Liga)
            
        Returns:
            Liste gefundener Matches
        """
        
        try:
            logger.info(f"Suche Matches mit Term: {search_term}")
            
            # TODO: Implementiere Suche
            return []
            
        except Exception as e:
            logger.error(f"Fehler bei Match-Suche: {e}", exc_info=True)
            return []
    
    def get_today_date(self) -> str:
        """Gibt heutiges Datum formatiert zurück"""
        return datetime.now().strftime("%d.%m.%Y")

class BettingService:
    """Service für Wett-Management"""
    
    async def get_recommendations(self, limit: int = 5) -> List[Dict]:
        """
        Holt Top-Wettempfehlungen
        
        Args:
            limit: Maximale Anzahl Empfehlungen
            
        Returns:
            Liste von Empfehlungen
        """
        
        try:
            logger.info(f"Lade Top-{limit} Empfehlungen")
            
            # TODO: Implementiere mit Analyse-Logik
            # Dummy-Daten
            return [
                {
                    'match_id': 1,
                    'match': 'Bayern München vs Dortmund',
                    'market': 'Over 2.5',
                    'odds': 1.75,
                    'stake': 25.0,
                    'risk_score': 4,
                    'confidence': 0.87
                }
            ]
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Empfehlungen: {e}", exc_info=True)
            return []
    
    async def get_active_positions(self, user_id: int) -> List[Dict]:
        """
        Holt aktive Wetten eines Users
        
        Args:
            user_id: Telegram User ID
            
        Returns:
            Liste aktiver Wetten
        """
        
        try:
            logger.info(f"Lade Positionen für User {user_id}")
            
            # TODO: Aus Datenbank laden
            return []
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Positionen: {e}", exc_info=True)
            return []
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """
        Holt Performance-Statistiken eines Users
        
        Args:
            user_id: Telegram User ID
            
        Returns:
            Stats-Dictionary
        """
        
        try:
            logger.info(f"Lade Stats für User {user_id}")
            
            # TODO: Aus Datenbank laden
            return {
                'bankroll': {
                    'current': 1247.50,
                    'start': 1000.0
                },
                'total_bets': 47,
                'wins': 28,
                'losses': 19,
                'roi': 12.3,
                'best_markets': {
                    'Over 2.5': 65.0,
                    'BTTS': 58.0,
                    'Home Win': 54.0
                }
            }
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Stats: {e}", exc_info=True)
            return {}

class MLService:
    """Service für ML-Modell-Verwaltung"""
    
    def __init__(self):
        self.model = TablePositionML()
    
    async def train_model(self, timeout: int = 300) -> Dict:
        """
        Trainiert ML-Modell
        
        Args:
            timeout: Timeout in Sekunden
            
        Returns:
            Training-Ergebnis Dictionary
        """
        
        try:
            logger.info("Starte ML-Training")
            
            # TODO: Lade historische Matches
            historical_matches = []  # Placeholder
            
            if not historical_matches:
                return {
                    'success': False,
                    'message': 'Keine historischen Daten verfügbar'
                }
            
            # Training in separatem Thread (blockiert nicht)
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
                'success': False,
                'message': str(e)
            }
    
    async def get_model_info(self) -> Dict:
        """
        Holt Modell-Informationen
        
        Returns:
            Model-Info Dictionary
        """
        
        try:
            return self.model.get_model_info()
        except Exception as e:
            logger.error(f"Fehler beim Laden der Model-Info: {e}", exc_info=True)
            return {
                'is_trained': False,
                'error': str(e)
            }

class NotificationService:
    """Service für Push-Notifications"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
    
    async def send_notification(self, chat_id: int, message: str, parse_mode: str = "HTML"):
        """
        Sendet Push-Notification an User
        
        Args:
            chat_id: Telegram Chat ID
            message: Nachricht
            parse_mode: HTML oder Markdown
        """
        
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
    
    async def send_daily_summary(self, chat_id: int, stats: Dict):
        """Sendet tägliche Zusammenfassung"""
        
        message = f"""🌙 <b>TAGES-ZUSAMMENFASSUNG</b>
━━━━━━━━━━━━━━━━━━━━━━

📅 {datetime.now().strftime('%d.%m.%Y')}

💰 <b>PERFORMANCE</b>
Wetten: {stats.get('bets', 0)}
Wins: {stats.get('wins', 0)} ({stats.get('win_rate', 0):.0f}%)
P&L: €{stats.get('profit', 0):+.2f}

📊 <b>BANKROLL</b>
Start: €{stats.get('start_bankroll', 0):.2f}
Ende: €{stats.get('end_bankroll', 0):.2f}
Change: {stats.get('change_pct', 0):+.1f}% ↗️

Gute Nacht! 😴
"""
        
        await self.send_notification(chat_id, message)
    
    async def send_match_alert(self, chat_id: int, match_info: Dict, analysis: Dict):
        """Sendet Alert für neues interessantes Match"""
        
        message = f"""⚡ <b>MATCH ALERT</b>
{match_info['home']} vs {match_info['away']}
Beginn: {match_info['time']}

📊 Predicted: {analysis['predicted_score']}
⭐ Risk: {analysis['risk_score']}/5

💰 Empfehlung: {analysis.get('bet_recommendation', {}).get('market', 'N/A')}

/analyze {match_info['id']} für Details
"""
        
        await self.send_notification(chat_id, message)
