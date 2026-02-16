"""
Command Handlers fuer den Telegram Bot
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot.formatters import (
    format_analysis_result,
    format_match_list,
    format_performance_stats,
    format_error_message
)

logger = logging.getLogger(__name__)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /start Command"""
    user = update.effective_user
    
    welcome_text = f"""Willkommen <b>{user.first_name}</b>!

Ich bin dein <b>Sportwetten-Analyse Bot</b>

Was kann ich fuer dich tun?

<b>ANALYSEN</b>
/analyze Bayern vs Dortmund - Match analysieren
/today - Heutige Matches
/quick 1 - Schnellanalyse

<b>WETTEN</b>
/bet - Top Empfehlungen
/stats - Deine Performance

<b>ML</b>
/train - Modell trainieren
/model - Model Status

<b>HILFE</b>
/help - Ausfuehrliche Hilfe

Los gehts!
"""
    
    await update.message.reply_html(welcome_text)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /help Command"""
    
    help_text = """<b>HILFE</b>

<b>ANALYSEN</b>
/analyze [Team1] vs [Team2] - Vollstaendige Analyse
/today - Heutige Matches
/quick [ID] - Schnellanalyse

<b>WETTEN</b>
/bet - Top Wett-Empfehlungen
/stats - Deine Statistiken

<b>ML</b>
/train - ML-Modell trainieren
/model - Modell-Status

<b>EINSTELLUNGEN</b>
/settings - Einstellungen

Viel Erfolg!
"""
    
    await update.message.reply_html(help_text)


async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /analyze Command"""
    
    if not context.args:
        await update.message.reply_html(
            "Bitte Match angeben\n\n"
            "Format: /analyze Team1 vs Team2\n\n"
            "Beispiel:\n"
            "/analyze Bayern Muenchen vs Dortmund"
        )
        return
    
    match_string = " ".join(context.args)
    loading_msg = await update.message.reply_html("Analysiere Match...")
    
    try:
        # TODO: Implementiere Analyse
        await loading_msg.edit_text(
            "<b>Demo-Modus</b>\n\n"
            f"Match: {match_string}\n\n"
            "Analyse-Integration kommt bald!\n"
            "Der Bot laeuft und ist bereit."
        )
        
    except Exception as e:
        logger.error(f"Fehler bei Analyse: {e}", exc_info=True)
        await loading_msg.edit_text(format_error_message("api_error", str(e)))


async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /today Command"""
    
    await update.message.reply_html(
        "<b>HEUTE</b>\n\n"
        "Demo-Matches:\n"
        "1. Bayern Muenchen vs Dortmund (20:30)\n"
        "2. Leipzig vs Bremen (18:30)\n\n"
        "Integration mit echten Daten kommt bald!"
    )


async def quick_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /quick Command"""
    
    await update.message.reply_html(
        "<b>QUICK ANALYSE</b>\n\n"
        "Feature kommt bald!"
    )


async def live_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /live Command"""
    
    await update.message.reply_html(
        "<b>LIVE MATCHES</b>\n\n"
        "Live-Tracking kommt bald!"
    )


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /search Command"""
    
    await update.message.reply_html(
        "<b>SUCHE</b>\n\n"
        "Such-Feature kommt bald!"
    )


async def bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /bet Command"""
    
    await update.message.reply_html(
        "<b>TOP WETT-EMPFEHLUNGEN</b>\n\n"
        "Demo-Empfehlung:\n"
        "Bayern vs Dortmund\n"
        "Over 2.5 @ 1.75\n"
        "Stake: EUR25\n\n"
        "Integration mit echten Analysen kommt bald!"
    )


async def place_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /place Command"""
    
    await update.message.reply_html(
        "<b>Wette platzieren</b>\n\n"
        "Wett-Tracking kommt bald!"
    )


async def positions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /positions Command"""
    
    await update.message.reply_html(
        "<b>AKTIVE WETTEN</b>\n\n"
        "Keine aktiven Wetten\n\n"
        "Tracking-Feature kommt bald!"
    )


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /stats Command"""
    
    stats = {
        "bankroll": {"current": 1000.0, "start": 1000.0},
        "total_bets": 0,
        "wins": 0,
        "roi": 0
    }
    
    response = format_performance_stats(stats)
    await update.message.reply_html(response)


async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /history Command"""
    
    await update.message.reply_html(
        "<b>VERLAUF</b>\n\n"
        "Noch keine Wetten platziert"
    )


async def train_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /train Command"""
    
    info_msg = await update.message.reply_html(
        "<b>ML-TRAINING</b>\n\n"
        "Training-Feature kommt bald!\n"
        "Bot ist bereit fuer Integration."
    )


