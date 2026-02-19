"""
Google Sheets Persistenz für das Bankroll System
Speichert pro User: Bankroll-Status + Wett-Historie
"""

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SHEET_NAME = "Bankroll"


def _get_sheets_service():
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    import streamlit as st

    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def _get_sheet_id() -> Optional[str]:
    try:
        import streamlit as st
        return st.secrets.get("tracking", {}).get("sheet_id")
    except Exception:
        return os.getenv("TRACKING_SHEET_ID")


def _ensure_sheet_exists(service, spreadsheet_id: str):
    """Erstellt Bankroll-Tab falls nicht vorhanden"""
    try:
        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if SHEET_NAME not in sheets:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": SHEET_NAME}}}]}
            ).execute()
            # Header
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{SHEET_NAME}!A1:B1",
                valueInputOption="RAW",
                body={"values": [["user_id", "data"]]},
            ).execute()
    except Exception as e:
        logger.error(f"Sheet-Erstellung fehlgeschlagen: {e}")


def load_user(user_id: int) -> Optional[dict]:
    try:
        sheet_id = _get_sheet_id()
        if not sheet_id:
            return None

        service = _get_sheets_service()
        _ensure_sheet_exists(service, sheet_id)

        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{SHEET_NAME}!A:B",
        ).execute()

        rows = result.get("values", [])
        for row in rows[1:]:  # Skip header
            if len(row) >= 2 and str(row[0]) == str(user_id):
                return json.loads(row[1])
        return None
    except Exception as e:
        logger.error(f"load_user Fehler: {e}")
        return None


def save_user(user_id: int, data: dict):
    try:
        sheet_id = _get_sheet_id()
        if not sheet_id:
            return

        service = _get_sheets_service()
        _ensure_sheet_exists(service, sheet_id)

        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{SHEET_NAME}!A:B",
        ).execute()

        rows = result.get("values", [])
        json_data = json.dumps(data, ensure_ascii=False)

        # Suche existierende Zeile
        row_num = None
        for i, row in enumerate(rows[1:], start=2):
            if len(row) >= 1 and str(row[0]) == str(user_id):
                row_num = i
                break

        if row_num:
            # Update
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{SHEET_NAME}!A{row_num}:B{row_num}",
                valueInputOption="RAW",
                body={"values": [[str(user_id), json_data]]},
            ).execute()
        else:
            # Append
            service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range=f"{SHEET_NAME}!A:B",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [[str(user_id), json_data]]},
            ).execute()

    except Exception as e:
        logger.error(f"save_user Fehler: {e}")
