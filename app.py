import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
import plotly.graph_objects as go
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import math
from datetime import datetime
import numpy as np
import hashlib
from collections import Counter
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

st.set_page_config(page_title="Sportwetten-Prognose v5.0 (SMART-PRECISION)",
                    page_icon="⚽", layout="wide")

# ==================== SESSION STATE INITIALISIERUNG ====================
# Phase 1: Risiko-Management Session State
if 'alert_thresholds' not in st.session_state:
    st.session_state.alert_thresholds = {
        'mu_total_high': 4.5,
        'tki_high': 1.0,
        'ppg_diff_extreme': 1.5
    }

if 'risk_management' not in st.session_state:
    st.session_state.risk_management = {
        'bankroll': 1000.0,
        'risk_profile': 'moderat',
        'stake_history': []
    }

# Phase 3 & 4: ML-Modelle Session State
if 'position_ml_model' not in st.session_state:
    st.session_state.position_ml_model = None

if 'extended_ml_model' not in st.session_state:
    st.session_state.extended_ml_model = None

# Demo-Modus
if 'enable_demo_mode' not in st.session_state:
    st.session_state.enable_demo_mode = False

# ==================== RISIKOPROFILE & STAKE-PROZENTSÄTZE (PHASE 1) ======
RISK_PROFILES = {
    "sehr_konservativ": {
        "name": "Sehr konservativ",
        "adjustment": 0.7,
        "max_stake_percent": 2.0,
        "description": "Minimales Risiko, kleine Einsätze",
        "color": "green"
    },
    "konservativ": {
        "name": "Konservativ",
        "adjustment": 0.85,
        "max_stake_percent": 3.0,
        "description": "Sicherheitsorientiert",
        "color": "lightgreen"
    },
    "moderat": {
        "name": "Moderat",
        "adjustment": 1.0,
        "max_stake_percent": 5.0,
        "description": "Ausgewogenes Risiko/Ertrag",
        "color": "yellow"
    },
    "aggressiv": {
        "name": "Aggressiv",
        "adjustment": 1.15,
        "max_stake_percent": 7.0,
        "description": "Höhere Risikobereitschaft",
        "color": "orange"
    },
    "sehr_aggressiv": {
        "name": "Sehr aggressiv",
        "adjustment": 1.3,
        "max_stake_percent": 10.0,
        "description": "Maximale Risikobereitschaft",
        "color": "red"
    }
}

STAKE_PERCENTAGES = {
    1: 0.5,
    2: 1.0,
    3: 2.0,
    4: 3.5,
    5: 5.0
}

# ==================== DATENKLASSEN ====================


@dataclass
class TeamStats:
    name: str
    position: int
    games: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_diff: int
    points: int
    form_points: int
    form_goals_for: int
    form_goals_against: int
    ha_points: int
    ha_goals_for: int
    ha_goals_against: int
    ppg_overall: float
    ppg_ha: float
    avg_goals_match: float
    avg_goals_match_ha: float
    goals_scored_per_match: float
    goals_conceded_per_match: float
    goals_scored_per_match_ha: float
    goals_conceded_per_match_ha: float
    btts_yes_overall: float
    btts_yes_ha: float
    cs_yes_overall: float
    cs_yes_ha: float
    fts_yes_overall: float
    fts_yes_ha: float
    xg_for: float
    xg_against: float
    xg_for_ha: float
    xg_against_ha: float
    shots_per_match: float
    shots_on_target: float
    conversion_rate: float
    possession: float


@dataclass
class H2HResult:
    date: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int


@dataclass
class MatchData:
    home_team: TeamStats
    away_team: TeamStats
    h2h_results: List[H2HResult]
    date: str
    competition: str
    kickoff: str
    odds_1x2: Tuple[float, float, float]
    odds_ou25: Tuple[float, float]
    odds_btts: Tuple[float, float]

# Phase 4: Erweiterte Datenklasse


@dataclass
class ExtendedMatchData:
    match_id: str
    halftime_score: str
    possession_home: float
    possession_away: float
    shots_home: int
    shots_away: int
    shots_on_target_home: int
    shots_on_target_away: int
    corners_home: int
    corners_away: int
    fouls_home: int
    fouls_away: int
    yellow_cards_home: int
    yellow_cards_away: int
    red_cards_home: int
    red_cards_away: int
    substitutions_home: int
    substitutions_away: int
    notes: str

    def to_dict(self):
        return {
            'match_id': self.match_id,
            'halftime': self.halftime_score,
            'possession_home': self.possession_home,
            'possession_away': self.possession_away,
            'shots_home': self.shots_home,
            'shots_away': self.shots_away,
            'shots_on_target_home': self.shots_on_target_home,
            'shots_on_target_away': self.shots_on_target_away,
            'corners_home': self.corners_home,
            'corners_away': self.corners_away,
            'fouls_home': self.fouls_home,
            'fouls_away': self.fouls_away,
            'yellow_home': self.yellow_cards_home,
            'yellow_away': self.yellow_cards_away,
            'red_home': self.red_cards_home,
            'red_away': self.red_cards_away,
            'subs_home': self.substitutions_home,
            'subs_away': self.substitutions_away,
            'notes': self.notes
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            match_id=data.get('match_id', ''),
            halftime_score=data.get('halftime', '0:0'),
            possession_home=float(data.get('possession_home', 50.0)),
            possession_away=float(data.get('possession_away', 50.0)),
            shots_home=int(data.get('shots_home', 0)),
            shots_away=int(data.get('shots_away', 0)),
            shots_on_target_home=int(data.get('shots_on_target_home', 0)),
            shots_on_target_away=int(data.get('shots_on_target_away', 0)),
            corners_home=int(data.get('corners_home', 0)),
            corners_away=int(data.get('corners_away', 0)),
            fouls_home=int(data.get('fouls_home', 0)),
            fouls_away=int(data.get('fouls_away', 0)),
            yellow_cards_home=int(data.get('yellow_home', 0)),
            yellow_cards_away=int(data.get('yellow_away', 0)),
            red_cards_home=int(data.get('red_home', 0)),
            red_cards_away=int(data.get('red_away', 0)),
            substitutions_home=int(data.get('subs_home', 0)),
            substitutions_away=int(data.get('subs_away', 0)),
            notes=data.get('notes', '')
        )

# ==================== KERN FUNKTIONEN ====================


def poisson_probability(lmbda: float, k: int) -> float:
    if lmbda <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)


def connect_to_sheets(readonly=True):
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(credentials_dict, scopes=SHEETS_SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        return service
    except Exception as e:
        st.error(f"❌ Fehler bei Google Sheets Verbindung: {e}")
        return None

def connect_to_drive():
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(credentials_dict, scopes=DRIVE_SCOPES)
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"❌ Fehler bei Google Drive Verbindung: {e}")
        return None

DATE_NAME_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")

@st.cache_data(ttl=300)
def list_daily_sheets_in_folder(folder_id: str) -> Dict[str, str]:
    """
    Returns mapping: '15.12.2025' -> '<spreadsheetId>'
    Only includes files whose name matches dd.mm.yyyy
    """
    service = connect_to_drive()
    if service is None:
        return {}

    q = (
        f"'{folder_id}' in parents "
        "and mimeType='application/vnd.google-apps.spreadsheet' "
        "and trashed=false"
    )

    date_to_id: Dict[str, str] = {}
    page_token = None

    while True:
        resp = service.files().list(
            q=q,
            fields="nextPageToken, files(id, name)",
            pageToken=page_token,
            pageSize=1000
        ).execute()

        for f in resp.get("files", []):
            name = (f.get("name") or "").strip()
            if DATE_NAME_RE.match(name):
                date_to_id[name] = f["id"]

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return date_to_id

@st.cache_data(ttl=300)
def list_match_tabs_for_day(sheet_id: str) -> List[str]:
    """Returns worksheet titles in the order they appear (match list)."""
    service = connect_to_sheets(readonly=True)
    if service is None:
        return []

    meta = service.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="sheets(properties(title,index))"
    ).execute()

    sheets = meta.get("sheets", [])
    sheets_sorted = sorted(
        sheets, key=lambda s: s["properties"].get("index", 0)
    )

    return [s["properties"]["title"] for s in sheets_sorted]

@st.cache_data(ttl=300)
def read_sheet_range(sheet_id: str, a1_range: str) -> List[List[str]]:
    service = connect_to_sheets(readonly=True)
    if service is None:
        return []
    resp = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=a1_range
    ).execute()
    return resp.get("values", [])


# ==================== PHASE 1: RISIKO-MANAGEMENT FUNKTIONEN =============


def get_tracking_sheet_id():
    """Return the Google Sheets ID used for tracking (supports fallbacks)."""
    if "tracking" not in st.secrets:
        return None
    tracking = st.secrets["tracking"]
    return (
        tracking.get("sheet_id")
        or tracking.get("sheet_id_v48")
        or tracking.get("sheet_id_v47")
    )
def add_to_stake_history(
    match_info: str,
    stake: float,
    profit: float,
        market: str):
    """Fügt eine Wette zur Historie hinzu"""
    if 'stake_history' not in st.session_state.risk_management:
        st.session_state.risk_management['stake_history'] = []

    history_entry = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'match': match_info,
        'stake': stake,
        'profit': profit,
        'market': market,
        'bankroll_before': st.session_state.risk_management['bankroll'] - profit
    }

    st.session_state.risk_management['stake_history'].append(history_entry)

    # Limitiere Historie auf 100 Einträge
    if len(st.session_state.risk_management['stake_history']) > 100:
        st.session_state.risk_management['stake_history'] = st.session_state.risk_management['stake_history'][-100:]

    # Aktualisiere Bankroll
    st.session_state.risk_management['bankroll'] += profit


def calculate_stake_recommendation(
    risk_score: int,
    odds: float,
    market: str = "1x2",
        match_info: str = "") -> Dict:
    bankroll = st.session_state.risk_management['bankroll']
    risk_profile = st.session_state.risk_management['risk_profile']
    profile_data = RISK_PROFILES[risk_profile]

    base_percentage = STAKE_PERCENTAGES.get(risk_score, 2.0)
    adjusted_percentage = base_percentage * profile_data['adjustment']
    max_percentage = profile_data['max_stake_percent']
    final_percentage = min(adjusted_percentage, max_percentage)

    recommended_stake = bankroll * (final_percentage / 100)
    min_stake = max(10.0, recommended_stake * 0.5)
    max_stake = min(bankroll * 0.25, recommended_stake * 1.5)

    potential_win = recommended_stake * (odds - 1)
    potential_loss = recommended_stake

    return {
        'risk_score': risk_score,
        'risk_profile': risk_profile,
        'base_percentage': base_percentage,
        'adjusted_percentage': round(final_percentage, 2),
        'recommended_stake': round(recommended_stake, 2),
        'min_stake': round(min_stake, 2),
        'max_stake': round(max_stake, 2),
        'potential_win': round(potential_win, 2),
        'potential_loss': round(potential_loss, 2),
        'new_bankroll_win': round(bankroll + potential_win, 2),
        'new_bankroll_loss': round(bankroll - potential_loss, 2)
    }


def display_stake_recommendation(
    risk_score: int,
    odds: float,
    market_name: str,
        match_info: str = ""):
    stake_info = calculate_stake_recommendation(
        risk_score, odds, market_name, match_info)

    st.markdown("---")
    st.subheader(f"💰 EINSATZEMPFEHLUNG: {market_name}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label=f"Risiko-Score",
            value=f"{risk_score}/5",
            delta=f"{RISK_PROFILES[st.session_state.risk_management['risk_profile']]['name']}"
        )

    with col2:
        st.metric(
            label="Empfohlener Einsatz",
            value=f"€{stake_info['recommended_stake']}",
            delta=f"{stake_info['adjusted_percentage']}% der Bankroll"
        )

    with col3:
        st.metric(
            label=f"Potentieller Gewinn",
            value=f"+€{stake_info['potential_win']}",
            delta=f"Quote: {odds:.2f}"
        )

    # DEMO: Simulierte Wette-Buttons
    if st.session_state.get('enable_demo_mode', False) and match_info:
        col_sim1, col_sim2 = st.columns(2)
        with col_sim1:
            if st.button(f"✅ {market_name} GEWINN simulieren", use_container_width=True, key=f"win_{market_name}_{hash(match_info)}"):
                add_to_stake_history(
                    match_info=match_info,
                    stake=stake_info['recommended_stake'],
                    profit=stake_info['potential_win'],
                    market=market_name
                )
                st.success(
                    f"✅ +€{stake_info['potential_win']} Gewinn simuliert!")
                st.rerun()

        with col_sim2:
            if st.button(f"❌ {market_name} VERLUST simulieren", use_container_width=True, key=f"loss_{market_name}_{hash(match_info)}"):
                add_to_stake_history(
                    match_info=match_info,
                    stake=stake_info['recommended_stake'],
                    profit=-stake_info['potential_loss'],
                    market=market_name
                )
                st.error(
                    f"❌ -€{stake_info['potential_loss']} Verlust simuliert!")
                st.rerun()

    with st.expander("📊 Detaillierte Einsatz-Analyse", expanded=False):
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            st.markdown("**Einsatz-Bereich:**")
            st.caption(f"• Minimum: €{stake_info['min_stake']}")
            st.caption(f"• Empfohlen: €{stake_info['recommended_stake']}")
            st.caption(f"• Maximum: €{stake_info['max_stake']}")

        with col_b:
            st.markdown("**Risiko-Analyse:**")
            st.caption(f"• Basis: {stake_info['base_percentage']}%")
            st.caption(f"• Adjustiert: {stake_info['adjusted_percentage']}%")
            st.caption(
                f"• Max. erlaubt: {RISK_PROFILES[st.session_state.risk_management['risk_profile']]['max_stake_percent']}%")

        with col_c:
            st.markdown("**Konsequenzen:**")
            st.caption(
                f"• Bei Gewinn: +{stake_info['potential_win'] / stake_info['recommended_stake'] * 100:.1f}%")
            st.caption(
                f"• Bei Verlust: -{stake_info['adjusted_percentage']:.1f}% Bankroll")
            st.caption(
                f"• Quote benötigt für EV=0: {100 / (stake_info['adjusted_percentage'] + 0.01):.2f}")

# ==================== PHASE 2: TRACKING & ERGEBNISSE ====================


def save_prediction_to_sheets(match_info: Dict, probabilities: Dict, odds: Dict,
                                risk_score: Dict, predicted_score: str, mu_info: Dict):
    try:
        if "tracking" not in st.secrets:
            st.warning("⚠️ Tracking nicht konfiguriert")
            return False

        if "sheet_id" not in st.secrets["tracking"]:
            st.warning("⚠️ sheet_id nicht in tracking secrets gefunden")
            if "sheet_id_v48" in st.secrets["tracking"]:
                sheet_id = st.secrets["tracking"]["sheet_id_v48"]
            elif "sheet_id_v47" in st.secrets["tracking"]:
                sheet_id = st.secrets["tracking"]["sheet_id_v47"]
            else:
                return False
        else:
            sheet_id = st.secrets["tracking"]["sheet_id"]

        service = connect_to_sheets(readonly=False)
        if service is None:
            return False

        best_over_under = "Over 2.5" if probabilities['over_25'] >= (
            100 - probabilities['over_25']) else "Under 2.5"
        prob_over_under = max(
            probabilities['over_25'], 100 - probabilities['over_25'])
        odds_over_under = odds['ou25'][0] if best_over_under == "Over 2.5" else odds['ou25'][1]

        best_btts = "BTTS Yes" if probabilities['btts_yes'] >= probabilities['btts_no'] else "BTTS No"
        prob_btts = max(probabilities['btts_yes'], probabilities['btts_no'])
        odds_btts = odds['btts'][0] if best_btts == "BTTS Yes" else odds['btts'][1]

        probs_1x2 = [probabilities['home_win'],
            probabilities['draw'], probabilities['away_win']]
        markets_1x2 = ['Heimsieg', 'Unentschieden', 'Auswärtssieg']
        best_idx = probs_1x2.index(max(probs_1x2))
        best_1x2 = markets_1x2[best_idx]
        prob_1x2 = probs_1x2[best_idx]
        odds_1x2_value = odds['1x2'][best_idx]

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        match_str = f"{match_info['home']} vs {match_info['away']}"
        mu_total = mu_info.get('total', 0.0)

        version = "v4.7+"

        values = [[
            timestamp,                                  # A: Timestamp
            version,                                    # B: Version
            match_str,                                  # C: Match
            predicted_score,                            # D: Predicted_Score
            best_1x2,                                   # E: Predicted_1X2
            f"{prob_1x2:.1f}%",                        # F: Probability_1X2
            best_over_under,                            # G: Best_OverUnder
            # H: Probability_OverUnder
            f"{prob_over_under:.1f}%",
            f"{odds_over_under:.2f}",                  # I: Odds_OverUnder
            best_btts,                                  # J: Best_BTTS
            f"{prob_btts:.1f}%",                       # K: Probability_BTTS
            f"{odds_btts:.2f}",                        # L: Odds_BTTS
            f"{odds_1x2_value:.2f}",                   # M: Odds_1X2
            str(risk_score['score']),                   # N: Risk_Score (1-5)
            risk_score['category'],                     # O: Risk_Category
            f"{mu_total:.2f}",                         # P: μ_Total
            "PENDING",                                  # Q: Status

            # NEU: ERGEBNIS-COLUMNS (R:W)
            "",                                         # R: Actual_Score
            "",                                         # S: Actual_Home
            "",                                         # T: Actual_Away
            "",                                         # U: Goals_Total
            "",                                         # V: BTTS_Actual
            ""                                          # W: Over25_Actual
        ]]

        body = {'values': values}
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="PREDICTIONS!A:W",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

        st.success(f"✅ Vorhersage ({version}) gespeichert!")
        return True

    except Exception as e:
        st.error(f"❌ Fehler beim Speichern: {str(e)}")
        return False


def update_match_result_in_sheets(match_str: str, actual_score: str):
    try:
        service = connect_to_sheets(readonly=False)
        if service is None:
            return False

        home_goals, away_goals = map(int, actual_score.split(':'))
        goals_total = home_goals + away_goals
        btts_actual = "TRUE" if home_goals > 0 and away_goals > 0 else "FALSE"
        over25_actual = "TRUE" if goals_total > 2.5 else "FALSE"

        spreadsheet_id = st.secrets["tracking"]["sheet_id"]

        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="PREDICTIONS!A:W"
        ).execute()

        values = result.get('values', [])

        for i, row in enumerate(values):
            if i == 0:
                continue

            if len(row) > 2 and match_str in row[2]:
                update_range = f"PREDICTIONS!R{i + 1}:W{i + 1}"
                update_values = [[
                    actual_score,
                    str(home_goals),
                    str(away_goals),
                    str(goals_total),
                    btts_actual,
                    over25_actual
                ]]

                body = {'values': update_values}
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=update_range,
                    valueInputOption="USER_ENTERED",
                    body=body
                ).execute()

                status_range = f"PREDICTIONS!Q{i + 1}"
                status_body = {'values': [["COMPLETED"]]}
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=status_range,
                    valueInputOption="USER_ENTERED",
                    body=status_body
                ).execute()

                return True

        return False

    except Exception as e:
        st.error(f"❌ Fehler beim Eintragen des Ergebnisses: {str(e)}")
        return False


def get_match_info_by_id(match_id: str):
    try:
        sheet_id = get_tracking_sheet_id()
        if not sheet_id:
            return None

        service = connect_to_sheets(readonly=True)
        if service is None:
            return None

        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="PREDICTIONS!A:W"
        ).execute()

        values = result.get('values', [])

        for i, row in enumerate(values):
            if i == 0:
                continue

            if len(row) > 2 and row[2] == match_id:
                return {
                    'match': row[2],
                    'predicted_score': row[3] if len(row) > 3 else '',
                    'date': row[0] if len(row) > 0 else '',
                    'risk_score': row[13] if len(row) > 13 else ''
                }

            row_id = f"{row[0]}_{row[2]}" if len(row) > 2 else ""
            if row_id == match_id:
                return {
                    'match': row[2],
                    'predicted_score': row[3] if len(row) > 3 else '',
                    'date': row[0],
                    'risk_score': row[13] if len(row) > 13 else ''
                }

        return None

    except Exception as e:
        st.error(f"❌ Fehler beim Laden der Match-Info: {e}")
        return None


def save_historical_match(historical_match: Dict) -> bool:
    """Speichert ein historisches Match in HISTORICAL_DATA Sheet - EINFACHE VERSION"""
    try:
        if "tracking" not in st.secrets:
            st.warning("⚠️ Tracking nicht konfiguriert")
            return False

        sheet_id = get_tracking_sheet_id()
        if not sheet_id:
            st.error("❌ Keine Google Sheets ID gefunden (sheet_id / sheet_id_v48 / sheet_id_v47)")
            return False

        service = connect_to_sheets(readonly=False)
        if service is None:
            st.error("❌ Keine Verbindung zu Google Sheets")
            return False

        # Extrahiere Daten auf EINFACHE Weise
        home_team = historical_match.get('home_team')
        away_team = historical_match.get('away_team')

        # Hole Namen - sicher für TeamStats Objekte und Dictionaries
        if hasattr(home_team, 'name'):
            home_name = home_team.name
        elif isinstance(home_team, dict):
            home_name = home_team.get('name', 'Unbekannt')
        else:
            home_name = 'Unbekannt'

        if hasattr(away_team, 'name'):
            away_name = away_team.name
        elif isinstance(away_team, dict):
            away_name = away_team.get('name', 'Unbekannt')
        else:
            away_name = 'Unbekannt'

        st.info(f"💾 Speichere: {home_name} vs {away_name}")

        # Hole Positionen
        if hasattr(home_team, 'position'):
            home_position = home_team.position
        elif isinstance(home_team, dict):
            home_position = home_team.get('position', 10)
        else:
            home_position = 10

        if hasattr(away_team, 'position'):
            away_position = away_team.position
        elif isinstance(away_team, dict):
            away_position = away_team.get('position', 15)
        else:
            away_position = 15

        # Hole Spiele
        if hasattr(home_team, 'games'):
            home_games = home_team.games
        elif isinstance(home_team, dict):
            home_games = home_team.get('games', 20)
        else:
            home_games = 20

        if hasattr(away_team, 'games'):
            away_games = away_team.games
        elif isinstance(away_team, dict):
            away_games = away_team.get('games', 20)
        else:
            away_games = 20

        # Hole Punkte
        if hasattr(home_team, 'points'):
            home_points = home_team.points
        elif isinstance(home_team, dict):
            home_points = home_team.get('points', 30)
        else:
            home_points = 30

        if hasattr(away_team, 'points'):
            away_points = away_team.points
        elif isinstance(away_team, dict):
            away_points = away_team.get('points', 25)
        else:
            away_points = 25

        # Hole andere Werte
        predicted_mu_home = historical_match.get('predicted_mu_home', 1.8)
        predicted_mu_away = historical_match.get('predicted_mu_away', 1.2)
        actual_mu_home = historical_match.get('actual_mu_home', 2.0)
        actual_mu_away = historical_match.get('actual_mu_away', 1.0)
        actual_score = historical_match.get('actual_score', '0:0')
        competition = historical_match.get('competition', 'Unbekannt')
        match_date = historical_match.get(
            'date', datetime.now().strftime("%Y-%m-%d"))

        # Berechnungen
        home_ppg = home_points / home_games if home_games > 0 else 0
        away_ppg = away_points / away_games if away_games > 0 else 0

        home_correction = actual_mu_home / \
            predicted_mu_home if predicted_mu_home > 0 else 1.0
        away_correction = actual_mu_away / \
            predicted_mu_away if predicted_mu_away > 0 else 1.0

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Erstelle Datenzeile
        values = [[
            timestamp,                          # Timestamp
            match_date,                         # Date
            home_name,                          # Home_Team
            away_name,                          # Away_Team
            competition,                        # Competition
            str(home_position),                 # Home_Position
            str(away_position),                 # Away_Position
            str(home_games),                    # Home_Games
            str(away_games),                    # Away_Games
            str(home_points),                   # Home_Points
            str(away_points),                   # Away_Points
            f"{home_ppg:.3f}",                  # Home_PPG
            f"{away_ppg:.3f}",                  # Away_PPG
            f"{predicted_mu_home:.3f}",         # Predicted_MU_Home
            f"{predicted_mu_away:.3f}",         # Predicted_MU_Away
            f"{actual_mu_home:.3f}",            # Actual_MU_Home
            f"{actual_mu_away:.3f}",            # Actual_MU_Away
            f"{home_correction:.3f}",           # Home_Correction
            f"{away_correction:.3f}",           # Away_Correction
            actual_score,                       # Actual_Score
            ""                                  # Notes (leer)
        ]]

        # Versuche zu speichern
        body = {'values': values}
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="HISTORICAL_DATA!A:U",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()

        st.success(f"✅ {home_name} vs {away_name} gespeichert!")
        return True

    except Exception as e:
        st.error(f"❌ Fehler beim Speichern: {str(e)}")
        return False

