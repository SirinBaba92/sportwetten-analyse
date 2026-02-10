"""
Export-Funktionen für Google Sheets (Wettquoten Tipps)
"""

import streamlit as st
from datetime import datetime
from data.google_sheets import connect_to_sheets
from config.constants import EXPORT_SHEET_ID


def export_analysis_to_sheets(result: dict, actual_score: str = None) -> bool:
    """
    Exportiert Analyse-Ergebnis zu Google Sheets (Wettquoten Tipps)

    Args:
        result: Analyse-Ergebnis Dictionary
        actual_score: Tatsächliches Ergebnis falls bekannt (z.B. "2:1")

    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        # Google Sheets Verbindung herstellen
        service = connect_to_sheets(readonly=False)
        if not service:
            st.error("❌ Keine Verbindung zu Google Sheets")
            return False

        # Match-Datum extrahieren
        match_date_str = result["match_info"]["date"]  # Format: "dd.mm.yyyy"

        # Konvertiere zu Sheet-Tab Format (dd.mm.yyyy bleibt gleich)
        sheet_tab_name = match_date_str

        # Prüfe ob Tab existiert
        sheet_metadata = (
            service.spreadsheets().get(spreadsheetId=EXPORT_SHEET_ID).execute()
        )
        sheets = sheet_metadata.get("sheets", [])
        sheet_titles = [s["properties"]["title"] for s in sheets]

        if sheet_tab_name not in sheet_titles:
            st.error(f"❌ Tabellenblatt '{sheet_tab_name}' existiert nicht!")
            st.info(f"💡 Verfügbare Blätter: {', '.join(sheet_titles[:5])}...")
            return False

        # Bereite Daten vor
        match_name = f"{result['match_info']['home']} vs {result['match_info']['away']}"

        # Wenn ein tatsächliches Ergebnis übergeben wird, soll *dieselbe Match-Zeile*
        # (Blockstart B1/B11/B21/...) aktualisiert werden.
        # Falls der Match-Block noch nicht existiert, fällt es auf den nächsten freien Block zurück.
        if actual_score:
            next_row = find_match_row(service, sheet_tab_name, match_name)
            if next_row is None:
                next_row = find_next_free_row(service, sheet_tab_name)
        else:
            # Standard: nächsten freien Block nehmen
            next_row = find_next_free_row(service, sheet_tab_name)

        if next_row is None:
            st.error("❌ Fehler beim Finden der passenden Zeile")
            return False

        predicted_score = result.get("predicted_score", "")
        # Gewünschtes Format im Sheet: "1-0" statt "1:0"
        if isinstance(predicted_score, str):
            predicted_score = predicted_score.replace(":", "-").strip()

        probs = result["probabilities"]

        # Prüfe Schwellenwerte
        prob_1x2_home = probs["home_win"]
        prob_1x2_draw = probs["draw"]
        prob_1x2_away = probs["away_win"]
        prob_over = probs["over_25"]
        prob_under = probs["under_25"]
        prob_btts_yes = probs["btts_yes"]
        prob_btts_no = probs["btts_no"]

        # Bestimme beste 1X2 Option
        best_1x2_prob = max(prob_1x2_home, prob_1x2_draw, prob_1x2_away)
        prob_1x2_to_export = best_1x2_prob if best_1x2_prob >= 50 else None

        # Bestimme beste O/U Option
        best_ou_prob = max(prob_over, prob_under)
        prob_ou_to_export = best_ou_prob if best_ou_prob >= 60 else None

        # Bestimme beste BTTS Option
        best_btts_prob = max(prob_btts_yes, prob_btts_no)
        prob_btts_to_export = best_btts_prob if best_btts_prob >= 60 else None

        # Erstelle Update-Requests passend zum Template:
        # B1/B11/B21...: Match-Name
        # B4/B14/B24...: 1X2 % (>= 50%)
        # B6/B16/B26...: O/U % (>= 60%)
        # B8/B18/B28...: BTTS % (>= 60%)
        # B9/B19/B29...: Predicted Score
        # G1/G11/G21...: Tatsächliches Ergebnis (falls vorhanden)

        updates = [
            {"range": f"{sheet_tab_name}!B{next_row}", "values": [[match_name]]},
            {
                "range": f"{sheet_tab_name}!B{next_row + 3}",
                "values": [[f"{prob_1x2_to_export:.1f}%" if prob_1x2_to_export else ""]],
            },
            {
                "range": f"{sheet_tab_name}!B{next_row + 5}",
                "values": [[f"{prob_ou_to_export:.1f}%" if prob_ou_to_export else ""]],
            },
            {
                "range": f"{sheet_tab_name}!B{next_row + 7}",
                "values": [[f"{prob_btts_to_export:.1f}%" if prob_btts_to_export else ""]],
            },
            {"range": f"{sheet_tab_name}!B{next_row + 8}", "values": [[predicted_score]]},
        ]

        if actual_score:
            updates.append({"range": f"{sheet_tab_name}!G{next_row}", "values": [[actual_score]]})

        # Batch Update durchführen
        body = {"valueInputOption": "USER_ENTERED", "data": updates}

        service.spreadsheets().values().batchUpdate(
            spreadsheetId=EXPORT_SHEET_ID, body=body
        ).execute()

        st.success(f"✅ Export erfolgreich! Zeile {next_row} in '{sheet_tab_name}'")
        return True

    except Exception as e:
        st.error(f"❌ Export-Fehler: {str(e)}")
        import traceback

        st.error(traceback.format_exc())
        return False


def find_next_free_row(service, sheet_tab_name: str) -> int:
    """
    Findet die nächste freie Zeile im 10er-Intervall (1, 11, 21, 31...)

    Args:
        service: Google Sheets Service
        sheet_tab_name: Name des Tabellenblatts

    Returns:
        Nächste freie Zeile oder None bei Fehler
    """
    try:
        # Wir prüfen die Block-Startzellen B1, B11, B21, ...
        # Ein Block ist "frei", wenn die Match-Name-Zelle (B{start}) leer ist.
        max_row = 2000
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=EXPORT_SHEET_ID, range=f"{sheet_tab_name}!B1:B{max_row}")
            .execute()
        )

        values = result.get("values", [])

        def cell_value(row_1_indexed: int) -> str:
            idx = row_1_indexed - 1
            if idx < len(values) and values[idx]:
                return str(values[idx][0]).strip()
            return ""

        for start in range(1, max_row + 1, 10):
            if cell_value(start) == "":
                return start

        # Falls alles belegt ist, hänge am Ende einen neuen Block an
        return max_row + 1

    except Exception as e:
        st.error(f"Fehler beim Finden der freien Zeile: {e}")
        return None


def find_match_row(service, sheet_tab_name: str, match_name: str) -> int | None:
    """Findet den Blockstart (1, 11, 21, ...) für einen bereits exportierten Match.

    Gesucht wird in Spalte B nur an den Block-Start-Zeilen (B1/B11/B21/...).
    Gibt die Startzeile zurück, wenn der Matchname exakt übereinstimmt.
    """
    try:
        max_row = 2000
        resp = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=EXPORT_SHEET_ID, range=f"{sheet_tab_name}!B1:B{max_row}")
            .execute()
        )
        values = resp.get("values", [])

        def cell_value(row_1_indexed: int) -> str:
            idx = row_1_indexed - 1
            if idx < len(values) and values[idx]:
                return str(values[idx][0]).strip()
            return ""

        target = (match_name or "").strip()
        if not target:
            return None

        for start in range(1, max_row + 1, 10):
            if cell_value(start) == target:
                return start

        return None
    except Exception as e:
        st.error(f"Fehler beim Finden der Match-Zeile: {e}")
        return None
