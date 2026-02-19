"""
Telegram Bot Handler - Sportwetten Analyse (Mehrsprachig)
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
from telegram_bot.translations import t, get_risk_label, get_bet_type

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# SPRACHE
# ─────────────────────────────────────────────

def get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", "de")


# ─────────────────────────────────────────────
# HILFSFUNKTIONEN
# ─────────────────────────────────────────────

def _run_analysis(spreadsheet_id: str, tab_name: str) -> Optional[dict]:
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


def _format_analysis(result: dict, lang: str = "de") -> str:
    info = result.get("match_info", {})
    probs = result.get("probabilities", {})
    mu = result.get("mu", {})
    risk_score = result.get("risk_score", 0)
    ext_risk = result.get("extended_risk", {})
    score = result.get("predicted_score", "?-?")
    tki = result.get("tki", {})

    home = info.get("home", info.get("home_team", "Heim"))
    away = info.get("away", info.get("away_team", "Gast"))
    competition = info.get("competition", "")
    kickoff = info.get("kickoff", "")

    _overall = ext_risk.get("overall", risk_score) if ext_risk else risk_score
    if isinstance(_overall, dict):
        overall_risk = _overall.get("score", _overall.get("value", risk_score))
    else:
        overall_risk = _overall
    try:
        overall_risk = int(overall_risk)
    except Exception:
        overall_risk = int(risk_score)

    empfehlung = get_risk_label(overall_risk, lang)
    risk_emoji = ["🟢", "🟢", "🟡", "🟡", "🔴", "🔴"][min(overall_risk, 5)]

    tki_h = tki.get("home", 0)
    tki_a = tki.get("away", 0)
    tki_note = ""
    if tki_h > 2.5:
        tki_note += f"\n{t('tki_krise', lang, team=home, val=tki_h)}"
    if tki_a > 2.5:
        tki_note += f"\n{t('tki_krise', lang, team=away, val=tki_a)}"

    # Gelbe Punkte bei erfüllten Kriterien (identisch mit Streamlit)
    def dot(prob, threshold):
        return "🟡 " if prob >= threshold else "     "

    hw = probs.get("home_win", 0)
    dr = probs.get("draw", 0)
    aw = probs.get("away_win", 0)
    ov = probs.get("over_25", 0)
    un = probs.get("under_25", 0)
    by = probs.get("btts_yes", 0)
    bn = probs.get("btts_no", 0)

    text = (
        f"⚽ <b>{home} vs {away}</b>\n"
        f"🏆 {competition}  |  ⏰ {kickoff}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>{t('prognose', lang)}: {score}</b>\n\n"
        f"{t('wahrscheinlichkeiten', lang)}\n"
        f"  {dot(hw,50)}{t('heimsieg', lang)}:      <b>{hw:.1f}%</b>\n"
        f"  {dot(dr,50)}{t('unentschieden', lang)}: <b>{dr:.1f}%</b>\n"
        f"  {dot(aw,50)}{t('auswaertssieg', lang)}: <b>{aw:.1f}%</b>\n\n"
        f"  {dot(ov,60)}{t('ueber', lang)}:  <b>{ov:.1f}%</b>\n"
        f"  {dot(un,60)}{t('unter', lang)}: <b>{un:.1f}%</b>\n"
        f"  {dot(by,60)}{t('btts_ja', lang)}:   <b>{by:.1f}%</b>\n"
        f"  {dot(bn,60)}{t('btts_nein', lang)}: <b>{bn:.1f}%</b>\n"
        f"{tki_note}\n"
        f"{t('mu_label', lang, home=mu.get('home', 0), away=mu.get('away', 0))}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{risk_emoji} <b>{t('risiko', lang)}: {overall_risk}/5</b>  {empfehlung}\n"
    )
    return text


def _format_match_list(matches: list, title: str, lang: str = "de") -> str:
    text = f"📅 <b>{title}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, m in enumerate(matches, 1):
        text += f"{i}. {m['home']} vs {m['away']}\n"
    text += f"\n{t('click_number', lang)}"
    return text


# ─────────────────────────────────────────────
# COMMAND HANDLERS
# ─────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    keyboard = [
        [
            InlineKeyboardButton(t("btn_today", lang), callback_data="cmd_today"),
            InlineKeyboardButton(t("btn_bet", lang), callback_data="cmd_bet"),
        ],
        [InlineKeyboardButton(t("btn_all_dates", lang), callback_data="cmd_dates")],
    ]
    await update.message.reply_html(
        t("start_welcome", lang),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def lang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    keyboard = [
        [
            InlineKeyboardButton(t("btn_de", lang), callback_data="lang_de"),
            InlineKeyboardButton(t("btn_tr", lang), callback_data="lang_tr"),
            InlineKeyboardButton(t("btn_en", lang), callback_data="lang_en"),
        ]
    ]
    await update.message.reply_html(
        t("lang_current", lang),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    msg = update.message or update.callback_query.message
    loading = await msg.reply_html(t("loading_today", lang))

    result = get_todays_sheet_id()
    if not result:
        await loading.edit_text(t("no_matches_today", lang))
        return

    date_str, sheet_id = result
    tabs = list_tabs_in_sheet(sheet_id)
    skip = {"overview", "übersicht", "zusammenfassung", "tracking", "results"}
    match_tabs = [t_ for t_ in tabs if t_.lower() not in skip]

    if not match_tabs:
        await loading.edit_text(t("no_tabs_today", lang))
        return

    matches = [
        {"home": t_.split(" vs ")[0].strip() if " vs " in t_ else t_,
         "away": t_.split(" vs ")[1].strip() if " vs " in t_ else "",
         "tab": t_, "sheet_id": sheet_id}
        for t_ in match_tabs
    ]
    context.bot_data[f"matches_{date_str}"] = matches

    text = _format_match_list(
        [{"home": m["home"], "away": m["away"]} for m in matches],
        t("title_today", lang, date=date_str),
        lang
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
    lang = get_lang(context)
    msg = update.message or update.callback_query.message
    loading = await msg.reply_html(t("loading_dates", lang))

    dates = list_available_dates()
    if not dates:
        await loading.edit_text(t("no_dates", lang))
        return

    sorted_dates = sorted(dates.keys(), reverse=True)
    text = t("title_dates", lang, count=len(sorted_dates))

    by_month: dict = {}
    for d in sorted_dates:
        month = d[3:]
        by_month.setdefault(month, []).append(d)

    for month in sorted(by_month.keys(), reverse=True)[:4]:
        text += f"<b>{month}</b>\n"
        for d in by_month[month][:10]:
            text += f"  • {d}\n"
        text += "\n"

    text += t("hint_date", lang)
    await loading.edit_text(text, parse_mode="HTML")


async def date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    if not context.args:
        await update.message.reply_html(t("format_date", lang))
        return

    date_str = context.args[0]
    loading = await update.message.reply_html(t("loading_date", lang, date=date_str))

    dates = list_available_dates()
    if date_str not in dates:
        await loading.edit_text(t("no_data_date", lang, date=date_str))
        return

    sheet_id = dates[date_str]
    tabs = list_tabs_in_sheet(sheet_id)
    skip = {"overview", "übersicht", "zusammenfassung", "tracking", "results"}
    match_tabs = [t_ for t_ in tabs if t_.lower() not in skip]

    if not match_tabs:
        await loading.edit_text(t("no_tabs_date", lang, date=date_str))
        return

    matches = [
        {"home": t_.split(" vs ")[0].strip() if " vs " in t_ else t_,
         "away": t_.split(" vs ")[1].strip() if " vs " in t_ else "",
         "tab": t_, "sheet_id": sheet_id}
        for t_ in match_tabs
    ]
    context.bot_data[f"matches_{date_str}"] = matches

    text = _format_match_list(
        [{"home": m["home"], "away": m["away"]} for m in matches],
        t("title_date", lang, date=date_str),
        lang
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
    lang = get_lang(context)
    msg = update.message or update.callback_query.message
    loading = await msg.reply_html(t("loading_bet", lang))

    result = get_todays_sheet_id()
    if not result:
        await loading.edit_text(t("no_matches_bet", lang))
        return

    date_str, sheet_id = result
    tabs = list_tabs_in_sheet(sheet_id)
    skip = {"overview", "übersicht", "zusammenfassung", "tracking", "results"}
    match_tabs = [t_ for t_ in tabs if t_.lower() not in skip]

    if not match_tabs:
        await loading.edit_text(t("no_tabs_today", lang))
        return

    await loading.edit_text(t("analyzing", lang, count=len(match_tabs)))

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
                    "home": info.get("home", info.get("home_team", "?")),
                    "away": info.get("away", info.get("away_team", "?")),
                    "bet_type": bet_type,
                    "prob": our_prob,
                    "odd": odd,
                    "edge": edge,
                    "risk": overall_risk,
                })

    if not recommendations:
        await loading.edit_text(t("no_value_bets", lang), parse_mode="HTML")
        return

    recommendations.sort(key=lambda x: x["edge"], reverse=True)

    text = t("title_bet", lang, date=date_str)
    for i, rec in enumerate(recommendations[:5], 1):
        risk_emoji = "🟢" if rec["risk"] <= 2 else "🟡"
        bet_label = get_bet_type(rec["bet_type"], lang)
        text += (
            f"<b>{i}. {rec['home']} vs {rec['away']}</b>\n"
            f"   {t('bet_tip', lang)}: <b>{bet_label}</b>\n"
            f"   {t('bet_quote', lang)}: {rec['odd']}  |  {t('bet_prob', lang)}: {rec['prob']:.1f}%\n"
            f"   {t('bet_edge', lang)}: +{rec['edge']:.1f}%  {risk_emoji} {t('bet_risk', lang)} {rec['risk']}/5\n\n"
        )

    await loading.edit_text(text, parse_mode="HTML")


# ─────────────────────────────────────────────
# CALLBACK HANDLER
# ─────────────────────────────────────────────

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    lang = get_lang(context)

    if data == "cmd_today":
        await today_handler(update, context)
    elif data == "cmd_bet":
        await bet_handler(update, context)
    elif data == "cmd_dates":
        await dates_handler(update, context)

    elif data.startswith("lang_"):
        new_lang = data.split("_")[1]
        if new_lang in ("de", "tr", "en"):
            context.user_data["lang"] = new_lang
            await query.edit_message_text(
                t("lang_changed", new_lang),
                parse_mode="HTML"
            )

    elif data.startswith("analyze_"):
        parts = data.split("_", 2)
        if len(parts) == 3:
            _, date_str, idx_str = parts
            try:
                idx = int(idx_str)
            except ValueError:
                await query.edit_message_text(t("unknown_action", lang))
                return

            matches = context.bot_data.get(f"matches_{date_str}")
            if not matches or idx >= len(matches):
                await query.edit_message_text(t("cache_miss", lang))
                return

            match = matches[idx]
            await query.edit_message_text(
                t("analyzing_match", lang, home=match["home"], away=match["away"])
            )

            result = _run_analysis(match["sheet_id"], match["tab"])
            if not result:
                await query.edit_message_text(t("analysis_failed", lang))
                return

            text = _format_analysis(result, lang)

            # Bankroll Button wenn Bankroll gesetzt
            from telegram_bot.bankroll import get_bankroll
            keyboard = None
            if get_bankroll(query.from_user.id) > 0:
                # Beste Option für Wette ermitteln
                probs = result.get("probabilities", {})
                odds = result.get("odds", {})
                info = result.get("match_info", {})
                match_name = f"{info.get('home', '?')[:15]} vs {info.get('away', '?')[:15]}"

                best = max([
                    ("Heimsieg", probs.get("home_win", 0), odds.get("1x2", [0,0,0])[0]),
                    ("Unentschieden", probs.get("draw", 0), odds.get("1x2", [0,0,0])[1]),
                    ("Auswärtssieg", probs.get("away_win", 0), odds.get("1x2", [0,0,0])[2]),
                    ("Über 2.5", probs.get("over_25", 0), odds.get("ou25", [0,0])[0]),
                    ("Unter 2.5", probs.get("under_25", 0), odds.get("ou25", [0,0])[1]),
                    ("BTTS Ja", probs.get("btts_yes", 0), odds.get("btts", [0,0])[0]),
                    ("BTTS Nein", probs.get("btts_no", 0), odds.get("btts", [0,0])[1]),
                ], key=lambda x: x[1])

                cb = f"bet_menu_{match_name}|{best[0]}|{best[2]}|{best[1]:.1f}"
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("💰 Wette platzieren", callback_data=cb)
                ]])

            await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    elif data == "bank_open":
        await open_bets_handler(update, context)
    elif data == "bank_stats":
        await stats_handler(update, context)
    elif data == "bank_cancel":
        await query.edit_message_text("❌ Abgebrochen.")
    elif data == "bank_reset_confirm":
        keyboard = [[
            InlineKeyboardButton("✅ Ja, reset", callback_data="bank_reset_do"),
            InlineKeyboardButton("❌ Nein", callback_data="bank_cancel"),
        ]]
        await query.edit_message_text(
            "⚠️ Bankroll wirklich zurücksetzen? Alle Daten werden gelöscht.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif data == "bank_reset_do":
        from telegram_bot.bankroll import set_bankroll, get_user_data
        init = get_user_data(query.from_user.id)["initial"]
        set_bankroll(query.from_user.id, init)
        await query.edit_message_text(f"✅ Bankroll zurückgesetzt auf {init:.2f} €")

    elif data.startswith("close_"):
        parts = data.split("_")
        bet_id = int(parts[1])
        won = parts[2] == "won"
        from telegram_bot.bankroll import close_bet
        result = close_bet(query.from_user.id, bet_id, won)
        if "error" in result:
            await query.answer("❌ Wette nicht gefunden", show_alert=True)
        else:
            emoji = "✅" if won else "❌"
            profit_str = f"+{result['profit']:.2f}" if result['profit'] >= 0 else f"{result['profit']:.2f}"
            await query.edit_message_text(
                "{} <b>Wette abgeschlossen!</b>\n\nErgebnis: <b>{}</b>\nP&L: <b>{} €</b>\n💼 Bankroll: <b>{:.2f} €</b>".format(
                    emoji,
                    "Gewonnen" if won else "Verloren",
                    profit_str,
                    result["bankroll"]
                ),
                parse_mode="HTML"
            )
    elif data.startswith("bet_menu_"):
        raw = data[len("bet_menu_"):]
        parts = raw.split("|")
        if len(parts) == 4:
            match, bet_type, odds, prob = parts
            from telegram_bot.bankroll import get_bankroll, kelly_stake
            bankroll = get_bankroll(query.from_user.id)
            kelly = kelly_stake(float(prob), float(odds), bankroll)
            text = (
                "💰 <b>Wette platzieren</b>\n\n"
                f"Match: <b>{match}</b>\n"
                f"Tipp: <b>{bet_type}</b> @ {odds}\n"
                f"Wahrsch.: <b>{float(prob):.1f}%</b>\n\n"
                f"💼 Bankroll: <b>{bankroll:.2f} €</b>\n"
                f"📐 Kelly-Empfehlung: <b>{kelly:.2f} €</b>\n\n"
                "Wähle deinen Einsatz:"
            )
            options = []
            for pct in [1, 2, 5]:
                stake = round(bankroll * pct / 100, 2)
                if stake > 0:
                    options.append(InlineKeyboardButton(
                        f"{pct}% ({stake:.2f}€)",
                        callback_data=f"bet_place_{match}|{bet_type}|{odds}|{stake}|{prob}"
                    ))
            if kelly > 0:
                options.append(InlineKeyboardButton(
                    f"Kelly ({kelly:.2f}€)",
                    callback_data=f"bet_place_{match}|{bet_type}|{odds}|{kelly}|{prob}"
                ))
            keyboard = [options[i:i+2] for i in range(0, len(options), 2)]
            keyboard.append([InlineKeyboardButton("❌ Abbrechen", callback_data="bank_cancel")])
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


# ─────────────────────────────────────────────
# ERROR HANDLER
# ─────────────────────────────────────────────

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Fehler: {context.error}", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            f"❌ Fehler: {str(context.error)[:200]}"
        )


# ─────────────────────────────────────────────
# BANKROLL HANDLERS
# ─────────────────────────────────────────────

async def bankroll_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from telegram_bot.bankroll import get_user_data, get_stats
    data = get_user_data(user_id)
    stats = get_stats(user_id)

    if data["initial"] == 0:
        await update.message.reply_html(
            "💼 <b>Demo Bankroll</b>\n\n"
            "Noch kein Startkapital gesetzt.\n\n"
            "Nutze /setbank [Betrag] um zu starten.\n"
            "Beispiel: /setbank 1000"
        )
        return

    profit = data["bankroll"] - data["initial"]
    profit_emoji = "📈" if profit >= 0 else "📉"
    profit_str = f"+{profit:.2f}" if profit >= 0 else f"{profit:.2f}"

    text = (
        f"💼 <b>Demo Bankroll</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Aktuell:     <b>{data['bankroll']:.2f} €</b>\n"
        f"🏦 Start:       <b>{data['initial']:.2f} €</b>\n"
        f"{profit_emoji} Gesamt P&L: <b>{profit_str} €</b>\n\n"
        f"📊 <b>Statistiken</b>\n"
        f"  Wetten:    {stats['total']} ({stats['won']}W / {stats['lost']}L)\n"
        f"  Win Rate:  {stats['win_rate']:.1f}%\n"
        f"  ROI:       {stats['roi']:+.1f}%\n"
        f"  Offen:     {stats['open']} Wetten\n"
    )
    keyboard = [
        [
            InlineKeyboardButton("📋 Offene Wetten", callback_data="bank_open"),
            InlineKeyboardButton("📈 Details", callback_data="bank_stats"),
        ],
        [InlineKeyboardButton("🔄 Reset", callback_data="bank_reset_confirm")],
    ]
    await update.message.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def setbank_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_html("❌ Format: /setbank [Betrag]\nBeispiel: /setbank 1000")
        return
    try:
        amount = float(context.args[0].replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_html("❌ Ungültiger Betrag. Beispiel: /setbank 1000")
        return

    from telegram_bot.bankroll import set_bankroll
    set_bankroll(user_id, amount)
    await update.message.reply_html(
        f"✅ <b>Bankroll gesetzt!</b>\n\n"
        f"💰 Startkapital: <b>{amount:.2f} €</b>\n\n"
        f"Nach einer Analyse kannst du direkt Wetten platzieren.\n"
        f"Nutze /bankroll für die Übersicht."
    )


async def open_bets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from telegram_bot.bankroll import get_open_bets, get_bankroll
    bets = get_open_bets(user_id)
    bankroll = get_bankroll(user_id)
    msg = update.message or update.callback_query.message

    if not bets:
        await msg.reply_html(
            f"📋 <b>Offene Wetten</b>\n\nKeine offenen Wetten.\n\n"
            f"💰 Verfügbar: <b>{bankroll:.2f} €</b>"
        )
        return

    text = f"📋 <b>Offene Wetten ({len(bets)})</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    for bet in bets:
        text += (
            f"<b>#{bet['id']} {bet['match']}</b>\n"
            f"  {bet['bet_type']} @ {bet['odds']}\n"
            f"  Einsatz: {bet['stake']:.2f} € → Gewinn: {bet['potential_win']:.2f} €\n"
            f"  📅 {bet['date']}\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"✅ #{bet['id']} Gewonnen", callback_data=f"close_{bet['id']}_won"),
            InlineKeyboardButton(f"❌ #{bet['id']} Verloren", callback_data=f"close_{bet['id']}_lost"),
        ])
    text += f"💰 Verfügbar: <b>{bankroll:.2f} €</b>"
    await msg.reply_html(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from telegram_bot.bankroll import get_stats
    stats = get_stats(user_id)
    msg = update.message or update.callback_query.message

    if stats["initial"] == 0 or stats["total"] == 0:
        await msg.reply_html("📈 <b>Statistiken</b>\n\nNoch keine abgeschlossenen Wetten.")
        return

    roi_emoji = "📈" if stats["roi"] >= 0 else "📉"
    profit_str = f"+{stats['total_profit']:.2f}" if stats["total_profit"] >= 0 else f"{stats['total_profit']:.2f}"

    text = (
        f"📈 <b>Statistiken</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Wetten gesamt: <b>{stats['total']}</b>\n"
        f"✅ Gewonnen:      <b>{stats['won']}</b>\n"
        f"❌ Verloren:      <b>{stats['lost']}</b>\n"
        f"🎯 Win Rate:      <b>{stats['win_rate']:.1f}%</b>\n\n"
        f"💶 Einsatz gesamt: <b>{stats['total_staked']:.2f} €</b>\n"
        f"💰 Profit:         <b>{profit_str} €</b>\n"
        f"{roi_emoji} ROI:            <b>{stats['roi']:+.1f}%</b>\n\n"
        f"🏦 Start:   <b>{stats['initial']:.2f} €</b>\n"
        f"💼 Aktuell: <b>{stats['bankroll']:.2f} €</b>\n"
    )
    if stats.get("best_win"):
        text += f"\n🏆 Bester Gewinn: <b>+{stats['best_win']['profit']:.2f} €</b> ({stats['best_win']['match']})\n"
    if stats.get("worst_loss"):
        text += f"💔 Größter Verlust: <b>{stats['worst_loss']['profit']:.2f} €</b> ({stats['worst_loss']['match']})\n"

    await msg.reply_html(text)