# ==================== NEUE FUNKTIONEN FÜR DIREKTE HISTORICAL_DATA SPEICHE


def create_historical_sheet(service, sheet_id):
    """Erstellt das HISTORICAL_DATA Sheet mit Headern, falls es nicht existiert"""
    try:
        # Sheet hinzufügen
        body = {
            'requests': [{
                'addSheet': {
                    'properties': {
                        'title': 'HISTORICAL_DATA'
                    }
                }
            }]
        }
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body=body
        ).execute()

        # Header hinzufügen
        headers = [
            'Timestamp', 'Date', 'Home_Team', 'Away_Team', 'Competition',
            'Home_Position', 'Away_Position', 'Home_Games', 'Away_Games',
            'Home_Points', 'Away_Points', 'Home_PPG', 'Away_PPG',
            'Predicted_MU_Home', 'Predicted_MU_Away',
            'Actual_MU_Home', 'Actual_MU_Away',
            'Home_Correction', 'Away_Correction',
            'Actual_Score', 'Notes'
        ]

        body = {'values': [headers]}
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="HISTORICAL_DATA!A:U",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

        return True
    except Exception as e:
        st.error(f"❌ Fehler beim Erstellen des HISTORICAL_DATA Sheets: {e}")
        return False


def save_historical_directly(match_data: MatchData, actual_home_goals: int, actual_away_goals: int,
                            predicted_mu_home: float, predicted_mu_away: float):
    """Speichert historische Daten direkt nach der Analyse (wenn Ergebnis bekannt)"""
    try:
        if "tracking" not in st.secrets:
            st.warning("⚠️ Tracking nicht konfiguriert")
            return False

        sheet_id = get_tracking_sheet_id()
        if not sheet_id:
            st.error("❌ Keine Google Sheets ID gefunden (sheet_id / sheet_id_v48 / sheet_id_v47)")
            return False

        service = connect_to_sheets(readonly=False)
        if service is None:
            st.error("❌ Keine Verbindung zu Google Sheets")
            return False

        # 1. Historische Daten speichern
        actual_mu_home = float(actual_home_goals)
        actual_mu_away = float(actual_away_goals)

        home_correction = actual_mu_home / \
            predicted_mu_home if predicted_mu_home > 0 else 1.0
        away_correction = actual_mu_away / \
            predicted_mu_away if predicted_mu_away > 0 else 1.0

        home_ppg = match_data.home_team.points / \
            max(match_data.home_team.games, 1)
        away_ppg = match_data.away_team.points / \
            max(match_data.away_team.games, 1)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        actual_score = f"{actual_home_goals}:{actual_away_goals}"

        # Prüfe ob HISTORICAL_DATA Sheet existiert, sonst erstelle es
        try:
            service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="HISTORICAL_DATA!A:A"
            ).execute()
        except:
            # Sheet existiert nicht, erstelle es
            create_historical_sheet(service, sheet_id)

        values = [[
            timestamp,
            str(match_data.date),
            match_data.home_team.name,
            match_data.away_team.name,
            match_data.competition,
            int(match_data.home_team.position),
            int(match_data.away_team.position),
            int(match_data.home_team.games),
            int(match_data.away_team.games),
            int(match_data.home_team.points),
            int(match_data.away_team.points),
            round(home_ppg, 3),
            round(away_ppg, 3),
            round(predicted_mu_home, 3),
            round(predicted_mu_away, 3),
            round(actual_mu_home, 3),
            round(actual_mu_away, 3),
            round(home_correction, 3),
            round(away_correction, 3),
            actual_score,
            "Direkt nach Analyse gespeichert"
        ]]

        body = {'values': values}
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="HISTORICAL_DATA!A:U",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()

        # 2. Auch PREDICTIONS als COMPLETED markieren
        match_str = f"{match_data.home_team.name} vs {match_data.away_team.name}"
        update_match_result_in_sheets(match_str, actual_score)

        st.success(
            f"✅ Historische Daten für {match_data.home_team.name} vs {match_data.away_team.name} gespeichert!")
        return True

    except Exception as e:
        st.error(f"❌ Fehler beim direkten Speichern: {str(e)}")
        return False


def load_historical_matches_from_sheets():
    """Lädt historische Matches für ML-Training"""
    try:
        sheet_id = get_tracking_sheet_id()
        if not sheet_id:
            return []

        service = connect_to_sheets(readonly=True)
        if service is None:
            return []

        # Versuche von HISTORICAL_DATA zu laden
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="HISTORICAL_DATA!A:T"
            ).execute()
        except:
            # Fallback: Lade von PREDICTIONS mit COMPLETED Status
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="PREDICTIONS!A:W"
            ).execute()

        values = result.get('values', [])
        if len(values) <= 1:  # Nur Header oder leer
            return []

        historical_matches = []

        for i, row in enumerate(values):
            if i == 0:  # Header überspringen
                continue

            try:
                if "HISTORICAL_DATA" in result.get('range', ''):
                    # Parse HISTORICAL_DATA Format
                    if len(row) >= 20:
                        home_team = TeamStats(
                            name=row[2],
                            position=int(row[5]),
                            games=int(row[7]),
                            points=int(row[9]),
                            wins=0, draws=0, losses=0,
                            goals_for=0, goals_against=0, goal_diff=0,
                            form_points=0, form_goals_for=0, form_goals_against=0,
                            ha_points=0, ha_goals_for=0, ha_goals_against=0,
                            ppg_overall=float(row[11]),
                            ppg_ha=0,
                            avg_goals_match=0,
                            avg_goals_match_ha=0,
                            goals_scored_per_match=0,
                            goals_conceded_per_match=0,
                            goals_scored_per_match_ha=0,
                            goals_conceded_per_match_ha=0,
                            btts_yes_overall=0,
                            btts_yes_ha=0,
                            cs_yes_overall=0,
                            cs_yes_ha=0,
                            fts_yes_overall=0,
                            fts_yes_ha=0,
                            xg_for=0,
                            xg_against=0,
                            xg_for_ha=0,
                            xg_against_ha=0,
                            shots_per_match=0,
                            shots_on_target=0,
                            conversion_rate=0,
                            possession=0
                        )

                        away_team = TeamStats(
                            name=row[3],
                            position=int(row[6]),
                            games=int(row[8]),
                            points=int(row[10]),
                            wins=0, draws=0, losses=0,
                            goals_for=0, goals_against=0, goal_diff=0,
                            form_points=0, form_goals_for=0, form_goals_against=0,
                            ha_points=0, ha_goals_for=0, ha_goals_against=0,
                            ppg_overall=float(row[12]),
                            ppg_ha=0,
                            avg_goals_match=0,
                            avg_goals_match_ha=0,
                            goals_scored_per_match=0,
                            goals_conceded_per_match=0,
                            goals_scored_per_match_ha=0,
                            goals_conceded_per_match_ha=0,
                            btts_yes_overall=0,
                            btts_yes_ha=0,
                            cs_yes_overall=0,
                            cs_yes_ha=0,
                            fts_yes_overall=0,
                            fts_yes_ha=0,
                            xg_for=0,
                            xg_against=0,
                            xg_for_ha=0,
                            xg_against_ha=0,
                            shots_per_match=0,
                            shots_on_target=0,
                            conversion_rate=0,
                            possession=0
                        )

                        match_data = {
                            'home_team': home_team,
                            'away_team': away_team,
                            'date': row[1],
                            'predicted_mu_home': float(row[13]),
                            'predicted_mu_away': float(row[14]),
                            'actual_mu_home': float(row[15]),
                            'actual_mu_away': float(row[16]),
                            'home_correction': float(row[17]),
                            'away_correction': float(row[18]),
                            'actual_score': row[19] if len(row) > 19 else ""
                        }

                        historical_matches.append(match_data)

                elif "PREDICTIONS" in result.get('range', ''):
                    # Parse PREDICTIONS Format (COMPLETED Matches)
                    if len(row) > 16 and row[16] == "COMPLETED":
                        # Hier vereinfacht - in Realität müssten TeamStats
                        # rekonstruiert werden
                        try:
                            match_str = row[2] if len(row) > 2 else ""
                            actual_score = row[17] if len(row) > 17 else "0:0"
                            home_goals, away_goals = map(
                                int, actual_score.split(':'))

                            # Vereinfachte TeamStats für Demo
                            home_team = TeamStats(
                                name=match_str.split(
                                    " vs ")[0] if " vs " in match_str else "Heim",
                                position=10,
                                games=20,
                                points=30,
                                wins=0, draws=0, losses=0,
                                goals_for=0, goals_against=0, goal_diff=0,
                                form_points=0, form_goals_for=0, form_goals_against=0,
                                ha_points=0, ha_goals_for=0, ha_goals_against=0,
                                ppg_overall=1.5,
                                ppg_ha=0,
                                avg_goals_match=0,
                                avg_goals_match_ha=0,
                                goals_scored_per_match=0,
                                goals_conceded_per_match=0,
                                goals_scored_per_match_ha=0,
                                goals_conceded_per_match_ha=0,
                                btts_yes_overall=0,
                                btts_yes_ha=0,
                                cs_yes_overall=0,
                                cs_yes_ha=0,
                                fts_yes_overall=0,
                                fts_yes_ha=0,
                                xg_for=0,
                                xg_against=0,
                                xg_for_ha=0,
                                xg_against_ha=0,
                                shots_per_match=0,
                                shots_on_target=0,
                                conversion_rate=0,
                                possession=0
                            )

                            away_team = TeamStats(
                                name=match_str.split(
                                    " vs ")[1] if " vs " in match_str else "Auswärts",
                                position=15,
                                games=20,
                                points=25,
                                wins=0, draws=0, losses=0,
                                goals_for=0, goals_against=0, goal_diff=0,
                                form_points=0, form_goals_for=0, form_goals_against=0,
                                ha_points=0, ha_goals_for=0, ha_goals_against=0,
                                ppg_overall=1.25,
                                ppg_ha=0,
                                avg_goals_match=0,
                                avg_goals_match_ha=0,
                                goals_scored_per_match=0,
                                goals_conceded_per_match=0,
                                goals_scored_per_match_ha=0,
                                goals_conceded_per_match_ha=0,
                                btts_yes_overall=0,
                                btts_yes_ha=0,
                                cs_yes_overall=0,
                                cs_yes_ha=0,
                                fts_yes_overall=0,
                                fts_yes_ha=0,
                                xg_for=0,
                                xg_against=0,
                                xg_for_ha=0,
                                xg_against_ha=0,
                                shots_per_match=0,
                                shots_on_target=0,
                                conversion_rate=0,
                                possession=0
                            )

                            # Schätze μ-Werte aus tatsächlichen Toren
                            predicted_mu_home = 1.8  # Beispielwert
                            predicted_mu_away = 1.2  # Beispielwert

                            match_data = {
                                'home_team': home_team,
                                'away_team': away_team,
                                'date': row[0] if len(row) > 0 else "",
                                'predicted_mu_home': predicted_mu_home,
                                'predicted_mu_away': predicted_mu_away,
                                'actual_mu_home': float(home_goals),
                                'actual_mu_away': float(away_goals),
                                'home_correction': float(home_goals) / predicted_mu_home if predicted_mu_home > 0 else 1.0,
                                'away_correction': float(away_goals) / predicted_mu_away if predicted_mu_away > 0 else 1.0,
                                'actual_score': actual_score
                            }

                            historical_matches.append(match_data)
                        except:
                            continue
            except Exception as e:
                continue

        return historical_matches

    except Exception as e:
        st.error(f"Fehler beim Laden historischer Daten: {e}")
        return []

# ==================== PHASE 3: TABELLENPOSITION ML ====================
# Phase 3: Feature Engineering


def create_position_features(
    home_team: TeamStats,
    away_team: TeamStats,
    match_date: str,
        total_teams: int = 18):
    features = {}

    features['home_position'] = home_team.position
    features['away_position'] = away_team.position
    features['position_diff'] = home_team.position - away_team.position
    features['position_diff_abs'] = abs(features['position_diff'])

    features['home_pos_norm'] = (home_team.position - 1) / (total_teams - 1)
    features['away_pos_norm'] = (away_team.position - 1) / (total_teams - 1)

    features['home_ppg'] = home_team.points / max(home_team.games, 1)
    features['away_ppg'] = away_team.points / max(away_team.games, 1)
    features['ppg_diff'] = features['home_ppg'] - features['away_ppg']
    features['ppg_diff_abs'] = abs(features['ppg_diff'])

    def get_table_zone(position, total_teams):
        if position <= 3:
            return 'champions_league'
        elif position <= 6:
            return 'europa_league'
        elif position <= total_teams - 4:
            return 'midfield'
        elif position <= total_teams - 2:
            return 'relegation_threat'
        else:
            return 'direct_relegation'

    features['home_zone'] = get_table_zone(home_team.position, total_teams)
    features['away_zone'] = get_table_zone(away_team.position, total_teams)

    features['season_progress'] = home_team.games / 34

    def calculate_pressure(position, games_played, season_progress):
        pressure = 0.0

        if position >= total_teams - 2:
            pressure += 0.8
        elif position >= total_teams - 4:
            pressure += 0.5

        if position <= 3:
            pressure += 0.4

        if season_progress > 0.75:
            pressure *= 1.3

        return min(1.0, pressure)

    features['home_pressure'] = calculate_pressure(
        home_team.position,
        home_team.games,
        features['season_progress']
    )
    features['away_pressure'] = calculate_pressure(
        away_team.position,
        away_team.games,
        features['season_progress']
    )

    features['is_top_vs_bottom'] = 1 if home_team.position <= 3 and away_team.position >= total_teams - 3 else 0
    features['is_midfield_clash'] = 1 if 6 <= home_team.position <= 12 and 6 <= away_team.position <= 12 else 0
    features['is_relegation_battle'] = 1 if home_team.position >= total_teams - \
        4 and away_team.position >= total_teams - 4 else 0

    try:
        match_dt = datetime.strptime(match_date, "%Y-%m-%d")
        features['month'] = match_dt.month
        features['is_second_half'] = 1 if match_dt.month >= 1 else 0
        features['is_final_month'] = 1 if match_dt.month == 5 else 0
    except:
        features['month'] = 0
        features['is_second_half'] = 0
        features['is_final_month'] = 0

    return features


def encode_position_features(features_dict):
    encoded = {}

    numeric_features = [
        'home_position', 'away_position', 'position_diff', 'position_diff_abs',
        'home_pos_norm', 'away_pos_norm',
        'home_ppg', 'away_ppg', 'ppg_diff', 'ppg_diff_abs',
        'season_progress',
        'home_pressure', 'away_pressure',
        'is_top_vs_bottom', 'is_midfield_clash', 'is_relegation_battle',
        'month', 'is_second_half', 'is_final_month'
    ]

    for feature in numeric_features:
        if feature in features_dict:
            encoded[feature] = features_dict[feature]

    zone_mapping = {
        'champions_league': [1, 0, 0, 0, 0],
        'europa_league': [0, 1, 0, 0, 0],
        'midfield': [0, 0, 1, 0, 0],
        'relegation_threat': [0, 0, 0, 1, 0],
        'direct_relegation': [0, 0, 0, 0, 1]
    }

    home_zone = features_dict.get('home_zone', 'midfield')
    away_zone = features_dict.get('away_zone', 'midfield')

    for i, val in enumerate(zone_mapping.get(home_zone, [0, 0, 0, 0, 0])):
        encoded[f'home_zone_{i}'] = val

    for i, val in enumerate(zone_mapping.get(away_zone, [0, 0, 0, 0, 0])):
        encoded[f'away_zone_{i}'] = val

    return encoded

# Phase 3: ML-Modell Klasse


class TablePositionML:
    def __init__(self):
        self.model = None
        self.is_trained = False
        self.training_data_size = 0
        self.last_trained = None
        self.feature_importance = {}
        self.model_type = 'none'

    def initialize_model(self):
        try:
            try:
                import xgboost as xgb
                self.model = xgb.XGBRegressor(
                    n_estimators=100,
                    max_depth=6,
                    learning_rate=0.1,
                    random_state=42,
                    objective='reg:squarederror'
                )
                self.model_type = 'xgboost'
            except ImportError:
                from sklearn.ensemble import RandomForestRegressor
                self.model = RandomForestRegressor(
                    n_estimators=100,
                    max_depth=10,
                    random_state=42,
                    min_samples_split=5,
                    min_samples_leaf=2
                )
                self.model_type = 'randomforest'

            return True
        except Exception as e:
            st.error(f"❌ Fehler bei ML-Modell Initialisierung: {e}")
            self.model = None
            return False

    def create_features(
    self,
    home_team: TeamStats,
    away_team: TeamStats,
        match_date: str):
        return create_position_features(home_team, away_team, match_date)

    def prepare_training_data(self, historical_matches):
        X_train = []
        y_train = []

        for match in historical_matches:
            try:
                home_team_data = match.get('home_team', {})
                away_team_data = match.get('away_team', {})
                match_date = match.get('date', '')

                features = self.create_features(
                    home_team_data, away_team_data, match_date)
                encoded_features = encode_position_features(features)

                predicted_mu_home = match.get('predicted_mu_home', 1.0)
                predicted_mu_away = match.get('predicted_mu_away', 1.0)
                actual_mu_home = match.get('actual_mu_home', 1.0)
                actual_mu_away = match.get('actual_mu_away', 1.0)

                if predicted_mu_home > 0 and predicted_mu_away > 0:
                    correction_home = actual_mu_home / predicted_mu_home
                    correction_away = actual_mu_away / predicted_mu_away

                    X_train.append(list(encoded_features.values()))
                    y_train.append([correction_home, correction_away])

            except Exception as e:
                continue

        return X_train, y_train

    def train(self, historical_matches, min_matches=30):
        if len(historical_matches) < min_matches:
            return {
                'success': False,
                'message': f'Nicht genügend Daten: {len(historical_matches)}/{min_matches}',
                'matches_required': min_matches - len(historical_matches)
            }

        if self.model is None:
            if not self.initialize_model():
                return {
    'success': False,
        'message': 'ML-Modell konnte nicht initialisiert werden'}

        X_train, y_train = self.prepare_training_data(historical_matches)

        if len(X_train) < min_matches:
            return {
                'success': False,
                'message': f'Nicht genügend Trainingsdaten: {len(X_train)}/{min_matches}',
                'matches_required': min_matches - len(X_train)
            }

        try:
            self.model.fit(X_train, y_train)
            self.is_trained = True
            self.training_data_size = len(X_train)
            self.last_trained = datetime.now()

            if hasattr(self.model, 'feature_importances_'):
                dummy_team = TeamStats('', 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                features = self.create_features(
                    dummy_team, dummy_team, '2024-01-01')
                encoded = encode_position_features(features)
                feature_names = list(encoded.keys())

                if len(feature_names) == len(self.model.feature_importances_):
                    self.feature_importance = dict(
                        zip(feature_names, self.model.feature_importances_))

            return {
                'success': True,
                'message': f'Modell erfolgreich mit {len(X_train)} Matches trainiert',
                'training_size': len(X_train),
                'model_type': self.model_type,
                'last_trained': self.last_trained.strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            return {
                'success': False,
                'message': f'Fehler beim Training: {str(e)}'
            }

    def predict_correction(
    self,
    home_team: TeamStats,
    away_team: TeamStats,
        match_date: str):
        if not self.is_trained or self.model is None:
            return {
                'home_correction': 1.0,
                'away_correction': 1.0,
                'confidence': 0.0,
                'is_trained': False,
                'message': 'Modell nicht trainiert'
            }

        try:
            features = self.create_features(home_team, away_team, match_date)
            encoded_features = encode_position_features(features)

            X_pred = [list(encoded_features.values())]
            prediction = self.model.predict(X_pred)[0]

            home_correction = float(prediction[0])
            away_correction = float(prediction[1])

            home_correction = max(0.5, min(1.5, home_correction))
            away_correction = max(0.5, min(1.5, away_correction))

            confidence = min(0.9, self.training_data_size / 100)

            return {
                'home_correction': home_correction,
                'away_correction': away_correction,
                'confidence': confidence,
                'is_trained': True,
                'features_used': list(encoded_features.keys()),
                'message': f'ML-Korrektur basierend auf {self.training_data_size} Trainings-Matches'
            }

        except Exception as e:
            return {
                'home_correction': 1.0,
                'away_correction': 1.0,
                'confidence': 0.0,
                'is_trained': False,
                'message': f'Vorhersagefehler: {str(e)}'
            }

    def get_model_info(self):
        return {
            'is_trained': self.is_trained,
            'model_type': self.model_type,
            'training_data_size': self.training_data_size,
            'last_trained': self.last_trained.strftime("%Y-%m-%d %H:%M:%S") if self.last_trained else 'never',
            'feature_importance': self.feature_importance
        }

# ==================== PHASE 4: ERWEITERTE ML-DATEN ====================


def save_extended_match_data(extended_data: ExtendedMatchData):
    try:
        if "tracking" not in st.secrets:
            return {"success": False, "message": "Tracking nicht konfiguriert"}

        sheet_id = get_tracking_sheet_id()
        if not sheet_id:
            return {"success": False, "message": "sheet_id nicht gefunden"}

        service = connect_to_sheets(readonly=False)
        if service is None:
            return {
                "success": False,
                "message": "Keine Verbindung zu Google Sheets"}

        sheet_name = "EXTENDED_DATA"

        try:
            service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A:A"
            ).execute()
        except:
            body = {
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': sheet_name
                        }
                    }
                }]
            }
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body=body
            ).execute()

            headers = [
                'Timestamp', 'Match_ID', 'Match', 'Halftime',
                'Possession_Home', 'Possession_Away',
                'Shots_Home', 'Shots_Away',
                'ShotsOnTarget_Home', 'ShotsOnTarget_Away',
                'Corners_Home', 'Corners_Away',
                'Fouls_Home', 'Fouls_Away',
                'Yellow_Home', 'Yellow_Away',
                'Red_Home', 'Red_Away',
                'Subs_Home', 'Subs_Away',
                'Shot_Efficiency_Home', 'Shot_Efficiency_Away',
                'Corner_Frequency', 'Foul_Frequency',
                'Cards_Total', 'Subs_Total',
                'Notes'
            ]

            # ✅ GEÄNDERT: A:AB statt A:Z (27 Spalten statt 26)
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A:AB",
                valueInputOption="USER_ENTERED",
                body={'values': [headers]}
            ).execute()

        match_info = get_match_info_by_id(extended_data.match_id)

        shot_efficiency_home = (extended_data.shots_on_target_home /
                                extended_data.shots_home * 100) if extended_data.shots_home > 0 else 0
        shot_efficiency_away = (extended_data.shots_on_target_away /
                                extended_data.shots_away * 100) if extended_data.shots_away > 0 else 0

        corner_frequency = (extended_data.corners_home +
                            extended_data.corners_away) / 90
        foul_frequency = (extended_data.fouls_home +
                            extended_data.fouls_away) / 90

        cards_total = extended_data.yellow_cards_home + extended_data.yellow_cards_away + \
            extended_data.red_cards_home + extended_data.red_cards_away
        subs_total = extended_data.substitutions_home + extended_data.substitutions_away

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        match_str = match_info.get(
            'match', 'Unknown Match') if match_info else extended_data.match_id

        values = [[
            timestamp,
            extended_data.match_id,
            match_str,
            extended_data.halftime_score,
            f"{extended_data.possession_home:.1f}",
            f"{extended_data.possession_away:.1f}",
            str(extended_data.shots_home),
            str(extended_data.shots_away),
            str(extended_data.shots_on_target_home),
            str(extended_data.shots_on_target_away),
            str(extended_data.corners_home),
            str(extended_data.corners_away),
            str(extended_data.fouls_home),
            str(extended_data.fouls_away),
            str(extended_data.yellow_cards_home),
            str(extended_data.yellow_cards_away),
            str(extended_data.red_cards_home),
            str(extended_data.red_cards_away),
            str(extended_data.substitutions_home),
            str(extended_data.substitutions_away),
            f"{shot_efficiency_home:.1f}",
            f"{shot_efficiency_away:.1f}",
            f"{corner_frequency:.2f}",
            f"{foul_frequency:.2f}",
            str(cards_total),
            str(subs_total),
            extended_data.notes
        ]]

        body = {'values': values}
        # ✅ GEÄNDERT: A:AB statt A:Z
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A:AB",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()

        return {
            "success": True,
            "message": f"Erweiterte Daten für '{match_str}' gespeichert",
            "updated_cells": result.get('updates', {}).get('updatedCells', 0)
        }

    except Exception as e:
        return {"success": False, "message": f"Fehler beim Speichern: {str(e)}"}



