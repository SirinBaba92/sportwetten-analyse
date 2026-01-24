import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import pandas as pd
import plotly.graph_objects as go
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple
import math

st.set_page_config(page_title="Sportwetten-Prognose v4.9+", page_icon="⚽", layout="wide")

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

# ==================== POISSON FUNKTION ====================
def poisson_probability(lmbda: float, k: int) -> float:
    """Exakte Poisson-Wahrscheinlichkeit"""
    if lmbda <= 0: 
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

# ==================== NEUES RISIKO-SCORING SYSTEM (1-5) ====================
def calculate_extended_risk_scores_v49(prob_1x2_home: float, prob_1x2_draw: float, prob_1x2_away: float,
                                      prob_over: float, prob_under: float,
                                      prob_btts_yes: float, prob_btts_no: float,
                                      odds_1x2: tuple, odds_ou: tuple, odds_btts: tuple,
                                      mu_total: float, tki_combined: float, ppg_diff: float) -> Dict:
    """
    Berechnet Risiko-Scores für alle Wetten + Gesamt-Risiko (1-5)
    1 = Sehr hohes Risiko, 5 = Sehr geringes Risiko
    """
    
    # Hilfsfunktion für Risiko-Beschreibung
    def risk_description(score: int) -> str:
        descriptions = {
            1: "🔴 SEHR RISIKANT",
            2: "🔴 RISIKANT", 
            3: "🟡 NEUTRAL",
            4: "🟢 SICHER",
            5: "🟢 SEHR SICHER"
        }
        return descriptions.get(score, "🟡 NEUTRAL")
    
    # 1. RISIKO-SCORE FÜR 1X2 (basierend auf Expected Value)
    def calculate_1x2_risk(best_prob: float, best_odds: float) -> int:
        """
        Risiko-Score für 1X2 (1-5)
        1 = Sehr riskant, 5 = Sehr sicher
        """
        # Expected Value Berechnung
        ev = (best_prob / 100) * best_odds - 1
        
        if ev < -0.25:
            return 1  # Sehr schlechte Wette
        elif ev < -0.1:
            return 2  # Risikoreich
        elif ev < 0.05:
            return 3  # Neutral
        elif ev < 0.15:
            return 4  # Gute Wette
        else:
            return 5  # Sehr gute Wette
    
    # Beste 1X2 Option finden
    best_1x2_prob = max(prob_1x2_home, prob_1x2_draw, prob_1x2_away)
    if best_1x2_prob == prob_1x2_home:
        best_1x2_odds = odds_1x2[0]
        best_1x2_market = "Heimsieg"
    elif best_1x2_prob == prob_1x2_draw:
        best_1x2_odds = odds_1x2[1]
        best_1x2_market = "Unentschieden"
    else:
        best_1x2_odds = odds_1x2[2]
        best_1x2_market = "Auswärtssieg"
    
    risk_1x2 = calculate_1x2_risk(best_1x2_prob, best_1x2_odds)
    
    # 2. RISIKO-SCORE FÜR OVER/UNDER
    def calculate_ou_risk(prob: float, odds: float) -> int:
        """Risiko-Score für Over/Under (1-5)"""
        ev = (prob / 100) * odds - 1
        
        if ev < -0.25:
            return 1
        elif ev < -0.1:
            return 2
        elif ev < 0.05:
            return 3
        elif ev < 0.15:
            return 4
        else:
            return 5
    
    risk_over = calculate_ou_risk(prob_over, odds_ou[0])
    risk_under = calculate_ou_risk(prob_under, odds_ou[1])
    
    # 3. RISIKO-SCORE FÜR BTTS
    risk_btts_yes = calculate_ou_risk(prob_btts_yes, odds_btts[0])
    risk_btts_no = calculate_ou_risk(prob_btts_no, odds_btts[1])
    
    # 4. GESAMT-RISIKO-SCORE (1-5) basierend auf allen Faktoren
    def calculate_overall_risk(risk_1x2: int, risk_over: int, risk_under: int, 
                              risk_btts_yes: int, risk_btts_no: int,
                              best_1x2_prob: float, mu_total: float, 
                              tki_combined: float, ppg_diff: float) -> Dict:
        """
        Gesamt-Risiko-Score 1-5
        1 = Sehr hohes Risiko
        2 = Hohes Risiko  
        3 = Moderates Risiko
        4 = Geringes Risiko
        5 = Sehr geringes Risiko
        """
        # Basis-Score aus Einzel-Risikos (gewichteter Durchschnitt)
        avg_risk = (risk_1x2 * 0.4 +  # 1X2 hat höchste Gewichtung
                   ((risk_over + risk_under) / 2) * 0.3 +
                   ((risk_btts_yes + risk_btts_no) / 2) * 0.3)
        
        # Anpassungen basierend auf Match-Charakteristika
        adjustments = 0.0
        
        # μ-Total Anpassung (torreiche Spiele = riskanter)
        if mu_total > 4.5:
            adjustments -= 1.2
        elif mu_total > 4.0:
            adjustments -= 0.8
        elif mu_total > 3.5:
            adjustments -= 0.4
        elif mu_total < 2.0:
            adjustments += 0.4
        
        # TKI Anpassung (Torwart-Krise = riskanter)
        if tki_combined > 1.0:
            adjustments -= 1.0
        elif tki_combined > 0.8:
            adjustments -= 0.5
        elif tki_combined > 0.6:
            adjustments -= 0.3
        
        # PPG Differenz (klarer Favorit = sicherer)
        ppg_diff_abs = abs(ppg_diff)
        if ppg_diff_abs > 1.5:
            adjustments += 1.0
        elif ppg_diff_abs > 1.0:
            adjustments += 0.5
        elif ppg_diff_abs > 0.5:
            adjustments += 0.2
        
        # Wahrscheinlichkeits-Anpassung (klare Favoriten = sicherer)
        if best_1x2_prob > 70:
            adjustments += 0.8
        elif best_1x2_prob > 60:
            adjustments += 0.4
        elif best_1x2_prob < 35:
            adjustments -= 0.5
        
        # Finalen Score berechnen (1-5)
        final_score = avg_risk + adjustments
        final_score = max(1, min(5, round(final_score)))
        
        # Kategorie und Empfehlung
        if final_score == 1:
            category = "🔴 SEHR HOHES RISIKO"
            recommendation = "Extrem spekulativ - Vermeiden"
            color = "darkred"
            score_text = "1/5"
        elif final_score == 2:
            category = "🔴 HOHES RISIKO"
            recommendation = "Nur für erfahrene Wettende"
            color = "red"
            score_text = "2/5"
        elif final_score == 3:
            category = "🟡 MODERATES RISIKO"
            recommendation = "Standard-Risiko - Mit Vorsicht"
            color = "yellow"
            score_text = "3/5"
        elif final_score == 4:
            category = "🟢 GERINGES RISIKO"
            recommendation = "Solide Wettmöglichkeit"
            color = "lightgreen"
            score_text = "4/5"
        else:  # final_score == 5
            category = "🟢 SEHR GERINGES RISIKO"
            recommendation = "Gute Basis für Wetten"
            color = "green"
            score_text = "5/5"
        
        return {
            'score': final_score,
            'score_text': score_text,
            'category': category,
            'recommendation': recommendation,
            'color': color,
            'details': {
                'average_risk': round(avg_risk, 2),
                'adjustments': round(adjustments, 2),
                'mu_total_impact': mu_total,
                'tki_impact': tki_combined,
                'favorite_prob': best_1x2_prob,
                'ppg_diff_abs': ppg_diff_abs
            }
        }
    
    # Gesamt-Risiko berechnen
    overall_risk = calculate_overall_risk(
        risk_1x2, risk_over, risk_under, risk_btts_yes, risk_btts_no,
        best_1x2_prob, mu_total, tki_combined, ppg_diff
    )
    
    return {
        'overall': overall_risk,
        '1x2': {
            'market': best_1x2_market,
            'probability': best_1x2_prob,
            'odds': best_1x2_odds,
            'risk_score': risk_1x2,
            'risk_text': risk_description(risk_1x2)
        },
        'over_under': {
            'over': {
                'probability': prob_over,
                'odds': odds_ou[0],
                'risk_score': risk_over,
                'risk_text': risk_description(risk_over)
            },
            'under': {
                'probability': prob_under,
                'odds': odds_ou[1],
                'risk_score': risk_under,
                'risk_text': risk_description(risk_under)
            }
        },
        'btts': {
            'yes': {
                'probability': prob_btts_yes,
                'odds': odds_btts[0],
                'risk_score': risk_btts_yes,
                'risk_text': risk_description(risk_btts_yes)
            },
            'no': {
                'probability': prob_btts_no,
                'odds': odds_btts[1],
                'risk_score': risk_btts_no,
                'risk_text': risk_description(risk_btts_no)
            }
        }
    }

