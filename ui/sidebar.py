"""
Sidebar UI-Komponente
"""

import streamlit as st
import pandas as pd
from datetime import date
from config.constants import RISK_PROFILES, APP_VERSION, APP_FEATURES
from data.google_sheets import get_tracking_sheet_id, connect_to_sheets
from models.tracking import update_match_result_in_sheets
from utils.match_index import group_matches_by_country_league


def show_sidebar(navigator: dict | None = None):
    """
    Zeigt die Sidebar mit allen Einstellungen und Funktionen
    """
    with st.sidebar:
        # ==================== MATCH NAVIGATOR (optional) ====================
        if navigator:
            st.title("🧭 Matches")

            available_dates = navigator.get("available_dates") or []
            selected_date = navigator.get("selected_date")
            today = navigator.get("today") or date.today()

            # ---- apply pending date update BEFORE date_input is created ----
            if "_pending_nav_date" in st.session_state:
                pending = st.session_state.pop("_pending_nav_date", None)
                if pending:
                    st.session_state["nav_date_picker"] = pending
                    selected_date = pending

            # --- AUTO-FIX: if selected_date is not available, jump to next available with data ---
            if available_dates and selected_date and (selected_date not in available_dates):
                sorted_dates = sorted(available_dates)
                new_date = next((d for d in sorted_dates if d >= selected_date), sorted_dates[-1])

                # avoid loops
                last_fix = st.session_state.get("_nav_last_autofix")
                if last_fix != (selected_date, new_date):
                    st.session_state["_nav_last_autofix"] = (selected_date, new_date)
                    navigator["on_date_change"](new_date)
                    st.rerun()

            # Date picker
            if available_dates and selected_date:
                min_d = min(available_dates)
                max_d = max(available_dates)

                # initialize widget state once (no value=... to avoid warnings)
                if "nav_date_picker" not in st.session_state:
                    st.session_state["nav_date_picker"] = selected_date

                picked = st.date_input(
                    "📅 Datum",
                    min_value=min_d,
                    max_value=max_d,
                    key="nav_date_picker",
                )

                if picked != selected_date:
                    navigator["on_date_change"](picked)

                    # reset view/filter to all matches on date change
                    st.session_state.nav_view_mode = "all"
                    st.session_state.nav_selected_country = ""
                    st.session_state.nav_selected_league = ""
                    st.session_state.nav_search_query = ""
                    st.rerun()

            # Prev/Next day with data (based on available_dates)
            cols = st.columns(2)

            try:
                current_idx = (
                    available_dates.index(selected_date)
                    if (available_dates and selected_date in available_dates)
                    else -1
                )
            except Exception:
                current_idx = -1

            has_prev = current_idx > 0
            has_next = current_idx != -1 and current_idx < (len(available_dates) - 1)

            with cols[0]:
                if st.button(
                    "⬅️ Vorheriger Tag mit Daten",
                    use_container_width=True,
                    disabled=not has_prev,
                ):
                    new_date = available_dates[current_idx - 1]
                    navigator["on_date_change"](new_date)

                    # reset view/filter
                    st.session_state.nav_view_mode = "all"
                    st.session_state.nav_selected_country = ""
                    st.session_state.nav_selected_league = ""
                    st.session_state.nav_search_query = ""
                    st.rerun()

            with cols[1]:
                if st.button(
                    "Nächster Tag mit Daten ➡️",
                    use_container_width=True,
                    disabled=not has_next,
                ):
                    new_date = available_dates[current_idx + 1]
                    navigator["on_date_change"](new_date)

                    # reset view/filter
                    st.session_state.nav_view_mode = "all"
                    st.session_state.nav_selected_country = ""
                    st.session_state.nav_selected_league = ""
                    st.session_state.nav_search_query = ""
                    st.rerun()

            # Search
            q = st.text_input(
                "🔍 Suche (Team / Liga)",
                value=st.session_state.get("nav_search_query", ""),
                key="nav_search_input",
            )
            st.session_state.nav_search_query = q
            if q.strip():
                st.session_state.nav_view_mode = "search"

            match_index = navigator.get("match_index") or []
            grouped = group_matches_by_country_league(match_index)

            # Country / League expanders
            if match_index:
                st.markdown("### 🌍 Ligen nach Land")

                country_items = []
                for c, leagues in grouped.items():
                    cnt = sum(len(v) for v in leagues.values())
                    country_items.append((c, leagues, cnt))
                country_items.sort(key=lambda x: (-x[2], x[0]))

                for country, leagues, cnt in country_items:
                    flag = (
                        navigator.get("flag_fn")(country)
                        if navigator.get("flag_fn")
                        else "🌍"
                    )
                    with st.expander(f"{flag} {country} ({cnt})", expanded=False):
                        league_items = [(lg, ms, len(ms)) for lg, ms in leagues.items()]
                        league_items.sort(key=lambda x: (-x[2], x[0]))
                        for league, _ms, lcnt in league_items:
                            if st.button(
                                f"• {league} ({lcnt})",
                                key=f"nav_league_{country}_{league}",
                                use_container_width=True,
                            ):
                                st.session_state.nav_view_mode = "league"
                                st.session_state.nav_selected_country = country
                                st.session_state.nav_selected_league = league
                                st.session_state.nav_search_query = ""
                                st.rerun()

            st.markdown("---")

        # ==================== SETTINGS ====================
        st.title("⚙️ Einstellungen")

        # Risk Management
        st.markdown("---")
        st.subheader("💰 Risk Management")

        demo_mode = st.session_state.get("enable_demo_mode", False)

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

        current_profile = st.session_state.risk_management["risk_profile"]
        profile_names = {k: v["name"] for k, v in RISK_PROFILES.items()}

        selected_profile = st.selectbox(
            "Risiko-Profil",
            options=list(RISK_PROFILES.keys()),
            format_func=lambda x: profile_names[x],
            index=list(RISK_PROFILES.keys()).index(current_profile),
        )

        st.session_state.risk_management["risk_profile"] = selected_profile

        profile_info = RISK_PROFILES[selected_profile]
        st.caption(
            f"📊 {profile_info['description']} (Max: {profile_info['max_stake_percent']}%)"
        )

        # Results Entry
        st.markdown("---")
        st.subheader("📝 Ergebnis eintragen")

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

            selected_info = next(m for m in pending_matches if m["match"] == selected_match)
            st.caption(f"📅 {selected_info['date']}")

            col1, col2 = st.columns(2)

            with col1:
                actual_score = st.text_input("Endstand (z.B. 2:1)")

            with col2:
                status = st.selectbox(
                    "Ergebnis",
                    options=["WIN", "LOSS", "VOID"],
                    format_func=lambda x: {"WIN": "✅ Gewinn", "LOSS": "❌ Verlust", "VOID": "⚪ Storno"}[x],
                )

            if st.button("💾 Speichern", type="primary"):
                try:
                    update_match_result_in_sheets(selected_match, actual_score, status)
                    st.success("✅ Ergebnis gespeichert!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Fehler beim Speichern: {e}")
        else:
            st.caption("✅ Keine offenen Predictions")

        # App Info
        st.markdown("---")
        st.subheader("ℹ️ App Info")

        st.caption(f"Version: {APP_VERSION}")
        if APP_FEATURES:
            st.caption("Features:")
            for feat in APP_FEATURES:
                st.caption(f"• {feat}")