def get_completed_matches_without_extended_data():
    try:
        sheet_id = get_tracking_sheet_id()
        if not sheet_id:
            return []

        service = connect_to_sheets(readonly=True)
        if service is None:
            return []

        predictions_result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="PREDICTIONS!A:W"
        ).execute()

        predictions = predictions_result.get('values', [])

        try:
            extended_result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="EXTENDED_DATA!B:B"
            ).execute()
            extended_matches = [row[0]
                for row in extended_result.get('values', []) if row]
        except:
            extended_matches = []

        completed_matches = []

        for i, row in enumerate(predictions):
            if i == 0:
                continue

            if len(row) > 16 and row[16] == "COMPLETED":
                match_str = row[2] if len(row) > 2 else ""
                match_id = match_str

                if match_id not in extended_matches:
                    completed_matches.append({
                        'match_id': match_id,
                        'match': match_str,
                        'actual_score': row[17] if len(row) > 17 else "",
                        'predicted_score': row[3] if len(row) > 3 else "",
                        'date': row[0] if len(row) > 0 else ""
                    })

        return completed_matches

    except Exception as e:
        st.error(f"❌ Fehler beim Laden der Spiele: {e}")
        return []


def create_extended_features(
    extended_data: ExtendedMatchData,
        match_info: Dict):
    features = {}

    try:
        ht_home, ht_away = map(int, extended_data.halftime_score.split(':'))

        features['halftime_home_goals'] = ht_home
        features['halftime_away_goals'] = ht_away
        features['halftime_total'] = ht_home + ht_away

        features['halftime_lead'] = ht_home - ht_away
        features['home_leading_at_ht'] = 1 if ht_home > ht_away else 0
        features['away_leading_at_ht'] = 1 if ht_away > ht_home else 0
        features['draw_at_halftime'] = 1 if ht_home == ht_away else 0

        if 'actual_score' in match_info:
            try:
                ft_home, ft_away = map(
                    int, match_info['actual_score'].split(':'))
                features['second_half_goals_home'] = ft_home - ht_home
                features['second_half_goals_away'] = ft_away - ht_away
                features['comeback_occurred'] = 1 if (ht_home < ht_away and ft_home > ft_away) or (
                    ht_home > ht_away and ft_home < ft_away) else 0
            except:
                pass

    except:
        features['halftime_home_goals'] = 0
        features['halftime_away_goals'] = 0
        features['halftime_total'] = 0
        features['halftime_lead'] = 0
        features['home_leading_at_ht'] = 0
        features['away_leading_at_ht'] = 0
        features['draw_at_halftime'] = 0

    features['possession_home'] = extended_data.possession_home
    features['possession_away'] = extended_data.possession_away
    features['possession_dominance'] = extended_data.possession_home - \
        extended_data.possession_away

    if extended_data.possession_home > 60:
        features['possession_category'] = 2
    elif extended_data.possession_home > 55:
        features['possession_category'] = 1
    elif extended_data.possession_home > 45:
        features['possession_category'] = 0
    elif extended_data.possession_home > 40:
        features['possession_category'] = -1
    else:
        features['possession_category'] = -2

    features['shots_total_home'] = extended_data.shots_home
    features['shots_total_away'] = extended_data.shots_away
    features['shots_total'] = extended_data.shots_home + \
        extended_data.shots_away

    features['shots_on_target_home'] = extended_data.shots_on_target_home
    features['shots_on_target_away'] = extended_data.shots_on_target_away
    features['shots_on_target_total'] = extended_data.shots_on_target_home + \
        extended_data.shots_on_target_away

    features['shot_accuracy_home'] = (
        extended_data.shots_on_target_home / extended_data.shots_home) if extended_data.shots_home > 0 else 0
    features['shot_accuracy_away'] = (
        extended_data.shots_on_target_away / extended_data.shots_away) if extended_data.shots_away > 0 else 0

    features['shot_dominance'] = extended_data.shots_home - \
        extended_data.shots_away
    features['shot_on_target_dominance'] = extended_data.shots_on_target_home - \
        extended_data.shots_on_target_away

    features['shots_per_minute_home'] = extended_data.shots_home / 90
    features['shots_per_minute_away'] = extended_data.shots_away / 90

    features['corners_home'] = extended_data.corners_home
    features['corners_away'] = extended_data.corners_away
    features['corners_total'] = extended_data.corners_home + \
        extended_data.corners_away

    features['corner_dominance'] = extended_data.corners_home - \
        extended_data.corners_away
    features['corners_per_minute'] = features['corners_total'] / 90

    if features['corners_total'] > 0:
        features['corner_ratio_home'] = extended_data.corners_home / \
            features['corners_total']
    else:
        features['corner_ratio_home'] = 0.5

    features['fouls_home'] = extended_data.fouls_home
    features['fouls_away'] = extended_data.fouls_away
    features['fouls_total'] = extended_data.fouls_home + \
        extended_data.fouls_away

    features['fouls_per_minute'] = features['fouls_total'] / 90

    features['yellow_cards_total'] = extended_data.yellow_cards_home + \
        extended_data.yellow_cards_away
    features['red_cards_total'] = extended_data.red_cards_home + \
        extended_data.red_cards_away
    features['cards_total'] = features['yellow_cards_total'] + \
        features['red_cards_total']

    features['aggression_index_home'] = (
        extended_data.fouls_home + extended_data.yellow_cards_home * 2 + extended_data.red_cards_home * 5) / 90
    features['aggression_index_away'] = (
        extended_data.fouls_away + extended_data.yellow_cards_away * 2 + extended_data.red_cards_away * 5) / 90

    features['substitutions_home'] = extended_data.substitutions_home
    features['substitutions_away'] = extended_data.substitutions_away
    features['substitutions_total'] = extended_data.substitutions_home + \
        extended_data.substitutions_away

    if features['shots_on_target_total'] > 0:
        features['expected_win_ratio_home'] = extended_data.shots_on_target_home / \
            features['shots_on_target_total']
    else:
        features['expected_win_ratio_home'] = 0.5

    features['control_score'] = (
        features['possession_dominance'] * 0.3 +
        features['shot_dominance'] * 0.3 +
        features['corner_dominance'] * 0.2 +
        features['halftime_lead'] * 0.2
    ) / 10

    features['defensive_stability_home'] = 1 / \
        (features['shots_on_target_away'] + 1) * 100
    features['defensive_stability_away'] = 1 / \
        (features['shots_on_target_home'] + 1) * 100

    if extended_data.shots_home > 0:
        features['offensive_efficiency_home'] = (features.get(
            'halftime_home_goals', 0) + features.get('second_half_goals_home', 0)) / extended_data.shots_home * 100
    else:
        features['offensive_efficiency_home'] = 0

    if extended_data.shots_away > 0:
        features['offensive_efficiency_away'] = (features.get(
            'halftime_away_goals', 0) + features.get('second_half_goals_away', 0)) / extended_data.shots_away * 100
    else:
        features['offensive_efficiency_away'] = 0

    return features

# Phase 4: Erweitertes ML-Modell


class ExtendedMatchML:
    def __init__(self):
        self.position_ml = None
        self.extended_model = None
        self.is_trained = False
        self.training_data_size = 0
        self.feature_importance = {}

    def initialize_model(self, base_ml_model):
        self.position_ml = base_ml_model

        try:
            from sklearn.ensemble import StackingRegressor, RandomForestRegressor
            from sklearn.linear_model import Ridge

            base_models = [
                ('rf', RandomForestRegressor(
                    n_estimators=50, max_depth=7, random_state=42)),
                ('ridge', Ridge(alpha=1.0))
            ]

            self.extended_model = StackingRegressor(
                estimators=base_models,
                final_estimator=Ridge(alpha=1.0),
                cv=5
            )

            return True
        except Exception as e:
            st.error(
                f"❌ Erweitertes ML-Modell Initialisierung fehlgeschlagen: {e}")
            return False

    def create_combined_features(
    self,
    position_features: Dict,
        extended_features: Dict):
        combined = {}

        position_keys = [
            'home_position', 'away_position', 'position_diff', 'position_diff_abs',
            'home_ppg', 'away_ppg', 'ppg_diff', 'ppg_diff_abs',
            'season_progress', 'home_pressure', 'away_pressure'
        ]

        for key in position_keys:
            if key in position_features:
                combined[f'pos_{key}'] = position_features[key]

        extended_keys = [
            'halftime_lead', 'home_leading_at_ht', 'possession_dominance',
            'shot_dominance', 'shot_on_target_dominance', 'corner_dominance',
            'control_score', 'defensive_stability_home', 'defensive_stability_away',
            'offensive_efficiency_home', 'offensive_efficiency_away'
        ]

        for key in extended_keys:
            if key in extended_features:
                combined[f'ext_{key}'] = extended_features[key]

        if 'pos_home_position' in combined and 'ext_possession_dominance' in combined:
            combined['interaction_top_possession'] = (
                (1 if combined['pos_home_position'] <= 3 else 0) *
                (1 if combined['ext_possession_dominance'] > 10 else 0)
            )

        if 'pos_home_pressure' in combined and 'ext_halftime_lead' in combined:
            combined['interaction_pressure_halftime'] = (
                combined['pos_home_pressure'] *
                (1 if combined['ext_halftime_lead'] > 0 else 0)
            )

        combined['match_type'] = self.classify_match_type(
            position_features, extended_features)

        return combined

    def classify_match_type(
    self,
    position_features: Dict,
        extended_features: Dict) -> int:
        possession = extended_features.get('possession_dominance', 0)
        shots_diff = extended_features.get('shot_dominance', 0)
        halftime_lead = extended_features.get('halftime_lead', 0)

        if abs(possession) > 15 and abs(shots_diff) > 8:
            return 1

        elif extended_features.get('fouls_total', 0) > 25:
            return 2

        elif extended_features.get('shots_total', 0) > 30:
            return 3

        elif abs(halftime_lead) > 2:
            return 4

        else:
            return 0

    def prepare_extended_training_data(self, historical_matches_with_extended):
        X_train = []
        y_train = []

        for match in historical_matches_with_extended:
            try:
                position_features = match.get('position_features', {})
                extended_features = match.get('extended_features', {})

                combined_features = self.create_combined_features(
                    position_features, extended_features)

                feature_vector = list(combined_features.values())

                predicted_mu_home = match.get('predicted_mu_home', 1.5)
                predicted_mu_away = match.get('predicted_mu_away', 1.5)
                actual_mu_home = match.get('actual_mu_home', 1.5)
                actual_mu_away = match.get('actual_mu_away', 1.5)

                if predicted_mu_home > 0 and predicted_mu_away > 0:
                    home_correction = actual_mu_home / predicted_mu_home
                    away_correction = actual_mu_away / predicted_mu_away

                    home_correction = max(0.5, min(2.0, home_correction))
                    away_correction = max(0.5, min(2.0, away_correction))

                    X_train.append(feature_vector)
                    y_train.append([home_correction, away_correction])

            except Exception as e:
                continue

        return np.array(X_train), np.array(y_train)

    def train(self, historical_matches_with_extended, min_matches=20):
        if len(historical_matches_with_extended) < min_matches:
            return {
                'success': False,
                'message': f'Nicht genügend erweiterte Daten: {len(historical_matches_with_extended)}/{min_matches}'
            }

        if self.extended_model is None:
            if not self.initialize_model(st.session_state.position_ml_model):
                return {
    'success': False,
        'message': 'Erweitertes Modell konnte nicht initialisiert werden'}

        X_train, y_train = self.prepare_extended_training_data(
            historical_matches_with_extended)

        if len(X_train) < min_matches:
            return {
                'success': False,
                'message': f'Nicht genügend Trainingsdaten: {len(X_train)}/{min_matches}'
            }

        try:
            self.extended_model.fit(X_train, y_train)
            self.is_trained = True
            self.training_data_size = len(X_train)

            return {
                'success': True,
                'message': f'Erweitertes ML-Modell mit {len(X_train)} Spielen trainiert',
                'feature_count': X_train.shape[1] if len(X_train.shape) > 1 else 0
            }

        except Exception as e:
            return {'success': False, 'message': f'Training fehlgeschlagen: {str(e)}'}

    def predict_with_extended_data(
    self,
    position_features: Dict,
        extended_features: Dict):
        if not self.is_trained:
            return {
                'home_correction': 1.0,
                'away_correction': 1.0,
                'confidence': 0.0,
                'message': 'Erweitertes Modell nicht trainiert'
            }

        try:
            combined_features = self.create_combined_features(
                position_features, extended_features)

            X_pred = np.array([list(combined_features.values())])
            prediction = self.extended_model.predict(X_pred)[0]

            home_correction = float(prediction[0])
            away_correction = float(prediction[1])

            home_correction = max(0.5, min(1.5, home_correction))
            away_correction = max(0.5, min(1.5, away_correction))

            confidence = min(0.95, self.training_data_size / 50)

            return {
                'home_correction': home_correction,
                'away_correction': away_correction,
                'confidence': confidence,
                'features_used': len(combined_features),
                'match_type': combined_features.get('match_type', 0)
            }

        except Exception as e:
            return {
                'home_correction': 1.0,
                'away_correction': 1.0,
                'confidence': 0.0,
                'message': f'Vorhersagefehler: {str(e)}'
            }

# ==================== ANALYSE-FUNKTIONEN ====================


def validate_match_data(match: MatchData) -> Tuple[bool, List[str]]:
    missing_fields = []

    def check_team_data(team: TeamStats, team_name: str):
        team_missing = []

        if not team.name or team.name.strip() == "":
            team_missing.append(f"{team_name}: Team-Name")
        if team.position is None or team.position <= 0:
            team_missing.append(f"{team_name}: Tabellenposition")
        if team.games is None or team.games <= 0:
            team_missing.append(f"{team_name}: Anzahl Spiele")
        if team.wins is None:
            team_missing.append(f"{team_name}: Siege")
        if team.draws is None:
            team_missing.append(f"{team_name}: Unentschieden")
        if team.losses is None:
            team_missing.append(f"{team_name}: Niederlagen")
        if team.goals_for is None:
            team_missing.append(f"{team_name}: Tore geschossen")
        if team.goals_against is None:
            team_missing.append(f"{team_name}: Tore kassiert")
        if team.goal_diff is None:
            team_missing.append(f"{team_name}: Tordifferenz")
        if team.points is None:
            team_missing.append(f"{team_name}: Punkte")
        if team.form_points is None:
            team_missing.append(f"{team_name}: Form-Punkte (L5)")
        if team.form_goals_for is None:
            team_missing.append(f"{team_name}: Form-Tore geschossen (L5)")
        if team.form_goals_against is None:
            team_missing.append(f"{team_name}: Form-Tore kassiert (L5)")
        if team.ha_points is None:
            team_missing.append(f"{team_name}: Heim/Auswärts-Punkte")
        if team.ha_goals_for is None:
            team_missing.append(f"{team_name}: H/A Tore geschossen")
        if team.ha_goals_against is None:
            team_missing.append(f"{team_name}: H/A Tore kassiert")
        if team.ppg_overall is None or team.ppg_overall < 0:
            team_missing.append(f"{team_name}: PPG Overall")
        if team.ppg_ha is None or team.ppg_ha < 0:
            team_missing.append(f"{team_name}: PPG Heim/Auswärts")
        if team.avg_goals_match is None or team.avg_goals_match < 0:
            team_missing.append(f"{team_name}: Ø Tore pro Spiel")
        if team.avg_goals_match_ha is None or team.avg_goals_match_ha < 0:
            team_missing.append(f"{team_name}: Ø Tore H/A")
        if team.goals_scored_per_match is None or team.goals_scored_per_match < 0:
            team_missing.append(f"{team_name}: Tore geschossen/Spiel")
        if team.goals_conceded_per_match is None or team.goals_conceded_per_match < 0:
            team_missing.append(f"{team_name}: Tore kassiert/Spiel")
        if team.goals_scored_per_match_ha is None or team.goals_scored_per_match_ha < 0:
            team_missing.append(f"{team_name}: Tore geschossen/Spiel H/A")
        if team.goals_conceded_per_match_ha is None or team.goals_conceded_per_match_ha < 0:
            team_missing.append(f"{team_name}: Tore kassiert/Spiel")
        if team.btts_yes_overall is None or team.btts_yes_overall < 0:
            team_missing.append(f"{team_name}: BTTS% Overall")
        if team.btts_yes_ha is None or team.btts_yes_ha < 0:
            team_missing.append(f"{team_name}: BTTS% H/A")
        if team.cs_yes_overall is None or team.cs_yes_overall < 0:
            team_missing.append(f"{team_name}: Clean Sheet% Overall")
        if team.cs_yes_ha is None or team.cs_yes_ha < 0:
            team_missing.append(f"{team_name}: Clean Sheet% H/A")
        if team.fts_yes_overall is None or team.fts_yes_overall < 0:
            team_missing.append(f"{team_name}: FTS% Overall")
        if team.fts_yes_ha is None or team.fts_yes_ha < 0:
            team_missing.append(f"{team_name}: FTS% H/A")
        if team.xg_for is None or team.xg_for < 0:
            team_missing.append(f"{team_name}: xG For")
        if team.xg_against is None or team.xg_against < 0:
            team_missing.append(f"{team_name}: xG Against")
        if team.xg_for_ha is None or team.xg_for_ha < 0:
            team_missing.append(f"{team_name}: xG For H/A")
        if team.xg_against_ha is None or team.xg_against_ha < 0:
            team_missing.append(f"{team_name}: xG Against H/A")
        if team.shots_per_match is None or team.shots_per_match < 0:
            team_missing.append(f"{team_name}: Schüsse/Spiel")
        if team.shots_on_target is None or team.shots_on_target < 0:
            team_missing.append(f"{team_name}: Schüsse aufs Tor")
        if team.conversion_rate is None or team.conversion_rate < 0:
            team_missing.append(f"{team_name}: Conversion Rate")
        if team.possession is None or team.possession < 0:
            team_missing.append(f"{team_name}: Ballbesitz%")

        return team_missing

    missing_fields.extend(check_team_data(match.home_team, "HEIM"))
    missing_fields.extend(check_team_data(match.away_team, "AUSWÄRTS"))

    if not match.date or match.date.strip() == "":
        missing_fields.append("Match-Datum")
    if not match.competition or match.competition.strip() == "":
        missing_fields.append("Wettbewerb/Liga")
    if not match.kickoff or match.kickoff.strip() == "":
        missing_fields.append("Anstoßzeit")

    if not match.odds_1x2 or len(match.odds_1x2) != 3:
        missing_fields.append("1X2 Quoten (vollständig)")
    else:
        if match.odds_1x2[0] is None or match.odds_1x2[0] <= 1.0:
            missing_fields.append("1X2 Quote: Heim")
        if match.odds_1x2[1] is None or match.odds_1x2[1] <= 1.0:
            missing_fields.append("1X2 Quote: Unentschieden")
        if match.odds_1x2[2] is None or match.odds_1x2[2] <= 1.0:
            missing_fields.append("1X2 Quote: Auswärts")

    if not match.odds_ou25 or len(match.odds_ou25) != 2:
        missing_fields.append("Over/Under 2.5 Quoten")
    else:
        if match.odds_ou25[0] is None or match.odds_ou25[0] <= 1.0:
            missing_fields.append("Over 2.5 Quote")
        if match.odds_ou25[1] is None or match.odds_ou25[1] <= 1.0:
            missing_fields.append("Under 2.5 Quote")

    if not match.odds_btts or len(match.odds_btts) != 2:
        missing_fields.append("BTTS Quoten")
    else:
        if match.odds_btts[0] is None or match.odds_btts[0] <= 1.0:
            missing_fields.append("BTTS Ja Quote")
        if match.odds_btts[1] is None or match.odds_btts[1] <= 1.0:
            missing_fields.append("BTTS Nein Quote")

    if match.h2h_results is None:
        missing_fields.append("H2H-Daten (Liste)")

    is_valid = len(missing_fields) == 0
    return is_valid, missing_fields


def analyze_h2h(
    home: TeamStats,
    away: TeamStats,
        h2h_data: List[H2HResult]) -> Dict:
    if not h2h_data:
        return {
            'avg_total_goals': 2.5,
            'avg_home_goals': 1.5,
            'avg_away_goals': 1.0,
            'home_wins': 0,
            'draws': 0,
            'away_wins': 0,
            'btts_percentage': 0.5
        }

    total_goals = []
    home_goals_list = []
    away_goals_list = []
    home_wins = 0
    draws = 0
    away_wins = 0
    btts_count = 0

    for result in h2h_data:
        total_goals.append(result.home_goals + result.away_goals)

        if result.home_team == home.name:
            home_goals_list.append(result.home_goals)
            away_goals_list.append(result.away_goals)

            if result.home_goals > result.away_goals:
                home_wins += 1
            elif result.home_goals == result.away_goals:
                draws += 1
            else:
                away_wins += 1
        else:
            home_goals_list.append(result.away_goals)
            away_goals_list.append(result.home_goals)

            if result.away_goals > result.home_goals:
                home_wins += 1
            elif result.home_goals == result.away_goals:
                draws += 1
            else:
                away_wins += 1

        if result.home_goals > 0 and result.away_goals > 0:
            btts_count += 1

    return {
        'avg_total_goals': sum(total_goals) / len(total_goals),
        'avg_home_goals': sum(home_goals_list) / len(home_goals_list),
        'avg_away_goals': sum(away_goals_list) / len(away_goals_list),
        'home_wins': home_wins,
        'draws': draws,
        'away_wins': away_wins,
        'btts_percentage': btts_count / len(h2h_data)
    }


