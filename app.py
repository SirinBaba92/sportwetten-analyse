"""
Sportwetten-Prognose App v6.0 - Modular
Hauptdatei mit Streamlit UI
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, date, timedelta


def _scroll_to_analysis_anchor(anchor_id: str = "analysis_results") -> None:
    """Scroll smoothly to a DOM element with the given id."""
    try:
        components.html(
            f"""
<script>
(() => {{
  const doc = window.parent.document;
  const el = doc.getElementById("{anchor_id}");
  if (el) {{
    el.scrollIntoView({{ behavior: "smooth", block: "start" }});
  }}
}})();
</script>
""",
            height=0,
        )
    except Exception:
        # Never hard-fail on scrolling
        pass

# Config & Settings
from config.constants import APP_TITLE, APP_ICON, APP_LAYOUT
from config.settings import initialize_session_state

# Data
from data import (
    list_daily_sheets_in_folder,
    list_match_tabs_for_day,
    read_worksheet_text_by_id,
    parse_date,
    DataParser,
)

# Analysis
from analysis import validate_match_data, analyze_match_v47_ml


def choose_consistent_predicted_score(result: dict) -> dict:
    """Passt nur predicted_score an, ohne die bestehenden Wahrscheinlichkeiten (1X2/OU/BTTS) zu verändern.

    Vorgehen:
      1) Wenn es eine Scoreline gibt, die alle "starken" Signale erfüllt -> nimm die wahrscheinlichste davon.
      2) Sonst: Soft-Optimierung (Penalty): wähle die Scoreline, die den starken Signalen am besten entspricht.
         Tie-Breaker: höhere Scoreline-Wahrscheinlichkeit.

    Schwellen:
      - OU/BTTS: 60%
      - 1X2: Home/Away >= 50% UND mind. 8%-Punkte vor dem Zweitbesten
      - Draw: >= 38% UND mind. 8%-Punkte vor dem Zweitbesten
    """
    try:
        scorelines = result.get("scorelines") or result.get("poisson_scorelines") or []
        if not scorelines:
            ps = result.get("predicted_score")
            if isinstance(ps, str):
                result["predicted_score"] = ps.strip().replace(":", "-")
            return result

        probs = result.get("probabilities", {}) or {}

        def _p(*keys):
            for k in keys:
                v = probs.get(k)
                if v is None:
                    continue
                try:
                    return float(v)
                except Exception:
                    continue
            return None

        # --- OU / BTTS ---
        over25 = _p("over_25", "over25", "over2_5")
        under25 = _p("under_25", "under25", "under2_5")
        btts_yes = _p("btts_yes", "btts_ja", "bttsYes")
        btts_no = _p("btts_no", "btts_nein", "bttsNo")

        TH_OU_BTTS = 60.0
        need_over = over25 is not None and over25 >= TH_OU_BTTS
        need_under = under25 is not None and under25 >= TH_OU_BTTS
        need_btts = btts_yes is not None and btts_yes >= TH_OU_BTTS
        need_nobtts = btts_no is not None and btts_no >= TH_OU_BTTS

        # Konflikte auflösen (wenn das Modell widersprüchliche starke Signale liefert)
        if need_over and need_under:
            need_over = need_under = False
        if need_btts and need_nobtts:
            need_btts = need_nobtts = False

        # --- 1X2 ---
        p_home = _p("home_win", "heim", "heimsieg", "1")
        p_draw = _p("draw", "remis", "x")
        p_away = _p("away_win", "auswaerts", "auswärtssieg", "2")

        TH_1X2 = 50.0
        GAP_1X2 = 8.0
        TH_DRAW = 38.0

        need_homewin = need_draw = need_awaywin = False
        # Nur erzwingen, wenn 1X2 wirklich klar ist
        if p_home is not None and p_draw is not None and p_away is not None:
            triples = [("H", p_home), ("D", p_draw), ("A", p_away)]
            triples_sorted = sorted(triples, key=lambda x: x[1], reverse=True)
            best_code, best_val = triples_sorted[0]
            second_val = triples_sorted[1][1]

            if (
                best_code == "H"
                and best_val >= TH_1X2
                and (best_val - second_val) >= GAP_1X2
            ):
                need_homewin = True
            elif (
                best_code == "A"
                and best_val >= TH_1X2
                and (best_val - second_val) >= GAP_1X2
            ):
                need_awaywin = True
            elif (
                best_code == "D"
                and best_val >= TH_DRAW
                and (best_val - second_val) >= GAP_1X2
            ):
                need_draw = True

        def parse_score(s):
            if isinstance(s, (tuple, list)) and len(s) == 2:
                return int(s[0]), int(s[1])
            if isinstance(s, str):
                s = s.strip().replace(":", "-")
                a, b = s.split("-", 1)
                return int(a), int(b)
            raise ValueError(f"Unbekanntes score-format: {s}")

        # sortiere Scorelines nach Wahrscheinlichkeit absteigend
        norm = []
        for s, p in scorelines:
            try:
                hg, ag = parse_score(s)
            except Exception:
                continue
            try:
                p = float(p)
            except Exception:
                p = 0.0
            norm.append((hg, ag, p))
        if not norm:
            return result
        norm.sort(key=lambda x: x[2], reverse=True)

        def hard_ok(hg, ag):
            total = hg + ag
            if need_over and total < 3:
                return False
            if need_under and total > 2:
                return False
            if need_btts and not (hg > 0 and ag > 0):
                return False
            if need_nobtts and (hg > 0 and ag > 0):
                return False
            if need_homewin and not (hg > ag):
                return False
            if need_awaywin and not (ag > hg):
                return False
            if need_draw and not (hg == ag):
                return False
            return True

        # 1) Wenn es eine perfekte Scoreline gibt: nimm die wahrscheinlichste davon
        for hg, ag, p in norm:
            if hard_ok(hg, ag):
                result["predicted_score"] = f"{hg}-{ag}"
                return result

        # 2) Soft-Optimierung (Penalty)
        # Gewichte: OU/BTTS wichtiger als 1X2 (damit Over>=60 nicht in 1-1 endet)
        W_OU = 3.0
        W_BTTS = 2.0
        W_1X2 = 1.0

        # Je stärker das Signal über der Schwelle liegt, desto teurer die Verletzung
        def strength(v, thr):
            if v is None:
                return 0.0
            return max(0.0, (float(v) - float(thr)) / 10.0)  # skaliert pro 10%-Punkte

        over_s = strength(over25, TH_OU_BTTS)
        under_s = strength(under25, TH_OU_BTTS)
        btts_s = strength(btts_yes, TH_OU_BTTS)
        nobtts_s = strength(btts_no, TH_OU_BTTS)

        # 1X2-Stärke basiert auf dem Abstand zum zweitbesten
        one_x_two_s = 0.0
        if p_home is not None and p_draw is not None and p_away is not None:
            triples = sorted([p_home, p_draw, p_away], reverse=True)
            gap = triples[0] - triples[1]
            one_x_two_s = max(0.0, (gap - GAP_1X2) / 10.0)  # pro 10%-Punkte extra Gap

        def penalty(hg, ag):
            total = hg + ag
            pen = 0.0

            # OU
            if need_over and total < 3:
                pen += W_OU * (1.0 + over_s)
            if need_under and total > 2:
                pen += W_OU * (1.0 + under_s)

            # BTTS
            btts_ok = hg > 0 and ag > 0
            if need_btts and not btts_ok:
                pen += W_BTTS * (1.0 + btts_s)
            if need_nobtts and btts_ok:
                pen += W_BTTS * (1.0 + nobtts_s)

            # 1X2
            if need_homewin and not (hg > ag):
                pen += W_1X2 * (1.0 + one_x_two_s)
            if need_awaywin and not (ag > hg):
                pen += W_1X2 * (1.0 + one_x_two_s)
            if need_draw and not (hg == ag):
                pen += W_1X2 * (1.0 + one_x_two_s)

            return pen

        best = None
        for hg, ag, p in norm:
            pen = penalty(hg, ag)
            key = (pen, -p)  # min penalty, dann max prob
            if best is None or key < best[0]:
                best = (key, hg, ag, p)

        if best:
            _, hg, ag, _p = best
            result["predicted_score"] = f"{hg}-{ag}"
        return result

    except Exception:
        return result


# UI Components
from ui import (
    display_results,
    display_risk_distribution,
    show_sidebar,
    show_ml_training_ui,
    show_extended_data_entry_ui,
    add_historical_match_ui,
)

# Navigator helpers
from utils.match_index import build_match_index, get_flag_emoji

# ML
from ml import TablePositionML

# Models
from models import save_historical_directly


def main():
    """
    Haupt-Entry-Point der Streamlit App
    """
    # Page Config
    st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)

    # Session State initialisieren
    initialize_session_state()

    # Telegram Bot im Hintergrund starten (nur wenn Token gesetzt)
    try:
        from telegram_bot.bot_runner import start_bot_in_background
        start_bot_in_background()
    except Exception:
        pass  # Bot-Fehler sollen die App nie blockieren

    # --- Export-Handler (läuft bei jedem Rerun) ---
    # Wichtig: Button-Klicks lösen immer einen Rerun aus. Damit Exporte auch ohne "Analyse erneut starten"
    # funktionieren, führen wir die Exporte hier aus – basierend auf dem zuletzt gespeicherten Analyse-Result.
    if st.session_state.get("_do_export_simple") or st.session_state.get(
        "_do_export_with_result"
    ):
        export_result = st.session_state.get("_last_analysis_result")
        if not export_result:
            # Flags zurücksetzen, damit es nicht in einer Schleife landet
            st.session_state["_do_export_simple"] = False
            st.session_state["_do_export_with_result"] = False
            st.error(
                "❌ Kein Analyse-Ergebnis vorhanden. Bitte zuerst eine Analyse ausführen."
            )
        else:
            from models import export_analysis_to_sheets

            if st.session_state.get("_do_export_simple"):
                st.session_state["_do_export_simple"] = False
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
                with st.spinner(f"Exportiere mit Ergebnis {actual_score}..."):
                    ok = export_analysis_to_sheets(export_result, actual_score)
                if ok:
                    st.success(f"✅ Mit Ergebnis {actual_score} exportiert!")
                    st.balloons()
                else:
                    st.error("❌ Export fehlgeschlagen")

    # Sidebar
    # Titel
    st.title(f"{APP_ICON} {APP_TITLE}")
    st.caption("🎯 SMART-PRECISION Algorithmus mit ML-Korrekturen")

    # Live-Update Indikator
    from datetime import datetime

    current_time = datetime.now()
    st.caption(f"⏱️ Daten-Stand: {current_time.strftime('%d.%m.%Y %H:%M')} Uhr")

    # Lade verfügbare Sheets
    if "prematch" not in st.secrets or "folder_id" not in st.secrets["prematch"]:
        st.error("❌ Google Drive Ordner nicht konfiguriert!")
        st.stop()

    folder_id = st.secrets["prematch"]["folder_id"]

    # Refresh Button
    col_refresh, col_info = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Aktualisieren"):
            st.session_state["_force_reanalyze"] = True
            st.cache_data.clear()
            st.rerun()

    # Lade Daily Sheets
    date_to_id = list_daily_sheets_in_folder(folder_id)

    if not date_to_id:
        st.warning("⚠️ Keine Sheets im Ordner gefunden!")
        st.stop()

    with col_info:
        st.info(f"📊 {len(date_to_id)} Tage mit Daten verfügbar")

    # Datum-Navigation (in Sidebar)
    # Konvertiere Datums-Strings zu date-Objekten
    available_dates: list[date] = []
    for date_str in date_to_id.keys():
        try:
            d = parse_date(date_str)
            available_dates.append(d)
        except Exception:
            continue

    available_dates.sort()

    if not available_dates:
        st.error("❌ Keine gültigen Daten gefunden!")
        st.stop()

    # Session State für ausgewähltes Datum
    if "selected_date" not in st.session_state:
        today = date.today()
        if today in available_dates:
            st.session_state.selected_date = today
        else:
            # Nächstgelegenes verfügbares Datum
            future_dates = [d for d in available_dates if d >= today]
            if future_dates:
                st.session_state.selected_date = min(future_dates)
            else:
                st.session_state.selected_date = max(available_dates)
# Ausgewähltes Datum
    selected_date_str = st.session_state.selected_date.strftime("%d.%m.%Y")
    st.success(f"✅ Ausgewähltes Datum: **{selected_date_str}**")

    if selected_date_str not in date_to_id:
        st.error(f"❌ Keine Daten für {selected_date_str} verfügbar!")
        st.stop()

    sheet_id = date_to_id[selected_date_str]

    # Convenience var (used by navigator)
    selected_date = st.session_state.selected_date

    # Lade Matches für den Tag
    match_tabs = list_match_tabs_for_day(sheet_id)

    if not match_tabs:
        st.warning(f"⚠️ Keine Matches für {selected_date_str} gefunden!")
        st.stop()

    st.info(f"🎯 {len(match_tabs)} Matches verfügbar für {selected_date_str}")

    # ================== MATCH NAVIGATOR INDEX (cached) ==================
    match_index = build_match_index(sheet_id, tuple(match_tabs))

    # Sidebar (Navigator + Settings)
    today = date.today()
    today_str = today.strftime("%d.%m.%Y")
    today_count = 0
    if today_str in date_to_id:
        _sid_today = date_to_id[today_str]
        _tabs_today = list_match_tabs_for_day(_sid_today) or []
        today_count = len(_tabs_today)

    def _on_date_change(new_date: date):
        st.session_state.selected_date = new_date
        # schedule sidebar date picker update for next run (avoid modifying widget state after instantiation)
        st.session_state['_pending_nav_date'] = new_date

    show_sidebar(
        navigator={
            "available_dates": available_dates,
            "selected_date": selected_date,
            "today": today,
            "today_count": today_count,
            "match_index": match_index,
            "on_date_change": _on_date_change,
            "flag_fn": get_flag_emoji,
        }
    )

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "⚽ Match-Analyse",
            "🤖 ML Training",
            "📚 Training Data",
            "📊 Statistiken",
            "🎮 Demo Performance",
        ]
    )

    # ================== TAB 1: MATCH-ANALYSE ==================
    with tab1:
        st.header("⚽ Match-Analyse")
        # UI: Card styling for match list
        st.markdown("""
