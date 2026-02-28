"""
UI-Komponenten für Ergebnis-Anzeige
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from typing import Dict, List
from collections import Counter
from models.risk_management import calculate_stake_recommendation
from analysis.validation import check_alerts


def _display_ml_predictions_inline(result: Dict):
    """
    Zeigt ML Predictions im gleichen Format wie Score-Vorhersage
    Lädt ECHTE Match-Daten aus Google Sheets!
    
    Args:
        result: Analyse-Ergebnis Dictionary
    """
    try:
        # Importiere benötigte Module
        from ml.football_ml_models import get_ml_models
        from ml.scoreline_predictor import ScorelinePredictor
        from ui.sheets_ml_integration import convert_match_data_to_features
        from data import read_worksheet_text_by_id, DataParser
        
        st.subheader("🤖 Machine Learning Prognose")
        
        # Lade Models
        ml_models = get_ml_models()
        
        if not ml_models.models_loaded:
            st.info("💡 ML Models nicht verfügbar. Nutze Tab 6 für manuelle ML Predictions.")
            return
        
        # Hole Match Info aus result
        match_info = result.get('match_info', {})
        home_team = match_info.get('home', '')
        away_team = match_info.get('away', '')
        match_date = match_info.get('date', '')
        
        if not home_team or not away_team:
            st.warning("⚠️ Match-Info fehlt")
            return
        
        # Versuche Match aus Google Sheets zu laden
        with st.spinner(f"🔍 Suche '{home_team} vs {away_team}' in Google Sheets..."):
            match_data = _load_match_from_sheets(home_team, away_team, match_date)
        
        if not match_data:
            # Fallback: Zeige Info dass Sheets-Daten benötigt werden
            st.info(f"""
            💡 **Match nicht in Google Sheets gefunden**
            
            Gesucht: **{home_team} vs {away_team}**
            Datum: {match_date or 'N/A'}
            
            **Mögliche Gründe:**
            - Match-Daten noch nicht in Sheets
            - Team-Namen unterscheiden sich (z.B. "FC Augsburg" vs "Augsburg")
            - Match in anderem Tabellenblatt
            
            **Für vollständige ML Predictions:**
            → Nutze Tab 6 "ML Predictions" und wähle Match aus der Liste
            """)
            return
        
        # Konvertiere zu Features
        features = convert_match_data_to_features(match_data)
        
        # Hole Predictions (MIT Quoten)
        predictions = ml_models.predict_all(features, use_odds=True)
        
        # Erstelle Scoreline Predictor
        scoreline_pred = ScorelinePredictor()
        
        # Berechne xG aus Features
        home_xg = features.get('home_avg_goals_scored_overall', 1.5) * 1.15
        away_xg = features.get('away_avg_goals_scored_overall', 1.3) * 0.95
        
        # Generiere Scorelines
        scorelines = scoreline_pred.predict_scorelines(home_xg, away_xg, top_n=5)
        best_scoreline = scorelines[0] if scorelines else None
        
        # Display im gleichen 4-Spalten Format
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # 1X2
            if '1x2' in predictions:
                pred_1x2 = predictions['1x2']
                label_map = {
                    'HOME WIN': 'Heimsieg',
                    'DRAW': 'Unentschieden',
                    'AWAY WIN': 'Auswärtssieg'
                }
                pred_label = label_map.get(pred_1x2['prediction'], pred_1x2['prediction'])
                st.success(
                    f"### 🎯 1X2\n\n"
                    f"**{pred_label}**\n\n"
                    f"# {pred_1x2['confidence']:.1f}%"
                )
        
        with col2:
            # Over/Under
            if 'over_under' in predictions:
                pred_ou = predictions['over_under']
                st.success(
                    f"### 📈 Over/Under 2.5\n\n"
                    f"**{pred_ou['prediction']}**\n\n"
                    f"# {pred_ou['confidence']:.1f}%"
                )
        
        with col3:
            # BTTS
            if 'btts' in predictions:
                pred_btts = predictions['btts']
                label_map = {'BTTS YES': 'BTTS Ja', 'BTTS NO': 'BTTS Nein'}
                pred_label = label_map.get(pred_btts['prediction'], pred_btts['prediction'])
                st.success(
                    f"### ⚽ BTTS\n\n"
                    f"**{pred_label}**\n\n"
                    f"# {pred_btts['confidence']:.1f}%"
                )
        
        with col4:
            # Wahrscheinlichstes Ergebnis
            if best_scoreline:
                st.success(
                    f"### 🏆 Wahrscheinlichstes Ergebnis\n\n"
                    f"# {best_scoreline['scoreline']}\n\n"
                    f"**Wahrscheinlichkeit:**\n"
                    f"# {best_scoreline['probability']:.1f}%"
                )
        
        # Konsens-Analyse
        _show_consensus_analysis(result, predictions, best_scoreline)
        
        # Erfolgs-Hinweis
        st.caption(f"✅ ML Predictions basieren auf echten Match-Daten aus Google Sheets")
        
    except Exception as e:
        # Stilles Fallback - zeige nur Info
        st.info("""
        💡 **ML Predictions mit vollständigen Daten:**
        → Nutze Tab 6 "ML Predictions" für Predictions mit allen Match-Stats
        """)


def _load_match_from_sheets(home_team: str, away_team: str, match_date: str):
    """
    Lädt Match-Daten aus Google Sheets basierend auf Team-Namen
    
    Returns:
        MatchData object oder None
    """
    try:
        from data import list_daily_sheets_in_folder, read_worksheet_text_by_id, DataParser
        
        # Hole Folder ID aus Session State
        folder_id = st.session_state.get('folder_id')
        if not folder_id:
            return None
        
        # Liste alle Sheets
        date_to_id = list_daily_sheets_in_folder(folder_id)
        
        if not date_to_id:
            return None
        
        # Finde das richtige Sheet (probiere aktuelles Datum oder alle)
        sheet_ids_to_check = []
        
        # Wenn Datum bekannt, versuche genau dieses Sheet
        if match_date and match_date in date_to_id:
            sheet_ids_to_check.append(date_to_id[match_date])
        
        # Sonst probiere die letzten 3 Sheets
        sorted_dates = sorted(date_to_id.keys(), reverse=True)[:3]
        for d in sorted_dates:
            if date_to_id[d] not in sheet_ids_to_check:
                sheet_ids_to_check.append(date_to_id[d])
        
        # Durchsuche Sheets
        parser = DataParser()
        
        for sheet_id in sheet_ids_to_check:
            try:
                # Hole alle Tabs
                from data.google_sheets import connect_to_sheets
                service = connect_to_sheets()
                if not service:
                    continue
                
                metadata = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                sheets = metadata.get('sheets', [])
                
                # Durchsuche alle Tabs
                for sheet in sheets:
                    tab_name = sheet['properties']['title']
                    
                    # Prüfe ob Tab-Name zu Teams passt
                    if _match_names_in_tab(tab_name, home_team, away_team):
                        # Lade und parse
                        match_text = read_worksheet_text_by_id(sheet_id, tab_name)
                        if match_text:
                            match_data = parser.parse(match_text)
                            return match_data
                            
            except Exception:
                continue
        
        return None
        
    except Exception:
        return None


def _match_names_in_tab(tab_name: str, home_team: str, away_team: str) -> bool:
    """
    Prüft ob Tab-Name die Team-Namen enthält
    Sehr tolerant für verschiedene Schreibweisen
    """
    def normalize_team_name(name: str) -> str:
        """Normalisiert Team-Namen für Vergleich"""
        name = name.lower().strip()
        
        # Entferne häufige Präfixe und Suffixe
        removals = [
            'fc ', ' fc', 'cf ', ' cf', 'sc ', ' sc', 'sv ', ' sv',
            'ac ', ' ac', 'rc ', ' rc', 'asc ', ' asc',
            'bfc ', ' bfc', 'ssc ', ' ssc',
            'united', 'city', 'town', 'athletic', 'rovers',
            'wanderers', 'albion', 'county', 'borough',
            '1. ', '1.fc ', 'fc.', 'e.v.', ' ii', ' iii',
            'vfl ', ' vfl', 'tsv ', ' tsv', 'sv ', ' sv'
        ]
        
        for removal in removals:
            name = name.replace(removal, ' ')
        
        # Entferne Zahlen am Anfang
        import re
        name = re.sub(r'^\d+\.?\s*', '', name)
        
        # Entferne mehrfache Leerzeichen
        name = ' '.join(name.split())
        
        return name.strip()
    
    # Normalisiere alle Namen
    tab_normalized = normalize_team_name(tab_name)
    home_normalized = normalize_team_name(home_team)
    away_normalized = normalize_team_name(away_team)
    
    # CHECK 1: Volle Namen
    if home_normalized in tab_normalized and away_normalized in tab_normalized:
        return True
    
    # CHECK 2: Erste Wörter (Hauptname)
    home_first = home_normalized.split()[0] if home_normalized else ''
    away_first = away_normalized.split()[0] if away_normalized else ''
    
    if len(home_first) >= 4 and len(away_first) >= 4:  # Mindestens 4 Buchstaben
        if home_first in tab_normalized and away_first in tab_normalized:
            return True
    
    # CHECK 3: Enthält beide Kernwörter (längste Wörter)
    def get_core_word(name: str) -> str:
        """Findet das längste Wort (meist der Hauptname)"""
        words = name.split()
        if not words:
            return ''
        # Ignoriere sehr kurze Wörter
        words = [w for w in words if len(w) >= 4]
        return max(words, key=len) if words else words[0] if words else ''
    
    home_core = get_core_word(home_normalized)
    away_core = get_core_word(away_normalized)
    
    if home_core and away_core:
        if home_core in tab_normalized and away_core in tab_normalized:
            return True
    
    # CHECK 4: Teilstring-Match mit mindestens 5 Zeichen
    if len(home_normalized) >= 5 and len(away_normalized) >= 5:
        # Nimm erste 5+ Zeichen
        home_prefix = home_normalized[:max(5, len(home_normalized)//2)]
        away_prefix = away_normalized[:max(5, len(away_normalized)//2)]
        
        if home_prefix in tab_normalized and away_prefix in tab_normalized:
            return True
    
    return False


def _show_consensus_analysis(result: Dict, ml_predictions: Dict, ml_scoreline: Dict):
    """
    Zeigt Konsens zwischen SMART-PRECISION und ML
    """
    try:
        # Extrahiere SMART-PRECISION Predictions
        probs = result.get("probabilities", {})
        
        smart_1x2 = "Heimsieg" if probs.get("home_win", 0) >= max(probs.get("draw", 0), probs.get("away_win", 0)) else (
            "Unentschieden" if probs.get("draw", 0) >= probs.get("away_win", 0) else "Auswärtssieg"
        )
        smart_ou = "Over 2.5" if probs.get("over_25", 0) >= probs.get("under_25", 0) else "Under 2.5"
        smart_btts = "BTTS Ja" if probs.get("btts_yes", 0) >= probs.get("btts_no", 0) else "BTTS Nein"
        smart_score = result.get("predicted_score", "N/A")
        
        # Extrahiere ML Predictions
        ml_1x2_raw = ml_predictions.get('1x2', {}).get('prediction', '')
        ml_1x2 = {'HOME WIN': 'Heimsieg', 'DRAW': 'Unentschieden', 'AWAY WIN': 'Auswärtssieg'}.get(ml_1x2_raw, ml_1x2_raw)
        ml_ou = ml_predictions.get('over_under', {}).get('prediction', '')
        ml_btts_raw = ml_predictions.get('btts', {}).get('prediction', '')
        ml_btts = {'BTTS YES': 'BTTS Ja', 'BTTS NO': 'BTTS Nein'}.get(ml_btts_raw, ml_btts_raw)
        ml_score = ml_scoreline.get('scoreline', 'N/A') if ml_scoreline else 'N/A'
        
        # Check Konsens
        consensus_items = []
        
        if smart_1x2 == ml_1x2:
            consensus_items.append(smart_1x2)
        if smart_ou == ml_ou:
            consensus_items.append(ml_ou)
        if smart_btts == ml_btts:
            consensus_items.append(ml_btts)
        if smart_score == ml_score:
            consensus_items.append(f"Score: {smart_score}")
        
        if len(consensus_items) >= 2:
            st.success(
                f"### ✅ Konsens-Analyse\n\n"
                f"**Beide Systeme einig bei:** {', '.join(consensus_items)}\n\n"
                f"🎯 **HOHE CONFIDENCE!**"
            )
        elif len(consensus_items) == 1:
            st.info(
                f"### 📊 Konsens-Analyse\n\n"
                f"**Übereinstimmung:** {consensus_items[0]}\n\n"
                f"⚠️ Andere Markets unterscheiden sich - Vorsicht!"
            )
        else:
            st.warning(
                f"### ⚠️ Konsens-Analyse\n\n"
                f"**Keine Übereinstimmung** zwischen den Systemen.\n\n"
                f"💡 Bei Uneinigkeit: höhere Vorsicht oder Skip!"
            )
            
    except Exception as e:
        # Stilles Ignorieren wenn Konsens nicht berechnet werden kann
        pass


def display_stake_recommendation(
    risk_score: int, odds: float, market_name: str, match_info: str = ""
):
    """
    Zeigt Einsatzempfehlung basierend auf Risiko-Score mit konsistenter Farbcodierung

    Args:
        risk_score: Risiko-Score 1-5
        odds: Wett-Quote
        market_name: Name des Markets
        match_info: Match-Information
    """
    from config.constants import RISK_PROFILES

    stake_info = calculate_stake_recommendation(
        risk_score, odds, market_name, match_info
    )

    st.markdown("---")

    # Konsistente Farbcodierung
    risk_colors = {
        1: "🔴",  # Rot
        2: "🟠",  # Orange
        3: "🟡",  # Gelb
        4: "🟢",  # Hellgrün
        5: "🟩",  # Grün
    }

    color_emoji = risk_colors.get(risk_score, "⚪")

    st.subheader(f"{color_emoji} EINSATZEMPFEHLUNG: {market_name}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label=f"Risiko-Score",
            value=f"{risk_score}/5",
            delta=f"{RISK_PROFILES[st.session_state.risk_management['risk_profile']]['name']}",
        )

    with col2:
        st.metric(
            label="Empfohlener Einsatz",
            value=f"€{stake_info['recommended_stake']}",
            delta=f"{stake_info['adjusted_percentage']}% der Bankroll",
        )

    with col3:
        st.metric(
            label=f"Potentieller Gewinn",
            value=f"+€{stake_info['potential_win']}",
            delta=f"Quote: {odds:.2f}",
        )

    # Demo-Modus: Speichere Wettoptionen
    demo_mode_active = st.session_state.get("enable_demo_mode", False)

    if demo_mode_active and match_info:
        if "demo_bet_options" not in st.session_state:
            st.session_state.demo_bet_options = []

        bet_option = {
            "market": market_name,
            "match_info": match_info,
            "potential_win": stake_info["potential_win"],
            "potential_loss": stake_info["potential_loss"],
            "stake": stake_info["recommended_stake"],
            "unique_id": f"{market_name}_{hash(match_info)}",
        }

        if not any(
            opt["unique_id"] == bet_option["unique_id"]
            for opt in st.session_state.demo_bet_options
        ):
            st.session_state.demo_bet_options.append(bet_option)

        st.caption("🎮 Demo-Modus: Wettauswahl am Ende der Analyse")

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

        with col_c:
            st.markdown("**Konsequenzen:**")
            st.caption(
                f"• Bei Gewinn: +{stake_info['potential_win'] / stake_info['recommended_stake'] * 100:.1f}%"
            )
            st.caption(
                f"• Bei Verlust: -{stake_info['adjusted_percentage']:.1f}% Bankroll"
            )


def display_results(result: Dict):
    """
    Zeigt vollständige Analyse-Ergebnisse an

    Args:
        result: Dictionary mit Analyse-Ergebnissen
    """
    st.header(f"🎯 {result['match_info']['home']} vs {result['match_info']['away']}")
    st.caption(
        f"📅 {result['match_info']['date']} | {result['match_info']['kickoff']} Uhr | {result['match_info']['competition']}"
    )

    # QUICK SUMMARY BOX
    st.markdown("---")
    probs = result["probabilities"]
    overall_risk = result["extended_risk"]["overall"]

    # Finde beste Empfehlung
    prob_1x2_home = probs["home_win"]
    prob_1x2_draw = probs["draw"]
    prob_1x2_away = probs["away_win"]
    best_1x2_prob = max(prob_1x2_home, prob_1x2_draw, prob_1x2_away)

    if prob_1x2_home == best_1x2_prob:
        best_1x2_market = "Heimsieg"
    elif prob_1x2_draw == best_1x2_prob:
        best_1x2_market = "Unentschieden"
    else:
        best_1x2_market = "Auswärtssieg"

    # Stake berechnen (falls Schwellenwert erreicht)
    if best_1x2_prob >= 50:
        best_1x2_risk = result["extended_risk"]["1x2"]
        stake_info = calculate_stake_recommendation(
            best_1x2_risk["risk_score"], best_1x2_risk["odds"], best_1x2_market, ""
        )
        recommended_stake = f"€{stake_info['recommended_stake']}"
    else:
        recommended_stake = "Keine Empfehlung"

    # Risk Color
    risk_colors = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "🟩"}
    risk_emoji = risk_colors.get(overall_risk["score"], "⚪")

    # Summary Box
    st.info(
        f"""
    ### 📊 QUICK SUMMARY
    
    **Top-Empfehlung:** {best_1x2_market} ({best_1x2_prob:.1f}%)  
    **Risiko-Score:** {risk_emoji} {overall_risk['score']}/5 - {overall_risk['category']}  
    **Empfohlener Einsatz:** {recommended_stake}  
    **Predicted Score:** {result['predicted_score']} ({result['scorelines'][0][1]:.1f}% Wahrscheinlichkeit)
    """
    )

    st.markdown("---")

    # Alarm-System
    alerts = check_alerts(
        result["mu"]["home"],
        result["mu"]["away"],
        result["tki"]["home"],
        result["tki"]["away"],
        result["mu"]["ppg_diff"],
        st.session_state.alert_thresholds,
    )

    if alerts:
        st.subheader("🚨 ALARM-SYSTEM")
        for alert in alerts:
            if alert["type"] == "warning":
                st.warning(f"{alert['level']} **{alert['title']}**: {alert['message']}")
            elif alert["type"] == "info":
                st.info(f"{alert['level']} **{alert['title']}**: {alert['message']}")
            elif alert["type"] == "success":
                st.success(f"{alert['level']} **{alert['title']}**: {alert['message']}")

    # SMART-PRECISION Werte
    st.subheader("🧠 SMART-PRECISION v6.0")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Smart μ Home", f"{result['mu']['home']:.2f}")
    with col2:
        st.metric("Smart μ Away", f"{result['mu']['away']:.2f}")
    with col3:
        st.metric("PPG Gap", f"{result['mu']['ppg_diff']:.2f}")

    if result.get("ml_position_correction", {}).get("applied", False):
        st.info(
            f"📊 ML-Korrektur angewandt: {result['ml_position_correction']['message']}"
        )

    # Erweiterte Risiko-Analyse
    st.subheader("⚠️ ERWEITERTE RISIKO-ANALYSE (1-5)")

    overall_risk = result["extended_risk"]["overall"]

    risk_color_map = {1: "darkred", 2: "red", 3: "yellow", 4: "lightgreen", 5: "green"}

    col1, col2, col3 = st.columns([2, 3, 2])
    with col1:
        st.markdown(f"### {overall_risk['score_text']}")
        st.progress(overall_risk["score"] / 5)
    with col2:
        st.markdown(f"**{overall_risk['category']}**")
        st.markdown(f"*{overall_risk['recommendation']}*")
    with col3:
        fig_risk = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=overall_risk["score"],
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "Gesamt-Risiko"},
                gauge={
                    "axis": {"range": [1, 5], "tickwidth": 1},
                    "bar": {"color": risk_color_map.get(overall_risk["score"], "gray")},
                    "steps": [
                        {"range": [1, 2], "color": "lightcoral"},
                        {"range": [2, 3], "color": "lightyellow"},
                        {"range": [3, 4], "color": "lightgreen"},
                        {"range": [4, 5], "color": "green"},
                    ],
                },
            )
        )
        fig_risk.update_layout(height=200)
        st.plotly_chart(fig_risk, use_container_width=True)

    # Einzelne Wett-Risikos
    st.subheader("📊 EINZELNE WETT-RISIKOS")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**🎯 1X2 WETTE**")
        risk_1x2 = result["extended_risk"]["1x2"]
        risk_display = f"{risk_1x2['risk_score']}/5 {risk_1x2['risk_text']}"
        st.metric(
            label=f"{risk_1x2['market']} ({risk_1x2['probability']:.1f}%)",
            value=f"{risk_1x2['odds']:.2f}",
            delta=risk_display,
            delta_color="off",
        )

    with col2:
        st.markdown("**📈 OVER/UNDER 2.5**")
        risk_ou = result["extended_risk"]["over_under"]
        col2a, col2b = st.columns(2)
        with col2a:
            risk_display_over = (
                f"{risk_ou['over']['risk_score']}/5 {risk_ou['over']['risk_text']}"
            )
            st.metric(
                label=f"Over ({risk_ou['over']['probability']:.1f}%)",
                value=f"{risk_ou['over']['odds']:.2f}",
                delta=risk_display_over,
                delta_color="off",
            )
        with col2b:
            risk_display_under = (
                f"{risk_ou['under']['risk_score']}/5 {risk_ou['under']['risk_text']}"
            )
            st.metric(
                label=f"Under ({risk_ou['under']['probability']:.1f}%)",
                value=f"{risk_ou['under']['odds']:.2f}",
                delta=risk_display_under,
                delta_color="off",
            )

    with col3:
        st.markdown("**⚽ BTTS**")
        risk_btts = result["extended_risk"]["btts"]
        col3a, col3b = st.columns(2)
        with col3a:
            risk_display_yes = (
                f"{risk_btts['yes']['risk_score']}/5 {risk_btts['yes']['risk_text']}"
            )
            st.metric(
                label=f"Ja ({risk_btts['yes']['probability']:.1f}%)",
                value=f"{risk_btts['yes']['odds']:.2f}",
                delta=risk_display_yes,
                delta_color="off",
            )
        with col3b:
            risk_display_no = (
                f"{risk_btts['no']['risk_score']}/5 {risk_btts['no']['risk_text']}"
            )
            st.metric(
                label=f"Nein ({risk_btts['no']['probability']:.1f}%)",
                value=f"{risk_btts['no']['odds']:.2f}",
                delta=risk_display_no,
                delta_color="off",
            )

    # Einsatzempfehlungen - nur wenn Schwellenwerte erreicht
    st.markdown("---")

    probs = result["probabilities"]

    # Prüfe welche Markets die Schwellenwerte erreichen
    show_1x2 = False
    show_ou = False
    show_btts = False

    # 1X2: Beste Option >= 50%
    prob_1x2_home = probs["home_win"]
    prob_1x2_draw = probs["draw"]
    prob_1x2_away = probs["away_win"]
    best_1x2_prob = max(prob_1x2_home, prob_1x2_draw, prob_1x2_away)
    if best_1x2_prob >= 50:
        show_1x2 = True

    # Over/Under: Beste Option >= 60%
    prob_over = probs["over_25"]
    prob_under = probs["under_25"]
    best_ou_prob = max(prob_over, prob_under)
    if best_ou_prob >= 60:
        show_ou = True

    # BTTS: Beste Option >= 60%
    prob_btts_yes = probs["btts_yes"]
    prob_btts_no = probs["btts_no"]
    best_btts_prob = max(prob_btts_yes, prob_btts_no)
    if best_btts_prob >= 60:
        show_btts = True

    # Zeige Empfehlungen nur wenn mindestens eine erfüllt ist
    if show_1x2 or show_ou or show_btts:
        # Beste 1X2 Option (wenn >= 50%)
        if show_1x2:
            best_1x2 = result["extended_risk"]["1x2"]
            display_stake_recommendation(
                risk_score=best_1x2["risk_score"],
                odds=best_1x2["odds"],
                market_name=best_1x2["market"],
                match_info=f"{result['match_info']['home']} vs {result['match_info']['away']} - {best_1x2['market']}",
            )

        # Beste Over/Under Option (wenn >= 60%)
        if show_ou:
            ou_risk = result["extended_risk"]["over_under"]
            best_ou = (
                "over"
                if ou_risk["over"]["risk_score"] >= ou_risk["under"]["risk_score"]
                else "under"
            )
            display_stake_recommendation(
                risk_score=ou_risk[best_ou]["risk_score"],
                odds=ou_risk[best_ou]["odds"],
                market_name=f"{best_ou.upper()} 2.5",
                match_info=f"{result['match_info']['home']} vs {result['match_info']['away']} - {best_ou.upper()} 2.5",
            )

        # Beste BTTS Option (wenn >= 60%)
        if show_btts:
            btts_risk = result["extended_risk"]["btts"]
            best_btts = (
                "yes"
                if btts_risk["yes"]["risk_score"] >= btts_risk["no"]["risk_score"]
                else "no"
            )
            display_stake_recommendation(
                risk_score=btts_risk[best_btts]["risk_score"],
                odds=btts_risk[best_btts]["odds"],
                market_name=f"BTTS {best_btts.upper()}",
                match_info=f"{result['match_info']['home']} vs {result['match_info']['away']} - BTTS {best_btts.upper()}",
            )
    else:
        st.info(
            "ℹ️ Keine Einsatzempfehlungen - Schwellenwerte nicht erreicht (1X2: ≥50%, O/U & BTTS: ≥60%)"
        )

    # Risiko-Faktoren Details
    with st.expander("📋 RISIKO-FAKTOREN DETAILS"):
        details = overall_risk["details"]
        col1, col2, col3 = st.columns(3)
        col1.metric("μ-Total", f"{details['mu_total_impact']:.2f}")
        col2.metric("TKI kombiniert", f"{details['tki_impact']:.2f}")
        col3.metric("Beste 1X2 Wahrscheinlichkeit", f"{details['favorite_prob']:.1f}%")
        col1.metric("PPG Differenz", f"{details['ppg_diff_abs']:.2f}")
        col2.metric("Durchschn. Risiko", f"{details['average_risk']:.2f}")
        col3.metric("Anpassungen", f"{details['adjustments']:.2f}")

    # TKI
    st.subheader("🧤 Torwart-Krisen-Index (TKI)")
    col1, col2, col3 = st.columns(3)
    with col1:
        tki_home = result["tki"]["home"]
        status_home = "🚨 KRISE" if tki_home > 0.3 else "✅ Stabil"
        st.metric(result["match_info"]["home"], f"{tki_home:.2f}", status_home)
    with col2:
        tki_away = result["tki"]["away"]
        status_away = "🚨 KRISE" if tki_away > 0.3 else "✅ Stabil"
        st.metric(result["match_info"]["away"], f"{tki_away:.2f}", status_away)
    with col3:
        st.metric("Kombiniert", f"{result['tki']['combined']:.2f}")

    # H2H
    st.subheader("🔄 Head-to-Head Statistik")
    h2h = result["h2h"]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ø Tore/Spiel", f"{h2h['avg_total_goals']:.1f}")
    col2.metric("Ø Heimtore", f"{h2h['avg_home_goals']:.1f}")
    col3.metric("Ø Auswärtstore", f"{h2h['avg_away_goals']:.1f}")
    col4.metric("BTTS-Quote", f"{h2h['btts_percentage'] * 100:.0f}%")

    st.caption(
        f"Bilanz: {h2h['home_wins']} Siege - {h2h['draws']} Remis - {h2h['away_wins']} Niederlagen"
    )

    # Wahrscheinlichkeiten & Quoten
    st.subheader("📈 Wahrscheinlichkeiten & Quoten")
    probs = result["probabilities"]
    odds = result["odds"]

    # Erstelle Daten mit Highlighting
    data = []

    # 1X2 Markets (Schwellenwert: 50%)
    markets = [
        ("Heimsieg", probs["home_win"], odds["1x2"][0], 50),
        ("Remis", probs["draw"], odds["1x2"][1], 50),
        ("Auswärtssieg", probs["away_win"], odds["1x2"][2], 50),
        ("Over 2.5", probs["over_25"], odds["ou25"][0], 60),
        ("Under 2.5", probs["under_25"], odds["ou25"][1], 60),
        ("BTTS Ja", probs["btts_yes"], odds["btts"][0], 60),
        ("BTTS Nein", probs["btts_no"], odds["btts"][1], 60),
    ]

    for market, prob, quote, threshold in markets:
        # Gelbes Emoji wenn Schwellenwert erreicht
        highlight = "🟡 " if prob >= threshold else ""
        data.append(
            {
                "Markt": f"{highlight}{market}",
                "Wahrscheinlichkeit": f"{prob:.1f}%",
                "Quote": f"{quote:.2f}",
            }
        )

    df = pd.DataFrame(data)
    styled_df = df.style.set_properties(
        **{
            "background-color": "#0e1117",
            "color": "white",
            "font-size": "20px",
            "font-weight": "bold",
        }
    )
    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # Score-Vorhersage - OPTIMIERTE VERSION
    st.subheader("📊 Score-Vorhersage")

    # Verwende 4 Spalten statt 3 für bessere Aufteilung
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # 1X2 mit größerer Schrift
        best_1x2 = (
            "Heimsieg"
            if probs["home_win"] >= probs["draw"]
            and probs["home_win"] >= probs["away_win"]
            else (
                "Unentschieden"
                if probs["draw"] >= probs["away_win"]
                else "Auswärtssieg"
            )
        )
        best_1x2_prob = max(probs["home_win"], probs["draw"], probs["away_win"])
        # Grüner Hintergrund wie st.success(), größere Schrift
        st.success(f"### 🎯 1X2\n\n" f"**{best_1x2}**\n\n" f"# {best_1x2_prob:.1f}%")

    with col2:
        # Over/Under 2.5 - separate Box
        best_ou = "Over 2.5" if probs["over_25"] >= probs["under_25"] else "Under 2.5"
        best_ou_prob = max(probs["over_25"], probs["under_25"])
        st.success(
            f"### 📈 Over/Under 2.5\n\n" f"**{best_ou}**\n\n" f"# {best_ou_prob:.1f}%"
        )

    with col3:
        # BTTS - separate Box
        best_btts = "BTTS Ja" if probs["btts_yes"] >= probs["btts_no"] else "BTTS Nein"
        best_btts_prob = max(probs["btts_yes"], probs["btts_no"])
        st.success(f"### ⚽ BTTS\n\n" f"**{best_btts}**\n\n" f"# {best_btts_prob:.1f}%")

    with col4:
        # Wahrscheinlichstes Ergebnis - größte Box
        if result["scorelines"]:
            predicted_score = result["predicted_score"]
            score_prob = result["scorelines"][0][1]
            st.success(
                f"### 🏆 Wahrscheinlichstes Ergebnis\n\n"
                f"# {predicted_score}\n\n"
                f"**Wahrscheinlichkeit:**\n"
                f"# {score_prob:.1f}%"
            )

    # ========================================================================
    # ML PREDICTIONS - DIREKT HIER!
    # ========================================================================
    st.markdown("---")
    _display_ml_predictions_inline(result)
    
    # Export zu Google Sheets
    st.markdown("---")
    st.subheader("📤 Export zu Google Sheets")

    # Letztes Analyse-Ergebnis speichern (damit Export nach Rerun funktioniert)
    st.session_state["_last_analysis_result"] = result

    def _trigger_simple_export():
        st.session_state["_do_export_simple"] = True

    def _trigger_export_with_result():
        h = st.session_state.get("exp_home_rd", 0)
        a = st.session_state.get("exp_away_rd", 0)
        st.session_state["_export_actual_score"] = f"{h}-{a}"
        st.session_state["_do_export_with_result"] = True

    col_export, col_actual = st.columns(2)
    with col_export:
        st.button(
            "💾 Analyse exportieren",
            use_container_width=True,
            key="export_btn_simple_rd",
            on_click=_trigger_simple_export,
        )

    with col_actual:
        st.caption("Optional: Tatsächliches Ergebnis für Export")
        c1, c2 = st.columns(2)
        with c1:
            st.number_input("Heim", 0, 10, 0, key="exp_home_rd")
        with c2:
            st.number_input("Auswärts", 0, 10, 0, key="exp_away_rd")
        st.button(
            "📤 Mit Ergebnis exportieren",
            use_container_width=True,
            key="export_btn_with_result_rd",
            on_click=_trigger_export_with_result,
        )

    # Exporte ausführen (klick-sicher nach Render)
    export_result = st.session_state.get("_last_analysis_result")
    if st.session_state.get("_do_export_simple"):
        st.session_state["_do_export_simple"] = False
        from models import export_analysis_to_sheets

        with st.spinner("Exportiere Analyse..."):
            ok = export_analysis_to_sheets(export_result)
        if ok:
            st.success("✅ Analyse exportiert!")
            st.balloons()
        else:
            st.error("❌ Export fehlgeschlagen")

    if st.session_state.get("_do_export_with_result"):
        st.session_state["_do_export_with_result"] = False
        actual_score = st.session_state.get("_export_actual_score")
        from models import export_analysis_to_sheets

        with st.spinner(f"Exportiere mit Ergebnis {actual_score}..."):
            ok = export_analysis_to_sheets(export_result, actual_score)
        if ok:
            st.success(f"✅ Mit Ergebnis {actual_score} exportiert!")
            st.balloons()
        else:
            st.error("❌ Export fehlgeschlagen")

    # Visualisierungen
    st.markdown("---")
    st.subheader("📈 Visualisierungen")

    # Import Visualisierungs-Funktionen
    from ui.visualizations import (
        show_poisson_heatmap,
        show_historical_performance,
        show_confidence_gauge,
        show_team_radar,
    )

    viz_tab1, viz_tab2, viz_tab3, viz_tab4 = st.tabs(
        [
            "📊 Poisson-Verteilung",
            "📈 Historische Performance",
            "🎲 Confidence-Level",
            "🕸️ Team-Radar",
        ]
    )

    with viz_tab1:
        show_poisson_heatmap(result)

    with viz_tab2:
        show_historical_performance()

    with viz_tab3:
        show_confidence_gauge(result)

    with viz_tab4:
        try:
            show_team_radar(result)
        except Exception as e:
            st.warning(f"⚠️ Radar-Chart nicht verfügbar: {str(e)}")
            st.info("Das Team-Radar-Chart benötigt vollständige Match-Daten.")


def display_risk_distribution(all_results: List[Dict]):
    """
    Zeigt Risiko-Score Verteilung über alle Matches

    Args:
        all_results: Liste von Analyse-Ergebnissen
    """
    if not all_results:
        return

    scores = []
    for item in all_results:
        if "result" in item and "extended_risk" in item["result"]:
            scores.append(item["result"]["extended_risk"]["overall"]["score"])

    if not scores:
        return

    distribution = Counter(scores)
    total = len(scores)

    st.markdown("---")
    st.subheader("📈 Risiko-Score Verteilung")
    st.caption("Zeigt wie viele Matches jedem Risiko-Level zugeordnet wurden")

    cols = st.columns(5)
    colors = ["darkred", "red", "yellow", "lightgreen", "green"]
    labels = ["1/5 Extrem", "2/5 Hoch", "3/5 Moderat", "4/5 Gering", "5/5 Optimal"]

    for i in range(1, 6):
        count = distribution.get(i, 0)
        percentage = (count / total) * 100 if total > 0 else 0

        with cols[i - 1]:
            st.metric(
                label=labels[i - 1],
                value=f"{count}",
                delta=f"{percentage:.1f}%",
                delta_color="off",
            )
            st.progress(min(percentage / 100, 1.0))

    score_5_pct = (distribution.get(5, 0) / total * 100) if total > 0 else 0
    score_3_pct = (distribution.get(3, 0) / total * 100) if total > 0 else 0

    st.markdown("---")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("### 📊 Verteilungs-Analyse")

        if score_5_pct > 10:
            st.warning(
                f"⚠️ **Zu viele 5/5 Bewertungen** ({score_5_pct:.1f}%) - Scoring könnte zu liberal sein!"
            )
        elif score_5_pct < 1 and total > 20:
            st.info(
                f"ℹ️ Sehr wenige 5/5 Bewertungen ({score_5_pct:.1f}%) - Scoring ist sehr streng"
            )
        elif score_5_pct >= 2 and score_5_pct <= 5:
            st.success(
                f"✅ Optimale 5/5 Verteilung ({score_5_pct:.1f}%) - Scoring funktioniert gut!"
            )

        if score_3_pct > 75:
            st.info(
                "ℹ️ Sehr viele 3/5 Bewertungen - Die meisten Wetten sind moderat riskant"
            )
        elif score_3_pct < 50:
            st.warning("⚠️ Wenige 3/5 Bewertungen - Ungewöhnliche Verteilung")

    with col2:
        st.markdown("### 🎯 Ziel-Verteilung")
        st.caption(
            """
        **Ideal:**
        - 5/5: 2-5%
        - 4/5: 10-15%
        - 3/5: 60-70%
        - 2/5: 15-20%
        - 1/5: 5-10%
        """
        )