def calculate_risk_score(mu_h: float, mu_a: float, tki_h: float, tki_a: float,
                        ppg_diff: float, h2h_avg_goals: float, btts_prob: float) -> Dict:
    score = 50
    faktor_details = {}

    mu_total = mu_h + mu_a
    faktor_details['mu_total'] = mu_total

    if mu_total > 4.5:
        score += 25
        faktor_details['mu_total_impact'] = "+25"
    elif mu_total > 4.0:
        score += 15
        faktor_details['mu_total_impact'] = "+15"
    elif mu_total > 3.5:
        score += 8
        faktor_details['mu_total_impact'] = "+8"
    elif mu_total < 2.0:
        score -= 15
        faktor_details['mu_total_impact'] = "-15"
    elif mu_total < 2.5:
        score -= 8
        faktor_details['mu_total_impact'] = "-8"
    else:
        faktor_details['mu_total_impact'] = "0"

    tki_combined = tki_h + tki_a
    faktor_details['tki_combined'] = tki_combined

    if tki_combined > 1.0:
        score += 20
        faktor_details['tki_impact'] = "+20"
    elif tki_combined > 0.8:
        score += 15
        faktor_details['tki_impact'] = "+15"
    elif tki_combined > 0.6:
        score += 10
        faktor_details['tki_impact'] = "+10"
    elif tki_combined > 0.4:
        score += 5
        faktor_details['tki_impact'] = "+5"
    else:
        faktor_details['tki_impact'] = "0"

    ppg_diff_abs = abs(ppg_diff)
    faktor_details['ppg_diff'] = ppg_diff_abs

    if ppg_diff_abs > 1.2:
        score -= 20
        faktor_details['ppg_impact'] = "-20"
    elif ppg_diff_abs > 0.8:
        score -= 12
        faktor_details['ppg_impact'] = "-12"
    elif ppg_diff_abs > 0.5:
        score -= 6
        faktor_details['ppg_impact'] = "-6"
    elif ppg_diff_abs < 0.2:
        score += 15
        faktor_details['ppg_impact'] = "+15"
    elif ppg_diff_abs < 0.3:
        score += 8
        faktor_details['ppg_impact'] = "+8"
    else:
        faktor_details['ppg_impact'] = "0"

    faktor_details['h2h_avg_goals'] = h2h_avg_goals

    if h2h_avg_goals > 4.5:
        score += 12
        faktor_details['h2h_impact'] = "+12"
    elif h2h_avg_goals > 4.0:
        score += 8
        faktor_details['h2h_impact'] = "+8"
    elif h2h_avg_goals > 3.5:
        score += 4
        faktor_details['h2h_impact'] = "+4"
    elif h2h_avg_goals < 1.5:
        score -= 10
        faktor_details['h2h_impact'] = "-10"
    else:
        faktor_details['h2h_impact'] = "0"

    faktor_details['btts_prob'] = btts_prob

    if btts_prob > 75:
        score += 8
        faktor_details['btts_impact'] = "+8"
    elif btts_prob > 65:
        score += 4
        faktor_details['btts_impact'] = "+4"
    elif btts_prob < 35:
        score -= 6
        faktor_details['btts_impact'] = "-6"
    else:
        faktor_details['btts_impact'] = "0"

    score = max(0, min(100, score))

    if score < 25:
        kategorie = "🟢 SEHR GERINGES RISIKO"
        color = "green"
        empfehlung = "Gute Basis für Wetten"
    elif score < 40:
        kategorie = "🟢 GERINGES RISIKO"
        color = "lightgreen"
        empfehlung = "Solide Wettmöglichkeit"
    elif score < 55:
        kategorie = "🟡 MODERATES RISIKO"
        color = "yellow"
        empfehlung = "Standard-Risiko"
    elif score < 70:
        kategorie = "🟠 ERHÖHTES RISIKO"
        color = "orange"
        empfehlung = "Vorsicht bei Wetten"
    elif score < 85:
        kategorie = "🔴 HOHES RISIKO"
        color = "red"
        empfehlung = "Nur für erfahrene Wettende"
    else:
        kategorie = "🔴 EXTREM HOHES RISIKO"
        color = "darkred"
        empfehlung = "Sehr spekulativ"

    return {
        'score': round(score),
        'kategorie': kategorie,
        'color': color,
        'empfehlung': empfehlung,
        'faktoren': faktor_details,
        'details': {
            'mu_total': f"{mu_total:.1f} ({faktor_details['mu_total_impact']})",
            'tki_combined': f"{tki_combined:.2f} ({faktor_details['tki_impact']})",
            'ppg_diff': f"{ppg_diff_abs:.2f} ({faktor_details['ppg_impact']})",
            'h2h_avg_goals': f"{h2h_avg_goals:.1f} ({faktor_details['h2h_impact']})",
            'btts_prob': f"{btts_prob:.1f}% ({faktor_details['btts_impact']})"
        }
    }


def check_alerts(mu_h: float, mu_a: float, tki_h: float, tki_a: float,
                ppg_diff: float, thresholds: Dict) -> List[Dict]:
    alerts = []

    mu_total = mu_h + mu_a
    if mu_total > thresholds.get('mu_total_high', 4.5):
        alerts.append({
            'level': '🔴',
            'title': 'EXTREM TORREICHES SPIEL',
            'message': f"μ-Total: {mu_total:.1f} (> {thresholds['mu_total_high']}) - Sehr unvorhersehbar!",
            'type': 'warning'
        })
    elif mu_total > 4.0:
        alerts.append({
            'level': '🟠',
            'title': 'Sehr torreiches Spiel',
            'message': f"μ-Total: {mu_total:.1f} - Erhöhte Unvorhersehbarkeit",
            'type': 'info'
        })

    tki_combined = tki_h + tki_a
    if tki_combined > thresholds.get('tki_high', 1.0):
        alerts.append({
            'level': '🔴',
            'title': 'EXTREME TORWART-KRISE',
            'message': f"TKI kombiniert: {tki_combined:.2f} (> {thresholds['tki_high']}) - Defensiven instabil!",
            'type': 'warning'
        })
    elif tki_combined > 0.8:
        alerts.append({
            'level': '🟠',
            'title': 'Torwart-Probleme',
            'message': f"TKI kombiniert: {tki_combined:.2f} - Defensiven geschwächt",
            'type': 'info'
        })

    ppg_diff_abs = abs(ppg_diff)
    if ppg_diff_abs > thresholds.get('ppg_diff_extreme', 1.5):
        alerts.append({
            'level': '🟢',
            'title': 'EXTREM KLARER FAVORIT',
            'message': f"PPG-Differenz: {ppg_diff_abs:.2f} - Sehr einseitiges Spiel erwartet",
            'type': 'success'
        })

    return alerts


def calculate_extended_risk_scores_strict(prob_1x2_home: float, prob_1x2_draw: float, prob_1x2_away: float,
                                            prob_over: float, prob_under: float,
                                            prob_btts_yes: float, prob_btts_no: float,
                                            odds_1x2: tuple, odds_ou: tuple, odds_btts: tuple,
                                            mu_total: float, tki_combined: float, ppg_diff: float,
                                            home_team, away_team) -> Dict:

    def strict_risk_description(score: int) -> str:
        descriptions = {
            1: "🔴 EXTREM RISIKANT",
            2: "🔴 HOHES RISIKO",
            3: "🟡 MODERATES RISIKO",
            4: "🟢 GERINGES RISIKO",
            5: "🟢 OPTIMALES RISIKO"
        }
        return descriptions.get(score, "🟡 MODERATES RISIKO")

    def calculate_1x2_risk_strict(
    best_prob: float,
    best_odds: float,
        second_best_prob: float) -> int:
        ev = (best_prob / 100) * best_odds - 1
        prob_dominance = best_prob - second_best_prob if second_best_prob > 0 else best_prob

        if ev < -0.15:
            return 1
        elif ev < -0.05:
            return 2
        elif ev < 0.08:
            if prob_dominance < 10:
                return 3
            else:
                return 4
        elif ev < 0.18:
            if prob_dominance > 15:
                return 4
            else:
                return 3
        else:
            if prob_dominance > 20 and ev > 0.25:
                return 5
            else:
                return 4

    probs_1x2 = [prob_1x2_home, prob_1x2_draw, prob_1x2_away]
    markets = ['Heimsieg', 'Unentschieden', 'Auswärtssieg']
    sorted_probs = sorted(zip(probs_1x2, odds_1x2, markets),
                            key=lambda x: x[0], reverse=True)

    best_prob, best_odds, best_market = sorted_probs[0]
    second_best_prob = sorted_probs[1][0]

    risk_1x2 = calculate_1x2_risk_strict(
        best_prob, best_odds, second_best_prob)

    def calculate_ou_risk_strict(
    prob: float,
    odds: float,
        mu_total: float) -> int:
        ev = (prob / 100) * odds - 1
        mu_adjustment = 0

        if mu_total > 4.0 and prob > 65:
            mu_adjustment = -1
        elif mu_total < 2.0 and prob > 65:
            mu_adjustment = -1

        if ev < -0.15:
            base_score = 1
        elif ev < -0.05:
            base_score = 2
        elif ev < 0.10:
            base_score = 3
        elif ev < 0.20:
            base_score = 4
        else:
            base_score = 5

        return max(1, min(5, base_score + mu_adjustment))

    risk_over = calculate_ou_risk_strict(prob_over, odds_ou[0], mu_total)
    risk_under = calculate_ou_risk_strict(prob_under, odds_ou[1], mu_total)

    def calculate_btts_risk_strict(prob: float, odds: float,
                                    home_cs_rate: float, away_cs_rate: float) -> int:
        ev = (prob / 100) * odds - 1
        cs_penalty = 0
        avg_cs_rate = (home_cs_rate + away_cs_rate) / 2

        if prob > 70:
            if avg_cs_rate > 0.4:
                cs_penalty = -2
            elif avg_cs_rate > 0.3:
                cs_penalty = -1

        if ev < -0.15:
            base_score = 1
        elif ev < -0.05:
            base_score = 2
        elif ev < 0.12:
            base_score = 3
        elif ev < 0.22:
            base_score = 4
        else:
            base_score = 5

        return max(1, min(5, base_score + cs_penalty))

    risk_btts_yes = calculate_btts_risk_strict(prob_btts_yes, odds_btts[0],
                                                home_team.cs_yes_ha, away_team.cs_yes_ha)
    risk_btts_no = calculate_btts_risk_strict(prob_btts_no, odds_btts[1],
                                                home_team.cs_yes_ha, away_team.cs_yes_ha)

    def calculate_overall_risk_strict(risk_1x2: int, risk_over: int, risk_under: int,
                                        risk_btts_yes: int, risk_btts_no: int,
                                        best_1x2_prob: float, mu_total: float,
                                        tki_combined: float, ppg_diff: float,
                                        home_games: int, away_games: int) -> Dict:

        weights = {
            '1x2': 0.35,
            'ou': 0.30,
            'btts': 0.25,
            'data_quality': 0.10
        }

        data_quality_score = 3
        if home_games < 10 or away_games < 10:
            data_quality_score = 2
        if home_games < 5 or away_games < 5:
            data_quality_score = 1

        avg_risk = (risk_1x2 * weights['1x2'] +
                    ((risk_over + risk_under) / 2) * weights['ou'] +
                    ((risk_btts_yes + risk_btts_no) / 2) * weights['btts'] +
                    data_quality_score * weights['data_quality'])

        adjustments = 0.0

        if mu_total > 4.5:
            adjustments -= 1.5
        elif mu_total > 4.0:
            adjustments -= 1.0
        elif mu_total > 3.5:
            adjustments -= 0.6
        elif mu_total < 2.0:
            adjustments += 0.3

        if tki_combined > 1.0:
            adjustments -= 1.5
        elif tki_combined > 0.8:
            adjustments -= 1.0
        elif tki_combined > 0.6:
            adjustments -= 0.6

        ppg_diff_abs = abs(ppg_diff)

        if ppg_diff_abs > 1.5:
            if best_1x2_prob > 75:
                adjustments -= 0.5
            else:
                adjustments += 0.3
        elif ppg_diff_abs > 1.0:
            adjustments += 0.1
        elif ppg_diff_abs < 0.2:
            adjustments += 0.4

        if best_1x2_prob > 75:
            adjustments -= 0.3
        elif best_1x2_prob > 65:
            adjustments += 0.1
        elif best_1x2_prob < 35:
            adjustments -= 0.3

        best_odds_value = max(odds_1x2)
        if best_odds_value > 3.0:
            adjustments -= 0.5
        elif best_odds_value < 1.5:
            adjustments -= 0.3

        total_games = home_games + away_games
        if total_games < 20:
            adjustments -= 0.5

        final_score = avg_risk + adjustments

        if final_score > 4.7:
            final_score_int = 5
        elif final_score > 3.7:
            final_score_int = 4
        elif final_score > 2.7:
            final_score_int = 3
        elif final_score > 1.7:
            final_score_int = 2
        else:
            final_score_int = 1

        if final_score_int == 1:
            category = "🔴 EXTREM RISIKANT"
            recommendation = "Vermeiden - sehr spekulativ"
            color = "darkred"
            score_text = "1/5"
            emoji = "☠️"
        elif final_score_int == 2:
            category = "🔴 HOHES RISIKO"
            recommendation = "Nur für erfahrene Wettende mit kleinem Einsatz"
            color = "red"
            score_text = "2/5"
            emoji = "⚠️"
        elif final_score_int == 3:
            category = "🟡 MODERATES RISIKO"
            recommendation = "Standard-Wette mit normalem Einsatz"
            color = "yellow"
            score_text = "3/5"
            emoji = "📊"
        elif final_score_int == 4:
            category = "🟢 GERINGES RISIKO"
            recommendation = "Gute Wettmöglichkeit - empfohlener Einsatz"
            color = "lightgreen"
            score_text = "4/5"
            emoji = "✅"
        else:
            category = "🟢 OPTIMALES RISIKO"
            recommendation = "Seltene Top-Wette - erhöhter Einsatz möglich"
            color = "green"
            score_text = "5/5"
            emoji = "🎯"

        return {
            'score': final_score_int,
            'score_text': score_text,
            'category': category,
            'recommendation': recommendation,
            'color': color,
            'emoji': emoji,
            'details': {
                'average_risk': round(avg_risk, 2),
                'adjustments': round(adjustments, 2),
                'mu_total_impact': mu_total,
                'tki_impact': tki_combined,
                'favorite_prob': best_1x2_prob,
                'ppg_diff_abs': ppg_diff_abs,
                'best_odds': round(best_odds_value, 2),
                'data_quality': f"{home_games}/{away_games} Spiele"
            }
        }

    overall_risk = calculate_overall_risk_strict(
        risk_1x2, risk_over, risk_under, risk_btts_yes, risk_btts_no,
        best_prob, mu_total, tki_combined, ppg_diff,
        home_team.games, away_team.games
    )

    return {
        'overall': overall_risk,
        '1x2': {
            'market': best_market,
            'probability': best_prob,
            'odds': best_odds,
            'risk_score': risk_1x2,
            'risk_text': strict_risk_description(risk_1x2),
            'second_best_prob': second_best_prob,
            'prob_dominance': best_prob - second_best_prob,
            'ev': (best_prob / 100) * best_odds - 1
        },
        'over_under': {
            'over': {
                'probability': prob_over,
                'odds': odds_ou[0],
                'risk_score': risk_over,
                'risk_text': strict_risk_description(risk_over),
                'ev': (prob_over / 100) * odds_ou[0] - 1
            },
            'under': {
                'probability': prob_under,
                'odds': odds_ou[1],
                'risk_score': risk_under,
                'risk_text': strict_risk_description(risk_under),
                'ev': (prob_under / 100) * odds_ou[1] - 1
            }
        },
        'btts': {
            'yes': {
                'probability': prob_btts_yes,
                'odds': odds_btts[0],
                'risk_score': risk_btts_yes,
                'risk_text': strict_risk_description(risk_btts_yes),
                'ev': (prob_btts_yes / 100) * odds_btts[0] - 1
            },
            'no': {
                'probability': prob_btts_no,
                'odds': odds_btts[1],
                'risk_score': risk_btts_no,
                'risk_text': strict_risk_description(risk_btts_no),
                'ev': (prob_btts_no / 100) * odds_btts[1] - 1
            }
        },
        'risk_factors': {
            'mu_total': mu_total,
            'tki_combined': tki_combined,
            'ppg_diff': ppg_diff,
            'home_games': home_team.games,
            'away_games': away_team.games,
            'avg_cs_rate': (home_team.cs_yes_ha + away_team.cs_yes_ha) / 2
        }
    }


def analyze_match_v47_ml(match: MatchData) -> Dict:
    """
    v5.0 mit v4.9 SMART-PRECISION LOGIK
    
    NEU von v4.9:
    - Form-Faktoren Integration
    - TKI-Krise deaktiviert BTTS-Dominanz-Killer
    - FTS-Check nur bei PPG > 1.0 (nicht 0.5)
    - Form-Boost bei starker Defensive reduziert
    - TKI-Krise überschreibt Form-Malus
    - Strengere Dominanz-Dämpfer
    - Auswärts-Underdog Boost
    - Verschärfte Clean Sheet Validierung
    - Conversion-Rate Adjustment
    """
    
    # DATEN-EXTRAKTION
    s_c_ha = [
        match.home_team.goals_scored_per_match_ha,
        match.home_team.goals_conceded_per_match_ha,
        match.away_team.goals_scored_per_match_ha,
        match.away_team.goals_conceded_per_match_ha
    ]

    xg_ha = [
        match.home_team.xg_for_ha,
        match.home_team.xg_against_ha,
        match.away_team.xg_for_ha,
        match.away_team.xg_against_ha
    ]

    cs_rates = [
        match.home_team.cs_yes_ha * 100,
        match.away_team.cs_yes_ha * 100
    ]

    ppg = [
        match.home_team.ppg_ha,
        match.away_team.ppg_ha
    ]

    conv_rate = [
        match.home_team.conversion_rate * 100,
        match.away_team.conversion_rate * 100
    ]
    
    # Form-Daten
    form_ppg_h = match.home_team.form_points / 5
    form_ppg_a = match.away_team.form_points / 5
    
    # Failed to Score
    fts_h = match.home_team.fts_yes_ha
    fts_a = match.away_team.fts_yes_ha
    
    # --- v4.9 SMART-PRECISION LOGIK ---
    
    # 1. BASIS μ
    mu_h = (xg_ha[0] + s_c_ha[0]) / 2
    mu_a = (xg_ha[2] + s_c_ha[2]) / 2
    
    # 2. FORM-FAKTOR
    def calculate_form_factor(form_ppg, overall_ppg):
        if overall_ppg == 0:
            return 1.0
        form_ratio = form_ppg / overall_ppg
        
        if form_ratio < 0.4:
            return 0.70
        elif form_ratio < 0.6:
            return 0.85
        elif form_ratio > 1.5:
            return 1.20
        elif form_ratio > 1.2:
            return 1.10
        else:
            return 1.0
    
    form_factor_h = calculate_form_factor(form_ppg_h, ppg[0])
    form_factor_a = calculate_form_factor(form_ppg_a, ppg[1])
    
    # 3. TKI BERECHNUNG (früh, für spätere Checks)
    tki_h = max(0, s_c_ha[1] - xg_ha[1])
    tki_a = max(0, s_c_ha[3] - xg_ha[3])
    tki_combined = tki_h + tki_a
    
    # 4. NEU v4.9: TKI-KRISE ÜBERSCHREIBT FORM-MALUS
    if tki_a > 1.0:  # Gast-Keeper in Krise
        if form_factor_h < 1.0:
            form_factor_h = 1.0  # Ignoriere Heim-Form-Malus
    
    if tki_h > 1.0:  # Heim-Keeper in Krise
        if form_factor_a < 1.0:
            form_factor_a = 1.0  # Ignoriere Gast-Form-Malus
    
    # 5. NEU v4.9: DEFENSIVE CONTEXT CHECK (Form-Boost reduzieren)
    if cs_rates[0] > 40 and form_factor_h > 1.0:
        form_factor_h = 1.0 + (form_factor_h - 1.0) * 0.5  # Halbiere den Boost
    
    if cs_rates[1] > 40 and form_factor_a > 1.0:
        form_factor_a = 1.0 + (form_factor_a - 1.0) * 0.5
    
    # 6. Form-Faktor anwenden
    mu_h *= form_factor_h
    mu_a *= form_factor_a
    
    # 7. DOMINANZ-DÄMPFER (aggressiv)
    ppg_diff = ppg[0] - ppg[1]
    
    if ppg_diff > 1.5:
        mu_a *= 0.45
        mu_h *= 1.30
    elif ppg_diff > 1.2:
        mu_a *= 0.55
        mu_h *= 1.25
    elif ppg_diff > 0.8:
        mu_a *= 0.65
        mu_h *= 1.15
    
    # 8. AUSWÄRTS-UNDERDOG BOOST
    if ppg_diff < -0.5:
        mu_a *= 1.20
        mu_h *= 0.80
    elif ppg_diff < -0.3:
        mu_a *= 1.10
        mu_h *= 0.90
    
    # 9. CLEAN SHEET VALIDIERUNG (verschärft)
    if cs_rates[0] > 50:
        mu_a *= 0.70
    elif cs_rates[0] > 40:
        mu_a *= 0.80
    elif cs_rates[0] > 30:
        mu_a *= 0.85
    
    if cs_rates[1] > 50:
        mu_h *= 0.70
    elif cs_rates[1] > 40:
        mu_h *= 0.80
    elif cs_rates[1] > 30:
        mu_h *= 0.85
    
    # 10. TKI-BOOST
    mu_h = mu_h * (1 + (tki_a * 0.4))
    mu_a = mu_a * (1 + (tki_h * 0.4))
    
    # 11. CONVERSION-RATE ADJUSTMENT
    def apply_conversion_adjustment(mu, conversion_rate):
        if conversion_rate > 14:
            return mu * 1.10
        elif conversion_rate < 8:
            return mu * 0.90
        return mu
    
    mu_h = apply_conversion_adjustment(mu_h, conv_rate[0])
    mu_a = apply_conversion_adjustment(mu_a, conv_rate[1])

    # ML-Korrektur (Phase 3) - NACH allen v4.9 Anpassungen
    ml_info = {'applied': False, 'reason': 'ML-Modell nicht initialisiert'}

    if st.session_state.position_ml_model and st.session_state.position_ml_model.is_trained:
        ml_correction = st.session_state.position_ml_model.predict_correction(
            home_team=match.home_team,
            away_team=match.away_team,
            match_date=match.date
        )

        if ml_correction['is_trained'] and ml_correction['confidence'] > 0.3:
            mu_h_original = mu_h
            mu_a_original = mu_a

            mu_h *= ml_correction['home_correction']
            mu_a *= ml_correction['away_correction']

            ml_info = {
                'applied': True,
                'home_correction': ml_correction['home_correction'],
                'away_correction': ml_correction['away_correction'],
                'confidence': ml_correction['confidence'],
                'original_mu': {'home': mu_h_original, 'away': mu_a_original},
                'corrected_mu': {'home': mu_h, 'away': mu_a},
                'message': ml_correction['message']
            }
        else:
            ml_info = {
                'applied': False,
                'reason': ml_correction['message'],
                'confidence': ml_correction['confidence']
            }

    # 12. POISSON MATRIX
    wh, dr, wa, ov25, btts_p = 0.0, 0.0, 0.0, 0.0, 0.0
    max_p, score = 0.0, (0, 0)

    for i in range(9):
        for j in range(9):
            p = poisson_probability(mu_h, i) * poisson_probability(mu_a, j)
            if i > j: 
                wh += p
            elif i == j: 
                dr += p
            else: 
                wa += p
            if (i + j) > 2.5: 
                ov25 += p
            if i > 0 and j > 0: 
                btts_p += p
            if p > max_p: 
                max_p, score = p, (i, j)

    # 13. BTTS-PRÄZISIONS-FILTER v4.9
    if mu_h < 1.0 or mu_a < 1.0:
        btts_p *= 0.8
    
    # NEU v4.9: DOMINANZ-KILLER (nur wenn KEINE TKI-Krise!)
    if tki_combined < 0.8:  # Nur bei stabilen Defensiven
        if ppg_diff > 1.0:
            btts_p *= 0.60
        elif ppg_diff > 0.8:
            btts_p *= 0.75
    
    # NEU v4.9: FAILED TO SCORE CHECK (nur bei starker Dominanz)
    if fts_a > 0.30 and ppg_diff > 1.0:  # GEÄNDERT von 0.5 auf 1.0
        btts_p *= 0.70
    if fts_h > 0.30 and ppg_diff < -1.0:  # GEÄNDERT von -0.5 auf -1.0
        btts_p *= 0.70

    h2h_stats = analyze_h2h(
        match.home_team, match.away_team, match.h2h_results)

    risk_score = calculate_risk_score(
        mu_h, mu_a, tki_h, tki_a, ppg_diff,
        h2h_stats['avg_total_goals'], btts_p * 100
    )

    extended_risk = calculate_extended_risk_scores_strict(
        prob_1x2_home=wh * 100,
        prob_1x2_draw=dr * 100,
        prob_1x2_away=wa * 100,
        prob_over=ov25 * 100,
        prob_under=(1 - ov25) * 100,
        prob_btts_yes=btts_p * 100,
        prob_btts_no=(1 - btts_p) * 100,
        odds_1x2=match.odds_1x2,
        odds_ou=match.odds_ou25,
        odds_btts=match.odds_btts,
        mu_total=mu_h + mu_a,
        tki_combined=tki_h + tki_a,
        ppg_diff=ppg_diff,
        home_team=match.home_team,
        away_team=match.away_team
    )

    result = {
        'match_info': {
            'home': match.home_team.name,
            'away': match.away_team.name,
            'date': match.date,
            'competition': match.competition,
            'kickoff': match.kickoff
        },
        'tki': {
            'home': round(tki_h, 2),
            'away': round(tki_a, 2),
            'combined': round(tki_h + tki_a, 2)
        },
        'mu': {
            'home': round(mu_h, 2),
            'away': round(mu_a, 2),
            'total': round(mu_h + mu_a, 2),
            'ppg_diff': round(ppg_diff, 2)
        },
        'form': {
            'home_factor': round(form_factor_h, 2),
            'away_factor': round(form_factor_a, 2),
            'home_ppg': round(form_ppg_h, 2),
            'away_ppg': round(form_ppg_a, 2)
        },
        'h2h': h2h_stats,
        'probabilities': {
            'home_win': round(wh * 100, 1),
            'draw': round(dr * 100, 1),
            'away_win': round(wa * 100, 1),
            'over_25': round(ov25 * 100, 1),
            'under_25': round((1 - ov25) * 100, 1),
            'btts_yes': round(btts_p * 100, 1),
            'btts_no': round((1 - btts_p) * 100, 1)
        },
        'scorelines': [(f"{score[0]}:{score[1]}", round(max_p * 100, 2))],
        'predicted_score': f"{score[0]}:{score[1]}",
        'risk_score': risk_score,
        'extended_risk': extended_risk,
        'ml_position_correction': ml_info,
        'odds': {
            '1x2': match.odds_1x2,
            'ou25': match.odds_ou25,
            'btts': match.odds_btts
        }
    }

    try:
        save_prediction_to_sheets(
            match_info=result['match_info'],
            probabilities=result['probabilities'],
            odds=result['odds'],
            risk_score=result['extended_risk']['overall'],
            predicted_score=result['predicted_score'],
            mu_info=result['mu']
        )
    except Exception:
        pass

    return result