async def model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /model Command"""
    
    await update.message.reply_html(
        "<b>ML-MODELL STATUS</b>\n\n"
        "Status: Nicht trainiert\n"
        "Type: XGBoost\n\n"
        "Nutze /train um das Modell zu trainieren"
    )


async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /settings Command"""
    
    text = """<b>EINSTELLUNGEN</b>

<b>BANKROLL</b>
Aktuell: EUR1,000
Risikoprofil: Moderat

<b>BENACHRICHTIGUNGEN</b>
Match Analysen: Aktiv
Daily Summary: Aktiv

Nutze /bankroll [Betrag] zum Aendern
"""
    
    await update.message.reply_html(text)


async def bankroll_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /bankroll Command"""
    
    await update.message.reply_html(
        "Aktuelle Bankroll: EUR1,000\n\n"
        "Format: /bankroll [Betrag]\n"
        "Beispiel: /bankroll 1500"
    )


async def alerts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /alerts Command"""
    
    await update.message.reply_html(
        "<b>BENACHRICHTIGUNGEN</b>\n\n"
        "Status: Aktiv\n\n"
        "Format: /alerts [on/off]"
    )


async def export_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /export Command"""
    
    await update.message.reply_html(
        "<b>EXPORT</b>\n\n"
        "Export-Feature kommt bald!"
    )


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer Inline-Keyboard Button Callbacks"""
    
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Button-Feature kommt bald!")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer Fehler"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Ein Fehler ist aufgetreten. Bitte versuche es erneut."
        )


async def date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /date Command - Beispiel: /date 15.02.2025"""
    
    if not context.args:
        await update.message.reply_html("Bitte Datum angeben\n\nFormat: /date DD.MM.YYYY\nBeispiel: /date 15.02.2025")
        return
    
    date_str = context.args[0]
    loading_msg = await update.message.reply_html(f"Lade Matches fuer {date_str}...")
    
    try:
        from telegram_bot.services import MatchService
        service = MatchService()
        matches = await service.get_matches_by_date(date_str)
        
        if not matches:
            await loading_msg.edit_text(f"Keine Matches fuer {date_str} gefunden")
            return
        
        response = format_match_list(matches, f"MATCHES - {date_str}")
        await loading_msg.edit_text(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        await loading_msg.edit_text(f"Fehler: {str(e)}")


async def dates_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /dates Command - Zeigt alle verfuegbaren Dates"""
    
    try:
        from telegram_bot.services import MatchService
        service = MatchService()
        dates = await service.get_available_dates()
        
        if not dates:
            await update.message.reply_html("Keine Daten verfuegbar")
            return
        
        recent_dates = dates[:30]
        text = f"<b>VERFUEGBARE DATES ({len(dates)} gesamt)</b>\n\n"
        
        by_month = {}
        for date_str in recent_dates:
            month = date_str[3:]
            if month not in by_month:
                by_month[month] = []
            by_month[month].append(date_str)
        
        for month in sorted(by_month.keys(), reverse=True):
            text += f"\n<b>{month}</b>\n"
            for date in by_month[month]:
                text += f"• {date}\n"
        
        if len(dates) > 30:
            text += f"\n...und {len(dates) - 30} weitere"
        
        text += "\n\nNutze: /date DD.MM.YYYY"
        await update.message.reply_html(text)
    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        await update.message.reply_html("Fehler beim Laden")


async def history_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /history Command - Sucht ueber alle Dates"""
    
    if not context.args:
        try:
            from telegram_bot.services import MatchService
            service = MatchService()
            dates = await service.get_available_dates()
            
            if not dates:
                await update.message.reply_html("Keine historischen Daten verfuegbar")
                return
            
            recent_dates = dates[:10]
            text = "<b>VERFUEGBARE DATES</b>\n\n"
            text += "\n".join(f"• {d}" for d in recent_dates)
            
            if len(dates) > 10:
                text += f"\n\n...und {len(dates) - 10} weitere"
            
            text += "\n\nNutze: /date DD.MM.YYYY\nOder: /history [Team-Name]"
            await update.message.reply_html(text)
        except Exception as e:
            logger.error(f"Fehler: {e}")
            await update.message.reply_html("Fehler beim Laden")
        return
    
    search_term = " ".join(context.args)
    loading_msg = await update.message.reply_html(f"Suche '{search_term}' in historischen Daten...")
    
    try:
        from telegram_bot.services import MatchService
        service = MatchService()
        matches = await service.search_all_matches(search_term)
        
        if not matches:
            await loading_msg.edit_text(f"Keine Matches mit '{search_term}' gefunden")
            return
        
        by_date = {}
        for match in matches:
            date = match.get("date", "Unknown")
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(match)
        
        text = f"<b>SUCHERGEBNISSE: {search_term}</b>\nGefunden: {len(matches)} Matches\n\n"
        
        for date in sorted(by_date.keys(), reverse=True)[:5]:
            text += f"\n<b>{date}</b>\n"
            for match in by_date[date]:
                text += f"• {match.get('home')} vs {match.get('away')}\n"
        
        if len(by_date) > 5:
            text += f"\n...und {len(by_date) - 5} weitere Dates"
        
        text += "\n\nNutze /analyze [Match] [Datum]"
        await loading_msg.edit_text(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        await loading_msg.edit_text(f"Fehler: {str(e)}")
