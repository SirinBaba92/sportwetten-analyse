"""
Telegram Bot Handler - Sportwetten Analyse
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.sheets_service import (
    list_available_dates,
    list_tabs_in_sheet,
    read_sheet_tab,
    get_todays_sheet_id,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# HILFSFUNKTIONEN
# ─────────────────────────────────────────────

def _run_analysis(spreadsheet_id: str, tab_name: str) -> Optional[dict]:
    """Liest Sheet-Tab und führt echte Analyse durch"""
    try:
        from data.parser import DataParser
        from analysis.match_analysis import analyze_match_v47_ml
        from app import choose_consistent_predicted_score

        raw_text = read_sheet_tab(spreadsheet_id, tab_name)
        if not raw_text.strip():
            return None

        parser = DataParser()
        match_data = parser.parse(raw_text)
        result = analyze_match_v47_ml(match_data)
        result = choose_consistent_predicted_score(result)
        return result
    except Exception as e:
        logger.error(f"Analyse-Fehler für Tab '{tab_name}': {e}", exc_info=True)
        return None
def _format_analysis(result: dict) -> str:
    """Formatiert Analyse-Ergebnis als Telegram-Nachricht"""
    info = result.get("match_info", {})
    probs = result.get("probabilities", {})
    mu = result.get("mu", {})
    risk_score = result.get("risk_score", 0)
    ext_risk = result.get("extended_risk", {})
    score = result.get("predicted_score", "?-?")
    odds = result.get("odds", {})
    tki = result.get("tki", {})

    home = info.get("home_team", "Heim")
    away = info.get("away_team", "Gast")
    competition = info.get("competition", "")
    kickoff = info.get("kickoff", "")

    # Risiko aus extended_risk["overall"] oder fallback auf risk_score
    # overall kann ein dict oder int sein je nach extended_risk Struktur
    _overall = ext_risk.get("overall", risk_score) if ext_risk else risk_score
    if isinstance(_overall, dict):
        overall_risk = _overall.get("score", _overall.get("value", risk_score))
    else:
        overall_risk = _overall
    try:
        overall_risk = int(overall_risk)
    except Exception:
        overall_risk = int(risk_score)
    empfehlung = ""

    # Empfehlung aus calculate_risk_score Struktur (simpler risk_score)
    risk_labels = {
        0: "Sehr niedrig",
        1: "Gute Basis für Wetten",
        2: "Solide Wettmöglichkeit",
        3: "Standard-Risiko",
        4: "Vorsicht bei Wetten",
        5: "Sehr spekulativ",
    }
    empfehlung = risk_labels.get(int(overall_risk), "")

    risk_emoji = ["🟢", "🟢", "🟡", "🟡", "🔴", "🔴"][min(int(overall_risk), 5)]

    # Value Bet Check
    def implied_prob(odd):
        try:
            return 1 / float(odd) * 100
        except Exception:
            return 0

    odds_1x2 = odds.get("1x2", (0, 0, 0))
    odds_ou = odds.get("ou25", (0, 0))
    odds_btts = odds.get("btts", (0, 0))

    value_hints = []
    checks = [
        ("Heimsieg", probs.get("home_win", 0), implied_prob(odds_1x2[0]), odds_1x2[0]),
        ("Unentschieden", probs.get("draw", 0), implied_prob(odds_1x2[1]), odds_1x2[1]),
        ("Auswärtssieg", probs.get("away_win", 0), implied_prob(odds_1x2[2]), odds_1x2[2]),
        ("Über 2.5", probs.get("over_25", 0), implied_prob(odds_ou[0]), odds_ou[0]),
        ("Unter 2.5", probs.get("under_25", 0), implied_prob(odds_ou[1]), odds_ou[1]),
        ("BTTS Ja", probs.get("btts_yes", 0), implied_prob(odds_btts[0]), odds_btts[0]),
        ("BTTS Nein", probs.get("btts_no", 0), implied_prob(odds_btts[1]), odds_btts[1]),
    ]
    for label, our_prob, imp_prob, odd in checks:
        if odd and our_prob > imp_prob + 5:
            value_hints.append(f"✅ VALUE: {label} @ {odd}")

    value_section = "\n".join(value_hints) if value_hints else "⚪ Kein klarer Value erkannt"

    # TKI Warnung
    tki_h = tki.get("home", 0)
    tki_a = tki.get("away", 0)
    tki_note = ""
    if tki_h > 2.5:
        tki_note += f"\n⚠️ TKI-Krise: {home} ({tki_h})"
    if tki_a > 2.5:
        tki_note += f"\n⚠️ TKI-Krise: {away} ({tki_a})"

    text = (
        f"⚽ <b>{home} vs {away}</b>\n"
        f"🏆 {competition}  |  ⏰ {kickoff}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>Prognose: {score}</b>\n\n"
        f"📊 <b>Wahrscheinlichkeiten</b>\n"
        f"  Heimsieg:      <b>{probs.get('home_win', 0):.1f}%</b>\n"
        f"  Unentschieden: <b>{probs.get('draw', 0):.1f}%</b>\n"
        f"  Auswärtssieg:  <b>{probs.get('away_win', 0):.1f}%</b>\n\n"
        f"  Über 2.5:  <b>{probs.get('over_25', 0):.1f}%</b>\n"
        f"  Unter 2.5: <b>{probs.get('under_25', 0):.1f}%</b>\n"
        f"  BTTS Ja:   <b>{probs.get('btts_yes', 0):.1f}%</b>\n"
        f"  BTTS Nein: <b>{probs.get('btts_no', 0):.1f}%</b>\n"
        f"{tki_note}\n"
        f"🔢 μ: Heim {mu.get('home', 0):.2f} | Gast {mu.get('away', 0):.2f}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Value Bets</b>\n"
        f"{value_section}\n\n"
        f"{risk_emoji} <b>Risiko: {int(overall_risk)}/5</b>  {empfehlung}\n"
    )
    return text


def _format_match_list(matches: list, title: str) -> str:
    text = f"📅 <b>{title}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, m in enumerate(matches, 1):
        text += f"{i}. {m['home']} vs {m['away']}\n"
    text += "\n💡 Klicke eine Zahl für die Analyse"
    return text


# ─────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"👋 <b>Sportwetten-Analyse Bot</b>\n\n"
        f"📋 <b>Befehle:</b>\n"
        f"/today – Heutige Matches\n"
        f"/date 15.02.2025 – Matches an einem Datum\n"
        f"/dates – Alle verfügbaren Daten\n"
        f"/bet – Wett-Empfehlungen für heute\n\n"
        f"Powered by SMART-PRECISION v4.7+ ⚽"
    )
    keyboard = [
        [
            InlineKeyboardButton("📅 Heute", callback_data="cmd_today"),
            InlineKeyboardButton("💰 Empfehlungen", callback_data="cmd_bet"),
        ],
        [InlineKeyboardButton("📆 Alle Daten", callback_data="cmd_dates")],
    ]
    await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    loading = await msg.reply_html("🔄 Lade heutige Matches...")

    result = get_todays_sheet_id()
    if not result:
        await loading.edit_text("📭 Keine Matches für heute gefunden.")
        return

    date_str, sheet_id = result
    tabs = list_tabs_in_sheet(sheet_id)
    skip = {"overview", "übersicht", "zusammenfassung", "tracking", "results"}
    match_tabs = [t for t in tabs if t.lower() not in skip]

    if not match_tabs:
        await loading.edit_text(f"📭 Keine Match-Tabs in Sheet {date_str} gefunden.")
        return

    matches = [
        {"home": t.split(" vs ")[0].strip() if " vs " in t else t,
         "away": t.split(" vs ")[1].strip() if " vs " in t else "",
         "tab": t, "sheet_id": sheet_id}
        for t in match_tabs
    ]
    context.bot_data[f"matches_{date_str}"] = matches

    text = _format_match_list(
        [{"home": m["home"], "away": m["away"]} for m in matches],
        f"HEUTE – {date_str}"
    )

    keyboard = []
    row = []
    for i in range(1, len(match_tabs) + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"analyze_{date_str}_{i-1}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await loading.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def dates_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    loading = await msg.reply_html("🔄 Lade verfügbare Daten...")

    dates = list_available_dates()
    if not dates:
        await loading.edit_text("📭 Keine Daten verfügbar.")
        return

    sorted_dates = sorted(dates.keys(), reverse=True)
    text = f"📆 <b>VERFÜGBARE DATEN</b> ({len(sorted_dates)} Tage)\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    by_month: dict = {}
    for d in sorted_dates:
        month = d[3:]
        by_month.setdefault(month, []).append(d)

    for month in sorted(by_month.keys(), reverse=True)[:4]:
        text += f"<b>{month}</b>\n"
        for d in by_month[month][:10]:
            text += f"  • {d}\n"
        text += "\n"

    text += "💡 Nutze /date DD.MM.YYYY"
    await loading.edit_text(text, parse_mode="HTML")


async def date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_html("❌ Format: /date DD.MM.YYYY\nBeispiel: /date 15.02.2025")
        return

    date_str = context.args[0]
    loading = await update.message.reply_html(f"🔄 Lade Matches für {date_str}...")

    dates = list_available_dates()
    if date_str not in dates:
        await loading.edit_text(f"❌ Keine Daten für {date_str} gefunden.")
        return

    sheet_id = dates[date_str]
    tabs = list_tabs_in_sheet(sheet_id)
    skip = {"overview", "übersicht", "zusammenfassung", "tracking", "results"}
    match_tabs = [t for t in tabs if t.lower() not in skip]

    if not match_tabs:
        await loading.edit_text(f"📭 Keine Match-Tabs für {date_str}.")
        return

    matches = [
        {"home": t.split(" vs ")[0].strip() if " vs " in t else t,
         "away": t.split(" vs ")[1].strip() if " vs " in t else "",
         "tab": t, "sheet_id": sheet_id}
        for t in match_tabs
    ]
    context.bot_data[f"matches_{date_str}"] = matches

    text = _format_match_list(
        [{"home": m["home"], "away": m["away"]} for m in matches],
        f"MATCHES – {date_str}"
    )

    keyboard = []
    row = []
    for i in range(1, len(match_tabs) + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"analyze_{date_str}_{i-1}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    await loading.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.callback_query.message
    loading = await msg.reply_html("💰 Berechne Wett-Empfehlungen...")

    result = get_todays_sheet_id()
    if not result:
        await loading.edit_text("📭 Keine heutigen Matches vorhanden.")
        return

    date_str, sheet_id = result
    tabs = list_tabs_in_sheet(sheet_id)
    skip = {"overview", "übersicht", "zusammenfassung", "tracking", "results"}
    match_tabs = [t for t in tabs if t.lower() not in skip]

    if not match_tabs:
        await loading.edit_text("📭 Keine Match-Tabs gefunden.")
        return

    await loading.edit_text(f"⏳ Analysiere {len(match_tabs)} Matches...")

    recommendations = []
    for tab in match_tabs:
        analysis = _run_analysis(sheet_id, tab)
        if not analysis:
            continue

        probs = analysis.get("probabilities", {})
        odds = analysis.get("odds", {})
        ext_risk = analysis.get("extended_risk", {})
        _ov = ext_risk.get("overall", analysis.get("risk_score", 5)) if ext_risk else analysis.get("risk_score", 5)
        if isinstance(_ov, dict):
            _ov = _ov.get("score", _ov.get("value", analysis.get("risk_score", 5)))
        try:
            overall_risk = int(_ov)
        except Exception:
            overall_risk = int(analysis.get("risk_score", 5))
        info = analysis.get("match_info", {})

        def implied(o):
            try: return 1 / float(o) * 100
            except: return 100

        odds_1x2 = odds.get("1x2", (0, 0, 0))
        odds_ou = odds.get("ou25", (0, 0))
        odds_btts = odds.get("btts", (0, 0))

        checks = [
            ("Heimsieg", probs.get("home_win", 0), implied(odds_1x2[0]), odds_1x2[0]),
            ("Unentschieden", probs.get("draw", 0), implied(odds_1x2[1]), odds_1x2[1]),
            ("Auswärtssieg", probs.get("away_win", 0), implied(odds_1x2[2]), odds_1x2[2]),
            ("Über 2.5", probs.get("over_25", 0), implied(odds_ou[0]), odds_ou[0]),
            ("Unter 2.5", probs.get("under_25", 0), implied(odds_ou[1]), odds_ou[1]),
            ("BTTS Ja", probs.get("btts_yes", 0), implied(odds_btts[0]), odds_btts[0]),
            ("BTTS Nein", probs.get("btts_no", 0), implied(odds_btts[1]), odds_btts[1]),
        ]

        for bet_type, our_prob, imp_prob, odd in checks:
            edge = our_prob - imp_prob
            if edge >= 5 and overall_risk <= 3 and odd:
                recommendations.append({
                    "home": info.get("home_team", "?"),
                    "away": info.get("away_team", "?"),
                    "bet_type": bet_type,
                    "prob": our_prob,
                    "odd": odd,
                    "edge": edge,
                    "risk": int(overall_risk),
                })

    if not recommendations:
        await loading.edit_text(
            "📭 <b>Keine klaren Value Bets heute</b>\n\n"
            "Kein ausreichendes Value (Edge < 5%) oder zu hohes Risiko.\n\n"
            "Nutze /today für manuelle Analyse.",
            parse_mode="HTML"
        )
        return

    recommendations.sort(key=lambda x: x["edge"], reverse=True)

    text = f"💰 <b>VALUE BETS – {date_str}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, rec in enumerate(recommendations[:5], 1):
        risk_emoji = "🟢" if rec["risk"] <= 2 else "🟡"
        text += (
            f"<b>{i}. {rec['home']} vs {rec['away']}</b>\n"
            f"   Tipp: <b>{rec['bet_type']}</b>\n"
            f"   Quote: {rec['odd']}  |  Prob: {rec['prob']:.1f}%\n"
            f"   Edge: +{rec['edge']:.1f}%  {risk_emoji} Risiko {rec['risk']}/5\n\n"
        )

    await loading.edit_text(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# CALLBACK HANDLER
# ─────────────────────────────────────────────

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cmd_today":
        await today_handler(update, context)
    elif data == "cmd_bet":
        await bet_handler(update, context)
    elif data == "cmd_dates":
        await dates_handler(update, context)
    elif data.startswith("analyze_"):
        parts = data.split("_", 2)
        if len(parts) == 3:
            _, date_str, idx_str = parts
            try:
                idx = int(idx_str)
            except ValueError:
                await query.edit_message_text("❌ Ungültige Match-ID")
                return

            matches = context.bot_data.get(f"matches_{date_str}")
            if not matches or idx >= len(matches):
                await query.edit_message_text("❌ Match nicht mehr im Cache. Nutze /today erneut.")
                return

            match = matches[idx]
            await query.edit_message_text(f"⏳ Analysiere {match['home']} vs {match['away']}...")

            result = _run_analysis(match["sheet_id"], match["tab"])
            if not result:
                await query.edit_message_text("❌ Analyse fehlgeschlagen – Tab-Daten unvollständig?")
                return

            text = _format_analysis(result)
            await query.edit_message_text(text, parse_mode="HTML")
    else:
        await query.edit_message_text("⚠️ Unbekannte Aktion")


# ─────────────────────────────────────────────
# ERROR HANDLER
# ─────────────────────────────────────────────

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Fehler: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            f"❌ Fehler: {str(context.error)[:200]}"
        )