# ==================== v4.9 ANALYSE FUNKTION (UNVERÄNDERT) ====================
def analyze_match_v49(match: MatchData) -> Dict:
    """
    v4.9 SMART-PRECISION LOGIK
    
    NEU in v4.9:
    - TKI-Krise deaktiviert BTTS-Dominanz-Killer
    - FTS-Check nur bei PPG > 1.0 (nicht 0.5)
    - Form-Boost bei starker Defensive reduziert
    - TKI-Krise überschreibt Form-Malus
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
    
    # H2H Analyse
    h2h_stats = analyze_h2h(match.home_team, match.away_team, match.h2h_results)
    
    # NEU: Erweitertes Risiko-Scoring
    extended_risk = calculate_extended_risk_scores_v49(
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
        ppg_diff=ppg_diff
    )
    
    return {
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
        'extended_risk': extended_risk,  # NEU: Erweitertes Risiko-Scoring
        'odds': {
            '1x2': match.odds_1x2,
            'ou25': match.odds_ou25,
            'btts': match.odds_btts
        }
    }

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

# ==================== OPTIMIERTE ANZEIGE FUNKTION ====================
def display_results_v49(result):
    """Zeigt die Analyseergebnisse mit neuem Risiko-Scoring an"""
    st.header(f"🎯 {result['match_info']['home']} vs {result['match_info']['away']}")
    st.caption(f"📅 {result['match_info']['date']} | {result['match_info']['kickoff']} Uhr | {result['match_info']['competition']}")
    
    # Smart-Precision Info
    st.subheader("🧠 SMART-PRECISION v4.9+")
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
    
    # NEU: ERWEITERTE RISIKO-ANALYSE
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
        # NEU: Score als Zahl + Text
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

# ==================== ALERT-SYSTEM (UNVERÄNDERT) ====================
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

# ==================== GOOGLE SHEETS FUNKTIONEN (UNVERÄNDERT) ====================
@st.cache_resource
def connect_to_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    
    try:
        # Prüfe ob Secrets existieren
        if 'gcp_service_account' not in st.secrets:
            st.error("❌ Google Sheets Credentials nicht gefunden")
            st.info("Bitte in Streamlit Cloud Secrets einrichten")
            return None
        
        # Secrets als JSON String parsen
        import json
        creds_json = st.secrets["gcp_service_account"]
        creds_info = json.loads(creds_json)
        
        # Credentials erstellen
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        service = build('sheets', 'v4', credentials=creds)
        return service
        
    except Exception as e:
        st.error(f"❌ Fehler bei Google Sheets Verbindung: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

@st.cache_data(ttl=300)
def get_all_worksheets(sheet_url):
    try:
        service = connect_to_sheets()
        spreadsheet_id = sheet_url.split('/d/')[1].split('/')[0]
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = sheet_metadata.get('sheets', [])
        return {sheet['properties']['title']: sheet['properties']['sheetId'] for sheet in sheets}
    except Exception as e:
        st.error(f"❌ Fehler: {e}")
        return None

def read_worksheet_data(sheet_url, sheet_name):
    try:
        service = connect_to_sheets()
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

# ==================== DATA PARSER (UNVERÄNDERT - KOPIERT VON OBEN) ====================
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
    st.title("⚽ SPORTWETTEN-PROGNOSEMODELL v4.9+")
    st.markdown("### v4.9+ PRECISION+ mit **ERWEITERTEM RISIKO-SCORING (1-5)**")
    st.markdown("**Neu:** Gesamt-Risiko 1-5 + individuelle Wetten-Risikos")
    st.markdown("---")
    
    st.subheader("📊 Schritt 1: Google Sheets Datei")
    sheet_url = st.text_input(
        "Google Sheets URL:",
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
                    
                    for i, (sheet_name, _) in enumerate(worksheets.items()):
                        status_text.text(f"📊 Analysiere {sheet_name}... ({i+1}/{len(worksheets)})")
                        progress_bar.progress((i + 1) / len(worksheets))
                        
                        match_data = read_worksheet_data(sheet_url, sheet_name)
                        if match_data:
                            try:
                                parser = DataParser()
                                match = parser.parse(match_data)
                                result = analyze_match_v49(match)
                                all_results.append({'sheet_name': sheet_name, 'result': result})
                            except Exception as e:
                                st.error(f"❌ Fehler bei {sheet_name}: {e}")
                    
                    status_text.text("✅ Alle Analysen abgeschlossen!")
                    progress_bar.empty()
                    
                    # Übersicht
                    st.markdown("---")
                    st.header("📊 ÜBERSICHT ALLER MATCHES")
                    
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
                    
                    # Detailansichten
                    st.markdown("---")
                    st.header("📋 DETAILLIERTE ANALYSEN")
                    for item in all_results:
                        with st.expander(f"🎯 {item['sheet_name']} - {item['result']['predicted_score']}", expanded=False):
                            display_results_v49(item['result'])
            
            elif selected_worksheet:
                if st.button(f"🔄 '{selected_worksheet}' analysieren", type="primary", use_container_width=True, 
                           key=f"analyze_single_{selected_worksheet}"):
                    with st.spinner(f"⚙️ Analysiere {selected_worksheet}..."):
                        match_data = read_worksheet_data(sheet_url, selected_worksheet)
                        
                        if match_data:
                            try:
                                parser = DataParser()
                                match = parser.parse(match_data)
                                result = analyze_match_v49(match)
                                
                                st.success("✅ Analyse abgeschlossen!")
                                st.markdown("---")
                                display_results_v49(result)
                                
                            except Exception as e:
                                st.error(f"❌ Fehler bei der Analyse: {e}")
                                st.info("Stelle sicher, dass die Tabellendaten korrekt formatiert sind.")

# ==================== SIDEBAR ====================
with st.sidebar:
    st.header("⚙️ v4.9+ Einstellungen & Tools")
    
    st.subheader("🆕 v4.9+ Changelog")
    with st.expander("Was ist neu?"):
        st.markdown("""
        **🚀 NEUES RISIKO-SCORING SYSTEM:**
        
        **Gesamt-Risiko (1-5):**
        - 1 = 🔴 Sehr hohes Risiko
        - 2 = 🔴 Hohes Risiko
        - 3 = 🟡 Moderates Risiko  
        - 4 = 🟢 Geringes Risiko
        - 5 = 🟢 Sehr geringes Risiko
        
        **Individuelle Wetten-Risikos:**
        - ✅ 1X2: Risiko-Score basierend auf EV
        - ✅ Over/Under: Getrennte Scores für Over/Under
        - ✅ BTTS: Getrennte Scores für Ja/Nein
        
        **Faktoren im Gesamt-Risiko:**
        - μ-Total (Tore erwartet)
        - TKI (Torwart-Krise)
        - PPG Differenz (Dominanz)
        - Wahrscheinlichkeit (Favorit)
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
    
    st.subheader("ℹ️ Risiko-Score Legende")
    st.caption("""
    **1/5 - 🔴 SEHR RISIKANT:**
    • Expected Value < -25%
    • Extrem unvorhersehbares Spiel
    • Nur für Spekulanten
    
    **2/5 - 🔴 RISIKANT:**
    • Expected Value -10% bis -25%
    • Erhöhte Unvorhersehbarkeit
    • Nur für erfahrene Wettende
    
    **3/5 - 🟡 NEUTRAL:**
    • Expected Value -10% bis +5%
    • Standard-Risiko
    • Mit normaler Vorsicht
    
    **4/5 - 🟢 SICHER:**
    • Expected Value +5% bis +15%
    • Solide Wettmöglichkeit
    • Gute Basis für Wetten
    
    **5/5 - 🟢 SEHR SICHER:**
    • Expected Value > +15%
    • Sehr gute Wettmöglichkeit
    • Empfohlene Basiswette
    """)
    
    # NEU: Schnellsuche in Sidebar
    st.markdown("---")
    st.subheader("🔍 Schnellsuche Tipps")
    st.caption("""
    **Suche nach:**
    • Teamnamen (z.B. "Bayern", "Real")
    • Ligen (z.B. "Bundesliga", "Premier")
    • Datum (z.B. "2024", "Samstag")
    • Kombinationen (z.B. "Bayern Bundesliga")
    """)

if __name__ == "__main__":
    main()