def analyze_match_with_extended_data(
    match: MatchData,
        extended_data: Optional[ExtendedMatchData] = None):
    result = analyze_match_v47_ml(match)

    if extended_data and st.session_state.get(
        'extended_ml_model') and st.session_state.extended_ml_model.is_trained:
        position_features = create_position_features(
            match.home_team, match.away_team, match.date)

        extended_features = create_extended_features(extended_data, {
            'actual_score': f"{result['mu']['home']:.0f}:{result['mu']['away']:.0f}"
        })

        extended_ml = st.session_state.extended_ml_model
        extended_correction = extended_ml.predict_with_extended_data(
            position_features,
            extended_features
        )

        if extended_correction.get('confidence', 0) > 0.3:
            original_mu = result['mu'].copy()

            result['mu']['home'] *= extended_correction['home_correction']
            result['mu']['away'] *= extended_correction['away_correction']
            result['mu']['total'] = result['mu']['home'] + result['mu']['away']

            result['extended_ml_correction'] = {
                'applied': True,
                'home_correction': extended_correction['home_correction'],
                'away_correction': extended_correction['away_correction'],
                'confidence': extended_correction['confidence'],
                'match_type': extended_correction.get('match_type', 0),
                'features_used': extended_correction.get('features_used', 0),
                'original_mu': original_mu,
                'message': f"Erweiterte ML-Korrektur (Spieltyp: {extended_correction.get('match_type', 0)})"
            }
        else:
            result['extended_ml_correction'] = {
                'applied': False,
                'message': extended_correction.get('message', 'Konfidenz zu niedrig')
            }
    else:
        result['extended_ml_correction'] = {
            'applied': False,
            'message': 'Keine erweiterten Daten oder ML-Modell nicht trainiert'
        }

    return result

# ==================== UI FUNKTIONEN ====================


def show_extended_data_entry_ui():
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Erweiterte Daten eintragen")

    completed_matches = get_completed_matches_without_extended_data()

    if not completed_matches:
        st.sidebar.info("✅ Alle Spiele haben erweiterte Daten")
        return

    selected_match = st.sidebar.selectbox(
        "Spiel auswählen",
        options=[m['match'] for m in completed_matches],
        help="Spiel für das du erweiterte Daten eintragen möchtest",
        key="extended_match_select"
    )

    selected_match_info = next(
        (m for m in completed_matches if m['match'] == selected_match), None)

    if selected_match_info:
        st.sidebar.caption(
            f"Ergebnis: {selected_match_info.get('actual_score', 'N/A')}")
        st.sidebar.caption(
            f"Vorhersage: {selected_match_info.get('predicted_score', 'N/A')}")

        with st.sidebar.expander("📝 Erweiterte Daten eingeben", expanded=False):

            # ====== FORMULAR START - KEINE VERZÖGERUNGEN! ======
            with st.form(key="extended_data_form"):

                st.markdown("**⏱️ Halbzeitergebnis**")
                col_ht1, col_ht2 = st.columns(2)
                with col_ht1:
                    ht_home = st.number_input(
                        "Heim", min_value=0, max_value=10, value=0, key="ht_home")
                with col_ht2:
                    ht_away = st.number_input(
                        "Auswärts", min_value=0, max_value=10, value=0, key="ht_away")

                st.markdown("**⚽ Ballbesitz (%)**")
                possession_home = st.slider(
                    "Heim-Besitz", 0, 100, 50, key="possession_home")
                possession_away = 100 - possession_home
                st.caption(
                    f"Heim: {possession_home}% | Auswärts: {possession_away}%")

                st.markdown("**🎯 Schüsse**")
                col_sh1, col_sh2 = st.columns(2)
                with col_sh1:
                    shots_home = st.number_input(
                        "Heim gesamt", min_value=0, max_value=50, value=10, key="shots_home")
                    shots_on_target_home = st.number_input(
                        "Heim auf Tor", min_value=0, max_value=50, value=4, key="shots_on_target_home")
                with col_sh2:
                    shots_away = st.number_input(
                        "Auswärts gesamt", min_value=0, max_value=50, value=8, key="shots_away")
                    shots_on_target_away = st.number_input(
                        "Auswärts auf Tor", min_value=0, max_value=50, value=3, key="shots_on_target_away")

                st.markdown("**↗️ Ecken**")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    corners_home = st.number_input(
                        "Heim", min_value=0, max_value=20, value=5, key="corners_home")
                with col_c2:
                    corners_away = st.number_input(
                        "Auswärts", min_value=0, max_value=20, value=3, key="corners_away")

                st.markdown("**⚖️ Fouls & Karten**")
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    fouls_home = st.number_input(
                        "Fouls Heim", min_value=0, max_value=30, value=12, key="fouls_home")
                    yellow_home = st.number_input(
                        "🟡 Heim", min_value=0, max_value=10, value=2, key="yellow_home")
                    red_home = st.number_input(
                        "🔴 Heim", min_value=0, max_value=5, value=0, key="red_home")
                with col_f2:
                    fouls_away = st.number_input(
                        "Fouls Auswärts", min_value=0, max_value=30, value=14, key="fouls_away")
                    yellow_away = st.number_input(
                        "🟡 Auswärts", min_value=0, max_value=10, value=3, key="yellow_away")
                    red_away = st.number_input(
                        "🔴 Auswärts", min_value=0, max_value=5, value=0, key="red_away")

                st.markdown("**🔄 Wechsel**")
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    subs_home = st.number_input(
                        "Heim", min_value=0, max_value=5, value=3, key="subs_home")
                with col_s2:
                    subs_away = st.number_input(
                        "Auswärts", min_value=0, max_value=5, value=3, key="subs_away")

                st.markdown("**📝 Notizen**")
                notes = st.text_area(
                    "Besondere Ereignisse oder Beobachtungen:",
                    placeholder="z.B. Verletzungen, Torchancen, Spielverlauf...",
                    height=100,
                    key="extended_notes"
                )

                # ====== SUBMIT BUTTON - NUR HIER ERFOLGT RERUN! ======
                submitted = st.form_submit_button(
                    "💾 Erweiterte Daten speichern", use_container_width=True, type="primary")

                if submitted:
                    halftime_score = f"{ht_home}:{ht_away}"

                    extended_data = ExtendedMatchData(
                        match_id=selected_match_info['match_id'],
                        halftime_score=halftime_score,
                        possession_home=float(possession_home),
                        possession_away=float(possession_away),
                        shots_home=shots_home,
                        shots_away=shots_away,
                        shots_on_target_home=shots_on_target_home,
                        shots_on_target_away=shots_on_target_away,
                        corners_home=corners_home,
                        corners_away=corners_away,
                        fouls_home=fouls_home,
                        fouls_away=fouls_away,
                        yellow_cards_home=yellow_home,
                        yellow_cards_away=yellow_away,
                        red_cards_home=red_home,
                        red_cards_away=red_away,
                        substitutions_home=subs_home,
                        substitutions_away=subs_away,
                        notes=notes
                    )

                    result = save_extended_match_data(extended_data)

                    if result['success']:
                        st.success(f"✅ {result['message']}")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error(f"❌ {result['message']}")


def show_ml_training_ui():
    st.header("🧠 TABELLENPOSITION ML-MODELL")

    if st.session_state.position_ml_model is None:
        st.session_state.position_ml_model = TablePositionML()

    ml_model = st.session_state.position_ml_model

    col1, col2, col3 = st.columns(3)

    with col1:
        status = "✅ Trainiert" if ml_model.is_trained else "❌ Nicht trainiert"
        st.metric("Modell-Status", status)

    with col2:
        if ml_model.is_trained:
            st.metric("Trainingsdaten", ml_model.training_data_size)
        else:
            st.metric("Benötigte Daten", "30+")

    with col3:
        if ml_model.is_trained and ml_model.last_trained:
            st.metric("Zuletzt trainiert",
                        ml_model.last_trained.strftime("%d.%m.%Y"))
        else:
            st.metric("Training", "Ausstehend")

    st.markdown("---")

    st.subheader("🚀 ML-Modell trainieren")

    # Lade historische Daten
    historical_matches = load_historical_matches_from_sheets()

    if historical_matches:
        st.info(
            f"📊 **{len(historical_matches)} historische Spiele** für Training verfügbar")

        if len(historical_matches) < 30:
            st.warning(
                f"⚠️ **Noch {30 - len(historical_matches)} Spiele benötigt** für Training")
        else:
            st.success(
                f"✅ **Genügend Daten vorhanden** für Training ({len(historical_matches)}/30)")

            if st.button(
    "🎯 ML-Modell jetzt trainieren",
    type="primary",
        use_container_width=True):
                with st.spinner("Training ML-Modell mit historischen Daten..."):
                    result = ml_model.train(historical_matches)

                    if result['success']:
                        st.success(f"✅ {result['message']}")
                        st.balloons()

                        if ml_model.feature_importance:
                            st.subheader("📈 Feature Importance")
                            importance_df = pd.DataFrame.from_dict(
                                ml_model.feature_importance,
                                orient='index',
                                columns=['Importance']
                            ).sort_values('Importance', ascending=False)

                            st.dataframe(importance_df.head(
                                10), use_container_width=True)

                            fig = go.Figure(data=[
                                go.Bar(
                                    x=importance_df.head(10).index,
                                    y=importance_df.head(10)['Importance'],
                                    marker_color='lightblue'
                                )
                            ])
                            fig.update_layout(
                                title="Top 10 Wichtigste Features",
                                yaxis_title="Importance",
                                height=400
                            )
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.error(
                            f"❌ Training fehlgeschlagen: {result['message']}")

    else:
        st.warning("⚠️ **Keine historischen Daten verfügbar**")
        st.info("""
        **So sammelst du Trainingsdaten:**
        1. Analysiere Spiele (Match-Analyse Tab)
        2. Trage Ergebnisse nach (Sidebar → Ergebnisse nachtragen)
        3. Warte bis 30+ abgeschlossene Spiele vorhanden sind
        4. Trainiere dann das ML-Modell
        """)

    if ml_model.is_trained:
        st.markdown("---")
        st.subheader("🧪 Live ML-Korrektur Test")

        col_home, col_away = st.columns(2)

        with col_home:
            home_pos = st.number_input(
                "Heim-Position", min_value=1, max_value=18, value=1, key="test_home_pos")
            home_points = st.number_input(
                "Heim-Punkte", min_value=0, max_value=100, value=50, key="test_home_points")
            home_games = st.number_input(
                "Heim-Spiele", min_value=1, max_value=34, value=20, key="test_home_games")

        with col_away:
            away_pos = st.number_input(
                "Auswärts-Position", min_value=1, max_value=18, value=18, key="test_away_pos")
            away_points = st.number_input(
                "Auswärts-Punkte", min_value=0, max_value=100, value=15, key="test_away_points")
            away_games = st.number_input(
                "Auswärts-Spiele", min_value=1, max_value=34, value=20, key="test_away_games")

        if st.button(
    "🧠 ML-Korrektur berechnen",
    use_container_width=True,
        key="test_ml_correction"):
            home_team = TeamStats(
                name="Test Heim", position=home_pos, games=home_games,
                points=home_points, wins=0, draws=0, losses=0,
                goals_for=0, goals_against=0, goal_diff=0,
                form_points=0, form_goals_for=0, form_goals_against=0,
                ha_points=0, ha_goals_for=0, ha_goals_against=0,
                ppg_overall=home_points / home_games if home_games > 0 else 0,
                ppg_ha=0, avg_goals_match=0,
                avg_goals_match_ha=0, goals_scored_per_match=0,
                goals_conceded_per_match=0, goals_scored_per_match_ha=0,
                goals_conceded_per_match_ha=0, btts_yes_overall=0,
                btts_yes_ha=0, cs_yes_overall=0, cs_yes_ha=0,
                fts_yes_overall=0, fts_yes_ha=0, xg_for=0,
                xg_against=0, xg_for_ha=0, xg_against_ha=0,
                shots_per_match=0, shots_on_target=0, conversion_rate=0,
                possession=0
            )
            away_team = TeamStats(
                name="Test Auswärts", position=away_pos, games=away_games,
                points=away_points, wins=0, draws=0, losses=0,
                goals_for=0, goals_against=0, goal_diff=0,
                form_points=0, form_goals_for=0, form_goals_against=0,
                ha_points=0, ha_goals_for=0, ha_goals_against=0,
                ppg_overall=away_points / away_games if away_games > 0 else 0,
                ppg_ha=0, avg_goals_match=0,
                avg_goals_match_ha=0, goals_scored_per_match=0,
                goals_conceded_per_match=0, goals_scored_per_match_ha=0,
                goals_conceded_per_match_ha=0, btts_yes_overall=0,
                btts_yes_ha=0, cs_yes_overall=0, cs_yes_ha=0,
                fts_yes_overall=0, fts_yes_ha=0, xg_for=0,
                xg_against=0, xg_for_ha=0, xg_against_ha=0,
                shots_per_match=0, shots_on_target=0, conversion_rate=0,
                possession=0
            )

            correction = ml_model.predict_correction(
                home_team=home_team,
                away_team=away_team,
                match_date=datetime.now().strftime("%Y-%m-%d")
            )

            if correction['is_trained']:
                st.success("✅ ML-Korrektur berechnet")

                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.metric(
                        "Heim-Korrektur",
                        f"{correction['home_correction']:.3f}",
                        delta=f"μ × {correction['home_correction']:.3f}"
                    )
                with col_res2:
                    st.metric(
                        "Auswärts-Korrektur",
                        f"{correction['away_correction']:.3f}",
                        delta=f"μ × {correction['away_correction']:.3f}"
                    )

                st.caption(f"Konfidenz: {correction['confidence'] * 100:.1f}%")
            else:
                st.warning(f"⚠️ {correction['message']}")


def display_results(result):
    st.header(
        f"🎯 {result['match_info']['home']} vs {result['match_info']['away']}")
    st.caption(
        f"📅 {result['match_info']['date']} | {result['match_info']['kickoff']} Uhr | {result['match_info']['competition']}")

    alerts = check_alerts(
        result['mu']['home'], result['mu']['away'],
        result['tki']['home'], result['tki']['away'],
        result['mu']['ppg_diff'], st.session_state.alert_thresholds
    )

    if alerts:
        st.subheader("🚨 ALARM-SYSTEM")
        for alert in alerts:
            if alert['type'] == 'warning':
                st.warning(
                    f"{alert['level']} **{alert['title']}**: {alert['message']}")
            elif alert['type'] == 'info':
                st.info(
                    f"{alert['level']} **{alert['title']}**: {alert['message']}")
            elif alert['type'] == 'success':
                st.success(
                    f"{alert['level']} **{alert['title']}**: {alert['message']}")

    st.subheader("🧠 SMART-PRECISION v4.7+")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Smart μ Home", f"{result['mu']['home']:.2f}")
    with col2:
        st.metric("Smart μ Away", f"{result['mu']['away']:.2f}")
    with col3:
        st.metric("PPG Gap", f"{result['mu']['ppg_diff']:.2f}")

    if result.get('ml_position_correction', {}).get('applied', False):
        st.info(
            f"📊 ML-Korrektur angewandt: {result['ml_position_correction']['message']}")

    st.subheader("⚠️ ERWEITERTE RISIKO-ANALYSE (1-5)")

    overall_risk = result['extended_risk']['overall']

    risk_color_map = {
        1: "darkred", 2: "red", 3: "yellow", 4: "lightgreen", 5: "green"
    }

    col1, col2, col3 = st.columns([2, 3, 2])
    with col1:
        st.markdown(f"### {overall_risk['score_text']}")
        st.progress(overall_risk['score'] / 5)
    with col2:
        st.markdown(f"**{overall_risk['category']}**")
        st.markdown(f"*{overall_risk['recommendation']}*")
    with col3:
        fig_risk = go.Figure(go.Indicator(
            mode="gauge+number",
            value=overall_risk['score'],
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Gesamt-Risiko"},
            gauge={
                'axis': {'range': [1, 5], 'tickwidth': 1},
                'bar': {'color': risk_color_map.get(overall_risk['score'], "gray")},
                'steps': [
                    {'range': [1, 2], 'color': "lightcoral"},
                    {'range': [2, 3], 'color': "lightyellow"},
                    {'range': [3, 4], 'color': "lightgreen"},
                    {'range': [4, 5], 'color': "green"}
                ],
                'threshold': {
                    'line': {'color': "black", 'width': 4},
                    'thickness': 0.75,
                    'value': overall_risk['score']
                }
            }
        ))
        fig_risk.update_layout(height=200)
        st.plotly_chart(fig_risk, use_container_width=True)

    st.subheader("📊 EINZELNE WETT-RISIKOS")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**🎯 1X2 WETTE**")
        risk_1x2 = result['extended_risk']['1x2']
        risk_display = f"{risk_1x2['risk_score']}/5 {risk_1x2['risk_text']}"
        st.metric(
            label=f"{risk_1x2['market']} ({risk_1x2['probability']:.1f}%)",
            value=f"{risk_1x2['odds']:.2f}",
            delta=risk_display,
            delta_color="off"
        )

    with col2:
        st.markdown("**📈 OVER/UNDER 2.5**")
        risk_ou = result['extended_risk']['over_under']
        col2a, col2b = st.columns(2)
        with col2a:
            risk_display_over = f"{risk_ou['over']['risk_score']}/5 {risk_ou['over']['risk_text']}"
            st.metric(
                label=f"Over ({risk_ou['over']['probability']:.1f}%)",
                value=f"{risk_ou['over']['odds']:.2f}",
                delta=risk_display_over,
                delta_color="off"
            )
        with col2b:
            risk_display_under = f"{risk_ou['under']['risk_score']}/5 {risk_ou['under']['risk_text']}"
            st.metric(
                label=f"Under ({risk_ou['under']['probability']:.1f}%)",
                value=f"{risk_ou['under']['odds']:.2f}",
                delta=risk_display_under,
                delta_color="off"
            )

    with col3:
        st.markdown("**⚽ BTTS**")
        risk_btts = result['extended_risk']['btts']
        col3a, col3b = st.columns(2)
        with col3a:
            risk_display_yes = f"{risk_btts['yes']['risk_score']}/5 {risk_btts['yes']['risk_text']}"
            st.metric(
                label=f"Ja ({risk_btts['yes']['probability']:.1f}%)",
                value=f"{risk_btts['yes']['odds']:.2f}",
                delta=risk_display_yes,
                delta_color="off"
            )
        with col3b:
            risk_display_no = f"{risk_btts['no']['risk_score']}/5 {risk_btts['no']['risk_text']}"
            st.metric(
                label=f"Nein ({risk_btts['no']['probability']:.1f}%)",
                value=f"{risk_btts['no']['odds']:.2f}",
                delta=risk_display_no,
                delta_color="off"
            )

    # PHASE 1: STAKE-EMPFEHLUNGEN
    st.markdown("---")
    st.subheader("💰 EINSATZEMPFEHLUNGEN (basierend auf deiner Bankroll)")

    # Beste 1X2 Option
    best_1x2 = result['extended_risk']['1x2']
    display_stake_recommendation(
        risk_score=best_1x2['risk_score'],
        odds=best_1x2['odds'],
        market_name=best_1x2['market'],
        match_info=f"{result['match_info']['home']} vs {result['match_info']['away']} - {best_1x2['market']}"
    )

    # Beste Over/Under Option
    ou_risk = result['extended_risk']['over_under']
    best_ou = 'over' if ou_risk['over']['risk_score'] >= ou_risk['under']['risk_score'] else 'under'
    display_stake_recommendation(
        risk_score=ou_risk[best_ou]['risk_score'],
        odds=ou_risk[best_ou]['odds'],
        market_name=f"{best_ou.upper()} 2.5",
        match_info=f"{result['match_info']['home']} vs {result['match_info']['away']} - {best_ou.upper()} 2.5"
    )

    # Beste BTTS Option
    btts_risk = result['extended_risk']['btts']
    best_btts = 'yes' if btts_risk['yes']['risk_score'] >= btts_risk['no']['risk_score'] else 'no'
    display_stake_recommendation(
        risk_score=btts_risk[best_btts]['risk_score'],
        odds=btts_risk[best_btts]['odds'],
        market_name=f"BTTS {best_btts.upper()}",
        match_info=f"{result['match_info']['home']} vs {result['match_info']['away']} - BTTS {best_btts.upper()}"
    )

    with st.expander("📋 RISIKO-FAKTOREN DETAILS"):
        details = overall_risk['details']
        col1, col2, col3 = st.columns(3)
        col1.metric("μ-Total", f"{details['mu_total_impact']:.2f}")
        col2.metric("TKI kombiniert", f"{details['tki_impact']:.2f}")
        col3.metric("Beste 1X2 Wahrscheinlichkeit",
                    f"{details['favorite_prob']:.1f}%")
        col1.metric("PPG Differenz", f"{details['ppg_diff_abs']:.2f}")
        col2.metric("Durchschn. Risiko", f"{details['average_risk']:.2f}")
        col3.metric("Anpassungen", f"{details['adjustments']:.2f}")

    st.subheader("🧤 Torwart-Krisen-Index (TKI)")
    col1, col2, col3 = st.columns(3)
    with col1:
        tki_home = result['tki']['home']
        status_home = "🚨 KRISE" if tki_home > 0.3 else "✅ Stabil"
        st.metric(result['match_info']['home'], f"{tki_home:.2f}", status_home)
    with col2:
        tki_away = result['tki']['away']
        status_away = "🚨 KRISE" if tki_away > 0.3 else "✅ Stabil"
        st.metric(result['match_info']['away'], f"{tki_away:.2f}", status_away)
    with col3:
        st.metric("Kombiniert", f"{result['tki']['combined']:.2f}")

    st.subheader("🔄 Head-to-Head Statistik")
    h2h = result['h2h']
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ø Tore/Spiel", f"{h2h['avg_total_goals']:.1f}")
    col2.metric("Ø Heimtore", f"{h2h['avg_home_goals']:.1f}")
    col3.metric("Ø Auswärtstore", f"{h2h['avg_away_goals']:.1f}")
    col4.metric("BTTS-Quote", f"{h2h['btts_percentage'] * 100:.0f}%")

    st.caption(
        f"Bilanz: {h2h['home_wins']} Siege - {h2h['draws']} Remis - {h2h['away_wins']} Niederlagen")

    st.subheader("📈 Wahrscheinlichkeiten & Quoten")
    probs = result['probabilities']
    odds = result['odds']

    data = {
        'Markt': ['Heimsieg', 'Remis', 'Auswärtssieg', 'Over 2.5', 'Under 2.5', 'BTTS Ja', 'BTTS Nein'],
        'Wahrscheinlichkeit': [
            f"{probs['home_win']:.1f}%",
            f"{probs['draw']:.1f}%",
            f"{probs['away_win']:.1f}%",
            f"{probs['over_25']:.1f}%",
            f"{probs['under_25']:.1f}%",
            f"{probs['btts_yes']:.1f}%",
            f"{probs['btts_no']:.1f}%"
        ],
        'Quote': [
            f"{odds['1x2'][0]:.2f}",
            f"{odds['1x2'][1]:.2f}",
            f"{odds['1x2'][2]:.2f}",
            f"{odds['ou25'][0]:.2f}",
            f"{odds['ou25'][1]:.2f}",
            f"{odds['btts'][0]:.2f}",
            f"{odds['btts'][1]:.2f}"
        ]
    }

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.subheader("📊 Score-Vorhersage")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        best_1x2 = "Heimsieg" if probs['home_win'] >= probs['draw'] and probs['home_win'] >= probs[
            'away_win'] else "Unentschieden" if probs['draw'] >= probs['away_win'] else "Auswärtssieg"
        best_1x2_prob = max(probs['home_win'],
                            probs['draw'], probs['away_win'])
        st.info(f"**1X2**\n{best_1x2}\n**{best_1x2_prob:.1f}%**")

    with col2:
        best_ou = "Over 2.5" if probs['over_25'] >= probs['under_25'] else "Under 2.5"
        best_ou_prob = max(probs['over_25'], probs['under_25'])
        st.info(f"**Over/Under 2.5**\n{best_ou}\n**{best_ou_prob:.1f}%**")

    with col3:
        best_btts = "BTTS Ja" if probs['btts_yes'] >= probs['btts_no'] else "BTTS Nein"
        best_btts_prob = max(probs['btts_yes'], probs['btts_no'])
        st.info(f"**BTTS**\n{best_btts}\n**{best_btts_prob:.1f}%**")

    with col4:
        if result['scorelines']:
            st.success(
                f"**Ergebnis**\n{result['predicted_score']}\n**{result['scorelines'][0][1]:.1f}%**")

    st.markdown("---")
    st.subheader("📈 Visualisierungen")

    tab1, tab2 = st.tabs(["μ-Werte", "Risiko-Übersicht"])

    with tab1:
        fig_mu = go.Figure(data=[
            go.Bar(
                name='Erwartete Tore',
                x=[result['match_info']['home'], result['match_info']['away']],
                y=[result['mu']['home'], result['mu']['away']],
                marker_color=['#1f77b4', '#ff7f0e']
            )
        ])
        fig_mu.update_layout(
            title="Smart μ-Werte Vergleich",
            yaxis_title="Erwartete Tore",
            height=300
        )
        st.plotly_chart(fig_mu, use_container_width=True)

    with tab2:
        risk_categories = ['1X2', 'Over', 'Under', 'BTTS Ja', 'BTTS Nein']
        risk_scores = [
            result['extended_risk']['1x2']['risk_score'],
            result['extended_risk']['over_under']['over']['risk_score'],
            result['extended_risk']['over_under']['under']['risk_score'],
            result['extended_risk']['btts']['yes']['risk_score'],
            result['extended_risk']['btts']['no']['risk_score']
        ]

        colors = []
        for score in risk_scores:
            if score <= 2:
                colors.append('red')
            elif score == 3:
                colors.append('yellow')
            else:
                colors.append('green')

        fig_risk_overview = go.Figure(data=[
            go.Bar(
                x=risk_categories,
                y=risk_scores,
                marker_color=colors,
                text=[f"Score: {s}" for s in risk_scores],
                textposition='auto'
            )
        ])

        fig_risk_overview.update_layout(
            title="Risiko-Scores pro Wette (1-5)",
            yaxis_title="Risiko-Score",
            yaxis=dict(range=[0, 5.5]),
            height=350
        )
        st.plotly_chart(fig_risk_overview, use_container_width=True)


