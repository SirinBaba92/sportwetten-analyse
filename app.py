import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
import plotly.graph_objects as go
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple
import math
from datetime import datetime
import os

st.set_page_config(page_title="Sportwetten-Prognose v4.11 OPTIMIZED", page_icon="⚽", layout="wide")

# Session State initialisieren
if 'alert_thresholds' not in st.session_state:
    st.session_state.alert_thresholds = {
        'mu_total_high': 4.5,
        'tki_high': 1.0,
        'ppg_diff_extreme': 1.5
    }

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

# ==================== DATEN-VALIDIERUNG ====================
def validate_match_data(match: MatchData) -> Tuple[bool, List[str]]:
    """
    Überprüft ob alle kritischen Datenpunkte vorhanden sind.
    Returns: (is_valid, list_of_missing_fields)
    """
    missing_fields = []
    
    def check_team_data(team: TeamStats, team_name: str):
        """Überprüft alle Datenpunkte eines Teams"""
        team_missing = []
        
        # Team-Name (WICHTIG!)
        if not team.name or team.name.strip() == "":
            team_missing.append(f"{team_name}: Team-Name")
        
        # Basis-Statistiken
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
        
        # Tore & Punkte
        if team.goals_for is None:
            team_missing.append(f"{team_name}: Tore geschossen")
        if team.goals_against is None:
            team_missing.append(f"{team_name}: Tore kassiert")
        if team.goal_diff is None:
            team_missing.append(f"{team_name}: Tordifferenz")
        if team.points is None:
            team_missing.append(f"{team_name}: Punkte")
        
        # Form-Daten (letzte 5 Spiele)
        if team.form_points is None:
            team_missing.append(f"{team_name}: Form-Punkte (L5)")
        if team.form_goals_for is None:
            team_missing.append(f"{team_name}: Form-Tore geschossen (L5)")
        if team.form_goals_against is None:
            team_missing.append(f"{team_name}: Form-Tore kassiert (L5)")
        
        # Heim/Auswärts-Statistiken
        if team.ha_points is None:
            team_missing.append(f"{team_name}: Heim/Auswärts-Punkte")
        if team.ha_goals_for is None:
            team_missing.append(f"{team_name}: H/A Tore geschossen")
        if team.ha_goals_against is None:
            team_missing.append(f"{team_name}: H/A Tore kassiert")
        
        # Durchschnittswerte (PPG, Goals per Match)
        if team.ppg_overall is None or team.ppg_overall < 0:
            team_missing.append(f"{team_name}: PPG Overall")
        if team.ppg_ha is None or team.ppg_ha < 0:
            team_missing.append(f"{team_name}: PPG Heim/Auswärts")
        if team.avg_goals_match is None or team.avg_goals_match < 0:
            team_missing.append(f"{team_name}: Ø Tore pro Spiel")
        if team.avg_goals_match_ha is None or team.avg_goals_match_ha < 0:
            team_missing.append(f"{team_name}: Ø Tore H/A")
        
        # Goals scored/conceded per match
        if team.goals_scored_per_match is None or team.goals_scored_per_match < 0:
            team_missing.append(f"{team_name}: Tore geschossen/Spiel")
        if team.goals_conceded_per_match is None or team.goals_conceded_per_match < 0:
            team_missing.append(f"{team_name}: Tore kassiert/Spiel")
        if team.goals_scored_per_match_ha is None or team.goals_scored_per_match_ha < 0:
            team_missing.append(f"{team_name}: Tore geschossen/Spiel H/A")
        if team.goals_conceded_per_match_ha is None or team.goals_conceded_per_match_ha < 0:
            team_missing.append(f"{team_name}: Tore kassiert/Spiel H/A")
        
        # BTTS, CS, FTS Prozentsätze
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
        
        # xG-Werte (Expected Goals)
        if team.xg_for is None or team.xg_for < 0:
            team_missing.append(f"{team_name}: xG For")
        if team.xg_against is None or team.xg_against < 0:
            team_missing.append(f"{team_name}: xG Against")
        if team.xg_for_ha is None or team.xg_for_ha < 0:
            team_missing.append(f"{team_name}: xG For H/A")
        if team.xg_against_ha is None or team.xg_against_ha < 0:
            team_missing.append(f"{team_name}: xG Against H/A")
        
        # Schuss-Statistiken
        if team.shots_per_match is None or team.shots_per_match < 0:
            team_missing.append(f"{team_name}: Schüsse/Spiel")
        if team.shots_on_target is None or team.shots_on_target < 0:
            team_missing.append(f"{team_name}: Schüsse aufs Tor")
        if team.conversion_rate is None or team.conversion_rate < 0:
            team_missing.append(f"{team_name}: Conversion Rate")
        
        # Ballbesitz
        if team.possession is None or team.possession < 0:
            team_missing.append(f"{team_name}: Ballbesitz%")
        
        return team_missing
    
    # Team-Daten überprüfen
    missing_fields.extend(check_team_data(match.home_team, "HEIM"))
    missing_fields.extend(check_team_data(match.away_team, "AUSWÄRTS"))
    
    # Match-Informationen
    if not match.date or match.date.strip() == "":
        missing_fields.append("Match-Datum")
    if not match.competition or match.competition.strip() == "":
        missing_fields.append("Wettbewerb/Liga")
    if not match.kickoff or match.kickoff.strip() == "":
        missing_fields.append("Anstoßzeit")
    
    # Quoten überprüfen
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
    
    # H2H kann leer sein (bei erstem Aufeinandertreffen), aber sollte zumindest existieren
    if match.h2h_results is None:
        missing_fields.append("H2H-Daten (Liste)")
    
    # Validierung abschließen
    is_valid = len(missing_fields) == 0
    return is_valid, missing_fields

# ==================== POISSON FUNKTION ====================
def poisson_probability(lmbda: float, k: int) -> float:
    """Exakte Poisson-Wahrscheinlichkeit"""
    if lmbda <= 0: 
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

