"""
Command Handlers fuer den Telegram Bot
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from telegram_bot.formatters import (
    format_analysis_result,
    format_match_list,
    format_performance_stats,
    format_active_positions,
    format_ml_training_result,
    format_error_message,
    format_bet_recommendation,
    format_bot_stats,
    format_user_profile
)
from telegram_bot.services import AnalysisService, MatchService, BettingService, MLService
from telegram_bot.config import BOT_CONFIG, is_admin
from simple_user_db import db

logger = logging.getLogger(__name__)


# ===== RATE LIMITING =====

async def check_rate_limit(update: Update) -> bool:
    """Prueft Rate Limit fuer User"""
    user = update.effective_user
    if not user:
        return True
    
    # Admins haben kein Limit
    if is_admin(user.id):
        return True
    
    if not db.check_rate_limit(user.id):
        await update.message.reply_text(
            "⚠️ <b>Zu viele Anfragen</b>\n\n"
            "Bitte warte einen Moment, bevor du weitere Befehle sendest.",
            parse_mode="HTML"
        )
        return False
    return True


# ===== START & HELP =====

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /start Command"""
    user = update.effective_user
    
    # User registrieren
    db.register_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Aktivität tracken
    db.update_activity(user.id, "start")
    
    welcome_text = f"""👋 Willkommen <b>{user.first_name}</b>!

🤖 Ich bin dein <b>Sportwetten-Analyse Bot</b>

📊 <b>Verfügbare Befehle:</b>

🔍 <b>Analysen</b>
/analyze Bayern vs Dortmund - Match analysieren
/today - Heutige Matches
/date 15.02.2025 - Matches an bestimmtem Datum
/dates - Alle verfügbaren Daten
/history Bayern - In historischen Daten suchen

💰 <b>Wetten</b>
/bet - Top Empfehlungen
/stats - Deine Performance
/profile - Dein Profil

🤖 <b>ML</b>
/train - Modell trainieren
/model - Model Status

⚙️ <b>Einstellungen</b>
/settings - Konfiguration
/bankroll 1500 - Bankroll setzen
/alerts on/off - Benachrichtigungen

📊 <b>Admin</b>
/botstats - Bot-Statistiken (nur Admin)

Los geht's! ⚽
"""
    
    # Inline-Keyboard für Schnellzugriff
    keyboard = [
        [
            InlineKeyboardButton("📅 Heute", callback_data="cmd_today"),
            InlineKeyboardButton("💰 Wetten", callback_data="cmd_bet")
        ],
        [
            InlineKeyboardButton("❓ Hilfe", callback_data="cmd_help"),
            InlineKeyboardButton("📊 Stats", callback_data="cmd_stats")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(welcome_text, reply_markup=reply_markup)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /help Command"""
    user = update.effective_user
    db.update_activity(user.id, "help")
    
    if not await check_rate_limit(update):
        return
    
    help_text = """📚 <b>AUSFÜHRLICHE HILFE</b>
━━━━━━━━━━━━━━━━━━━━━━

🔍 <b>ANALYSEN</b>
• /analyze [Team1] vs [Team2] - Vollständige Analyse
• /today - Heutige Matches anzeigen
• /quick [ID] - Schnellanalyse
• /date [DD.MM.YYYY] - Matches an bestimmtem Datum
• /dates - Alle verfügbaren Daten
• /history [Team] - In historischen Daten suchen

💰 <b>WETTEN</b>
• /bet - Top Wett-Empfehlungen
• /stats - Deine Statistiken
• /profile - Dein Profil anzeigen
• /bankroll [Betrag] - Bankroll setzen

🤖 <b>ML & TRAINING</b>
• /train - ML-Modell trainieren
• /model - Modell-Status anzeigen

⚙️ <b>EINSTELLUNGEN</b>
• /settings - Einstellungen ansehen
• /alerts [on/off] - Benachrichtigungen

📊 <b>ADMIN</b>
• /botstats - Bot-Statistiken (nur für Admins)

💡 <b>Tipps:</b>
• Nutze /today um heutige Matches zu sehen
• Dann /quick 1 für Schnellanalyse
• Mit /bet bekommst du Empfehlungen

Fragen? Einfach ausprobieren! 🚀
"""
    
    await update.message.reply_html(help_text)


# ===== ANALYSE COMMANDS =====

async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /analyze Command"""
    user = update.effective_user
    db.update_activity(user.id, "analyze")
    
    if not await check_rate_limit(update):
        return
    
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Bitte Match angeben</b>\n\n"
            "Format: /analyze Team1 vs Team2\n\n"
            "Beispiele:\n"
            "/analyze Bayern vs Dortmund\n"
            "/analyze Real Madrid - Barcelona"
        )
        return
    
    match_string = " ".join(context.args)
    loading_msg = await update.message.reply_html("🔄 Analysiere Match...")
    
    try:
        service = AnalysisService()
        result = await service.analyze_match_from_string(match_string)
        
        if not result:
            # Fallback zu Demo-Daten
            await loading_msg.edit_text(
                f"<b>🔍 Match nicht gefunden</b>\n\n"
                f"Gesucht: {match_string}\n\n"
                "Demo-Modus: Verwende /today für verfügbare Matches.",
                parse_mode="HTML"
            )
            return
        
        response_text = format_analysis_result(result)
        
        # Inline-Keyboard
        keyboard = [
            [
                InlineKeyboardButton("💰 Wetten", callback_data="cmd_bet"),
                InlineKeyboardButton("📊 Details", callback_data=f"details_{result.get('match_id', 0)}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_msg.edit_text(response_text, parse_mode="HTML", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Fehler bei Analyse: {e}", exc_info=True)
        await loading_msg.edit_text(format_error_message("api_error", str(e)))


async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /today Command"""
    user = update.effective_user
    db.update_activity(user.id, "today")
    
    if not await check_rate_limit(update):
        return
    
    loading_msg = await update.message.reply_text("🔄 Lade heutige Matches...")
    
    try:
        service = MatchService()
        matches = await service.get_todays_matches()
        
        if not matches:
            await loading_msg.edit_text("📭 Keine Matches für heute gefunden")
            return
        
        response = format_match_list(matches, f"HEUTE - {service.get_today_date()}")
        
        # Inline-Keyboard für Schnellzugriff
        keyboard = []
        row = []
        for i, match in enumerate(matches[:4], 1):
            row.append(InlineKeyboardButton(f"{i}", callback_data=f"quick_{match.get('id')}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("📅 Alle Daten", callback_data="cmd_dates")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_msg.edit_text(response, parse_mode="HTML", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Fehler bei today: {e}", exc_info=True)
        await loading_msg.edit_text(format_error_message("api_error", str(e)))


async def quick_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /quick Command"""
    user = update.effective_user
    db.update_activity(user.id, "quick")
    
    if not await check_rate_limit(update):
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Bitte Match-ID angeben\n\n"
            "Format: /quick [ID]\n"
            "Beispiel: /quick 1"
        )
        return
    
    try:
        match_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Match-ID muss eine Zahl sein")
        return
    
    loading_msg = await update.message.reply_text("⚡ Schnellanalyse...")
    
    try:
        service = AnalysisService()
        result = await service.quick_analyze(match_id)
        
        if not result:
            await loading_msg.edit_text("❌ Match nicht gefunden")
            return
        
        home = result.get("home_team", "Heim")
        away = result.get("away_team", "Gast")
        score = result.get("predicted_score", "?-?")
        risk = result.get("risk_score", 0)
        
        stars = "⭐" * risk
        text = f"""⚡ <b>QUICK ANALYSE</b>
━━━━━━━━━━━━━━━━━━━━━━

⚽ {home} vs {away}
📊 Score: <b>{score}</b>
⭐ Risiko: {risk}/5 {stars}
"""
        
        keyboard = [
            [InlineKeyboardButton("📊 Vollständige Analyse", callback_data=f"analyze_{match_id}")],
            [InlineKeyboardButton("💰 Wetten", callback_data="cmd_bet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_msg.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Fehler bei quick: {e}", exc_info=True)
        await loading_msg.edit_text(format_error_message("api_error", str(e)))


async def live_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /live Command"""
    user = update.effective_user
    db.update_activity(user.id, "live")
    
    await update.message.reply_html(
        "🔴 <b>LIVE MATCHES</b>\n\n"
        "⚠️ Live-Tracking kommt bald!\n\n"
        "Nutze in der Zwischenzeit:\n"
        "/today - Heutige Matches\n"
        "/date 15.02.2025 - Historische Matches"
    )


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /search Command"""
    user = update.effective_user
    db.update_activity(user.id, "search")
    
    if not await check_rate_limit(update):
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Bitte Suchbegriff angeben\n\n"
            "Format: /search [Team/Liga]\n"
            "Beispiel: /search Bayern"
        )
        return
    
    search_term = " ".join(context.args)
    loading_msg = await update.message.reply_text(f"🔍 Suche nach '{search_term}'...")
    
    try:
        service = MatchService()
        results = await service.search_matches(search_term)
        
        if not results:
            await loading_msg.edit_text(f"❌ Keine Ergebnisse für '{search_term}'")
            return
        
        response = format_match_list(results, f"SUCHERGEBNISSE: {search_term}")
        await loading_msg.edit_text(response, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Fehler bei search: {e}", exc_info=True)
        await loading_msg.edit_text(format_error_message("api_error", str(e)))


# ===== HISTORISCHE MATCHES =====

async def date_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /date Command"""
    user = update.effective_user
    db.update_activity(user.id, "date")
    
    if not await check_rate_limit(update):
        return
    
    if not context.args:
        await update.message.reply_html(
            "❌ <b>Bitte Datum angeben</b>\n\n"
            "Format: /date DD.MM.YYYY\n"
            "Beispiel: /date 15.02.2025"
        )
        return
    
    date_str = context.args[0]
    loading_msg = await update.message.reply_html(f"📅 Lade Matches für {date_str}...")
    
    try:
        service = MatchService()
        matches = await service.get_matches_by_date(date_str)
        
        if not matches:
            await loading_msg.edit_text(f"📭 Keine Matches für {date_str} gefunden")
            return
        
        response = format_match_list(matches, f"MATCHES - {date_str}")
        
        # Inline-Keyboard für Navigation
        keyboard = [
            [InlineKeyboardButton("📅 Alle Daten", callback_data="cmd_dates")],
            [InlineKeyboardButton("🔍 Suchen", callback_data="cmd_search")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_msg.edit_text(response, parse_mode="HTML", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        await loading_msg.edit_text(f"❌ Fehler: {str(e)}")


async def dates_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /dates Command"""
    user = update.effective_user
    db.update_activity(user.id, "dates")
    
    if not await check_rate_limit(update):
        return
    
    try:
        service = MatchService()
        dates = await service.get_available_dates()
        
        if not dates:
            await update.message.reply_html("📭 Keine Daten verfügbar")
            return
        
        # Gruppiere nach Monat
        by_month = {}
        for date_str in dates[:50]:  # Nur die letzten 50
            month = date_str[3:]  # MM.YYYY
            if month not in by_month:
                by_month[month] = []
            by_month[month].append(date_str)
        
        text = f"📅 <b>VERFÜGBARE DATES</b>\n"
        text += f"Gesamt: {len(dates)} Tage\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        
        for month in sorted(by_month.keys(), reverse=True)[:6]:  # Letzte 6 Monate
            text += f"\n<b>{month}</b>\n"
            # Zeige erste paar Daten
            for date in sorted(by_month[month], reverse=True)[:5]:
                text += f"• {date}\n"
            if len(by_month[month]) > 5:
                text += f"  ...und {len(by_month[month]) - 5} weitere\n"
        
        if len(dates) > 50:
            text += f"\n...und {len(dates) - 50} weitere Tage"
        
        text += "\n\n💡 Nutze /date DD.MM.YYYY"
        
        await update.message.reply_html(text)
        
    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        await update.message.reply_html(f"❌ Fehler: {str(e)}")


async def history_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /history Command"""
    user = update.effective_user
    db.update_activity(user.id, "history")
    
    if not await check_rate_limit(update):
        return
    
    if not context.args:
        # Zeige verfügbare Daten
        try:
            service = MatchService()
            dates = await service.get_available_dates()
            
            if not dates:
                await update.message.reply_html("📭 Keine historischen Daten verfügbar")
                return
            
            recent_dates = dates[:15]
            text = "<b>📚 HISTORISCHE DATEN</b>\n\n"
            text += "<b>Letzte 15 Tage:</b>\n"
            text += "\n".join(f"• {d}" for d in recent_dates)
            
            if len(dates) > 15:
                text += f"\n\n...und {len(dates) - 15} weitere"
            
            text += "\n\n<b>Beispiele:</b>\n"
            text += "/history Bayern\n"
            text += "/date 15.02.2025"
            
            await update.message.reply_html(text)
        except Exception as e:
            logger.error(f"Fehler: {e}")
            await update.message.reply_html("❌ Fehler beim Laden")
        return
    
    search_term = " ".join(context.args)
    loading_msg = await update.message.reply_html(f"🔍 Suche '{search_term}' in historischen Daten...")
    
    try:
        service = MatchService()
        matches = await service.search_all_matches(search_term)
        
        if not matches:
            await loading_msg.edit_text(f"📭 Keine Matches mit '{search_term}' gefunden")
            return
        
        # Gruppiere nach Datum
        by_date = {}
        for match in matches:
            date = match.get("date", "Unbekannt")
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(match)
        
        text = f"<b>🔍 SUCHERGEBNISSE: {search_term}</b>\n"
        text += f"Gefunden: {len(matches)} Matches\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        
        for date in sorted(by_date.keys(), reverse=True)[:7]:
            text += f"\n📅 <b>{date}</b> ({len(by_date[date])})\n"
            for match in by_date[date][:3]:  # Max 3 pro Tag
                text += f"• {match.get('home')} vs {match.get('away')}\n"
            if len(by_date[date]) > 3:
                text += f"  ...und {len(by_date[date]) - 3} weitere\n"
        
        if len(by_date) > 7:
            text += f"\n...und {len(by_date) - 7} weitere Tage"
        
        text += "\n\n💡 Nutze /date DD.MM.YYYY für Details"
        
        await loading_msg.edit_text(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Fehler: {e}", exc_info=True)
        await loading_msg.edit_text(f"❌ Fehler: {str(e)}")


# ===== WETT-MANAGEMENT =====

async def bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /bet Command"""
    user = update.effective_user
    db.update_activity(user.id, "bet")
    
    if not await check_rate_limit(update):
        return
    
    loading_msg = await update.message.reply_text("💰 Lade Empfehlungen...")
    
    try:
        service = BettingService()
        recommendations = await service.get_recommendations()
        
        if not recommendations:
            await loading_msg.edit_text("📭 Keine Empfehlungen verfügbar")
            return
        
        text = "💰 <b>TOP WETT-EMPFEHLUNGEN</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, rec in enumerate(recommendations[:3], 1):
            text += format_bet_recommendation(rec)
            if i < len(recommendations[:3]):
                text += "\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Inline-Keyboard
        keyboard = [
            [InlineKeyboardButton("📊 Meine Stats", callback_data="cmd_stats")],
            [InlineKeyboardButton("⚙️ Bankroll", callback_data="cmd_bankroll")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_msg.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Fehler bei bet: {e}", exc_info=True)
        await loading_msg.edit_text(format_error_message("api_error", str(e)))


async def place_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /place Command"""
    user = update.effective_user
    db.update_activity(user.id, "place")
    
    await update.message.reply_html(
        "💰 <b>Wette platzieren</b>\n\n"
        "⚠️ Wett-Tracking kommt bald!\n\n"
        "Nutze vorerst:\n"
        "/bet für Empfehlungen\n"
        "/stats für deine Performance"
    )


async def positions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /positions Command"""
    user = update.effective_user
    db.update_activity(user.id, "positions")
    
    loading_msg = await update.message.reply_text("💼 Lade Positionen...")
    
    try:
        service = BettingService()
        positions = await service.get_active_positions(user.id)
        
        response = format_active_positions(positions)
        await loading_msg.edit_text(response, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Fehler bei positions: {e}", exc_info=True)
        await loading_msg.edit_text(format_error_message("api_error", str(e)))


# ===== PERFORMANCE & STATS =====

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /stats Command"""
    user = update.effective_user
    db.update_activity(user.id, "stats")
    
    if not await check_rate_limit(update):
        return
    
    loading_msg = await update.message.reply_text("📊 Lade Statistiken...")
    
    try:
        # Hole User-spezifische Stats aus DB
        user_stats = db.get_user_stats(user.id)
        settings = db.get_user_settings(user.id)
        
        service = BettingService()
        stats = await service.get_user_stats(user.id)
        
        # Merge mit DB-Stats
        if "stats" in user_stats:
            stats["personal"] = user_stats["stats"]
        
        stats["bankroll"]["current"] = settings.get("bankroll", 1000.0)
        
        response = format_performance_stats(stats)
        
        # Inline-Keyboard
        keyboard = [
            [InlineKeyboardButton("👤 Profil", callback_data="cmd_profile")],
            [InlineKeyboardButton("💰 Bankroll ändern", callback_data="cmd_bankroll")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await loading_msg.edit_text(response, parse_mode="HTML", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Fehler bei stats: {e}", exc_info=True)
        await loading_msg.edit_text(format_error_message("api_error", str(e)))


async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /profile Command"""
    user = update.effective_user
    db.update_activity(user.id, "profile")
    
    if not await check_rate_limit(update):
        return
    
    # Hole User-Daten
    user_stats = db.get_user_stats(user.id)
    settings = db.get_user_settings(user.id)
    
    if not user_stats:
        await update.message.reply_html("👤 Noch kein Profil vorhanden. Sende /start um eins zu erstellen.")
        return
    
    response = format_user_profile(user_stats["user"], settings)
    
    # Inline-Keyboard
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data="cmd_stats")],
        [InlineKeyboardButton("⚙️ Einstellungen", callback_data="cmd_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(response, reply_markup=reply_markup)


# ===== ML COMMANDS =====

async def train_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /train Command"""
    user = update.effective_user
    db.update_activity(user.id, "train")
    
    if not await check_rate_limit(update):
        return
    
    info_msg = await update.message.reply_html(
        "🤖 <b>ML-TRAINING GESTARTET</b>\n\n"
        "Lade historische Daten...\n"
        "⏳ Dies kann bis zu 2 Minuten dauern.\n\n"
        "Ich informiere dich wenn fertig!"
    )
    
    try:
        service = MLService()
        result = await service.train_model()
        
        response = format_ml_training_result(result)
        await info_msg.edit_text(response, parse_mode="HTML")
        
    except asyncio.TimeoutError:
        await info_msg.edit_text(
            format_error_message("timeout", "Training dauerte zu lange (>5min)")
        )
    except Exception as e:
        logger.error(f"Fehler beim Training: {e}", exc_info=True)
        await info_msg.edit_text(format_error_message("api_error", str(e)))


async def model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /model Command"""
    user = update.effective_user
    db.update_activity(user.id, "model")
    
    if not await check_rate_limit(update):
        return
    
    try:
        service = MLService()
        info = await service.get_model_info()
        
        text = f"""🤖 <b>ML-MODELL STATUS</b>
━━━━━━━━━━━━━━━━━━━━━━

Status: {'✅ Trainiert' if info.get('is_trained') else '❌ Nicht trainiert'}
Type: {info.get('model_type', 'N/A')}
Samples: {info.get('training_data_size', 0)}
Last Updated: {info.get('last_trained', 'Nie')}

Confidence: {info.get('confidence', 0):.0%}
"""
        
        if not info.get('is_trained'):
            text += "\n💡 Nutze /train um das Modell zu trainieren"
        
        await update.message.reply_html(text)
        
    except Exception as e:
        logger.error(f"Fehler bei model: {e}", exc_info=True)
        await update.message.reply_html(format_error_message("api_error", str(e)))


# ===== SETTINGS =====

async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /settings Command"""
    user = update.effective_user
    db.update_activity(user.id, "settings")
    
    if not await check_rate_limit(update):
        return
    
    settings = db.get_user_settings(user.id)
    
    text = f"""⚙️ <b>EINSTELLUNGEN</b>
━━━━━━━━━━━━━━━━━━━━━━

💰 <b>BANKROLL</b>
Aktuell: €{settings.get('bankroll', 1000):.2f}
Risikoprofil: {settings.get('risk_profile', 'moderat').capitalize()}

🔔 <b>BENACHRICHTIGUNGEN</b>
Status: {'✅ Aktiv' if settings.get('notifications', True) else '❌ Deaktiviert'}

🌍 <b>SPRACHE</b>
{settings.get('language', 'de').upper()}

<i>Ändern mit:</i>
/bankroll [Betrag]
/alerts [on/off]
"""
    
    # Inline-Keyboard für Schnelleinstellungen
    keyboard = [
        [
            InlineKeyboardButton("💰 Bankroll", callback_data="cmd_bankroll"),
            InlineKeyboardButton("🔔 Alerts", callback_data="cmd_alerts")
        ],
        [
            InlineKeyboardButton("👤 Profil", callback_data="cmd_profile"),
            InlineKeyboardButton("📊 Stats", callback_data="cmd_stats")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_html(text, reply_markup=reply_markup)


async def bankroll_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /bankroll Command"""
    user = update.effective_user
    db.update_activity(user.id, "bankroll")
    
    if not await check_rate_limit(update):
        return
    
    settings = db.get_user_settings(user.id)
    current = settings.get('bankroll', 1000.0)
    
    if not context.args:
        await update.message.reply_html(
            f"💰 <b>Aktuelle Bankroll:</b> €{current:.2f}\n\n"
            f"<b>Format:</b> /bankroll [Betrag]\n"
            f"<b>Beispiel:</b> /bankroll 1500\n\n"
            f"<b>Empfohlene Stakes:</b>\n"
            f"• Low Risk (2%): €{current * 0.02:.2f}\n"
            f"• Medium Risk (3.5%): €{current * 0.035:.2f}\n"
            f"• High Risk (5%): €{current * 0.05:.2f}"
        )
        return
    
    try:
        amount = float(context.args[0].replace(',', '.'))
        if amount < 10:
            await update.message.reply_text("❌ Bankroll muss mindestens €10 sein")
            return
        if amount > 100000:
            await update.message.reply_text("❌ Bankroll zu hoch (max €100.000)")
            return
        
        # In DB speichern
        db.update_user_settings(user.id, {"bankroll": amount})
        
        await update.message.reply_html(
            f"✅ <b>Bankroll aktualisiert</b>\n\n"
            f"Neu: €{amount:.2f}\n\n"
            f"<b>Neue Stakes:</b>\n"
            f"• Low Risk (2%): €{amount * 0.02:.2f}\n"
            f"• Medium Risk (3.5%): €{amount * 0.035:.2f}\n"
            f"• High Risk (5%): €{amount * 0.05:.2f}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Ungültiger Betrag. Beispiel: /bankroll 1500")


async def alerts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /alerts Command"""
    user = update.effective_user
    db.update_activity(user.id, "alerts")
    
    if not await check_rate_limit(update):
        return
    
    settings = db.get_user_settings(user.id)
    current = settings.get('notifications', True)
    
    if not context.args:
        status = "✅ Aktiv" if current else "❌ Deaktiviert"
        await update.message.reply_html(
            f"🔔 <b>BENACHRICHTIGUNGEN</b>\n\n"
            f"Status: {status}\n\n"
            f"<b>Ändern:</b>\n"
            f"/alerts on - Aktivieren\n"
            f"/alerts off - Deaktivieren"
        )
        return
    
    action = context.args[0].lower()
    
    if action == "on":
        db.update_user_settings(user.id, {"notifications": True})
        await update.message.reply_html(
            "✅ <b>Benachrichtigungen aktiviert</b>\n\n"
            "Du erhältst jetzt:\n"
            "• Neue Analysen\n"
            "• Tägliche Zusammenfassung (kommt bald)"
        )
    elif action == "off":
        db.update_user_settings(user.id, {"notifications": False})
        await update.message.reply_html(
            "🔕 <b>Benachrichtigungen deaktiviert</b>\n\n"
            "Du erhältst keine automatischen Updates mehr.\n"
            "Nutze /alerts on zum Reaktivieren."
        )
    else:
        await update.message.reply_text("❌ Nutze: /alerts on oder /alerts off")


# ===== ADMIN COMMANDS =====

async def botstats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /botstats Command (nur Admin)"""
    user = update.effective_user
    
    if not is_admin(user.id):
        await update.message.reply_text("❌ Nur für Admins")
        return
    
    db.update_activity(user.id, "botstats")
    
    stats = db.get_bot_stats()
    response = format_bot_stats(stats)
    
    # Detaillierte User-Liste für Admins
    if context.args and context.args[0] == "users":
        user_list = ""
        for uid, data in list(stats["users"].items())[-10:]:
            user_list += f"• {data['first_name']} (@{data['username']})\n"
            user_list += f"  Letzte Aktivität: {data['last_active'][:16]}\n"
            user_list += f"  Commands: {data.get('total_commands', 0)}\n\n"
        
        await update.message.reply_html(
            response + f"\n\n<b>Letzte 10 User:</b>\n{user_list}"
        )
    else:
        await update.message.reply_html(response)


# ===== UTILITIES =====

async def export_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer /export Command"""
    user = update.effective_user
    db.update_activity(user.id, "export")
    
    await update.message.reply_html(
        "📥 <b>EXPORT</b>\n\n"
        "⚠️ Export-Feature kommt bald!\n\n"
        "In Zukunft kannst du hier exportieren:\n"
        "• Deine Wett-Historie\n"
        "• Performance-Daten\n"
        "• ML-Analysen"
    )


# ===== CALLBACK QUERY HANDLER =====

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer Inline-Keyboard Button Callbacks"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    db.update_activity(user.id, f"callback_{query.data}")
    
    data = query.data
    
    # Command-Callbacks
    if data == "cmd_today":
        await today_handler(update, context)
    elif data == "cmd_bet":
        await bet_handler(update, context)
    elif data == "cmd_help":
        await help_handler(update, context)
    elif data == "cmd_stats":
        await stats_handler(update, context)
    elif data == "cmd_profile":
        await profile_handler(update, context)
    elif data == "cmd_settings":
        await settings_handler(update, context)
    elif data == "cmd_dates":
        await dates_handler(update, context)
    elif data == "cmd_search":
        await search_handler(update, context)
    elif data == "cmd_bankroll":
        await bankroll_handler(update, context)
    elif data == "cmd_alerts":
        await alerts_handler(update, context)
    
    # Match-bezogene Callbacks
    elif data.startswith("quick_"):
        match_id = data.split("_")[1]
        context.args = [match_id]
        await quick_handler(update, context)
    
    elif data.startswith("analyze_"):
        match_id = data.split("_")[1]
        # TODO: Vollständige Analyse
        await query.edit_message_text(f"📊 Vollständige Analyse für Match {match_id} kommt bald!")
    
    elif data.startswith("details_"):
        match_id = data.split("_")[1]
        await query.edit_message_text(f"📊 Detaillierte Ansicht für Match {match_id} kommt bald!")
    
    else:
        await query.edit_message_text("⚠️ Unbekannte Aktion")


# ===== ERROR HANDLER =====

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler fuer Fehler"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ein Fehler ist aufgetreten. Bitte versuche es erneut."
        )