def display_risk_distribution(all_results):
    if not all_results:
        return

    scores = []
    for item in all_results:
        if 'result' in item and 'extended_risk' in item['result']:
            scores.append(item['result']['extended_risk']['overall']['score'])

    if not scores:
        return

    distribution = Counter(scores)
    total = len(scores)

    st.markdown("---")
    st.subheader("📈 Risiko-Score Verteilung")
    st.caption("Zeigt wie viele Matches jedem Risiko-Level zugeordnet wurden")

    cols = st.columns(5)
    colors = ['darkred', 'red', 'yellow', 'lightgreen', 'green']
    labels = ['1/5 Extrem', '2/5 Hoch',
        '3/5 Moderat', '4/5 Gering', '5/5 Optimal']

    for i in range(1, 6):
        count = distribution.get(i, 0)
        percentage = (count / total) * 100 if total > 0 else 0

        with cols[i - 1]:
            st.metric(
                label=labels[i - 1],
                value=f"{count}",
                delta=f"{percentage:.1f}%",
                delta_color="off"
            )
            st.progress(min(percentage / 100, 1.0))

    score_5_pct = (distribution.get(5, 0) / total * 100) if total > 0 else 0
    score_4_pct = (distribution.get(4, 0) / total * 100) if total > 0 else 0
    score_3_pct = (distribution.get(3, 0) / total * 100) if total > 0 else 0

    st.markdown("---")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### 📊 Verteilungs-Analyse")

        if score_5_pct > 10:
            st.warning(
                f"⚠️ **Zu viele 5/5 Bewertungen** ({score_5_pct:.1f}%) - Scoring könnte zu liberal sein!")
        elif score_5_pct < 1 and total > 20:
            st.info(
                f"ℹ️ Sehr wenige 5/5 Bewertungen ({score_5_pct:.1f}%) - Scoring ist sehr streng")
        elif score_5_pct >= 2 and score_5_pct <= 5:
            st.success(
                f"✅ Optimale 5/5 Verteilung ({score_5_pct:.1f}%) - Scoring funktioniert gut!")

        if score_3_pct > 75:
            st.info(
                "ℹ️ Sehr viele 3/5 Bewertungen - Die meisten Wetten sind moderat riskant")
        elif score_3_pct < 50:
            st.warning("⚠️ Wenige 3/5 Bewertungen - Ungewöhnliche Verteilung")

    with col2:
        st.markdown("### 🎯 Ziel-Verteilung")
        st.caption("""
        **Ideal:**
        - 5/5: 2-5%
        - 4/5: 10-15%
        - 3/5: 60-70%
        - 2/5: 15-20%
        - 1/5: 5-10%
        """)

# ==================== GOOGLE SHEETS PARSING FUNKTIONEN ====================


@st.cache_resource
def get_all_worksheets(sheet_url):
    try:
        service = connect_to_sheets(readonly=True)
        if service is None:
            return None
        spreadsheet_id = sheet_url.split('/d/')[1].split('/')[0]
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', [])
        return {sheet['properties']['title']
            : sheet['properties']['sheetId'] for sheet in sheets}
    except Exception as e:
        st.error(f"❌ Fehler: {e}")
        return None


@st.cache_data(ttl=300)
def read_worksheet_data(sheet_url, sheet_name):
    try:
        service = connect_to_sheets(readonly=True)
        if service is None:
            return None
        spreadsheet_id = sheet_url.split('/d/')[1].split('/')[0]
        range_name = f"'{sheet_name}'!A:Z"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_name).execute()
        data = result.get('values', [])
        text_data = []
        for row in data:
            if any(cell.strip() for cell in row if cell):
                text_data.append('\t'.join(row))
        return '\n'.join(text_data)
    except Exception as e:
        st.error(f"❌ Fehler: {e}")
        return None

@st.cache_resource
def get_all_worksheets_by_id(spreadsheet_id: str):
    """Wie get_all_worksheets(), aber bekommt direkt die spreadsheetId."""
    try:
        service = connect_to_sheets(readonly=True)
        if service is None:
            return None

        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()

        sheets = sheet_metadata.get('sheets', [])
        return {s['properties']['title']: s['properties']['sheetId'] for s in sheets}

    except Exception as e:
        st.error(f"❌ Fehler: {e}")
        return None


@st.cache_data(ttl=300)
def read_worksheet_text_by_id(spreadsheet_id: str, sheet_name: str) -> Optional[str]:
    """Wie read_worksheet_data(), aber spreadsheetId direkt + gibt Text für DataParser zurück."""
    try:
        service = connect_to_sheets(readonly=True)
        if service is None:
            return None

        range_name = f"'{sheet_name}'!A:Z"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()

        data = result.get('values', [])

        text_data = []
        for row in data:
            if any(cell.strip() for cell in row if cell):
                text_data.append('\t'.join(row))

        return '\n'.join(text_data)

    except Exception as e:
        st.error(f"❌ Fehler: {e}")
        return None


class DataParser:
    def __init__(self):
        self.lines = []

    def parse(self, text: str) -> MatchData:
        self.lines = [line.strip()
                                    for line in text.split('\n') if line.strip()]
        home_name, away_name = self._parse_match_details()
        date, competition, kickoff = self._parse_date_competition()
        home_overall = self._parse_team_overall(home_name)
        away_overall = self._parse_team_overall(away_name)
        home_form = self._parse_team_form(home_name)
        away_form = self._parse_team_form(away_name)
        home_ha = self._parse_team_ha(home_name, is_home=True)
        away_ha = self._parse_team_ha(away_name, is_home=False)
        h2h_results = self._parse_h2h(home_name, away_name)
        home_stats, away_stats = self._parse_statistics()
        odds_1x2, odds_ou25, odds_btts = self._parse_odds()
        home_team = self._create_team_stats(
            home_name, home_overall, home_form, home_ha, home_stats)
        away_team = self._create_team_stats(
            away_name, away_overall, away_form, away_ha, away_stats)
        return MatchData(
            home_team=home_team,
            away_team=away_team,
            h2h_results=h2h_results,
            date=date,
            competition=competition,
            kickoff=kickoff,
            odds_1x2=odds_1x2,
            odds_ou25=odds_ou25,
            odds_btts=odds_btts
        )

    def _find_line_with(self, text: str, start_from: int = 0) -> int:
        for i in range(start_from, len(self.lines)):
            if text.lower() in self.lines[i].lower():
                return i
        return -1

    def _parse_match_details(self) -> Tuple[str, str]:
        idx = self._find_line_with("heimteam")
        if idx == -1:
            raise ValueError("Heimteam nicht gefunden")
        idx += 1
        while idx < len(self.lines) and not self.lines[idx]:
            idx += 1
        teams_line = self.lines[idx]
        teams = [t.strip() for t in teams_line.split('\t') if t.strip()]
        if len(teams) >= 2:
            return teams[0], teams[1]
        teams = [t.strip()
                            for t in re.split(r'\s{2,}', teams_line) if t.strip()]
        return teams[0], teams[1]

    def _parse_date_competition(self) -> Tuple[str, str, str]:
        date_idx = self._find_line_with("datum:")
        date = self.lines[date_idx].split(
            ':', 1)[1].strip() if date_idx != -1 else ""
        comp_idx = self._find_line_with("wettbewerb:")
        competition = self.lines[comp_idx].split(
            ':', 1)[1].strip() if comp_idx != -1 else ""
        kick_idx = self._find_line_with("anstoß:")
        kickoff = self.lines[kick_idx].split(
            ':', 1)[1].strip() if kick_idx != -1 else ""
        return date, competition, kickoff

    def _parse_team_overall(self, team_name: str) -> Dict:
        for i, line in enumerate(self.lines):
            if team_name in line and 'tabellenposition' not in line.lower(
            ) and 'letzte 5' not in line.lower():
                parts = [p.strip() for p in line.split('\t') if p.strip()]
                if len(parts) >= 9:
                    goals = parts[6].split(':')
                    return {
                        'position': int(parts[1].replace('.', '')),
                        'games': int(parts[2]),
                        'wins': int(parts[3]),
                        'draws': int(parts[4]),
                        'losses': int(parts[5]),
                        'goals_for': int(goals[0]),
                        'goals_against': int(goals[1]),
                        'goal_diff': int(parts[7]),
                        'points': int(parts[8])
                    }
        return {}

    def _parse_team_form(self, team_name: str) -> Dict:
        idx = self._find_line_with(f"{team_name} letzte 5 spiele")
        if idx == -1:
            return {}
        line = self.lines[idx]
        parts = [p.strip() for p in line.split('\t') if p.strip()]
        if len(parts) >= 8:
            goals = parts[6].split(':')
            return {
                'points': int(parts[-1]),
                'goals_for': int(goals[0]),
                'goals_against': int(goals[1])
            }
        return {}

    def _parse_team_ha(self, team_name: str, is_home: bool) -> Dict:
        search_term = "heimspiele" if is_home else "auswärtsspiele"
        idx = self._find_line_with(f"{team_name} letzte 5 {search_term}")
        if idx == -1:
            return {}
        line = self.lines[idx]
        parts = [p.strip() for p in line.split('\t') if p.strip()]
        goals_for = 0
        goals_against = 0
        points = 0
        for part in parts:
            if ':' in part and re.match(r'\d+:\d+', part):
                goals = part.split(':')
                goals_for = int(goals[0])
                goals_against = int(goals[1])
            elif part.isdigit() and int(part) <= 15:
                points = int(part)
        return {
    'points': points,
    'goals_for': goals_for,
        'goals_against': goals_against}

    def _parse_h2h(self, home_name: str, away_name: str) -> List[H2HResult]:
        results = []
        idx = self._find_line_with("ergebnisse")
        if idx == -1:
            return results
        idx += 1
        while idx < len(self.lines):
            line = self.lines[idx]
            if any(
    marker in line.lower() for marker in [
        'statistische',
        'wettquoten',
        '1x2',
            'points per game']):
                break
            if re.search(r'\d+:\d+', line):
                parts = [p.strip() for p in line.split('\t') if p.strip()]
                if len(parts) >= 2:
                    date = parts[0]
                    match_str = parts[1]
                    match = re.search(r'(.+?)\s+(\d+):(\d+)\s+(.+)', match_str)
                    if match:
                        team1 = match.group(1).strip()
                        goals1 = int(match.group(2))
                        goals2 = int(match.group(3))
                        team2 = match.group(4).strip()
                        results.append(H2HResult(
                            date=date,
                            home_team=team1,
                            away_team=team2,
                            home_goals=goals1,
                            away_goals=goals2
                        ))
            idx += 1
        return results

    def _parse_statistics(self) -> Tuple[Dict, Dict]:
        home_stats = {}
        away_stats = {}
        idx = self._find_line_with("points per game overall")
        if idx == -1:
            return home_stats, away_stats
        stat_lines = []
        i = idx
        while i < len(self.lines):
            line = self.lines[i]
            if 'wettquoten' in line.lower() or '1x2' in line.lower():
                break
            if line and not line.startswith('*'):
                stat_lines.append(line)
            i += 1
        for line in stat_lines:
            parts = [p.strip() for p in line.split('\t') if p.strip()]
            if len(parts) >= 3:
                stat_name = parts[0].lower()
                try:
                    if 'points per game overall' in stat_name:
                        home_stats['ppg_overall'] = float(parts[1])
                        away_stats['ppg_overall'] = float(parts[2])
                    elif 'points per game home/away' in stat_name:
                        home_stats['ppg_ha'] = float(parts[1])
                        away_stats['ppg_ha'] = float(parts[2])
                    elif 'average goals scored/conceded per match overall' in stat_name:
                        if len(parts) >= 5:
                            home_stats['goals_scored_per_match'] = float(
                                parts[1])
                            home_stats['goals_conceded_per_match'] = float(
                                parts[2])
                            away_stats['goals_scored_per_match'] = float(
                                parts[3])
                            away_stats['goals_conceded_per_match'] = float(
                                parts[4])
                    elif 'average goals scored/conceded per match home/away' in stat_name:
                        if len(parts) >= 5:
                            home_stats['goals_scored_per_match_ha'] = float(
                                parts[1])
                            home_stats['goals_conceded_per_match_ha'] = float(
                                parts[2])
                            away_stats['goals_scored_per_match_ha'] = float(
                                parts[3])
                            away_stats['goals_conceded_per_match_ha'] = float(
                                parts[4])
                    elif 'xg overall' in stat_name.lower():
                        if len(parts) >= 5:
                            home_stats['xg_for'] = float(parts[1])
                            home_stats['xg_against'] = float(parts[2])
                            away_stats['xg_for'] = float(parts[3])
                            away_stats['xg_against'] = float(parts[4])
                    elif 'xg home/away' in stat_name.lower():
                        if len(parts) >= 5:
                            home_stats['xg_for_ha'] = float(parts[1])
                            home_stats['xg_against_ha'] = float(parts[2])
                            away_stats['xg_for_ha'] = float(parts[3])
                            away_stats['xg_against_ha'] = float(parts[4])
                    elif 'clean sheet yes/no overall' in stat_name:
                        if len(parts) >= 5:
                            home_stats['cs_yes_overall'] = float(
                                parts[1].replace('%', '')) / 100
                            away_stats['cs_yes_overall'] = float(
                                parts[3].replace('%', '')) / 100
                    elif 'clean sheet yes/no home/away' in stat_name:
                        if len(parts) >= 5:
                            home_stats['cs_yes_ha'] = float(
                                parts[1].replace('%', '')) / 100
                            away_stats['cs_yes_ha'] = float(
                                parts[3].replace('%', '')) / 100
                    elif 'failed to score yes/no home/away' in stat_name:
                        if len(parts) >= 5:
                            home_stats['fts_yes_ha'] = float(
                                parts[1].replace('%', '')) / 100
                            away_stats['fts_yes_ha'] = float(
                                parts[3].replace('%', '')) / 100
                    elif 'conversion rate' in stat_name.lower():
                        home_stats['conversion_rate'] = float(
                            parts[1].replace('%', '')) / 100
                        away_stats['conversion_rate'] = float(
                            parts[2].replace('%', '')) / 100
                except (ValueError, IndexError):
                    continue
        return home_stats, away_stats

    def _parse_odds(self) -> Tuple[Tuple[float, float, float],
                    Tuple[float, float], Tuple[float, float]]:
        odds_1x2 = (1.0, 1.0, 1.0)
        odds_ou25 = (1.0, 1.0)
        odds_btts = (1.0, 1.0)
        for line in self.lines:
            line_lower = line.lower()
            if '1x2' in line_lower:
                match = re.search(
                    r'([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)', line)
                if match:
                    odds_1x2 = (float(match.group(1)), float(
                        match.group(2)), float(match.group(3)))
            elif 'over/under 2' in line_lower:
                match = re.search(r'([\d.]+)\s*/\s*([\d.]+)', line)
                if match:
                    odds_ou25 = (float(match.group(1)), float(match.group(2)))
            elif 'btts' in line_lower and 'ja/nein' in line_lower:
                match = re.search(r'([\d.]+)\s*/\s*([\d.]+)', line)
                if match:
                    odds_btts = (float(match.group(1)), float(match.group(2)))
        return odds_1x2, odds_ou25, odds_btts

    def _create_team_stats(
    self,
    name: str,
    overall: Dict,
    form: Dict,
    ha: Dict,
        stats: Dict) -> TeamStats:
        return TeamStats(
            name=name,
            position=overall.get('position', 0),
            games=overall.get('games', 0),
            wins=overall.get('wins', 0),
            draws=overall.get('draws', 0),
            losses=overall.get('losses', 0),
            goals_for=overall.get('goals_for', 0),
            goals_against=overall.get('goals_against', 0),
            goal_diff=overall.get('goal_diff', 0),
            points=overall.get('points', 0),
            form_points=form.get('points', 0),
            form_goals_for=form.get('goals_for', 0),
            form_goals_against=form.get('goals_against', 0),
            ha_points=ha.get('points', 0),
            ha_goals_for=ha.get('goals_for', 0),
            ha_goals_against=ha.get('goals_against', 0),
            ppg_overall=stats.get('ppg_overall', 0.0),
            ppg_ha=stats.get('ppg_ha', 0.0),
            avg_goals_match=stats.get('avg_goals_match', 0.0),
            avg_goals_match_ha=stats.get('avg_goals_match_ha', 0.0),
            goals_scored_per_match=stats.get('goals_scored_per_match', 0.0),
            goals_conceded_per_match=stats.get(
                'goals_conceded_per_match', 0.0),
            goals_scored_per_match_ha=stats.get(
                'goals_scored_per_match_ha', 0.0),
            goals_conceded_per_match_ha=stats.get(
                'goals_conceded_per_match_ha', 0.0),
            btts_yes_overall=stats.get('btts_yes_overall', 0.0),
            btts_yes_ha=stats.get('btts_yes_ha', 0.0),
            cs_yes_overall=stats.get('cs_yes_overall', 0.0),
            cs_yes_ha=stats.get('cs_yes_ha', 0.0),
            fts_yes_overall=stats.get('fts_yes_overall', 0.0),
            fts_yes_ha=stats.get('fts_yes_ha', 0.0),
            xg_for=stats.get('xg_for', 0.0),
            xg_against=stats.get('xg_against', 0.0),
            xg_for_ha=stats.get('xg_for_ha', 0.0),
            xg_against_ha=stats.get('xg_against_ha', 0.0),
            shots_per_match=stats.get('shots_per_match', 0.0),
            shots_on_target=stats.get('shots_on_target', 0.0),
            conversion_rate=stats.get('conversion_rate', 0.0),
            possession=stats.get('possession', 0.0)
        )

# ==================== SIDEBAR ====================