<style>
.match-card { padding: 12px 14px; border: 1px solid rgba(49,51,63,0.2); border-radius: 12px; margin-bottom: 10px; }
.match-meta { opacity: 0.75; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)


        # Navigator-driven Matchliste (Sidebar steuert Filter/Selection)
        if "nav_view_mode" not in st.session_state:
            st.session_state.nav_view_mode = "all"
        if "nav_selected_country" not in st.session_state:
            st.session_state.nav_selected_country = ""
        if "nav_selected_league" not in st.session_state:
            st.session_state.nav_selected_league = ""
        if "nav_search_query" not in st.session_state:
            st.session_state.nav_search_query = ""
        if "selected_tab" not in st.session_state:
            st.session_state.selected_tab = ""

        view_mode = st.session_state.get("nav_view_mode", "all")
        country_sel = (st.session_state.get("nav_selected_country") or "").strip()
        league_sel = (st.session_state.get("nav_selected_league") or "").strip()
        q = (st.session_state.get("nav_search_query") or "").strip().lower()

        filtered = match_index
        if view_mode == "league" and country_sel and league_sel:
            filtered = [m for m in match_index if (m.get("country")==country_sel and m.get("league")==league_sel)]
        elif view_mode == "search" and q:
            def _hit(m):
                hay = " ".join([
                    str(m.get("home","")), str(m.get("away","")), str(m.get("country","")), str(m.get("league","")), str(m.get("competition","")), str(m.get("tab",""))
                ]).lower()
                return q in hay
            filtered = [m for m in match_index if _hit(m)]
        # else: all
        filtered_tabs = [m.get("tab") for m in filtered]

        title_bits = []
        if view_mode == "league" and league_sel:
            title_bits.append(f"{country_sel} / {league_sel}")
        if view_mode == "search" and q:
            title_bits.append(f"Suche: \"{q}\"")
        subtitle = (" – ".join(title_bits)) if title_bits else "Alle Spiele"
        st.subheader(f"🧾 Spiele ({len(filtered)}) · {subtitle}")

        if not filtered:
            st.warning("Keine Spiele für den aktuellen Filter gefunden.")
        else:
            for m in filtered:
                home = m.get("home", "")
                away = m.get("away", "")
                flag = m.get("flag", "🌍")
                league = m.get("league", "")
                kickoff = m.get("kickoff", "")
                tab = m.get("tab")

                match_key = f"{sheet_id}::{tab}"

                meta = f"{flag} {league}"
                if kickoff:
                    meta += f" · ⏱️ {kickoff}"

                st.markdown(
                    f"""
<div class='match-card'>
  <div><b>{home} vs {away}</b></div>
  <div class='match-meta'>{meta}</div>
</div>
""",
                    unsafe_allow_html=True,
                )

                if st.button("🎯 Analysieren", key=f"an::{match_key}", use_container_width=True):
                    st.session_state.selected_tab = tab
                    st.session_state._trigger_analyze_tab = tab
                    st.session_state._scroll_to_results = True
                    st.rerun()


        selected_tab = st.session_state.get("selected_tab") or ""
        if selected_tab:
            st.success(f"✅ Ausgewählt: **{selected_tab}**")
        else:
            st.info("⬅️ Wähle links (Sidebar) eine Liga oder klicke auf ein Spiel.")


        # Auto-zeige letzte Analyse (falls vorhanden)
        if "analysis_cache_by_tab" not in st.session_state:
            st.session_state.analysis_cache_by_tab = {}
        _cache_key = f"{sheet_id}::{selected_tab}" if selected_tab else ""
        if selected_tab and _cache_key in st.session_state.analysis_cache_by_tab:
            st.markdown("<div id='analysis_results'></div>", unsafe_allow_html=True)
            if st.session_state.get("_scroll_to_results"):
                _scroll_to_analysis_anchor("analysis_results")
                st.session_state._scroll_to_results = False
            st.markdown("### 🧠 Letztes Analyse-Ergebnis")
            display_results(st.session_state.analysis_cache_by_tab[_cache_key])
            st.markdown("---")

        # Lade Match-Daten

        with st.expander("📄 Rohdaten anzeigen"):
            if not selected_tab:
                st.info("Bitte zuerst ein Match auswählen.")
            else:
                match_text = read_worksheet_text_by_id(sheet_id, selected_tab)
                if match_text:
                    st.text_area("Daten", match_text, height=300)
                else:
                    st.error("Fehler beim Laden der Daten")

        # Analyse-Buttons

        # Auto-Trigger aus Match-Karte (setzt selected_tab und startet Analyse ohne extra Klick)
        auto_tab = st.session_state.pop("_trigger_analyze_tab", "")
        auto_analyze = bool(auto_tab)
        if auto_tab:
            st.session_state.selected_tab = auto_tab
            selected_tab = auto_tab

        col_single, col_all = st.columns(2)

        col_single, col_all = st.columns(2)

        with col_single:
            analyze_single = st.button(
                "🎯 Analysiere ausgewähltes Match",
                use_container_width=True,
                disabled=not bool(selected_tab),
            )
            if analyze_single:
                st.session_state._scroll_to_results = True

        with col_all:
            analyze_all = st.button(
                f"📊 Analysiere alle {len(filtered_tabs)} Matches (aktueller Filter)",
                use_container_width=True,
                disabled=not bool(filtered_tabs),
            )

        # SINGLE MATCH ANALYSE
        if analyze_single or auto_analyze:
            with st.spinner(f"Analysiere {selected_tab}..."):
                match_text = read_worksheet_text_by_id(sheet_id, selected_tab)

                if not match_text:
                    st.error("❌ Fehler beim Laden der Match-Daten")
                else:
                    parser = DataParser()
                    try:
                        match_data = parser.parse(match_text)

                        is_valid, missing = validate_match_data(match_data)

                        if not is_valid:
                            st.warning(
                                f"⚠️ Unvollständige Daten ({len(missing)} fehlend)"
                            )
                            with st.expander("Fehlende Felder anzeigen"):
                                for field in missing:
                                    st.caption(f"• {field}")
                        # Analysiere (mit Cache, damit Eingaben wie "tatsächliches Ergebnis" keinen teuren Rerun auslösen)
                        # Cache-Key: Teams + Datum (falls vorhanden)
                        _home = (
                            getattr(match_data, "home_team", None)
                            or getattr(match_data, "home", None)
                            or ""
                        )
                        _away = (
                            getattr(match_data, "away_team", None)
                            or getattr(match_data, "away", None)
                            or ""
                        )
                        _date = (
                            getattr(match_data, "date", None)
                            or getattr(match_data, "match_date", None)
                            or ""
                        )
                        match_key = f"{_date}::{_home}::{_away}".strip()

                        if "current_match_result" not in st.session_state:
                            st.session_state.current_match_result = {}

                        # Optionaler "Refresh"-Button setzt diesen Flag (falls vorhanden)
                        force_reanalyze = st.session_state.pop(
                            "_force_reanalyze", False
                        )

                        if (not force_reanalyze) and (
                            match_key in st.session_state.current_match_result
                        ):
                            result = st.session_state.current_match_result[match_key]
                        else:
                            result = analyze_match_v47_ml(match_data)
                            result = choose_consistent_predicted_score(result)
                            st.session_state.current_match_result[match_key] = result
                        # Falls aus Cache geladen, Score ggf. anpassen
                        result = choose_consistent_predicted_score(result)
                        # Speichere in Session für Demo-Mode
                        if "current_match_result" not in st.session_state:
                            st.session_state.current_match_result = {}

                        match_key = f"{result['match_info']['home']}_{result['match_info']['away']}"
                        st.session_state.current_match_result[match_key] = result

                        # Cache pro Tab (für Auto-Anzeige beim nächsten Klick)
                        if "analysis_cache_by_tab" not in st.session_state:
                            st.session_state.analysis_cache_by_tab = {}
                        _ck = f"{sheet_id}::{selected_tab}"
                        st.session_state.analysis_cache_by_tab[_ck] = result

                        # Zeige Ergebnisse
                        st.markdown("<div id='analysis_results'></div>", unsafe_allow_html=True)
                        if st.session_state.get("_scroll_to_results"):
                            _scroll_to_analysis_anchor("analysis_results")
                            st.session_state._scroll_to_results = False
                        display_results(result)

                        # Export-Button - OPTIMIERTE VERSION
                        st.markdown("---")
                        st.subheader("📤 Export zu Google Sheets")

                        # Letztes Analyse-Ergebnis persistent speichern (damit Export nach Rerun ohne neue Analyse klappt)
                        st.session_state["_last_analysis_result"] = result

                        # Container mit besserer Lesbarkeit
                        export_container = st.container()

                        with export_container:
                            # Grüne Box für bessere Lesbarkeit
                            st.success("### 📤 Export-Optionen")

                            col_export, col_actual = st.columns(2)

                            def _trigger_simple_export():
                                st.session_state["_do_export_simple"] = True

                            def _trigger_export_with_result():
                                h = st.session_state.get("exp_home_app", 0)
                                a = st.session_state.get("exp_away_app", 0)
                                st.session_state["_export_actual_score"] = f"{h}-{a}"
                                st.session_state["_do_export_with_result"] = True

                            with col_export:
                                st.markdown("**Einfacher Export**")
                                st.button(
                                    "💾 Analyse exportieren",
                                    use_container_width=True,
                                    key="export_btn_simple_app",
                                    on_click=_trigger_simple_export,
                                    help="Exportiert die Analyse ohne Ergebnis",
                                )

                            with col_actual:
                                st.markdown("**Export mit Ergebnis**")
                                with st.form(
                                    "actual_score_form_app", clear_on_submit=False
                                ):
                                    st.caption("Tatsächliches Ergebnis eintragen")
                                    c1, c2 = st.columns(2)
                                    with c1:
                                        actual_home = st.number_input(
                                            "Heim",
                                            0,
                                            10,
                                            0,
                                            key="exp_home_app",
                                            label_visibility="collapsed",
                                        )
                                        st.caption("Heim")
                                    with c2:
                                        actual_away = st.number_input(
                                            "Auswärts",
                                            0,
                                            10,
                                            0,
                                            key="exp_away_app",
                                            label_visibility="collapsed",
                                        )
                                        st.caption("Auswärts")

                                    submitted = st.form_submit_button(
                                        "📤 Mit Ergebnis exportieren",
                                        use_container_width=True,
                                    )

                                    if submitted:
                                        st.session_state["_export_actual_score"] = (
                                            f"{actual_home}-{actual_away}"
                                        )
                                        st.session_state["_do_export_with_result"] = (
                                            True
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

                            with st.spinner(
                                f"Exportiere mit Ergebnis {actual_score}..."
                            ):
                                ok = export_analysis_to_sheets(
                                    export_result, actual_score
                                )
                            if ok:
                                st.success(
                                    f"✅ Mit Ergebnis {actual_score} exportiert!"
                                )
                                st.balloons()
                            else:
                                st.error("❌ Export fehlgeschlagen")

                    except Exception as e:
                        st.error(f"❌ Fehler bei der Analyse: {str(e)}")
                        st.exception(e)

            # DEMO MODE: Wettauswahl
            if st.session_state.get("enable_demo_mode", False):
                st.markdown("---")
                st.subheader("🎮 DEMO-MODUS: Wettauswahl")

                if (
                    "demo_bet_options" in st.session_state
                    and st.session_state.demo_bet_options
                ):
                    st.info(
                        f"Wähle aus {len(st.session_state.demo_bet_options)} verfügbaren Wetten:"
                    )

                    # Data Editor für Wettauswahl
                    bet_df = pd.DataFrame(st.session_state.demo_bet_options)
                    bet_df["Auswählen"] = False
                    bet_df["Gewonnen?"] = True

                    edited_df = st.data_editor(
                        bet_df[
                            [
                                "Auswählen",
                                "market",
                                "match_info",
                                "stake",
                                "potential_win",
                                "potential_loss",
                                "Gewonnen?",
                            ]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

                    selected_bets = edited_df[edited_df["Auswählen"] == True]

                    if len(selected_bets) > 0:
                        st.markdown(f"**{len(selected_bets)} Wetten ausgewählt:**")

                        total_stake = selected_bets["stake"].sum()
                        wins = selected_bets[selected_bets["Gewonnen?"] == True]
                        losses = selected_bets[selected_bets["Gewonnen?"] == False]

                        total_profit = (
                            wins["potential_win"].sum() - losses["stake"].sum()
                        )

                        col1, col2, col3 = st.columns(3)
                        col1.metric("Gesamteinsatz", f"€{total_stake:.2f}")
                        col2.metric("Gewonnene Wetten", len(wins))
                        col3.metric("P&L", f"€{total_profit:+.2f}")

                        if st.button("✅ Wetten bestätigen", use_container_width=True):
                            from models.risk_management import add_to_stake_history

                            for _, bet in selected_bets.iterrows():
                                if bet["Gewonnen?"]:
                                    profit = bet["potential_win"]
                                else:
                                    profit = -bet["stake"]

                                add_to_stake_history(
                                    match_info=bet["match_info"],
                                    stake=bet["stake"],
                                    profit=profit,
                                    market=bet["market"],
                                )

                            st.success(
                                f"✅ {len(selected_bets)} Demo-Wetten gespeichert! P&L: €{total_profit:+.2f}"
                            )
                            st.session_state.demo_bet_options = []
                            st.balloons()
                            st.rerun()

        # BULK ANALYSE
        if analyze_all:
            st.markdown("---")
            st.subheader(f"📊 Bulk-Analyse: {len(filtered_tabs)} Matches")

            progress_bar = st.progress(0)
            status_text = st.empty()

            all_results = []

            for i, tab in enumerate(filtered_tabs):
                status_text.text(f"Analysiere {i + 1}/{len(filtered_tabs)}: {tab}")
                progress_bar.progress((i + 1) / len(filtered_tabs))

                match_text = read_worksheet_text_by_id(sheet_id, tab)

                if match_text:
                    parser = DataParser()
                    try:
                        match_data = parser.parse(match_text)
                        result = analyze_match_v47_ml(match_data)
                        result = choose_consistent_predicted_score(result)
                        all_results.append({"tab": tab, "result": result})

                    except Exception as e:
                        st.warning(f"⚠️ Fehler bei {tab}: {str(e)}")

            status_text.text("✅ Analyse abgeschlossen!")

            st.success(f"✅ {len(all_results)} Matches erfolgreich analysiert!")

            # Zeige Risiko-Verteilung
            display_risk_distribution(all_results)

            # Optional: Zeige alle Ergebnisse
            with st.expander(f"📋 Alle {len(all_results)} Ergebnisse anzeigen"):
                for item in all_results:
                    with st.container():
                        st.markdown(f"### {item['tab']}")
                        display_results(item["result"])
                        st.markdown("---")

            # Export-UI für Bulk-Analyse - OPTIMIERTE VERSION
            st.markdown("---")
            st.subheader("📤 Bulk-Export zu Google Sheets")

            # Grüne Box für bessere Lesbarkeit
            st.success("### 🚀 Massenexport-Optionen")

            bulk_export_container = st.container()

            with bulk_export_container:
                col_bulk1, col_bulk2 = st.columns(2)

                def _trigger_bulk_simple_export():
                    st.session_state["_last_bulk_results"] = all_results
                    st.session_state["_do_bulk_export_simple"] = True

                with col_bulk1:
                    st.markdown("**Alle Analysen exportieren**")
                    st.button(
                        "💾 Alle exportieren",
                        use_container_width=True,
                        key="bulk_export_btn_simple",
                        on_click=_trigger_bulk_simple_export,
                        help="Exportiert alle analysierten Matches",
                    )

                with col_bulk2:
                    st.markdown("**Selektive Exporte**")
                    st.info(
                        "ℹ️ Für einzelne Exporte bitte in den jeweiligen Match-Analysen exportieren"
                    )

        # Historisches Ergebnis eintragen
        st.markdown("---")
        st.subheader("📝 Historisches Ergebnis eintragen")

        with st.form("historical_result_form"):
            st.caption(
                "Trage das tatsächliche Ergebnis ein um die Daten für ML-Training zu speichern"
            )

            col1, col2 = st.columns(2)
            with col1:
                hist_home_goals = st.number_input("Heim-Tore", 0, 10, 2)
            with col2:
                hist_away_goals = st.number_input("Auswärts-Tore", 0, 10, 1)

            save_historical = st.form_submit_button(
                "💾 Als historische Daten speichern"
            )

            if save_historical:
                # Hole aktuelles Match-Result
                if (
                    "current_match_result" in st.session_state
                    and st.session_state.current_match_result
                ):
                    # Hole das zuletzt analysierte Match
                    last_result = list(st.session_state.current_match_result.values())[
                        -1
                    ]

                    # Lade original MatchData nochmal
                    match_text = read_worksheet_text_by_id(sheet_id, selected_tab)
                    parser = DataParser()
                    match_data = parser.parse(match_text)

                    if save_historical_directly(
                        match_data=match_data,
                        actual_home_goals=hist_home_goals,
                        actual_away_goals=hist_away_goals,
                        predicted_mu_home=last_result["mu"]["home"],
                        predicted_mu_away=last_result["mu"]["away"],
                    ):
                        st.success("✅ Historische Daten gespeichert!")
                    else:
                        st.error("❌ Fehler beim Speichern")
                else:
                    st.warning("⚠️ Bitte erst ein Match analysieren!")

    # ================== TAB 2: ML TRAINING ==================
    with tab2:
        show_ml_training_ui()

    # ================== TAB 3: TRAINING DATA ==================
    with tab3:
        add_historical_match_ui()

    # ================== TAB 4: STATISTIKEN ==================
    with tab4:
        st.header("📊 ML-Modell Statistiken")

        from models.tracking import load_historical_matches_from_sheets

        historical_matches = load_historical_matches_from_sheets()

        if len(historical_matches) > 0:
            st.info(f"📊 {len(historical_matches)} historische Matches verfügbar")

            # Berechne Statistiken
            home_corrections = [
                m.get("home_correction", 1.0) for m in historical_matches
            ]
            away_corrections = [
                m.get("away_correction", 1.0) for m in historical_matches
            ]

            avg_home_corr = sum(home_corrections) / len(home_corrections)
            avg_away_corr = sum(away_corrections) / len(away_corrections)

            col1, col2, col3 = st.columns(3)
            col1.metric("Ø Heim-Korrektur", f"{avg_home_corr:.3f}")
            col2.metric("Ø Auswärts-Korrektur", f"{avg_away_corr:.3f}")
            col3.metric("Differenz", f"{abs(avg_home_corr - avg_away_corr):.3f}")

            # Histogram
            import plotly.graph_objects as go

            fig = go.Figure()
            fig.add_trace(
                go.Histogram(x=home_corrections, name="Heim", opacity=0.7, nbinsx=20)
            )
            fig.add_trace(
                go.Histogram(
                    x=away_corrections, name="Auswärts", opacity=0.7, nbinsx=20
                )
            )

            fig.update_layout(
                title="Verteilung der Korrektur-Faktoren",
                xaxis_title="Korrektur-Faktor",
                yaxis_title="Anzahl",
                barmode="overlay",
                height=400,
            )

            st.plotly_chart(fig, use_container_width=True)

            # Scatter: Position vs Correction
            positions = []
            corrections = []

            for m in historical_matches:
                home_team = m.get("home_team")
                if hasattr(home_team, "position"):
                    positions.append(home_team.position)
                    corrections.append(m.get("home_correction", 1.0))

                away_team = m.get("away_team")
                if hasattr(away_team, "position"):
                    positions.append(away_team.position)
                    corrections.append(m.get("away_correction", 1.0))

            if positions:
                fig2 = go.Figure()
                fig2.add_trace(
                    go.Scatter(
                        x=positions,
                        y=corrections,
                        mode="markers",
                        marker=dict(size=8, opacity=0.6),
                    )
                )

                fig2.update_layout(
                    title="Tabellenposition vs. Korrektur-Faktor",
                    xaxis_title="Position (1 = Bester)",
                    yaxis_title="Korrektur-Faktor",
                    height=400,
                )

                st.plotly_chart(fig2, use_container_width=True)

        else:
            st.info("Noch keine historischen Daten vorhanden")

    # ================== TAB 5: DEMO PERFORMANCE ==================
    with tab5:
        st.header("🎮 Demo Performance Dashboard")

        stake_history = st.session_state.risk_management.get("stake_history", [])

        if not stake_history:
            st.info("📊 Noch keine Demo-Wetten platziert")
        else:
            # Overview Metriken
            total_bets = len(stake_history)
            wins = sum(1 for s in stake_history if s["profit"] > 0)
            losses = sum(1 for s in stake_history if s["profit"] < 0)
            win_rate = (wins / total_bets) * 100 if total_bets > 0 else 0

            total_profit = sum(s["profit"] for s in stake_history)
            total_staked = sum(abs(s["stake"]) for s in stake_history)
            roi = (total_profit / total_staked * 100) if total_staked > 0 else 0

            st.markdown("### 📊 Overview")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Gesamt-Wetten", total_bets)
            col2.metric("Win-Rate", f"{win_rate:.1f}%")
            col3.metric("P&L", f"€{total_profit:+.2f}")
            col4.metric("ROI", f"{roi:+.1f}%")

            # Performance nach Market
            st.markdown("---")
            st.markdown("### 📈 Performance nach Market")

            market_stats = {}
            for bet in stake_history:
                market = bet.get("market", "Unknown")
                if market not in market_stats:
                    market_stats[market] = {
                        "bets": 0,
                        "wins": 0,
                        "profit": 0,
                        "staked": 0,
                    }

                market_stats[market]["bets"] += 1
                if bet["profit"] > 0:
                    market_stats[market]["wins"] += 1
                market_stats[market]["profit"] += bet["profit"]
                market_stats[market]["staked"] += abs(bet["stake"])

            market_df = []
            for market, stats in market_stats.items():
                wr = (stats["wins"] / stats["bets"] * 100) if stats["bets"] > 0 else 0
                roi_market = (
                    (stats["profit"] / stats["staked"] * 100)
                    if stats["staked"] > 0
                    else 0
                )

                market_df.append(
                    {
                        "Market": market,
                        "Wetten": stats["bets"],
                        "Wins": stats["wins"],
                        "WR%": f"{wr:.1f}%",
                        "P&L": f"€{stats['profit']:+.2f}",
                        "ROI%": f"{roi_market:+.1f}%",
                    }
                )

            df = pd.DataFrame(market_df)
            df = df.sort_values("ROI%", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Best & Worst Bets
            st.markdown("---")
            col_best, col_worst = st.columns(2)

            sorted_bets = sorted(stake_history, key=lambda x: x["profit"], reverse=True)

            with col_best:
                st.markdown("### ✅ Top 5 Gewinner")
                for bet in sorted_bets[:5]:
                    st.success(
                        f"{bet['match']} ({bet['market']}): €{bet['profit']:+.2f}"
                    )

            with col_worst:
                st.markdown("### ❌ Top 5 Verlierer")
                for bet in sorted_bets[-5:]:
                    st.error(f"{bet['match']} ({bet['market']}): €{bet['profit']:+.2f}")

            # Profit Development Chart
            st.markdown("---")
            st.markdown("### 📈 Profit-Entwicklung")

            cumulative_profit = []
            running_total = 0

            for bet in stake_history:
                running_total += bet["profit"]
                cumulative_profit.append(running_total)

            import plotly.graph_objects as go

            fig_profit = go.Figure()
            fig_profit.add_trace(
                go.Scatter(
                    x=list(range(1, len(cumulative_profit) + 1)),
                    y=cumulative_profit,
                    mode="lines+markers",
                    name="Kumulativer Gewinn",
                    line=dict(color="green" if total_profit >= 0 else "red", width=2),
                )
            )

            fig_profit.update_layout(
                title="Kumulativer Gewinn über alle Wetten",
                xaxis_title="Wetten-Anzahl",
                yaxis_title="Gewinn (€)",
                height=400,
            )

            st.plotly_chart(fig_profit, use_container_width=True)

            # Export & Reset
            st.markdown("---")
            col_export, col_reset = st.columns(2)

            with col_export:
                # Export zu CSV
                export_df = pd.DataFrame(stake_history)
                csv = export_df.to_csv(index=False).encode("utf-8")

                st.download_button(
                    label="📥 Daten als CSV exportieren",
                    data=csv,
                    file_name=f"demo_bets_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with col_reset:
                if st.button("🗑️ Performance zurücksetzen", use_container_width=True):
                    if st.button("✅ Wirklich löschen?", use_container_width=True):
                        st.session_state.risk_management["stake_history"] = []
                        st.success("✅ Performance zurückgesetzt!")
                        st.rerun()


if __name__ == "__main__":
    main()
