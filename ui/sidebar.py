"""
Sidebar UI-Komponente
"""

import streamlit as st
import pandas as pd
from config.constants import RISK_PROFILES, APP_VERSION, APP_FEATURES
from data.google_sheets import get_tracking_sheet_id, connect_to_sheets
from models.tracking import update_match_result_in_sheets


def show_sidebar():
    """
    Zeigt die Sidebar mit allen Einstellungen und Funktionen
    """
    with st.sidebar:
        st.title("⚙️ Einstellungen")

        # Risk Management
        st.markdown("---")
        st.subheader("💰 Risk Management")

        demo_mode = st.session_state.get("enable_demo_mode", False)

        # Bankroll - read-only im Demo-Modus
        current_bankroll = st.session_state.risk_management["bankroll"]

        if demo_mode:
            st.number_input(
                "Bankroll (€)",
                value=current_bankroll,
                step=100.0,
                disabled=True,
                help="Im Demo-Modus schreibgeschützt",
            )
            st.caption("🎮 Demo-Modus aktiv - Bankroll wird durch Demo-Wetten geändert")
        else:
            new_bankroll = st.number_input(
                "Bankroll (€)",
                value=current_bankroll,
                step=100.0,
                min_value=10.0,
            )
            st.session_state.risk_management["bankroll"] = new_bankroll

        # Risk Profile
        current_profile = st.session_state.risk_management["risk_profile"]
        profile_names = {k: v["name"] for k, v in RISK_PROFILES.items()}

        selected_profile = st.selectbox(
            "Risiko-Profil",
            options=list(RISK_PROFILES.keys()),
            format_func=lambda x: profile_names[x],
            index=list(RISK_PROFILES.keys()).index(current_profile),
        )

        st.session_state.risk_management["risk_profile"] = selected_profile

        # Zeige Profil-Details
        profile_info = RISK_PROFILES[selected_profile]
        st.caption(
            f"📊 {profile_info['description']} (Max: {profile_info['max_stake_percent']}%)"
        )

        # Results Entry
        st.markdown("---")
        st.subheader("📝 Ergebnis eintragen")

        # Lade PENDING Predictions
        sheet_id = get_tracking_sheet_id()
        pending_matches = []

        if sheet_id:
            try:
                service = connect_to_sheets(readonly=True)
                if service:
                    result = (
                        service.spreadsheets()
                        .values()
                        .get(spreadsheetId=sheet_id, range="PREDICTIONS!A:W")
                        .execute()
                    )

                    values = result.get("values", [])

                    for i, row in enumerate(values):
                        if i == 0:
                            continue

                        if len(row) > 16 and row[16] == "PENDING":
                            match_str = row[2] if len(row) > 2 else ""
                            date_str = row[0] if len(row) > 0 else ""
                            predicted_score = row[3] if len(row) > 3 else ""

                            pending_matches.append(
                                {
                                    "match": match_str,
                                    "date": date_str,
                                    "predicted": predicted_score,
                                }
                            )

            except Exception as e:
                st.error(f"Fehler beim Laden der Predictions: {e}")

        if pending_matches:
            st.caption(f"🔴 {len(pending_matches)} offene Vorhersagen")

            selected_match = st.selectbox(
                "Match auswählen",
                options=[m["match"] for m in pending_matches],
                format_func=lambda x: f"{x} ({next(m['predicted'] for m in pending_matches if m['match'] == x)})",
            )

            selected_info = next(
                m for m in pending_matches if m["match"] == selected_match
            )
            st.caption(f"📅 {selected_info['date']}")

            col1, col2 = st.columns(2)
            with col1:
                home_goals = st.number_input(
                    "Heim-Tore", min_value=0, max_value=20, value=0, step=1
                )
            with col2:
                away_goals = st.number_input(
                    "Auswärts-Tore", min_value=0, max_value=20, value=0, step=1
                )

            if st.button("💾 Ergebnis speichern", use_container_width=True):
                actual_score = f"{home_goals}:{away_goals}"
                if update_match_result_in_sheets(selected_match, actual_score):
                    st.success(f"✅ Ergebnis {actual_score} gespeichert!")
                    st.rerun()
                else:
                    st.error("❌ Fehler beim Speichern")

        else:
            st.info("✅ Keine offenen Vorhersagen")

        # Bankroll Statistiken
        st.markdown("---")
        st.subheader("📊 Bankroll Statistiken")

        stake_history = st.session_state.risk_management.get("stake_history", [])

        if stake_history:
            recent_stakes = stake_history[-10:]
            total_profit = sum(s["profit"] for s in recent_stakes)
            wins = sum(1 for s in recent_stakes if s["profit"] > 0)
            win_rate = (wins / len(recent_stakes)) * 100 if recent_stakes else 0

            col1, col2 = st.columns(2)
            col1.metric("Letzte 10 Wetten", f"{win_rate:.0f}% WR")
            col2.metric("P&L", f"€{total_profit:+.2f}")

            # Reset Button
            if st.button("🔄 Bankroll zurücksetzen", use_container_width=True):
                st.session_state.risk_management["bankroll"] = 1000.0
                st.session_state.risk_management["stake_history"] = []
                st.success("✅ Bankroll zurückgesetzt!")
                st.rerun()

            # Bet History Expander
            with st.expander("📜 Wett-Historie (Letzte 5)"):
                for stake in reversed(recent_stakes[-5:]):
                    status = "✅" if stake["profit"] > 0 else "❌"
                    st.caption(
                        f"{status} {stake['match']} ({stake['market']}): €{stake['profit']:+.2f}"
                    )

        else:
            st.info("Noch keine Wetten platziert")

        # Google Sheets Info
        st.markdown("---")
        st.subheader("📊 Google Sheets")

        if sheet_id:
            st.success("✅ Verbunden")

            try:
                service = connect_to_sheets(readonly=True)
                if service:
                    result = (
                        service.spreadsheets()
                        .values()
                        .get(spreadsheetId=sheet_id, range="PREDICTIONS!A:A")
                        .execute()
                    )
                    row_count = len(result.get("values", [])) - 1
                    st.caption(f"📝 {row_count} Vorhersagen gespeichert")
            except:
                pass

        else:
            st.warning("⚠️ Nicht verbunden")

        # Alarm Settings
        with st.expander("🔔 Alarm-Einstellungen"):
            st.caption("Schwellenwerte für kritische Situationen")

            new_mu_threshold = st.number_input(
                "μ-Total Schwelle",
                value=st.session_state.alert_thresholds["mu_total_high"],
                min_value=3.0,
                max_value=6.0,
                step=0.5,
            )

            new_tki_threshold = st.number_input(
                "TKI-Krise Schwelle",
                value=st.session_state.alert_thresholds["tki_high"],
                min_value=0.5,
                max_value=2.0,
                step=0.1,
            )

            new_ppg_threshold = st.number_input(
                "PPG-Differenz Extrem",
                value=st.session_state.alert_thresholds["ppg_diff_extreme"],
                min_value=1.0,
                max_value=3.0,
                step=0.1,
            )

            if st.button("💾 Schwellenwerte speichern"):
                st.session_state.alert_thresholds["mu_total_high"] = new_mu_threshold
                st.session_state.alert_thresholds["tki_high"] = new_tki_threshold
                st.session_state.alert_thresholds["ppg_diff_extreme"] = (
                    new_ppg_threshold
                )
                st.success("✅ Gespeichert!")

        # Quick Actions
        st.markdown("---")
        st.subheader("⚡ Quick Actions")

        if st.button("🔄 Cache leeren", use_container_width=True):
            st.cache_data.clear()
            st.success("✅ Cache geleert!")

        if st.button("🤖 ML neu laden", use_container_width=True):
            from ml.position_ml import TablePositionML

            st.session_state.position_ml_model = TablePositionML()
            st.success("✅ ML-Modell neu initialisiert!")

        # Demo Mode Toggle
        st.markdown("---")
        demo_enabled = st.toggle(
            "🎮 Demo-Modus",
            value=st.session_state.get("enable_demo_mode", False),
            help="Ermöglicht simulierte Wetten ohne echtes Geld",
        )
        st.session_state.enable_demo_mode = demo_enabled

        if demo_enabled:
            st.info("🎮 Demo-Modus aktiv - Simuliere Wetten!")

        # Strategy Info
        with st.expander("📚 Strategie-Info"):
            st.markdown(
                """
            **v4.7+ SMART-PRECISION:**
            - Basis μ aus xG + Tore/Spiel
            - Form-Faktoren (0.7-1.2)
            - TKI überschreibt Form-Malus
            - Dominanz-Dämpfer aktiv
            - Clean Sheet Validierung
            - ML-Korrekturen (Position)
            
            **Risk-Scoring:**
            - Skala: 1 (extrem) bis 5 (optimal)
            - Target: 60-70% bei 3/5
            - EV-Adjustments aktiv
            """
            )

        # Risk Scoring Explanation
        with st.expander("ℹ️ Risiko-Scoring Erklärung"):
            st.markdown(
                """
            **1/5 - Extrem risikant** ☠️
            - Sehr spekulativ
            - EV < -15%
            - Vermeiden!
            
            **2/5 - Hohes Risiko** ⚠️
            - Nur für Profis
            - Kleiner Einsatz
            - EV < -5%
            
            **3/5 - Moderates Risiko** 📊
            - Standard-Wette
            - Normaler Einsatz
            - EV: -5% bis +8%
            
            **4/5 - Geringes Risiko** ✅
            - Gute Wettmöglichkeit
            - Empfohlener Einsatz
            - EV: +8% bis +18%
            
            **5/5 - Optimales Risiko** 🎯
            - Seltene Top-Wette
            - Erhöhter Einsatz möglich
            - EV > +18%
            """
            )

        # Search Tips
        with st.expander("🔍 Such-Tipps"):
            st.markdown(
                """
            **Match-Suche:**
            - Teamnamen direkt eingeben
            - z.B. "Bayern" findet "Bayern München"
            - Groß-/Kleinschreibung egal
            
            **Datum-Navigation:**
            - Kalender zeigt verfügbare Tage
            - Pfeil-Buttons: Vor/Zurück
            - Heute-Button: Springt zu heute
            """
            )

        # Version Info
        st.markdown("---")
        st.caption(f"**{APP_VERSION}**")
        for feature in APP_FEATURES:
            st.caption(feature)