def show_sidebar():
    with st.sidebar:
        st.header("⚙️ Einstellungen & Tools")

        # PHASE 1: RISIKO-MANAGEMENT
        st.markdown("---")
        st.subheader("💰 RISIKO-MANAGEMENT")

        bankroll = st.number_input(
            "Aktuelle Bankroll (€)",
            min_value=10.0,
            max_value=100000.0,
            value=st.session_state.risk_management['bankroll'],
            step=50.0,
            help="Dein aktuelles Wett-Kapital"
        )
        st.session_state.risk_management['bankroll'] = bankroll

        risk_profile = st.selectbox(
            "Dein Risikoprofil",
            options=list(RISK_PROFILES.keys()),
            format_func=lambda x: RISK_PROFILES[x]['name'],
            index=list(RISK_PROFILES.keys()).index(
                st.session_state.risk_management['risk_profile']),
            help="Wie risikobereit bist du?"
        )
        st.session_state.risk_management['risk_profile'] = risk_profile

        profile_info = RISK_PROFILES[risk_profile]
        st.caption(f"**{profile_info['description']}**")
        st.caption(
            f"Max. Einsatz: {profile_info['max_stake_percent']}% der Bankroll")

        # ========== ERGEBNISSE NACHTRAGEN ==========
        st.markdown("---")
        st.subheader("📝 Ergebnisse nachtragen")

        try:
            if "tracking" not in st.secrets:
                st.sidebar.warning("⚠️ Tracking nicht konfiguriert")
            else:
                sheet_id = get_tracking_sheet_id()
                if not sheet_id:
                    # Fallback auf alternative sheet_id Einträge
                    if "sheet_id_v48" in st.secrets["tracking"]:
                        sheet_id = st.secrets["tracking"]["sheet_id_v48"]
                    elif "sheet_id_v47" in st.secrets["tracking"]:
                        sheet_id = st.secrets["tracking"]["sheet_id_v47"]
                    else:
                        st.sidebar.warning(
                            "⚠️ Keine Google Sheets ID gefunden")
                        sheet_id = None

                if sheet_id:
                    service = connect_to_sheets(readonly=True)
                    if service:
                        # Lade PENDING Spiele
                        result = service.spreadsheets().values().get(
                            spreadsheetId=sheet_id,
                            range="PREDICTIONS!A:Q"
                        ).execute()

                        values = result.get('values', [])
                        pending_matches = []

                        for i, row in enumerate(values):
                            if i == 0:  # Header überspringen
                                continue

                            if len(row) > 16 and row[16] == "PENDING":
                                match_str = row[2] if len(row) > 2 else ""
                                date_str = row[0] if len(row) > 0 else ""
                                predicted_score = row[3] if len(
                                    row) > 3 else ""
                                risk_score = row[13] if len(
                                    row) > 13 else "N/A"

                                pending_matches.append({
                                    'match': match_str,
                                    'date': date_str,
                                    'predicted': predicted_score,
                                    'risk_score': risk_score,
                                    'row_index': i + 1
                                })

                        if pending_matches:
                            st.sidebar.info(
                                f"📋 **{len(pending_matches)}** ausstehende Ergebnisse")

                            match_options = [
                                f"{m['date']} - {m['match']}" for m in pending_matches]
                            selected_match = st.sidebar.selectbox(
                                "Wähle Spiel:",
                                options=match_options,
                                help="Wähle ein Spiel um das Ergebnis einzutragen",
                                key="pending_match_select"
                            )

                            if selected_match:
                                match_idx = match_options.index(selected_match)
                                match_info = pending_matches[match_idx]

                                with st.sidebar.expander("📊 Match Details", expanded=True):
                                    st.caption(
                                        f"**Vorhersage:** {match_info['predicted']}")
                                    st.caption(
                                        f"**Risiko-Score:** {match_info['risk_score']}")

                                    col1, col2 = st.columns(2)
                                    with col1:
                                        home_goals = st.number_input(
                                            "Heimtore",
                                            min_value=0,
                                            max_value=20,
                                            value=0,
                                            key="home_goals_input"
                                        )
                                    with col2:
                                        away_goals = st.number_input(
                                            "Auswärtstore",
                                            min_value=0,
                                            max_value=20,
                                            value=0,
                                            key="away_goals_input"
                                        )

                                    actual_score = f"{home_goals}:{away_goals}"

                                    # Berechne zusätzliche Statistiken
                                    goals_total = home_goals + away_goals
                                    btts = "Ja" if home_goals > 0 and away_goals > 0 else "Nein"
                                    over25 = "Ja" if goals_total > 2.5 else "Nein"

                                    st.caption(
                                        f"**Gesamt:** {goals_total} Tore")
                                    st.caption(f"**BTTS:** {btts}")
                                    st.caption(f"**Over 2.5:** {over25}")

                                if st.sidebar.button(
                                    f"✅ Ergebnis {actual_score} speichern",
                                    use_container_width=True,
                                    type="primary",
                                    key="save_result_btn"
                                ):
                                    with st.spinner("Speichere Ergebnis..."):
                                        success = update_match_result_in_sheets(
                                            match_info['match'], actual_score)
                                        if success:
                                            st.sidebar.success(
                                                f"✅ Ergebnis {actual_score} gespeichert!")
                                            st.balloons()
                                            st.rerun()
                                        else:
                                            st.sidebar.error(
                                                "❌ Fehler beim Speichern")
                        else:
                            st.sidebar.success("✅ Alle Ergebnisse eingetragen")

        except Exception as e:
            st.sidebar.error(f"❌ Fehler beim Laden: {str(e)[:100]}...")

        # ========== ERWEITERTE DATEN EINTRAGEN ==========
        show_extended_data_entry_ui()

        # ========== BANKROLL-STATISTIK ==========
        st.markdown("---")
        st.subheader("📈 Bankroll-Statistik")

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.metric(
                "Aktuelle Bankroll",
                f"€{bankroll:,.2f}",
                delta="0.0%"
            )

        with col_s2:
            # Berechne Performance aus gespeicherten Wetten
            if st.session_state.risk_management['stake_history']:
                last_10 = st.session_state.risk_management['stake_history'][-10:]
                profit = sum([h.get('profit', 0) for h in last_10])
                st.metric(
                    "Letzte 10 Wetten",
                    f"€{profit:+.2f}",
                    delta=f"{(profit / sum([h.get('stake', 1) for h in last_10]) * 100 if sum([h.get('stake', 1) for h in last_10]) > 0 else 0):+.1f}%"
                )
            else:
                st.metric(
                    "Letzte 10 Wetten",
                    "€0.00",
                    delta="0.0%"
                )

        if st.button("🔄 Bankroll auf €1.000 zurücksetzen",
                    use_container_width=True,
                    key="reset_bankroll",
                    help="Setzt deine Bankroll auf den Startwert zurück"):
            st.session_state.risk_management['bankroll'] = 1000.0
            st.session_state.risk_management['stake_history'] = []
            st.rerun()

        # ========== WETT-HISTORIE ANZEIGEN ==========
        if st.session_state.risk_management['stake_history']:
            with st.sidebar.expander("📋 Letzte Wetten", expanded=False):
                for i, wette in enumerate(
                    reversed(st.session_state.risk_management['stake_history'][-5:])):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        match_name = wette.get('match', 'Unbekannt')
                        st.caption(f"{match_name}")
                    with col2:
                        profit = wette.get('profit', 0)
                        color = "green" if profit > 0 else "red" if profit < 0 else "gray"
                        st.caption(
                            f"€{profit:+.2f}", help=f"Einsatz: €{wette.get('stake', 0):.2f}")

        # ========== GOOGLE SHEETS INFO ==========
        st.markdown("---")
        st.subheader("📊 Google Sheets Info")

        try:
            worksheets = get_all_worksheets(sheet_url)
            if worksheets:
                st.success("✅ Verbunden")
                st.caption(f"{len(worksheets)} Tabellenblätter")
                match_names = list(worksheets.keys()) if worksheets else []
                match_names_sorted = match_names  # bleibt in Sheet-Reihenfolge (so wie keys geliefert werden)

                # Zeige letzte Aktualisierung
                try:
                    service = connect_to_sheets(readonly=True)
                    if service:
                        result = service.spreadsheets().values().get(
                            spreadsheetId=spreadsheet_id,
                            range="PREDICTIONS!A:A"
                        ).execute()
                        row_count = len(result.get('values', [])
                                        ) - 1  # Minus Header
                        st.caption(f"{row_count} Vorhersagen gespeichert")
                except:
                    pass
            else:
                st.info("ℹ️ Bitte Google Sheets URL eingeben")
        except:
            st.info("ℹ️ Google Sheets Verbindung prüfen")

        # ========== ALARM-EINSTELLUNGEN ==========
        st.markdown("---")
        st.subheader("🔧 Alarm-Einstellungen")
        with st.expander("Alarm-Schwellenwerte anpassen", expanded=False):
            st.session_state.alert_thresholds['mu_total_high'] = st.slider(
                "μ-Total Alarm (torreich)",
                min_value=3.0, max_value=6.0, value=4.5, step=0.1,
                key="mu_total_slider"
            )
            st.session_state.alert_thresholds['tki_high'] = st.slider(
                "TKI Alarm (Torwart-Krise)",
                min_value=0.5, max_value=2.0, value=1.0, step=0.1,
                key="tki_slider"
            )
            st.session_state.alert_thresholds['ppg_diff_extreme'] = st.slider(
                "PPG Differenz Alarm (klarer Favorit)",
                min_value=0.5, max_value=3.0, value=1.5, step=0.1,
                key="ppg_slider"
            )

        # ========== QUICK ACTIONS ==========
        st.markdown("---")
        st.subheader("🔗 Quick Actions")

        col_qa1, col_qa2 = st.columns(2)
        with col_qa1:
            if st.button(
    "🔄 Cache leeren",
    key="clear_cache",
        use_container_width=True):
                st.cache_data.clear()
                st.cache_resource.clear()
                st.success("✅ Cache geleert!")
                st.rerun()

        with col_qa2:
            if st.button(
    "📊 ML neu laden",
    key="reload_ml",
        use_container_width=True):
                st.session_state.position_ml_model = None
                st.session_state.extended_ml_model = None
                st.success("✅ ML-Modelle zurückgesetzt!")
                st.rerun()

        # Demo-Modus Toggle
        st.markdown("---")
        st.subheader("🎮 Demo-Modus")

        demo_mode = st.toggle(
            "Demo-Modus aktivieren",
            value=st.session_state.get('enable_demo_mode', False),
            help="Aktiviert simulierte Wetten für Testzwecke"
        )
        st.session_state.enable_demo_mode = demo_mode

        if demo_mode:
            st.info("🎮 Demo-Modus aktiv - Wetten werden simuliert")

        # ========== WETT-STRATEGIE INFO ==========
        st.markdown("---")
        st.subheader("🎯 Wett-Strategie")

        with st.expander("📋 Empfohlene Vorgehensweise", expanded=False):
            st.markdown("""
            1. **Analysiere** ein Spiel im Tab "Match-Analyse"
            2. **Prüfe** das Risiko-Score (1-5)
            3. **Setze** gemäß Einsatzempfehlung
            4. **Trage** nach Spielende das Ergebnis nach
            5. **Trainiere** ML-Modell nach 30+ abgeschlossenen Spielen
            """)

        # ========== RISIKO-SCORING ERKLÄRUNG ==========
        with st.expander("ℹ️ Strenges Risiko-Scoring", expanded=False):
            st.markdown("""
            **🎯 NEUES STRENGES SYSTEM:**
            Weniger 5/5 Bewertungen, realistischere Einschätzung

            **1/5 - ☠️ EXTREM RISIKANT:**
            • EV < -15%
            • Vermeiden - sehr spekulativ
            • Nur 5-10% aller Matches

            **2/5 - ⚠️ HOHES RISIKO:**
            • EV -5% bis -15%
            • Nur für erfahrene Wettende
            • 15-20% aller Matches

            **3/5 - 📊 MODERATES RISIKO:**
            • EV -5% bis +10%
            • Standard-Wetten, normale Vorsicht
            • 60-70% aller Matches

            **4/5 - ✅ GERINGES RISIKO:**
            • EV +10% bis +20%
            • Gute Wettmöglichkeit
            • 10-15% aller Matches

            **5/5 - 🎯 OPTIMALES RISIKO:**
            • EV > +20% + hohe Dominanz
            • Seltene Top-Wetten (nur 2-5%)
            • Erhöhter Einsatz möglich
            """)

        # ========== SCHNELLSUCHE TIPPS ==========
        with st.expander("🔍 Schnellsuche Tipps", expanded=False):
            st.markdown("""
            **Suche nach:**
            • Teamnamen (z.B. "Bayern", "Real")
            • Ligen (z.B. "Bundesliga", "Premier")
            • Datum (z.B. "2024", "Samstag")
            • Kombinationen (z.B. "Bayern Bundesliga")
            """)

        # ========== VERSION INFO ==========
        st.markdown("---")
        st.caption("**Sportwetten-Prognose v4.7+**")
        st.caption("⚡ ML-Korrekturen aktiviert")
        st.caption("🎯 Strenges Risiko-Scoring 1-5")
        st.caption("💰 Bankroll-Management")

# ==================== HISTORISCHE DATEN HINZUFÜGEN UI ====================