# ==================== STRENGES RISIKO-SCORING SYSTEM ====================
def calculate_extended_risk_scores_strict(prob_1x2_home: float, prob_1x2_draw: float, prob_1x2_away: float,
                                         prob_over: float, prob_under: float,
                                         prob_btts_yes: float, prob_btts_no: float,
                                         odds_1x2: tuple, odds_ou: tuple, odds_btts: tuple,
                                         mu_total: float, tki_combined: float, ppg_diff: float,
                                         home_team, away_team) -> Dict:
    """
    STRENGES Risiko-Scoring System (1-5)
    Weniger 5/5, realistischere Bewertung
    Erwartete Verteilung: 5/5=2-5%, 4/5=10-15%, 3/5=60-70%, 2/5=15-20%, 1/5=5-10%
    """
    
    # Hilfsfunktion für strengere Risiko-Bewertung
    def strict_risk_description(score: int) -> str:
        descriptions = {
            1: "🔴 EXTREM RISIKANT",
            2: "🔴 HOHES RISIKO", 
            3: "🟡 MODERATES RISIKO",
            4: "🟢 GERINGES RISIKO",
            5: "🟢 OPTIMALES RISIKO"
        }
        return descriptions.get(score, "🟡 MODERATES RISIKO")
    
    # 1. STRENGERE 1X2 RISIKO-BEWERTUNG
    def calculate_1x2_risk_strict(best_prob: float, best_odds: float, 
                                 second_best_prob: float) -> int:
        """
        STRENG: Erwartet höheren EV und berücksichtigt Wett-Konkurrenz
        """
        # Expected Value
        ev = (best_prob / 100) * best_odds - 1
        
        # Prüfe Wett-Dominanz: Wie viel besser ist die beste Option?
        prob_dominance = best_prob - second_best_prob if second_best_prob > 0 else best_prob
        
        # STRENGE KRITERIEN:
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
        else:  # ev >= 0.18
            if prob_dominance > 20 and ev > 0.25:
                return 5
            else:
                return 4
    
    # Beste und zweitbeste 1X2 Option finden
    probs_1x2 = [prob_1x2_home, prob_1x2_draw, prob_1x2_away]
    markets = ['Heimsieg', 'Unentschieden', 'Auswärtssieg']
    sorted_probs = sorted(zip(probs_1x2, odds_1x2, markets), key=lambda x: x[0], reverse=True)
    
    best_prob, best_odds, best_market = sorted_probs[0]
    second_best_prob = sorted_probs[1][0]
    
    risk_1x2 = calculate_1x2_risk_strict(best_prob, best_odds, second_best_prob)
    
    # 2. STRENGERE OVER/UNDER RISIKO-BEWERTUNG
    def calculate_ou_risk_strict(prob: float, odds: float, mu_total: float) -> int:
        """Strengere Bewertung für Over/Under"""
        ev = (prob / 100) * odds - 1
        
        # Berücksichtige μ-Total für Realismus
        mu_adjustment = 0
        
        if mu_total > 4.0 and prob > 65:
            mu_adjustment = -1
        elif mu_total < 2.0 and prob > 65:
            mu_adjustment = -1
        
        # STRENGE EV KRITERIEN
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
    
    # 3. STRENGERE BTTS RISIKO-BEWERTUNG
    def calculate_btts_risk_strict(prob: float, odds: float, 
                                  home_cs_rate: float, away_cs_rate: float) -> int:
        """Strengere BTTS Bewertung mit Clean Sheet Berücksichtigung"""
        ev = (prob / 100) * odds - 1
        
        # Clean Sheet Rate Penalty
        cs_penalty = 0
        avg_cs_rate = (home_cs_rate + away_cs_rate) / 2
        
        if prob > 70:
            if avg_cs_rate > 0.4:
                cs_penalty = -2
            elif avg_cs_rate > 0.3:
                cs_penalty = -1
        
        # STRENGE EV KRITERIEN
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
    
    # 4. STRENGES GESAMT-RISIKO-SCORING
    def calculate_overall_risk_strict(risk_1x2: int, risk_over: int, risk_under: int,
                                     risk_btts_yes: int, risk_btts_no: int,
                                     best_1x2_prob: float, mu_total: float,
                                     tki_combined: float, ppg_diff: float,
                                     home_games: int, away_games: int) -> Dict:
        """
        SEHR STRENGES Gesamt-Risiko (1-5)
        Score 5 sollte extrem selten sein (<5% der Fälle)
        """
        
        # GEWICHTETER DURCHSCHNITT
        weights = {
            '1x2': 0.35,
            'ou': 0.30,
            'btts': 0.25,
            'data_quality': 0.10
        }
        
        # Datenqualität Score
        data_quality_score = 3
        if home_games < 10 or away_games < 10:
            data_quality_score = 2
        if home_games < 5 or away_games < 5:
            data_quality_score = 1
        
        avg_risk = (risk_1x2 * weights['1x2'] +
                   ((risk_over + risk_under) / 2) * weights['ou'] +
                   ((risk_btts_yes + risk_btts_no) / 2) * weights['btts'] +
                   data_quality_score * weights['data_quality'])
        
        # ANPASSUNGEN (viel strenger!)
        adjustments = 0.0
        
        # 1. μ-TOTAL ANPASSUNG
        if mu_total > 4.5:
            adjustments -= 1.5
        elif mu_total > 4.0:
            adjustments -= 1.0
        elif mu_total > 3.5:
            adjustments -= 0.6
        elif mu_total < 2.0:
            adjustments += 0.3
        
        # 2. TKI ANPASSUNG
        if tki_combined > 1.0:
            adjustments -= 1.5
        elif tki_combined > 0.8:
            adjustments -= 1.0
        elif tki_combined > 0.6:
            adjustments -= 0.6
        
        # 3. PPG DIFFERENZ (Paradox: Sehr klare Favoriten sind oft riskant)
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
        
        # 4. WAHRSCHEINLICHKEITS-QUALITÄT
        if best_1x2_prob > 75:
            adjustments -= 0.3
        elif best_1x2_prob > 65:
            adjustments += 0.1
        elif best_1x2_prob < 35:
            adjustments -= 0.3
        
        # 5. QUOTEN-QUALITÄT
        best_odds_value = max(odds_1x2)
        if best_odds_value > 3.0:
            adjustments -= 0.5
        elif best_odds_value < 1.5:
            adjustments -= 0.3
        
        # 6. STATISTISCHE SIGNIFIKANZ
        total_games = home_games + away_games
        if total_games < 20:
            adjustments -= 0.5
        
        # FINALER SCORE
        final_score = avg_risk + adjustments
        
        # SEHR STRENGE RUNDUNG
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
        
        # KATEGORIE UND EMPFEHLUNG
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
    
    # Gesamt-Risiko mit strengen Kriterien
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