def add_historical_match_ui():
    st.header("📚 Historische Daten hinzufügen")

    # NEU: Demo- und Test-Buttons
    st.markdown("---")
    st.subheader("🚀 Schnellstart für Tests")

    col_test1, col_test2, col_test3 = st.columns(3)

    with col_test1:
        if st.button("🧪 Demo-Daten erstellen",
                    use_container_width=True,
                    help="Erstellt 30 Demo-Matches für schnelles ML-Testing"):
            demo_matches = create_demo_historical_data()
            saved_count = 0

            with st.spinner("Speichere Demo-Daten..."):
                for match in demo_matches:
                    if save_historical_match(match):
                        saved_count += 1

            st.success(f"✅ {saved_count} Demo-Matches gespeichert!")
            st.balloons()

    with col_test2:
        if st.button("🔄 Aus PREDICTIONS erstellen",
                    use_container_width=True,
                    help="Konvertiert COMPLETED PREDICTIONS zu historischen Daten"):
            result = auto_create_historical_from_predictions()
            if result['success']:
                st.success(f"✅ {result['message']}")
            else:
                st.error(f"❌ {result['message']}")

    with col_test3:
        if st.button("🔍 Sheet prüfen",
                    use_container_width=True,
                    help="Prüft HISTORICAL_DATA Sheet"):
            check_historical_sheet()

    with st.expander("➕ Neues historisches Match", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            home_team = st.text_input("Heimteam", key="hist_home")
            home_position = st.number_input(
                "Tabellenposition Heim", min_value=1, max_value=20, value=1, key="hist_home_pos")
            home_points = st.number_input(
                "Punkte Heim", min_value=0, max_value=100, value=50, key="hist_home_pts")
            home_games = st.number_input(
                "Spiele Heim", min_value=1, max_value=38, value=20, key="hist_home_games")
            actual_home_goals = st.number_input(
                "Tatsächliche Tore Heim", min_value=0, max_value=10, value=2, key="hist_actual_home")

        with col2:
            away_team = st.text_input("Auswärtsteam", key="hist_away")
            away_position = st.number_input(
                "Tabellenposition Auswärts", min_value=1, max_value=20, value=10, key="hist_away_pos")
            away_points = st.number_input(
                "Punkte Auswärts", min_value=0, max_value=100, value=30, key="hist_away_pts")
            away_games = st.number_input(
                "Spiele Auswärts", min_value=1, max_value=38, value=20, key="hist_away_games")
            actual_away_goals = st.number_input(
                "Tatsächliche Tore Auswärts", min_value=0, max_value=10, value=1, key="hist_actual_away")

        match_date = st.date_input(
            "Spieldatum", value=datetime.now(), key="hist_date")
        competition = st.text_input(
            "Liga/Wettbewerb", value="Bundesliga", key="hist_comp")

        st.markdown("---")
        st.subheader("Vorhersage-Daten (für Korrektur-Berechnung)")

        col_pred1, col_pred2 = st.columns(2)
        with col_pred1:
            predicted_mu_home = st.number_input(
                "Vorhergesagtes μ Heim", min_value=0.0, max_value=5.0, value=1.8, step=0.1, key="pred_mu_home")
            predicted_mu_away = st.number_input(
                "Vorhergesagtes μ Auswärts", min_value=0.0, max_value=5.0, value=1.2, step=0.1, key="pred_mu_away")

        with col_pred2:
            # Berechne tatsächliche μ-Werte aus tatsächlichen Toren
            actual_mu_home = st.number_input("Tatsächliches μ Heim", min_value=0.0, max_value=5.0, value=float(
                actual_home_goals), step=0.1, key="actual_mu_home")
            actual_mu_away = st.number_input("Tatsächliches μ Auswärts", min_value=0.0, max_value=5.0, value=float(
                actual_away_goals), step=0.1, key="actual_mu_away")

        # Berechne Korrektur-Faktoren
        home_correction = actual_mu_home / \
            predicted_mu_home if predicted_mu_home > 0 else 1.0
        away_correction = actual_mu_away / \
            predicted_mu_away if predicted_mu_away > 0 else 1.0

        st.info(
            f"Korrektur-Faktoren: Heim ×{home_correction:.3f}, Auswärts ×{away_correction:.3f}")

        if st.button(
    "💾 Historisches Match speichern",
    type="primary",
    use_container_width=True,
        key="save_historical"):
            # Erstelle TeamStats-Objekte
            home_team_stats = TeamStats(
                name=home_team,
                position=home_position,
                games=home_games,
                points=home_points,
                wins=0, draws=0, losses=0,
                goals_for=0, goals_against=0, goal_diff=0,
                form_points=0, form_goals_for=0, form_goals_against=0,
                ha_points=0, ha_goals_for=0, ha_goals_against=0,
                ppg_overall=home_points / home_games if home_games > 0 else 0,
                ppg_ha=0,
                avg_goals_match=0,
                avg_goals_match_ha=0,
                goals_scored_per_match=0,
                goals_conceded_per_match=0,
                goals_scored_per_match_ha=0,
                goals_conceded_per_match_ha=0,
                btts_yes_overall=0,
                btts_yes_ha=0,
                cs_yes_overall=0,
                cs_yes_ha=0,
                fts_yes_overall=0,
                fts_yes_ha=0,
                xg_for=0,
                xg_against=0,
                xg_for_ha=0,
                xg_against_ha=0,
                shots_per_match=0,
                shots_on_target=0,
                conversion_rate=0,
                possession=0
            )

            away_team_stats = TeamStats(
                name=away_team,
                position=away_position,
                games=away_games,
                points=away_points,
                wins=0, draws=0, losses=0,
                goals_for=0, goals_against=0, goal_diff=0,
                form_points=0, form_goals_for=0, form_goals_against=0,
                ha_points=0, ha_goals_for=0, ha_goals_against=0,
                ppg_overall=away_points / away_games if away_games > 0 else 0,
                ppg_ha=0,
                avg_goals_match=0,
                avg_goals_match_ha=0,
                goals_scored_per_match=0,
                goals_conceded_per_match=0,
                goals_scored_per_match_ha=0,
                goals_conceded_per_match_ha=0,
                btts_yes_overall=0,
                btts_yes_ha=0,
                cs_yes_overall=0,
                cs_yes_ha=0,
                fts_yes_overall=0,
                fts_yes_ha=0,
                xg_for=0,
                xg_against=0,
                xg_for_ha=0,
                xg_against_ha=0,
                shots_per_match=0,
                shots_on_target=0,
                conversion_rate=0,
                possession=0
            )

            # Speichere in einer historischen Datenbank (Google Sheets)
            historical_match = {
                'home_team': home_team_stats,
                'away_team': away_team_stats,
                'date': match_date.strftime("%Y-%m-%d"),
                'predicted_mu_home': predicted_mu_home,
                'predicted_mu_away': predicted_mu_away,
                'actual_mu_home': actual_mu_home,
                'actual_mu_away': actual_mu_away,
                'actual_score': f"{actual_home_goals}:{actual_away_goals}",
                'competition': competition
            }

            # Speichere in Google Sheets
            success = save_historical_match(historical_match)
            if success:
                st.success(
                    f"✅ Historisches Match {home_team} vs {away_team} gespeichert!")
                st.balloons()
            else:
                st.error("❌ Fehler beim Speichern des historischen Matches")

    st.markdown("---")
    st.subheader("📥 Vorhandene Trainingsdaten")

    # Lade und zeige vorhandene Daten
    historical_matches = load_historical_matches_from_sheets()

    if historical_matches:
        st.success(f"✅ {len(historical_matches)} historische Matches geladen")

        # Erstelle Übersichtstabelle
        overview_data = []
        for match in historical_matches[:20]:  # Zeige nur die ersten 20
            overview_data.append({
                'Datum': match['date'],
                'Heim': match['home_team'].name,
                'Auswärts': match['away_team'].name,
                'Pos (H/A)': f"{match['home_team'].position}/{match['away_team'].position}",
                'Korrektur (H/A)': f"{match.get('home_correction', 1.0):.2f}/{match.get('away_correction', 1.0):.2f}",
                'Ergebnis': match.get('actual_score', 'N/A')
            })

        df = pd.DataFrame(overview_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        if len(historical_matches) > 20:
            st.caption(
                f"... und {len(historical_matches) - 20} weitere Matches")
    else:
        st.info("ℹ️ Noch keine Trainingsdaten vorhanden. Füge oben welche hinzu!")

# ==================== HAUPT-APP ====================


def main():
    st.title("⚽ SPORTWETTEN-PROGNOSEMODELL v4.7+")
    st.markdown(
        "### EXAKTE v4.7 SMART-PRECISION LOGIK mit **ERWEITERTEM RISIKO-SCORING (1-5)**")
    st.markdown(
        "**Neu:** Gesamt-Risiko 1-5 + individuelle Wetten-Risikos + Bankroll-Management + ML-Korrekturen")
    st.markdown("---")

    folder_id = st.secrets["prematch"]["folder_id"]
    date_to_sheet_id = list_daily_sheets_in_folder(folder_id)

    st.info(f"📅 Gefundene Tagesdateien: {len(date_to_sheet_id)}")

    if date_to_sheet_id:
        day = st.selectbox("Datum auswählen", sorted(date_to_sheet_id.keys()))
        matches = list_match_tabs_for_day(date_to_sheet_id[day])
        st.write("Matches:", matches)

    if matches:
        match_name = st.selectbox("Match auswählen", matches)
        st.write("Ausgewählt:", match_name)

    data = read_sheet_range(date_to_sheet_id[day], f"'{match_name}'!A1:Z200")
    st.write("Zeilen geladen:", len(data))
    if data:
        st.write(data[:5])


    # Tab-Layout für verschiedene Funktionen
    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 Match-Analyse", "🧠 ML-Training", "📚 Trainingsdaten", "📈 Statistiken"])

    with tab1:
        st.subheader("📊 Schritt 1: Google Sheets Datei")

        if not date_to_sheet_id:
            st.warning("⚠️ Keine Tagesdateien im Ordner gefunden.")
            st.stop()

        day_tab1 = st.selectbox("📅 Datum auswählen", sorted(date_to_sheet_id.keys()), key="day_select_tab1")
        spreadsheet_id = date_to_sheet_id[day_tab1]

        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

        st.info(f"📎 Tagesdatei: {day_tab1} — [Link]({sheet_url})")
    

        if sheet_url:
            st.markdown("---")
            st.subheader("📋 Schritt 2: Match auswählen")

            with st.spinner("📥 Lade Tabellenblätter..."):
                worksheets = get_all_worksheets(sheet_url)

            if worksheets:
                st.success(f"✅ {len(worksheets)} Matches gefunden!")

                st.markdown("**🔍 Match suchen:**")
                search_term = st.text_input(
                    "Suche nach Teamname oder Liga:",
                    placeholder="z.B. 'Bayern' oder 'Bundesliga'",
                    help="Suche nach Teamnamen oder Wettbewerben",
                    key="match_search"
                )

                if search_term:
                    filtered_worksheets = {
                        k: v for k, v in worksheets.items()
                        if search_term.lower() in k.lower()
                    }
                    st.info(
                        f"📋 {len(filtered_worksheets)} von {len(worksheets)} Matches passen zur Suche")
                else:
                    filtered_worksheets = worksheets

                col1, col2 = st.columns([3, 1])
                with col1:
                    if filtered_worksheets:
                        selected_worksheet = st.selectbox(
                            "Wähle Match:",
                            list(filtered_worksheets.keys()),
                            key="worksheet_select",
                            help="Wähle ein Match aus der gefilterten Liste"
                        )
                    else:
                        st.warning(
                            "Keine Matches gefunden, die der Suche entsprechen.")
                        selected_worksheet = None

                with col2:
                    st.markdown("**Oder analysiere alle:**")
                    analyze_all = st.checkbox(
                        "Alle Matches", key="analyze_all_check")
                    if search_term and analyze_all:
                        st.info(
                            f"⚠️ Suchfilter wird ignoriert, alle {len(worksheets)} Matches werden analysiert")

                if selected_worksheet and not analyze_all:
                    with st.expander("👁️ Daten-Vorschau"):
                        preview_data = read_worksheet_data(
                            sheet_url, selected_worksheet)
                        if preview_data:
                            st.text(preview_data[:800] + "\n...")

                st.markdown("---")
                st.subheader("⚙️ Schritt 3: Analyse")

                if analyze_all:
                    if st.button(
    "🔄 ALLE Matches analysieren",
    type="primary",
    use_container_width=True,
        key="analyze_all_btn"):
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        all_results = []
                        failed_matches = []

                        for i, (sheet_name, _) in enumerate(
                            worksheets.items()):
                            status_text.text(
                                f"📊 Analysiere {sheet_name}... ({i + 1}/{len(worksheets)})")
                            progress_bar.progress((i + 1) / len(worksheets))

                            match_data = read_worksheet_data(
                                sheet_url, sheet_name)
                            if match_data:
                                try:
                                    parser = DataParser()
                                    match = parser.parse(match_data)

                                    is_valid, missing_fields = validate_match_data(
                                        match)

                                    if not is_valid:
                                        failed_matches.append({
                                            'sheet_name': sheet_name,
                                            'missing_count': len(missing_fields),
                                            'missing_fields': missing_fields
                                        })
                                    else:
                                        result = analyze_match_v47_ml(match)
                                        all_results.append(
                                            {'sheet_name': sheet_name, 'result': result})

                                except Exception as e:
                                    failed_matches.append({
                                        'sheet_name': sheet_name,
                                        'missing_count': 0,
                                        'missing_fields': [f"Parsing-Fehler: {str(e)}"]
                                    })

                        status_text.text("✅ Alle Analysen abgeschlossen!")
                        progress_bar.empty()

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("✅ Erfolgreich analysiert",
                                        len(all_results))
                        with col2:
                            st.metric("⚠️ Fehlende Daten", len(failed_matches))
                        with col3:
                            st.metric("📊 Gesamt", len(worksheets))

                        if failed_matches:
                            st.markdown("---")
                            st.warning(
                                f"⚠️ **{len(failed_matches)} Matches konnten nicht analysiert werden (fehlende Daten)**")

                            with st.expander(f"📋 Details zu {len(failed_matches)} übersprungenen Matches"):
                                for failed in failed_matches:
                                    st.markdown(
                                        f"### 🚫 {failed['sheet_name']}")
                                    if failed['missing_count'] > 0:
                                        st.caption(
                                            f"Fehlende Datenpunkte: **{failed['missing_count']}**")

                                        fields_to_show = failed['missing_fields'][:10]
                                        for field in fields_to_show:
                                            st.markdown(f"- {field}")

                                        if len(failed['missing_fields']) > 10:
                                            st.caption(
                                                f"... und {len(failed['missing_fields']) - 10} weitere")
                                    else:
                                        st.markdown(
                                            f"- {failed['missing_fields'][0]}")

                                    st.markdown("---")

                        if all_results:
                            st.markdown("---")
                            st.header("📊 ÜBERSICHT ALLER ANALYSIERTEN MATCHES")

                            overview_data = []
                            for item in all_results:
                                r = item['result']
                                risk = r['extended_risk']['overall']

                                overview_data.append({
                                    'Match': f"{r['match_info']['home']} vs {r['match_info']['away']}",
                                    'μ_Total': f"{r['mu']['total']:.2f}",
                                    'Gesamt-Risiko': risk['score_text'],
                                    '1X2 Risiko': r['extended_risk']['1x2']['risk_text'],
                                    'Over 2.5': f"{r['probabilities']['over_25']:.1f}%",
                                    'BTTS Ja': f"{r['probabilities']['btts_yes']:.1f}%",
                                    'Vorhersage': r['predicted_score']
                                })

                            df_overview = pd.DataFrame(overview_data)
                            st.dataframe(
                                df_overview, use_container_width=True, hide_index=True)

                            display_risk_distribution(all_results)

                            st.markdown("---")
                            st.header("📋 DETAILLIERTE ANALYSEN")
                            for item in all_results:
                                with st.expander(f"🎯 {item['sheet_name']} - {item['result']['predicted_score']}", expanded=False):
                                    display_results(item['result'])
                        else:
                            st.error(
                                "❌ Keine Matches konnten erfolgreich analysiert werden. Alle haben fehlende Daten.")

                # Single Worksheet Analysis (moved here to be inside if worksheets block)
                if selected_worksheet and not analyze_all:
                    if st.button(f"🔄 '{selected_worksheet}' analysieren", type="primary", use_container_width=True,
                                key=f"analyze_single_{selected_worksheet}"):
                        with st.spinner(f"⚙️ Analysiere {selected_worksheet}..."):
                            match_data = read_worksheet_data(sheet_url, selected_worksheet)

                            if match_data:
                                try:
                                    parser = DataParser()
                                    match = parser.parse(match_data)

                                    # NEU: Speichere Match im session_state
                                    st.session_state.current_match = match
                                    st.session_state.current_match_name = selected_worksheet

                                    is_valid, missing_fields = validate_match_data(match)

                                    if not is_valid:
                                        st.error("⚠️ **FEHLENDE DATENPUNKTE ERKANNT!**")
                                        st.warning(
                                            f"Es fehlen **{len(missing_fields)}** kritische Datenpunkte. Analyse kann nicht durchgeführt werden.")

                                        st.markdown("### 📋 Folgende Daten fehlen:")

                                        heim_missing = [
                                            f for f in missing_fields if f.startswith("HEIM:")]
                                        away_missing = [
                                            f for f in missing_fields if f.startswith("AUSWÄRTS:")]
                                        other_missing = [f for f in missing_fields if not (
                                            f.startswith("HEIM:") or f.startswith("AUSWÄRTS:"))]

                                        if heim_missing:
                                            st.markdown("#### 🏠 Heimteam:")
                                            for field in heim_missing:
                                                st.markdown(f"- {field.replace('HEIM: ', '')}")

                                        if away_missing:
                                            st.markdown("#### ✈️ Auswärtsteam:")
                                            for field in away_missing:
                                                st.markdown(
                                                    f"- {field.replace('AUSWÄRTS: ', '')}")

                                        if other_missing:
                                            st.markdown("#### ⚽ Match-Informationen:")
                                            for field in other_missing:
                                                st.markdown(f"- {field}")

                                        st.info(
                                            "💡 **Tipp:** Überprüfe deinen Scraper und stelle sicher, dass alle Daten korrekt in Google Sheets eingetragen wurden.")

                                    else:
                                        result = analyze_match_v47_ml(match)
                                        # NEU: Speichere auch das Ergebnis
                                        st.session_state.current_result = result

                                        st.success("✅ Analyse abgeschlossen!")
                                        st.markdown("---")
                                        display_results(result)

                                except Exception as e:
                                    st.error(f"❌ Fehler bei der Analyse: {e}")
                                    st.info("Stelle sicher, dass die Tabellendaten korrekt formatiert sind.")

                # Ergebnis für historische Daten (stabil über Reruns)
                if 'current_result' in st.session_state and 'current_match' in st.session_state:
                    st.markdown('---')
                    st.subheader('📊 Ergebnis für historische Daten eintragen')
                    st.info('💡 **Spiel bereits beendet?** Trage hier das Ergebnis ein für ML-Training.')

                    with st.form('historical_result_form'):
                        col_res1, col_res2 = st.columns(2)
                        with col_res1:
                            actual_home = st.number_input(
                                f"**{st.session_state.current_result['match_info']['home']}** Tore",
                                min_value=0,
                                max_value=20,
                                value=0,
                            )
                        with col_res2:
                            actual_away = st.number_input(
                                f"**{st.session_state.current_result['match_info']['away']}** Tore",
                                min_value=0,
                                max_value=20,
                                value=0,
                            )

                        submitted = st.form_submit_button(
                            '💾 Mit Ergebnis in HISTORICAL_DATA speichern',
                            use_container_width=True,
                        )

                    if submitted:
                        match_obj = st.session_state.current_match
                        predicted_mu_home = st.session_state.current_result['mu']['home']
                        predicted_mu_away = st.session_state.current_result['mu']['away']

                        success = save_historical_directly(
                            match_data=match_obj,
                            actual_home_goals=int(actual_home),
                            actual_away_goals=int(actual_away),
                            predicted_mu_home=predicted_mu_home,
                            predicted_mu_away=predicted_mu_away,
                        )

                        if success:
                            st.balloons()
                            # Aufräumen, um Konflikte zu vermeiden
                            st.session_state.pop('current_match', None)
                            st.session_state.pop('current_result', None)
                            st.session_state.pop('current_match_name', None)
                            st.rerun()


    with tab2:
        show_ml_training_ui()

    with tab3:
        add_historical_match_ui()

    with tab4:
        st.header("📈 Statistiken & Analysen")

        # Lade alle historischen Daten
        historical_matches = load_historical_matches_from_sheets()
        
        if historical_matches:
            st.success(f"📊 {len(historical_matches)} historische Matches gefunden")
            
            # Basis-Statistiken
            col1, col2, col3 = st.columns(3)
            with col1:
                avg_home_correction = np.mean([m.get('home_correction', 1.0) for m in historical_matches])
                st.metric("Ø Heim-Korrektur", f"{avg_home_correction:.3f}")
            
            with col2:
                avg_away_correction = np.mean([m.get('away_correction', 1.0) for m in historical_matches])
                st.metric("Ø Auswärts-Korrektur", f"{avg_away_correction:.3f}")
            
            with col3:
                avg_correction_diff = np.mean([abs(m.get('home_correction', 1.0) - m.get('away_correction', 1.0)) for m in historical_matches])
                st.metric("Ø Korrektur-Differenz", f"{avg_correction_diff:.3f}")
            
            # Visualisierung der Korrektur-Faktoren
            st.markdown("---")
            st.subheader("📈 Korrektur-Faktoren Verteilung")
            
            home_corrections = [m.get('home_correction', 1.0) for m in historical_matches]
            away_corrections = [m.get('away_correction', 1.0) for m in historical_matches]
            
            fig_corrections = go.Figure()
            fig_corrections.add_trace(go.Histogram(
                x=home_corrections,
                name='Heim-Korrekturen',
                marker_color='#1f77b4',
                opacity=0.7
            ))
            fig_corrections.add_trace(go.Histogram(
                x=away_corrections,
                name='Auswärts-Korrekturen',
                marker_color='#ff7f0e',
                opacity=0.7
            ))
            
            fig_corrections.update_layout(
                title="Verteilung der ML-Korrektur-Faktoren",
                xaxis_title="Korrektur-Faktor",
                yaxis_title="Anzahl",
                barmode='overlay',
                height=400
            )
            st.plotly_chart(fig_corrections, use_container_width=True)
            
            # Position vs. Korrektur Analyse
            st.markdown("---")
            st.subheader("🎯 Position vs. Korrektur-Analyse")
            
            home_positions = [m['home_team'].position for m in historical_matches]
            home_corrections = [m.get('home_correction', 1.0) for m in historical_matches]
            
            fig_position_correction = go.Figure(data=go.Scatter(
                x=home_positions,
                y=home_corrections,
                mode='markers',
                marker=dict(
                    size=10,
                    color=home_corrections,
                    colorscale='RdYlGn',
                    showscale=True,
                    colorbar=dict(title="Korrektur")
                ),
                text=[f"Heim: {m['home_team'].name}<br>Pos: {m['home_team'].position}<br>Korrektur: {m.get('home_correction', 1.0):.3f}" 
                        for m in historical_matches],
                hoverinfo='text'
            ))
            
            fig_position_correction.update_layout(
                title="Tabellenposition vs. ML-Korrektur (Heim)",
                xaxis_title="Tabellenposition (1 = Beste)",
                yaxis_title="Korrektur-Faktor",
                height=400
            )
            st.plotly_chart(fig_position_correction, use_container_width=True)
            
        else:
            st.info("ℹ️ Noch keine statistischen Daten verfügbar.")
            st.caption("""
            **Statistiken werden verfügbar, sobald:**
            1. Historische Daten hinzugefügt wurden (Tab "Trainingsdaten")
            2. Oder Spiele analysiert und Ergebnisse nachgetragen wurden
            3. ML-Modell trainiert wurde
            """)
    
    # Sidebar anzeigen
    show_sidebar()

# ==================== NEUE FUNKTIONEN FÜR HISTORICAL_DATA ====================

def auto_create_historical_from_predictions():
    """Erstellt automatisch historische Daten aus COMPLETED PREDICTIONS"""
    try:
        if "tracking" not in st.secrets:
            return {"success": False, "message": "Tracking nicht konfiguriert"}
        
        sheet_id = get_tracking_sheet_id()
        if not sheet_id:
            return {"success": False, "message": "sheet_id nicht gefunden"}
        
        service = connect_to_sheets(readonly=True)
        if service is None:
            return {"success": False, "message": "Keine Verbindung zu Google Sheets"}
        
        # Lade COMPLETED Spiele aus PREDICTIONS
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="PREDICTIONS!A:W"
        ).execute()
        
        values = result.get('values', [])
        if len(values) <= 1:
            return {"success": False, "message": "Keine PREDICTIONS Daten gefunden"}
        
        completed_matches = []
        headers = values[0] if values else []
        
        # Finde Spalten-Indizes
        col_indices = {}
        for i, header in enumerate(headers):
            col_indices[header] = i
        
        for i, row in enumerate(values):
            if i == 0:  # Header überspringen
                continue
            
            # Prüfe ob COMPLETED
            status_col = col_indices.get('Status', 16)  # Standard: Spalte Q
            if len(row) > status_col and row[status_col] == "COMPLETED":
                match_info = {
                    'timestamp': row[col_indices.get('Timestamp', 0)] if len(row) > col_indices.get('Timestamp', 0) else "",
                    'match': row[col_indices.get('Match', 2)] if len(row) > col_indices.get('Match', 2) else "",
                    'predicted_score': row[col_indices.get('Predicted_Score', 3)] if len(row) > col_indices.get('Predicted_Score', 3) else "",
                    'actual_score': row[col_indices.get('Actual_Score', 17)] if len(row) > col_indices.get('Actual_Score', 17) else "",
                    'mu_total': float(row[col_indices.get('μ_Total', 15)]) if len(row) > col_indices.get('μ_Total', 15) and row[col_indices.get('μ_Total', 15)] else 0.0
                }
                completed_matches.append(match_info)
        
        if not completed_matches:
            return {"success": False, "message": "Keine COMPLETED Spiele gefunden"}
        
        # Konvertiere zu historischen Daten
        historical_matches_created = 0
        
        for match in completed_matches:
            try:
                # Extrahiere Teamnamen aus Match-String
                match_str = match['match']
                if ' vs ' in match_str:
                    home_name, away_name = match_str.split(' vs ')
                else:
                    home_name = "Heim"
                    away_name = "Auswärts"
                
                # Extrahiere tatsächliche Tore
                actual_score = match['actual_score']
                if ':' in actual_score:
                    home_goals, away_goals = map(int, actual_score.split(':'))
                else:
                    home_goals, away_goals = 0, 0
                
                # Erstelle vereinfachte TeamStats (für Demo)
                home_team = TeamStats(
                    name=home_name,
                    position=10,  # Beispielposition
                    games=20,
                    points=30,
                    wins=0, draws=0, losses=0,
                    goals_for=0, goals_against=0, goal_diff=0,
                    form_points=0, form_goals_for=0, form_goals_against=0,
                    ha_points=0, ha_goals_for=0, ha_goals_against=0,
                    ppg_overall=1.5,
                    ppg_ha=0,
                    avg_goals_match=0,
                    avg_goals_match_ha=0,
                    goals_scored_per_match=0,
                    goals_conceded_per_match=0,
                    goals_scored_per_match_ha=0,
                    goals_conceded_per_match_ha=0,
                    btts_yes_overall=0,
                    btts_yes_ha=0,
                    cs_yes_overall=0,
                    cs_yes_ha=0,
                    fts_yes_overall=0,
                    fts_yes_ha=0,
                    xg_for=0,
                    xg_against=0,
                    xg_for_ha=0,
                    xg_against_ha=0,
                    shots_per_match=0,
                    shots_on_target=0,
                    conversion_rate=0,
                    possession=0
                )
                
                away_team = TeamStats(
                    name=away_name,
                    position=15,  # Beispielposition
                    games=20,
                    points=25,
                    wins=0, draws=0, losses=0,
                    goals_for=0, goals_against=0, goal_diff=0,
                    form_points=0, form_goals_for=0, form_goals_against=0,
                    ha_points=0, ha_goals_for=0, ha_goals_against=0,
                    ppg_overall=1.25,
                    ppg_ha=0,
                    avg_goals_match=0,
                    avg_goals_match_ha=0,
                    goals_scored_per_match=0,
                    goals_conceded_per_match=0,
                    goals_scored_per_match_ha=0,
                    goals_conceded_per_match_ha=0,
                    btts_yes_overall=0,
                    btts_yes_ha=0,
                    cs_yes_overall=0,
                    cs_yes_ha=0,
                    fts_yes_overall=0,
                    fts_yes_ha=0,
                    xg_for=0,
                    xg_against=0,
                    xg_for_ha=0,
                    xg_against_ha=0,
                    shots_per_match=0,
                    shots_on_target=0,
                    conversion_rate=0,
                    possession=0
                )
                
                # Schätze μ-Werte (vereinfacht)
                predicted_mu_home = 1.8
                predicted_mu_away = 1.2
                
                historical_match = {
                    'home_team': home_team,
                    'away_team': away_team,
                    'date': match['timestamp'].split(' ')[0] if ' ' in match['timestamp'] else datetime.now().strftime("%Y-%m-%d"),
                    'predicted_mu_home': predicted_mu_home,
                    'predicted_mu_away': predicted_mu_away,
                    'actual_mu_home': float(home_goals),
                    'actual_mu_away': float(away_goals),
                    'actual_score': actual_score,
                    'competition': 'Auto-generiert'
                }
                
                # Speichere historisches Match
                if save_historical_match(historical_match):
                    historical_matches_created += 1
                    
            except Exception as e:
                continue
        
        return {
            "success": True,
            "message": f"{historical_matches_created} historische Matches aus PREDICTIONS erstellt",
            "created": historical_matches_created
        }
        
    except Exception as e:
        return {"success": False, "message": f"Fehler: {str(e)}"}

def check_historical_sheet():
    """Prüft ob HISTORICAL_DATA Sheet existiert und zeigt Status"""
    try:
        if "tracking" not in st.secrets:
            st.error("⚠️ Tracking nicht konfiguriert")
            return
        
        sheet_id = get_tracking_sheet_id()
        if not sheet_id:
            st.error("❌ Keine Google Sheets ID gefunden (sheet_id / sheet_id_v48 / sheet_id_v47)")
            return
        
        service = connect_to_sheets(readonly=True)
        if service is None:
            st.error("❌ Keine Verbindung zu Google Sheets")
            return
        
        # Hole alle Sheets
        spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheets = spreadsheet.get('sheets', [])
        
        sheet_names = [sheet['properties']['title'] for sheet in sheets]
        
        if "HISTORICAL_DATA" in sheet_names:
            # Prüfe ob Daten vorhanden sind
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="HISTORICAL_DATA!A:A"
            ).execute()
            
            values = result.get('values', [])
            row_count = len(values)
            
            st.success(f"✅ HISTORICAL_DATA Sheet existiert")
            st.info(f"📊 Enthält {row_count - 1 if row_count > 0 else 0} Datensätze (mit Header)")
            
            if row_count > 1:
                # Zeige letzte 5 Einträge
                st.subheader("📋 Letzte 5 Einträge:")
                last_rows = values[-5:] if len(values) > 5 else values[1:]
                for row in last_rows:
                    if len(row) >= 4:
                        st.caption(f"{row[0]} - {row[2]} vs {row[3]}")
        else:
            st.warning("⚠️ HISTORICAL_DATA Sheet existiert NICHT")
            st.info("Das Sheet wird automatisch erstellt, wenn du das erste historische Match speicherst.")
            
    except Exception as e:
        st.error(f"❌ Fehler beim Prüfen: {str(e)}")

def create_demo_historical_data():
    """Erstellt Demo-Daten für schnelles Testen"""
    import random
    demo_matches = []
    
    # Erstelle 30 Demo-Matches
    for i in range(30):
        home_pos = (i % 18) + 1
        away_pos = ((i + 5) % 18) + 1
        
        home_team = TeamStats(
            name=f"Demo_Heim_{i+1}",
            position=home_pos,
            games=20 + (i % 5),
            points=30 + (i * 2),
            wins=0, draws=0, losses=0,
            goals_for=0, goals_against=0, goal_diff=0,
            form_points=0, form_goals_for=0, form_goals_against=0,
            ha_points=0, ha_goals_for=0, ha_goals_against=0,
            ppg_overall=1.5 + (i * 0.05),
            ppg_ha=0,
            avg_goals_match=0,
            avg_goals_match_ha=0,
            goals_scored_per_match=0,
            goals_conceded_per_match=0,
            goals_scored_per_match_ha=0,
            goals_conceded_per_match_ha=0,
            btts_yes_overall=0,
            btts_yes_ha=0,
            cs_yes_overall=0,
            cs_yes_ha=0,
            fts_yes_overall=0,
            fts_yes_ha=0,
            xg_for=0,
            xg_against=0,
            xg_for_ha=0,
            xg_against_ha=0,
            shots_per_match=0,
            shots_on_target=0,
            conversion_rate=0,
            possession=0
        )
        
        away_team = TeamStats(
            name=f"Demo_Auswärts_{i+1}",
            position=away_pos,
            games=20 + (i % 3),
            points=25 + i,
            wins=0, draws=0, losses=0,
            goals_for=0, goals_against=0, goal_diff=0,
            form_points=0, form_goals_for=0, form_goals_against=0,
            ha_points=0, ha_goals_for=0, ha_goals_against=0,
            ppg_overall=1.25 + (i * 0.03),
            ppg_ha=0,
            avg_goals_match=0,
            avg_goals_match_ha=0,
            goals_scored_per_match=0,
            goals_conceded_per_match=0,
            goals_scored_per_match_ha=0,
            goals_conceded_per_match_ha=0,
            btts_yes_overall=0,
            btts_yes_ha=0,
            cs_yes_overall=0,
            cs_yes_ha=0,
            fts_yes_overall=0,
            fts_yes_ha=0,
            xg_for=0,
            xg_against=0,
            xg_for_ha=0,
            xg_against_ha=0,
            shots_per_match=0,
            shots_on_target=0,
            conversion_rate=0,
            possession=0
        )
        
        # Realistische μ-Werte
        predicted_mu_home = 1.6 + (i * 0.02)
        predicted_mu_away = 1.1 + (i * 0.015)
        
        # Zufällige tatsächliche Tore (0-4)
        home_goals = random.randint(0, 4)
        away_goals = random.randint(0, 3)
        
        demo_match = {
            'home_team': home_team,
            'away_team': away_team,
            'date': f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
            'predicted_mu_home': predicted_mu_home,
            'predicted_mu_away': predicted_mu_away,
            'actual_mu_home': float(home_goals),
            'actual_mu_away': float(away_goals),
            'actual_score': f"{home_goals}:{away_goals}",
            'competition': 'Demo-Liga'
        }
        
        demo_matches.append(demo_match)
    
    return demo_matches

if __name__ == "__main__":
    main()