# ==================== RISIKO-VERTEILUNGS-STATISTIK ====================
def display_risk_distribution(all_results):
    """Zeigt Verteilung der Risiko-Scores an"""
    
    if not all_results:
        return
    
    scores = []
    for item in all_results:
        if 'result' in item and 'extended_risk' in item['result']:
            scores.append(item['result']['extended_risk']['overall']['score'])
    
    if not scores:
        return
    
    # Verteilung berechnen
    from collections import Counter
    distribution = Counter(scores)
    total = len(scores)
    
    st.markdown("---")
    st.subheader("📈 Risiko-Score Verteilung")
    st.caption("Zeigt wie viele Matches jedem Risiko-Level zugeordnet wurden")
    
    cols = st.columns(5)
    colors = ['darkred', 'red', 'yellow', 'lightgreen', 'green']
    labels = ['1/5 Extrem', '2/5 Hoch', '3/5 Moderat', '4/5 Gering', '5/5 Optimal']
    
    for i in range(1, 6):
        count = distribution.get(i, 0)
        percentage = (count / total) * 100 if total > 0 else 0
        
        with cols[i-1]:
            st.metric(
                label=labels[i-1],
                value=f"{count}",
                delta=f"{percentage:.1f}%",
                delta_color="off"
            )
            
            # Fortschrittsbalken
            st.progress(min(percentage/100, 1.0))
    
    # Empfehlung basierend auf Verteilung
    score_5_pct = (distribution.get(5, 0) / total * 100) if total > 0 else 0
    score_4_pct = (distribution.get(4, 0) / total * 100) if total > 0 else 0
    score_3_pct = (distribution.get(3, 0) / total * 100) if total > 0 else 0
    
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 📊 Verteilungs-Analyse")
        
        if score_5_pct > 10:
            st.warning(f"⚠️ **Zu viele 5/5 Bewertungen** ({score_5_pct:.1f}%) - Scoring könnte zu liberal sein!")
        elif score_5_pct < 1 and total > 20:
            st.info(f"ℹ️ Sehr wenige 5/5 Bewertungen ({score_5_pct:.1f}%) - Scoring ist sehr streng")
        elif score_5_pct >= 2 and score_5_pct <= 5:
            st.success(f"✅ Optimale 5/5 Verteilung ({score_5_pct:.1f}%) - Scoring funktioniert gut!")
        
        if score_3_pct > 75:
            st.info("ℹ️ Sehr viele 3/5 Bewertungen - Die meisten Wetten sind moderat riskant")
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

# ==================== v4.11 ANALYSE FUNKTION ====================
def analyze_match_v411(match: MatchData) -> Dict:
    """
    v4.11 OPTIMIZED SMART-PRECISION LOGIK
    
    OPTIMIERUNGEN in v4.11:
    - Weniger aggressive Form-Faktoren (0.75 statt 0.70 etc.)
    - Weniger aggressive Dominanz-Dämpfer
    - TKI-Boost reduziert (0.25 statt 0.4)
    - BTTS-Dämpfung weniger aggressiv
    - Strengeres Risiko-Scoring
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
    
    # --- v4.11 OPTIMIZED SMART-PRECISION LOGIK ---
    
    # 1. BASIS μ
    mu_h = (xg_ha[0] + s_c_ha[0]) / 2
    mu_a = (xg_ha[2] + s_c_ha[2]) / 2
    
    # 2. FORM-FAKTOR (optimiert)
    def calculate_form_factor(form_ppg, overall_ppg):
        if overall_ppg == 0:
            return 1.0
        form_ratio = form_ppg / overall_ppg
        
        if form_ratio < 0.4:
            return 0.75  # v4.11: war 0.70 in v4.9
        elif form_ratio < 0.6:
            return 0.88  # v4.11: war 0.85 in v4.9
        elif form_ratio > 1.5:
            return 1.15  # v4.11: war 1.20 in v4.9
        elif form_ratio > 1.2:
            return 1.08  # v4.11: war 1.10 in v4.9
        else:
            return 1.0
    
    form_factor_h = calculate_form_factor(form_ppg_h, ppg[0])
    form_factor_a = calculate_form_factor(form_ppg_a, ppg[1])
    
    # 3. TKI BERECHNUNG
    tki_h = max(0, s_c_ha[1] - xg_ha[1])
    tki_a = max(0, s_c_ha[3] - xg_ha[3])
    tki_combined = tki_h + tki_a
    
    # 4. TKI-KRISE ÜBERSCHREIBT FORM-MALUS
    if tki_a > 1.0:  # Gast-Keeper in Krise
        if form_factor_h < 1.0:
            form_factor_h = 1.0
    
    if tki_h > 1.0:  # Heim-Keeper in Krise
        if form_factor_a < 1.0:
            form_factor_a = 1.0
    
    # 5. DEFENSIVE CONTEXT CHECK
    if cs_rates[0] > 40 and form_factor_h > 1.0:
        form_factor_h = 1.0 + (form_factor_h - 1.0) * 0.5
    
    if cs_rates[1] > 40 and form_factor_a > 1.0:
        form_factor_a = 1.0 + (form_factor_a - 1.0) * 0.5
    
    # 6. Form-Faktor anwenden
    mu_h *= form_factor_h
    mu_a *= form_factor_a
    
    # 7. DOMINANZ-DÄMPFER (weniger aggressiv)
    ppg_diff = ppg[0] - ppg[1]
    
    if ppg_diff > 1.5:
        mu_a *= 0.65  # v4.11: war 0.45 in v4.9
        mu_h *= 1.15  # v4.11: war 1.30 in v4.9
    elif ppg_diff > 1.2:
        mu_a *= 0.75  # v4.11: war 0.55 in v4.9
        mu_h *= 1.10  # v4.11: war 1.25 in v4.9
    elif ppg_diff > 0.8:
        mu_a *= 0.85  # v4.11: war 0.65 in v4.9
        mu_h *= 1.05  # v4.11: war 1.15 in v4.9
    
    # 8. AUSWÄRTS-UNDERDOG BOOST (optimiert)
    if ppg_diff < -0.5:
        mu_a *= 1.15  # v4.11: war 1.20 in v4.9
        mu_h *= 0.85  # v4.11: war 0.80 in v4.9
    elif ppg_diff < -0.3:
        mu_a *= 1.08  # v4.11: war 1.10 in v4.9
        mu_h *= 0.92  # v4.11: war 0.90 in v4.9
    
    # 9. CLEAN SHEET VALIDIERUNG (optimiert)
    if cs_rates[0] > 50:
        mu_a *= 0.75  # v4.11: war 0.70 in v4.9
    elif cs_rates[0] > 40:
        mu_a *= 0.85  # v4.11: war 0.80 in v4.9
    elif cs_rates[0] > 30:
        mu_a *= 0.90  # v4.11: war 0.85 in v4.9
    
    if cs_rates[1] > 50:
        mu_h *= 0.75  # v4.11: war 0.70 in v4.9
    elif cs_rates[1] > 40:
        mu_h *= 0.85  # v4.11: war 0.80 in v4.9
    elif cs_rates[1] > 30:
        mu_h *= 0.90  # v4.11: war 0.85 in v4.9
    
    # 10. TKI-BOOST (reduziert)
    mu_h = mu_h * (1 + (tki_a * 0.25))  # v4.11: war 0.4 in v4.9
    mu_a = mu_a * (1 + (tki_h * 0.25))  # v4.11: war 0.4 in v4.9
    
    # 11. CONVERSION-RATE ADJUSTMENT
    def apply_conversion_adjustment(mu, conversion_rate):
        if conversion_rate > 14:
            return mu * 1.10
        elif conversion_rate < 8:
            return mu * 0.90
        return mu
    
    mu_h = apply_conversion_adjustment(mu_h, conv_rate[0])
    mu_a = apply_conversion_adjustment(mu_a, conv_rate[1])
    
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
    
    # 13. BTTS-PRÄZISIONS-FILTER v4.11
    mu_total_check = mu_h + mu_a
    
    # Bei torreichem Spiel: reduziere BTTS-Dämpfung
    if mu_total_check > 3.5:
        btts_torreich_faktor = 1.5
    else:
        btts_torreich_faktor = 1.0
    
    # Normale BTTS Logik
    if mu_h < 1.0 or mu_a < 1.0:
        btts_p *= 0.85  # v4.11: war 0.80 in v4.9
    
    # DOMINANZ-KILLER (weniger aggressiv)
    if tki_combined < 0.6:  # v4.11: war 0.8 in v4.9
        if ppg_diff > 1.0:
            btts_p *= 0.75  # v4.11: weniger aggressiv
        elif ppg_diff > 0.8:
            btts_p *= 0.85  # v4.11: weniger aggressiv
    
    # FAILED TO SCORE CHECK (verschärft)
    if fts_a > 0.25 and ppg_diff > 1.2:  # v4.11: verschärft
        btts_p *= 0.85  # v4.11: war 0.70 in v4.9
    if fts_h > 0.25 and ppg_diff < -1.2:  # v4.11: verschärft
        btts_p *= 0.85  # v4.11: war 0.70 in v4.9
    
    # Wende Torreich-Faktor an
    btts_p *= btts_torreich_faktor
    
    # H2H Analyse
    h2h_stats = analyze_h2h(match.home_team, match.away_team, match.h2h_results)
    
    # Strenges Risiko-Scoring
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
        tki_combined=tki_combined,
        ppg_diff=ppg_diff,
        home_team=match.home_team,
        away_team=match.away_team
    )
    
    # Ergebnis-Dict erstellen
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
            'combined': round(tki_combined, 2)
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
        'extended_risk': extended_risk,
        'odds': {
            '1x2': match.odds_1x2,
            'ou25': match.odds_ou25,
            'btts': match.odds_btts
        }
    }
    
    # NEU: Vorhersage in Google Sheets speichern (mit robuster Fehlerbehandlung)
    try:
        save_prediction_to_sheets(
            match_info=result['match_info'],
            probabilities=result['probabilities'],
            odds=result['odds'],
            risk_score=result['extended_risk']['overall'],
            predicted_score=result['predicted_score'],
            mu_info=result['mu']
        )
    except Exception as e:
        # Kein Fehler anzeigen, nur in Console loggen
        print(f"Tracking-Fehler (nicht kritisch): {str(e)}")
    
    return result

def analyze_h2h(home: TeamStats, away: TeamStats, h2h_data: List[H2HResult]) -> Dict:
    """Analysiert Head-to-Head Daten"""
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

# ==================== GOOGLE SHEETS TRACKING FUNKTION (ROBUST) ====================
def save_prediction_to_sheets(match_info: Dict, probabilities: Dict, odds: Dict, 
                             risk_score: Dict, predicted_score: str, mu_info: Dict):
    """
    Speichert Vorhersage in Google Sheets Tracking-Datei
    ROBUST: Funktioniert mit und ohne tracking secrets
    """
    try:
        # Prüfe ob tracking secrets existieren
        if "tracking" not in st.secrets:
            # Kein Tracking konfiguriert - nur im Debug-Modus zeigen
            if st.session_state.get('debug_mode', False):
                st.info("ℹ️ Tracking nicht konfiguriert (tracking section fehlt in secrets)")
            return False
        
        tracking_secrets = st.secrets["tracking"]
        
        # Prüfe verschiedene mögliche sheet_id Namen
        sheet_id = None
        possible_keys = ['sheet_id', 'sheet_id_v411', 'sheet_id_v49', 'sheet_id_v48', 'sheet_id_v47']
        
        for key in possible_keys:
            if key in tracking_secrets:
                sheet_id = tracking_secrets[key]
                break
        
        if not sheet_id:
            if st.session_state.get('debug_mode', False):
                st.warning("⚠️ Keine sheet_id in tracking secrets gefunden")
            return False
        
        # Verbindung zu Google Sheets mit Schreibrechten
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        service = build('sheets', 'v4', credentials=creds)
        
        # Beste Over/Under Option
        best_over_under = "Over 2.5" if probabilities['over_25'] >= (100 - probabilities['over_25']) else "Under 2.5"
        prob_over_under = max(probabilities['over_25'], 100 - probabilities['over_25'])
        odds_over_under = odds['ou25'][0] if best_over_under == "Over 2.5" else odds['ou25'][1]
        
        # Beste BTTS Option  
        best_btts = "BTTS Yes" if probabilities['btts_yes'] >= probabilities['btts_no'] else "BTTS No"
        prob_btts = max(probabilities['btts_yes'], probabilities['btts_no'])
        odds_btts = odds['btts'][0] if best_btts == "BTTS Yes" else odds['btts'][1]
        
        # Beste 1X2 Option
        probs_1x2 = [probabilities['home_win'], probabilities['draw'], probabilities['away_win']]
        markets_1x2 = ['Heimsieg', 'Unentschieden', 'Auswärtssieg']
        best_idx = probs_1x2.index(max(probs_1x2))
        best_1x2 = markets_1x2[best_idx]
        prob_1x2 = probs_1x2[best_idx]
        odds_1x2_value = odds['1x2'][best_idx]
        
        # Daten vorbereiten
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        match_str = f"{match_info['home']} vs {match_info['away']}"
        mu_total = mu_info.get('total', 0.0)
        
        # Version erkennen
        current_file = os.path.basename(__file__)
        if "4.11" in current_file or "v411" in current_file:
            version = "v4.11"
        elif "4.9" in current_file or "v49" in current_file:
            version = "v4.9"
        elif "4.8" in current_file or "v48" in current_file:
            version = "v4.8"
        elif "4.7" in current_file or "v47" in current_file:
            version = "v4.7"
        else:
            version = "v4.x"
        
        values = [[
            timestamp,                                  # A: Timestamp
            version,                                    # B: Version
            match_str,                                  # C: Match
            predicted_score,                            # D: Predicted_Score
            best_1x2,                                   # E: Predicted_1X2
            f"{prob_1x2:.1f}%",                        # F: Probability_1X2
            best_over_under,                            # G: Best_OverUnder
            f"{prob_over_under:.1f}%",                 # H: Probability_OverUnder
            f"{odds_over_under:.2f}",                  # I: Odds_OverUnder
            best_btts,                                  # J: Best_BTTS
            f"{prob_btts:.1f}%",                       # K: Probability_BTTS
            f"{odds_btts:.2f}",                        # L: Odds_BTTS
            f"{odds_1x2_value:.2f}",                   # M: Odds_1X2
            str(risk_score['score']),                   # N: Risk_Score (1-5)
            risk_score['category'],                     # O: Risk_Category
            f"{mu_total:.2f}",                         # P: μ_Total
            "PENDING"                                   # Q: Status
        ]]
        
        # In Sheets schreiben
        body = {'values': values}
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="PREDICTIONS!A:Q",
            valueInputOption="USER_ENTERED",
            body=body
        ).execute()
        
        # Erfolgsmeldung (nur im Debug-Modus)
        if st.session_state.get('debug_mode', False):
            st.success(f"✅ Vorhersage ({version}) in Tracking-Sheet gespeichert!")
        
        return True
        
    except Exception as e:
        # Keine Fehlermeldung an Benutzer - nur in Console
        print(f"⚠️ Tracking-Fehler (nicht kritisch): {str(e)}")
        return False

# ==================== OPTIMIERTE ANZEIGE FUNKTION ====================
def display_results_v411(result):
    """Zeigt die Analyseergebnisse mit neuem Risiko-Scoring an"""
    st.header(f"🎯 {result['match_info']['home']} vs {result['match_info']['away']}")
    st.caption(f"📅 {result['match_info']['date']} | {result['match_info']['kickoff']} Uhr | {result['match_info']['competition']}")
    
    # Smart-Precision Info
    st.subheader("🧠 SMART-PRECISION v4.11 OPTIMIZED")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Smart μ Home", f"{result['mu']['home']:.2f}")
    with col2:
        st.metric("Smart μ Away", f"{result['mu']['away']:.2f}")
    with col3:
        st.metric("PPG Gap", f"{result['mu']['ppg_diff']:.2f}")
    with col4:
        st.metric("μ-Total", f"{result['mu']['total']:.2f}")
    
    # Form-Analyse
    st.subheader("📈 FORM-ANALYSE")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        form_h = result['form']['home_factor']
        color_h = "🟢" if form_h > 1.0 else "🔴" if form_h < 0.9 else "🟡"
        st.metric("Heim Form-Faktor", f"{color_h} {form_h:.2f}")
    with col2:
        form_a = result['form']['away_factor']
        color_a = "🟢" if form_a > 1.0 else "🔴" if form_a < 0.9 else "🟡"
        st.metric("Gast Form-Faktor", f"{color_a} {form_a:.2f}")
    with col3:
        st.metric("Heim Form-PPG", f"{result['form']['home_ppg']:.2f}")
    with col4:
        st.metric("Gast Form-PPG", f"{result['form']['away_ppg']:.2f}")
    
    # ERWEITERTE RISIKO-ANALYSE
    st.subheader("⚠️ ERWEITERTE RISIKO-ANALYSE")
    
    # Gesamt-Risiko
    overall_risk = result['extended_risk']['overall']
    
    # Gesamt-Risiko in einer Box
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
        # Risiko-Score Visualisierung
        fig_risk = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = overall_risk['score'],
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Gesamt-Risiko"},
            gauge = {
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
    
    # Einzelne Wetten-Risikos
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
    
    # Risiko-Details expander
    with st.expander("📋 RISIKO-FAKTOREN DETAILS"):
        details = overall_risk['details']
        col1, col2, col3 = st.columns(3)
        col1.metric("μ-Total", f"{details['mu_total_impact']:.2f}")
        col2.metric("TKI kombiniert", f"{details['tki_impact']:.2f}")
        col3.metric("Beste 1X2 Wahrscheinlichkeit", f"{details['favorite_prob']:.1f}%")
        col1.metric("PPG Differenz", f"{details['ppg_diff_abs']:.2f}")
        col2.metric("Durchschn. Risiko", f"{details['average_risk']:.2f}")
        col3.metric("Anpassungen", f"{details['adjustments']:.2f}")
    
    # Torwart-Krisen-Index
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
    
    # H2H Statistik
    st.subheader("🔄 Head-to-Head Statistik")
    h2h = result['h2h']
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ø Tore/Spiel", f"{h2h['avg_total_goals']:.1f}")
    col2.metric("Ø Heimtore", f"{h2h['avg_home_goals']:.1f}")
    col3.metric("Ø Auswärtstore", f"{h2h['avg_away_goals']:.1f}")
    col4.metric("BTTS-Quote", f"{h2h['btts_percentage']*100:.0f}%")
    
    st.caption(f"Bilanz: {h2h['home_wins']} Siege - {h2h['draws']} Remis - {h2h['away_wins']} Niederlagen")
    
    # Wahrscheinlichkeiten Tabelle
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
    
    # Score Prediction
    st.subheader("📊 Score-Vorhersage")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        best_1x2 = "Heimsieg" if probs['home_win'] >= probs['draw'] and probs['home_win'] >= probs['away_win'] else "Unentschieden" if probs['draw'] >= probs['away_win'] else "Auswärtssieg"
        best_1x2_prob = max(probs['home_win'], probs['draw'], probs['away_win'])
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
            st.success(f"**Ergebnis**\n{result['predicted_score']}\n**{result['scorelines'][0][1]:.1f}%**")
    
    # Visualisierung
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
        # Risiko-Übersicht Chart
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

# ==================== ALERT-SYSTEM ====================
def check_alerts(mu_h: float, mu_a: float, tki_h: float, tki_a: float, 
                ppg_diff: float, thresholds: Dict) -> List[Dict]:
    """Prüft ob Alarme ausgelöst werden"""
    alerts = []
    
    # 1. TORREICHES SPIEL
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
    
    # 2. TORWART-KRISE
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
    
    # 3. KLARER FAVORIT
    ppg_diff_abs = abs(ppg_diff)
    if ppg_diff_abs > thresholds.get('ppg_diff_extreme', 1.5):
        alerts.append({
            'level': '🟢',
            'title': 'EXTREM KLARER FAVORIT',
            'message': f"PPG-Differenz: {ppg_diff_abs:.2f} - Sehr einseitiges Spiel erwartet",
            'type': 'success'
        })
    
    return alerts

# ==================== GOOGLE SHEETS FUNKTIONEN ====================
@st.cache_resource
def connect_to_sheets(readonly=True):
    """
    Verbindung zu Google Sheets
    readonly=True: Nur Leserechte
    readonly=False: Lese- und Schreibrechte (für Tracking)
    """
    if readonly:
        scope = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    else:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
    
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return build('sheets', 'v4', credentials=creds)

@st.cache_data(ttl=300)
def get_all_worksheets(sheet_url):
    try:
        service = connect_to_sheets(readonly=True)
        spreadsheet_id = sheet_url.split('/d/')[1].split('/')[0]
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', [])
        return {sheet['properties']['title']: sheet['properties']['sheetId'] for sheet in sheets}
    except Exception as e:
        st.error(f"❌ Fehler: {e}")
        return None

def read_worksheet_data(sheet_url, sheet_name):
    try:
        service = connect_to_sheets(readonly=True)
        spreadsheet_id = sheet_url.split('/d/')[1].split('/')[0]
        range_name = f"'{sheet_name}'!A:Z"
        result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        data = result.get('values', [])
        text_data = []
        for row in data:
            if any(cell.strip() for cell in row if cell):
                text_data.append('\t'.join(row))
        return '\n'.join(text_data)
    except Exception as e:
        st.error(f"❌ Fehler: {e}")
        return None

# ==================== DATA PARSER ====================
class DataParser:
    def __init__(self):
        self.lines = []
    
    def parse(self, text: str) -> MatchData:
        self.lines = [line.strip() for line in text.split('\n') if line.strip()]
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
        home_team = self._create_team_stats(home_name, home_overall, home_form, home_ha, home_stats)
        away_team = self._create_team_stats(away_name, away_overall, away_form, away_ha, away_stats)
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
        teams = [t.strip() for t in re.split(r'\s{2,}', teams_line) if t.strip()]
        return teams[0], teams[1]
    
    def _parse_date_competition(self) -> Tuple[str, str, str]:
        date_idx = self._find_line_with("datum:")
        date = self.lines[date_idx].split(':', 1)[1].strip() if date_idx != -1 else ""
        comp_idx = self._find_line_with("wettbewerb:")
        competition = self.lines[comp_idx].split(':', 1)[1].strip() if comp_idx != -1 else ""
        kick_idx = self._find_line_with("anstoß:")
        kickoff = self.lines[kick_idx].split(':', 1)[1].strip() if kick_idx != -1 else ""
        return date, competition, kickoff
    
    def _parse_team_overall(self, team_name: str) -> Dict:
        for i, line in enumerate(self.lines):
            if team_name in line and 'tabellenposition' not in line.lower() and 'letzte 5' not in line.lower():
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
        return {'points': points, 'goals_for': goals_for, 'goals_against': goals_against}
    
    def _parse_h2h(self, home_name: str, away_name: str) -> List[H2HResult]:
        results = []
        idx = self._find_line_with("ergebnisse")
        if idx == -1:
            return results
        idx += 1
        while idx < len(self.lines):
            line = self.lines[idx]
            if any(marker in line.lower() for marker in ['statistische', 'wettquoten', '1x2', 'points per game']):
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
                            home_stats['goals_scored_per_match'] = float(parts[1])
                            home_stats['goals_conceded_per_match'] = float(parts[2])
                            away_stats['goals_scored_per_match'] = float(parts[3])
                            away_stats['goals_conceded_per_match'] = float(parts[4])
                    elif 'average goals scored/conceded per match home/away' in stat_name:
                        if len(parts) >= 5:
                            home_stats['goals_scored_per_match_ha'] = float(parts[1])
                            home_stats['goals_conceded_per_match_ha'] = float(parts[2])
                            away_stats['goals_scored_per_match_ha'] = float(parts[3])
                            away_stats['goals_conceded_per_match_ha'] = float(parts[4])
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
                            home_stats['cs_yes_overall'] = float(parts[1].replace('%', '')) / 100
                            away_stats['cs_yes_overall'] = float(parts[3].replace('%', '')) / 100
                    elif 'clean sheet yes/no home/away' in stat_name:
                        if len(parts) >= 5:
                            home_stats['cs_yes_ha'] = float(parts[1].replace('%', '')) / 100
                            away_stats['cs_yes_ha'] = float(parts[3].replace('%', '')) / 100
                    elif 'failed to score yes/no home/away' in stat_name:
                        if len(parts) >= 5:
                            home_stats['fts_yes_ha'] = float(parts[1].replace('%', '')) / 100
                            away_stats['fts_yes_ha'] = float(parts[3].replace('%', '')) / 100
                    elif 'conversion rate' in stat_name.lower():
                        home_stats['conversion_rate'] = float(parts[1].replace('%', '')) / 100
                        away_stats['conversion_rate'] = float(parts[2].replace('%', '')) / 100
                except (ValueError, IndexError):
                    continue
        return home_stats, away_stats
    
    def _parse_odds(self) -> Tuple[Tuple[float, float, float], Tuple[float, float], Tuple[float, float]]:
        odds_1x2 = (1.0, 1.0, 1.0)
        odds_ou25 = (1.0, 1.0)
        odds_btts = (1.0, 1.0)
        for line in self.lines:
            line_lower = line.lower()
            if '1x2' in line_lower:
                match = re.search(r'([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)', line)
                if match:
                    odds_1x2 = (float(match.group(1)), float(match.group(2)), float(match.group(3)))
            elif 'over/under 2' in line_lower:
                match = re.search(r'([\d.]+)\s*/\s*([\d.]+)', line)
                if match:
                    odds_ou25 = (float(match.group(1)), float(match.group(2)))
            elif 'btts' in line_lower and 'ja/nein' in line_lower:
                match = re.search(r'([\d.]+)\s*/\s*([\d.]+)', line)
                if match:
                    odds_btts = (float(match.group(1)), float(match.group(2)))
        return odds_1x2, odds_ou25, odds_btts
    
    def _create_team_stats(self, name: str, overall: Dict, form: Dict, ha: Dict, stats: Dict) -> TeamStats:
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
            goals_conceded_per_match=stats.get('goals_conceded_per_match', 0.0),
            goals_scored_per_match_ha=stats.get('goals_scored_per_match_ha', 0.0),
            goals_conceded_per_match_ha=stats.get('goals_conceded_per_match_ha', 0.0),
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

# ==================== HAUPT-APP ====================
def main():
    st.title("⚽ SPORTWETTEN-PROGNOSEMODELL v4.11 OPTIMIZED")
    st.markdown("### v4.11 PRECISION+ mit **STRENGEM RISIKO-SCORING (1-5)**")
    st.markdown("**Neu:** Daten-Validierung + Risiko-Verteilungs-Statistik + Google Sheets Tracking")
    st.markdown("---")
    
    # Debug-Modus Checkbox
    with st.sidebar:
        if st.checkbox("🔧 Debug-Modus", help="Zeigt Tracking-Informationen"):
            st.session_state['debug_mode'] = True
        else:
            st.session_state['debug_mode'] = False
    
    st.subheader("📊 Schritt 1: Google Sheets Datei")
    # ⚠️ WICHTIG: Deine feste Sheets URL beibehalten!
    SHEET_URL = "https://docs.google.com/spreadsheets/d/15V0TAf25LVekVMag7lklomQKNCj-fpl2POwWdVncN_A/edit"
    
    sheet_url = st.text_input(
        "Google Sheets URL:",
        value=SHEET_URL,  # Deine feste URL als Default
        placeholder="https://docs.google.com/spreadsheets/d/...",
        help="URL deiner 'Perplexity' Datei",
        key="sheet_url_input"
    )
    
    if sheet_url:
        st.markdown("---")
        st.subheader("📋 Schritt 2: Match auswählen")
        
        with st.spinner("📥 Lade Tabellenblätter..."):
            worksheets = get_all_worksheets(sheet_url)
        
        if worksheets:
            st.success(f"✅ {len(worksheets)} Matches gefunden!")
            
            # Suchfeld für Matches
            st.markdown("**🔍 Match suchen:**")
            search_term = st.text_input(
                "Suche nach Teamname oder Liga:",
                placeholder="z.B. 'Bayern' oder 'Bundesliga'",
                help="Suche nach Teamnamen oder Wettbewerben",
                key="match_search"
            )
            
            # Filtere die Worksheets basierend auf Suchbegriff
            if search_term:
                filtered_worksheets = {
                    k: v for k, v in worksheets.items() 
                    if search_term.lower() in k.lower()
                }
                st.info(f"📋 {len(filtered_worksheets)} von {len(worksheets)} Matches passen zur Suche")
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
                    st.warning("Keine Matches gefunden, die der Suche entsprechen.")
                    selected_worksheet = None
                    
            with col2:
                st.markdown("**Oder analysiere alle:**")
                analyze_all = st.checkbox("Alle Matches", key="analyze_all_check")
                if search_term and analyze_all:
                    st.info(f"⚠️ Suchfilter wird ignoriert, alle {len(worksheets)} Matches werden analysiert")
            
            if selected_worksheet and not analyze_all:
                with st.expander("👁️ Daten-Vorschau"):
                    preview_data = read_worksheet_data(sheet_url, selected_worksheet)
                    if preview_data:
                        st.text(preview_data[:800] + "\n...")
            
            st.markdown("---")
            st.subheader("⚙️ Schritt 3: Analyse")
            
            if analyze_all:
                if st.button("🔄 ALLE Matches analysieren", type="primary", use_container_width=True, key="analyze_all_btn"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    all_results = []
                    failed_matches = []  # Tracking für Matches mit fehlenden Daten
                    
                    for i, (sheet_name, _) in enumerate(worksheets.items()):
                        status_text.text(f"📊 Analysiere {sheet_name}... ({i+1}/{len(worksheets)})")
                        progress_bar.progress((i + 1) / len(worksheets))
                        
                        match_data = read_worksheet_data(sheet_url, sheet_name)
                        if match_data:
                            try:
                                parser = DataParser()
                                match = parser.parse(match_data)
                                
                                # ==================== DATEN-VALIDIERUNG ====================
                                is_valid, missing_fields = validate_match_data(match)
                                
                                if not is_valid:
                                    # Match hat fehlende Daten - überspringen
                                    failed_matches.append({
                                        'sheet_name': sheet_name,
                                        'missing_count': len(missing_fields),
                                        'missing_fields': missing_fields
                                    })
                                else:
                                    # Alle Daten vorhanden - analysieren
                                    result = analyze_match_v411(match)
                                    all_results.append({'sheet_name': sheet_name, 'result': result})
                                    
                            except Exception as e:
                                failed_matches.append({
                                    'sheet_name': sheet_name,
                                    'missing_count': 0,
                                    'missing_fields': [f"Parsing-Fehler: {str(e)}"]
                                })
                    
                    status_text.text("✅ Alle Analysen abgeschlossen!")
                    progress_bar.empty()
                    
                    # Zeige Zusammenfassung
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("✅ Erfolgreich analysiert", len(all_results))
                    with col2:
                        st.metric("⚠️ Fehlende Daten", len(failed_matches))
                    with col3:
                        st.metric("📊 Gesamt", len(worksheets))
                    
                    # Zeige fehlerhafte Matches falls vorhanden
                    if failed_matches:
                        st.markdown("---")
                        st.warning(f"⚠️ **{len(failed_matches)} Matches konnten nicht analysiert werden (fehlende Daten)**")
                        
                        with st.expander(f"📋 Details zu {len(failed_matches)} übersprungenen Matches"):
                            for failed in failed_matches:
                                st.markdown(f"### 🚫 {failed['sheet_name']}")
                                if failed['missing_count'] > 0:
                                    st.caption(f"Fehlende Datenpunkte: **{failed['missing_count']}**")
                                    
                                    # Zeige erste 10 fehlende Felder
                                    fields_to_show = failed['missing_fields'][:10]
                                    for field in fields_to_show:
                                        st.markdown(f"- {field}")
                                    
                                    if len(failed['missing_fields']) > 10:
                                        st.caption(f"... und {len(failed['missing_fields']) - 10} weitere")
                                else:
                                    st.markdown(f"- {failed['missing_fields'][0]}")
                                
                                st.markdown("---")
                    
                    # Übersicht aller erfolgreichen Analysen
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
                        st.dataframe(df_overview, use_container_width=True, hide_index=True)
                        
                        # RISIKO-VERTEILUNGS-STATISTIK
                        display_risk_distribution(all_results)
                        
                        # Detailansichten
                        st.markdown("---")
                        st.header("📋 DETAILLIERTE ANALYSEN")
                        for item in all_results:
                            with st.expander(f"🎯 {item['sheet_name']} - {item['result']['predicted_score']}", expanded=False):
                                display_results_v411(item['result'])
                    else:
                        st.error("❌ Keine Matches konnten erfolgreich analysiert werden. Alle haben fehlende Daten.")
            
            elif selected_worksheet:
                if st.button(f"🔄 '{selected_worksheet}' analysieren", type="primary", use_container_width=True, 
                           key=f"analyze_single_{selected_worksheet}"):
                    with st.spinner(f"⚙️ Analysiere {selected_worksheet}..."):
                        match_data = read_worksheet_data(sheet_url, selected_worksheet)
                        
                        if match_data:
                            try:
                                parser = DataParser()
                                match = parser.parse(match_data)
                                
                                # ==================== DATEN-VALIDIERUNG ====================
                                is_valid, missing_fields = validate_match_data(match)
                                
                                if not is_valid:
                                    st.error("⚠️ **FEHLENDE DATENPUNKTE ERKANNT!**")
                                    st.warning(f"Es fehlen **{len(missing_fields)}** kritische Datenpunkte. Analyse kann nicht durchgeführt werden.")
                                    
                                    st.markdown("### 📋 Folgende Daten fehlen:")
                                    
                                    # Gruppiere fehlende Felder nach Team
                                    heim_missing = [f for f in missing_fields if f.startswith("HEIM:")]
                                    away_missing = [f for f in missing_fields if f.startswith("AUSWÄRTS:")]
                                    other_missing = [f for f in missing_fields if not (f.startswith("HEIM:") or f.startswith("AUSWÄRTS:"))]
                                    
                                    if heim_missing:
                                        st.markdown("#### 🏠 Heimteam:")
                                        for field in heim_missing:
                                            st.markdown(f"- {field.replace('HEIM: ', '')}")
                                    
                                    if away_missing:
                                        st.markdown("#### ✈️ Auswärtsteam:")
                                        for field in away_missing:
                                            st.markdown(f"- {field.replace('AUSWÄRTS: ', '')}")
                                    
                                    if other_missing:
                                        st.markdown("#### ⚽ Match-Informationen:")
                                        for field in other_missing:
                                            st.markdown(f"- {field}")
                                    
                                    st.info("💡 **Tipp:** Überprüfe deinen Scraper und stelle sicher, dass alle Daten korrekt in Google Sheets eingetragen wurden.")
                                    
                                else:
                                    # Alle Daten vorhanden - Analyse durchführen
                                    result = analyze_match_v411(match)
                                    
                                    st.success("✅ Analyse abgeschlossen!")
                                    st.markdown("---")
                                    display_results_v411(result)
                                
                            except Exception as e:
                                st.error(f"❌ Fehler bei der Analyse: {e}")
                                st.info("Stelle sicher, dass die Tabellendaten korrekt formatiert sind.")

# ==================== SIDEBAR ====================
with st.sidebar:
    st.header("⚙️ v4.11 Einstellungen & Tools")
    
    st.subheader("🆕 v4.11 Changelog")
    with st.expander("Was ist neu?"):
        st.markdown("""
        **🚀 OPTIMIERTES SYSTEM:**
        
        **1. STRENGES RISIKO-SCORING:**
        - Weniger 5/5 Bewertungen (nur 2-5%)
        - Realistischere Risiko-Einschätzung
        - Berücksichtigt Datenqualität
        
        **2. DATEN-VALIDIERUNG:**
        - Prüft vor Analyse alle kritischen Datenpunkte
        - Zeigt fehlende Daten an
        - Verhindert fehlerhafte Analysen
        
        **3. RISIKO-VERTEILUNGS-STATISTIK:**
        - Zeigt wie viele Matches welchem Risiko zugeordnet werden
        - Verteilungskontrolle für Scoring-System
        
        **4. GOOGLE SHEETS TRACKING:**
        - Automatisches Speichern von Vorhersagen
        - Funktioniert mit/ohne Tracking-Secrets
        - Robust gegen Fehler
        
        **5. OPTIMIERTE LOGIK:**
        - Weniger aggressive Form-Faktoren
        - Reduzierte Dominanz-Dämpfer
        - Verbesserte BTTS-Berechnung
        """)
    
    st.markdown("---")
    
    st.subheader("📊 Google Sheets Info")
    try:
        if 'sheet_url' in st.session_state and sheet_url and 'worksheets' in locals() and worksheets:
            st.success("✅ Verbunden")
            st.caption(f"{len(worksheets)} Tabellenblätter")
        else:
            st.info("ℹ️ Bitte Google Sheets URL eingeben")
    except:
        st.info("ℹ️ Bitte Google Sheets URL eingeben")
    
    st.markdown("---")
    
    st.subheader("🔧 Alarm-Einstellungen")
    with st.expander("Alarm-Schwellenwerte anpassen"):
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
    
    st.markdown("---")
    
    st.subheader("🔗 Quick Actions")
    if st.button("🔄 Cache leeren", key="clear_cache"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()
    
    st.markdown("---")
    
    st.subheader("ℹ️ Strenges Risiko-Scoring")
    st.caption("""
    **🎯 OPTIMIERTES SYSTEM:**
    Weniger 5/5 Bewertungen, realistischere Einschätzung
    
    **1/5 - ☠️ EXTREM RISIKANT:**
    • EV < -15% (strenger als vorher)
    • Vermeiden - sehr spekulativ
    • Nur 5-10% aller Matches
    
    **2/5 - ⚠️ HOHES RISIKO:**
    • EV -5% bis -15%
    • Nur für erfahrene Wettende
    • 15-20% aller Matches
    
    **3/5 - 📊 MODERATES RISIKO:**
    • EV -5% bis +10% (strenger)
    • Standard-Wetten, normale Vorsicht
    • 60-70% aller Matches
    
    **4/5 - ✅ GERINGES RISIKO:**
    • EV +10% bis +20% (höher als vorher)
    • Gute Wettmöglichkeit
    • 10-15% aller Matches
    
    **5/5 - 🎯 OPTIMALES RISIKO:**
    • EV > +20% + hohe Dominanz
    • Seltene Top-Wetten (nur 2-5%)
    • Erhöhter Einsatz möglich
    
    **Zusätzliche Faktoren:**
    • Datenqualität (Spiele)
    • μ-Total, TKI, PPG-Differenz
    • Quoten-Value, Prob-Dominanz
    """)
    
    # NEU: Tracking Info
    st.markdown("---")
    st.subheader("📈 Tracking Status")
    
    # Prüfe ob Tracking konfiguriert ist
    if "tracking" in st.secrets:
        tracking_secrets = st.secrets["tracking"]
        sheet_id_found = False
        
        for key in ['sheet_id', 'sheet_id_v411', 'sheet_id_v49', 'sheet_id_v48', 'sheet_id_v47']:
            if key in tracking_secrets:
                sheet_id_found = True
                st.success(f"✅ Tracking aktiv ({key})")
                break
        
        if not sheet_id_found:
            st.warning("⚠️ Tracking konfiguriert, aber keine sheet_id gefunden")
    else:
        st.info("ℹ️ Tracking nicht konfiguriert")
        st.caption("Füge 'tracking' section zu Streamlit Secrets hinzu")
    
    # NEU: Debug-Modus Toggle
    st.markdown("---")
    if st.session_state.get('debug_mode', False):
        st.success("🔧 Debug-Modus aktiv")
    else:
        st.info("ℹ️ Debug-Modus inaktiv")
    
    st.caption("Debug-Modus zeigt Tracking-Informationen")

if __name__ == "__main__":
    main()