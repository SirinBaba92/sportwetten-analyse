“””
Command Handlers für den Telegram Bot
“””

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from telegram_bot.formatters import (
format_analysis_result,
format_match_list,
format_performance_stats,
format_active_positions,
format_ml_training_result,
format_error_message,
format_bet_recommendation
)
from telegram_bot.services import AnalysisService, MatchService, BettingService, MLService

logger = logging.getLogger(**name**)

# ===== START & HELP =====

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /start Command”””
user = update.effective_user

```
welcome_text = f"""👋 Willkommen <b>{user.first_name}</b>!
```

🤖 Ich bin dein <b>Sportwetten-Analyse Bot</b>

Was kann ich für dich tun?

🔍 <b>Analysen</b>
/analyze Bayern vs Dortmund - Match analysieren
/today - Heutige Matches
/quick 1 - Schnellanalyse

💰 <b>Wetten</b>
/bet - Top Empfehlungen
/positions - Aktive Wetten
/stats - Deine Performance

🤖 <b>ML</b>
/train - Modell trainieren
/model - Model Status

⚙️ <b>Einstellungen</b>
/settings - Konfiguration
/help - Ausführliche Hilfe

Los geht’s! ⚽
“””

```
await update.message.reply_html(welcome_text)
```

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /help Command”””

```
help_text = """📚 <b>HILFE</b>
```

━━━━━━━━━━━━━━━━━━━━━━

🔍 <b>ANALYSEN</b>
/analyze [Team1] vs [Team2] - Vollständige Analyse
/today - Heutige Matches auflisten
/quick [ID] - Schnellanalyse eines Matches
/live - Live-Matches mit deinen Wetten
/search [Team/Liga] - Matches suchen

💰 <b>WETTEN</b>
/bet - Top Wett-Empfehlungen
/place [ID] [Market] - Wette platzieren
/positions - Aktive Wetten anzeigen

📊 <b>PERFORMANCE</b>
/stats - Deine Statistiken
/history [Zeitraum] - Wett-Verlauf
/bankroll [Betrag] - Bankroll setzen

🤖 <b>ML & TRAINING</b>
/train - ML-Modell neu trainieren
/model - Modell-Status anzeigen

⚙️ <b>EINSTELLUNGEN</b>
/settings - Einstellungen ansehen
/alerts [on/off] - Benachrichtigungen

🛠️ <b>UTILITIES</b>
/export [csv] - Daten exportieren

<b>Beispiele:</b>
• /analyze Bayern München vs Borussia Dortmund
• /quick 1
• /bet
• /stats

Viel Erfolg! 🍀
“””

```
await update.message.reply_html(help_text)
```

# ===== ANALYSE COMMANDS =====

async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“””
Handler für /analyze Command
Beispiel: /analyze Bayern vs Dortmund
“””

```
# Prüfe ob Argumente vorhanden
if not context.args:
    await update.message.reply_html(
        "❌ <b>Bitte Match angeben</b>\n\n"
        "Format: /analyze Team1 vs Team2\n\n"
        "Beispiel:\n"
        "/analyze Bayern München vs Dortmund"
    )
    return

match_string = " ".join(context.args)

# Loading Message
loading_msg = await update.message.reply_html("🔄 Analysiere Match...")

try:
    # Parse und analysiere Match
    service = AnalysisService()
    result = await service.analyze_match_from_string(match_string)
    
    if not result:
        await loading_msg.edit_text(
            format_error_message('not_found', 'Match konnte nicht gefunden oder analysiert werden')
        )
        return
    
    # Formatiere Ergebnis
    response_text = format_analysis_result(result)
    
    # Erstelle Inline-Keyboard
    keyboard = [
        [
            InlineKeyboardButton("💰 Wette platzieren", callback_data=f"bet_{result.get('match_id', 0)}"),
            InlineKeyboardButton("📊 Details", callback_data=f"details_{result.get('match_id', 0)}")
        ],
        [
            InlineKeyboardButton("📤 Exportieren", callback_data=f"export_{result.get('match_id', 0)}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Sende Ergebnis
    await loading_msg.edit_text(
        response_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    logger.info(f"Analyse erfolgreich für User {update.effective_user.id}: {match_string}")
    
except asyncio.TimeoutError:
    await loading_msg.edit_text(
        format_error_message('timeout', 'Analyse hat zu lange gedauert. Bitte erneut versuchen.')
    )
except Exception as e:
    logger.error(f"Fehler bei Analyse: {e}", exc_info=True)
    await loading_msg.edit_text(
        format_error_message('api_error', str(e))
    )
```

async def today_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /today Command - zeigt heutige Matches”””

```
loading_msg = await update.message.reply_text("🔄 Lade heutige Matches...")

try:
    service = MatchService()
    matches = await service.get_todays_matches()
    
    if not matches:
        await loading_msg.edit_text("📭 Keine Matches für heute gefunden")
        return
    
    # Formatiere Match-Liste
    response = format_match_list(matches, f"HEUTE - {service.get_today_date()}")
    
    await loading_msg.edit_text(response, parse_mode='HTML')
    
except Exception as e:
    logger.error(f"Fehler bei today: {e}", exc_info=True)
    await loading_msg.edit_text(format_error_message('api_error', str(e)))
```

async def quick_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“””
Handler für /quick Command - Schnellanalyse
Beispiel: /quick 1
“””

```
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
    
    # Kurze Zusammenfassung
    home = result.get('home_team', 'Heim')
    away = result.get('away_team', 'Gast')
    score = result.get('predicted_score', '?-?')
    risk = result.get('risk_score', 0)
    
    text = f"""⚡ <b>QUICK ANALYSE</b>
```

━━━━━━━━━━━━━━━━━━━━━━

⚽ {home} vs {away}
📊 Score: <b>{score}</b>
⭐ Risk: {risk}/5 {‘⭐’ * risk}
“””

```
    # Beste Wette
    if 'bet_recommendation' in result:
        bet = result['bet_recommendation']
        text += f"\n💰 Bet: {bet.get('market')} @ €{bet.get('stake', 0):.2f}"
    
    keyboard = [
        [InlineKeyboardButton("📊 Vollständige Analyse", callback_data=f"full_analysis_{match_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await loading_msg.edit_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
except Exception as e:
    logger.error(f"Fehler bei quick: {e}", exc_info=True)
    await loading_msg.edit_text(format_error_message('api_error', str(e)))
```

async def live_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /live Command - zeigt live Matches mit aktiven Wetten”””

```
await update.message.reply_html(
    "🔴 <b>LIVE MATCHES</b>\n\n"
    "⚠️ Live-Tracking kommt bald!\n\n"
    "Nutze in der Zwischenzeit /positions für deine aktiven Wetten."
)
```

async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“””
Handler für /search Command
Beispiel: /search Bayern
“””

```
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
    await loading_msg.edit_text(response, parse_mode='HTML')
    
except Exception as e:
    logger.error(f"Fehler bei search: {e}", exc_info=True)
    await loading_msg.edit_text(format_error_message('api_error', str(e)))
```

# ===== WETT-MANAGEMENT =====

async def bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /bet Command - zeigt Top-Empfehlungen”””

```
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
    
    await loading_msg.edit_text(text, parse_mode='HTML')
    
except Exception as e:
    logger.error(f"Fehler bei bet: {e}", exc_info=True)
    await loading_msg.edit_text(format_error_message('api_error', str(e)))
```

async def place_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“””
Handler für /place Command
Beispiel: /place 1 over2.5
“””

```
await update.message.reply_html(
    "💰 <b>Wette platzieren</b>\n\n"
    "⚠️ Wett-Tracking kommt bald!\n\n"
    "Nutze vorerst /bet für Empfehlungen."
)
```

async def positions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /positions Command - zeigt aktive Wetten”””

```
loading_msg = await update.message.reply_text("💼 Lade Positionen...")

try:
    service = BettingService()
    positions = await service.get_active_positions(update.effective_user.id)
    
    response = format_active_positions(positions)
    await loading_msg.edit_text(response, parse_mode='HTML')
    
except Exception as e:
    logger.error(f"Fehler bei positions: {e}", exc_info=True)
    await loading_msg.edit_text(format_error_message('api_error', str(e)))
```

# ===== PERFORMANCE & STATS =====

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /stats Command”””

```
loading_msg = await update.message.reply_text("📊 Lade Statistiken...")

try:
    service = BettingService()
    stats = await service.get_user_stats(update.effective_user.id)
    
    response = format_performance_stats(stats)
    await loading_msg.edit_text(response, parse_mode='HTML')
    
except Exception as e:
    logger.error(f"Fehler bei stats: {e}", exc_info=True)
    await loading_msg.edit_text(format_error_message('api_error', str(e)))
```

async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /history Command”””

```
await update.message.reply_html(
    "📅 <b>VERLAUF</b>\n\n"
    "⚠️ Verlaufs-Feature kommt bald!\n\n"
    "Nutze /stats für aktuelle Performance."
)
```

# ===== ML COMMANDS =====

async def train_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /train Command”””

```
# Info-Nachricht
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
    await info_msg.edit_text(response, parse_mode='HTML')
    
except asyncio.TimeoutError:
    await info_msg.edit_text(
        format_error_message('timeout', 'Training dauerte zu lange (>5min). Bitte später erneut versuchen.')
    )
except Exception as e:
    logger.error(f"Fehler beim Training: {e}", exc_info=True)
    await info_msg.edit_text(format_error_message('api_error', str(e)))
```

async def model_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /model Command”””

```
try:
    service = MLService()
    info = await service.get_model_info()
    
    text = f"""🤖 <b>ML-MODELL STATUS</b>
```

━━━━━━━━━━━━━━━━━━━━━━

Status: {‘✅ Trainiert’ if info.get(‘is_trained’) else ‘❌ Nicht trainiert’}
Type: {info.get(‘model_type’, ‘N/A’)}
Samples: {info.get(‘training_data_size’, 0)}
Last Updated: {info.get(‘last_trained’, ‘Nie’)}

Confidence: {info.get(‘confidence’, 0):.0%}
“””

```
    if not info.get('is_trained'):
        text += "\n💡 Nutze /train um das Modell zu trainieren"
    
    await update.message.reply_html(text)
    
except Exception as e:
    logger.error(f"Fehler bei model: {e}", exc_info=True)
    await update.message.reply_html(format_error_message('api_error', str(e)))
```

# ===== SETTINGS =====

async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /settings Command”””

```
text = """⚙️ <b>EINSTELLUNGEN</b>
```

━━━━━━━━━━━━━━━━━━━━━━

💰 <b>BANKROLL</b>
Aktuell: €1,000
Risikoprofil: Moderat
Max Stake: 5%

🔔 <b>BENACHRICHTIGUNGEN</b>
Match Analysen: ✅
Live Updates: ✅
Daily Summary: ✅

🎯 <b>FILTER</b>
Min Risk Score: 3/5
Min Quote: 1.50

<i>Nutze /bankroll [Betrag] zum Ändern</i>
<i>Nutze /alerts [on/off] für Benachrichtigungen</i>
“””

```
await update.message.reply_html(text)
```

async def bankroll_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /bankroll Command”””

```
if not context.args:
    await update.message.reply_text(
        "💰 Aktuelle Bankroll: €1,000\n\n"
        "Format: /bankroll [Betrag]\n"
        "Beispiel: /bankroll 1500"
    )
    return

try:
    amount = float(context.args[0])
    if amount <= 0:
        await update.message.reply_text("❌ Betrag muss positiv sein")
        return
    
    # TODO: Save to database
    await update.message.reply_html(
        f"✅ <b>Bankroll aktualisiert</b>\n\n"
        f"Neu: €{amount:.2f}\n"
        f"Max Stakes:\n"
        f"Risk 3: €{amount * 0.02:.2f}\n"
        f"Risk 4: €{amount * 0.035:.2f}\n"
        f"Risk 5: €{amount * 0.05:.2f}"
    )
    
except ValueError:
    await update.message.reply_text("❌ Ungültiger Betrag")
```

async def alerts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /alerts Command”””

```
if not context.args:
    status = "✅ Aktiv"  # TODO: From database
    await update.message.reply_html(
        f"🔔 <b>BENACHRICHTIGUNGEN</b>\n\n"
        f"Status: {status}\n\n"
        f"Format: /alerts [on/off]\n"
        f"Beispiel: /alerts on"
    )
    return

action = context.args[0].lower()

if action == "on":
    await update.message.reply_html(
        "✅ <b>Benachrichtigungen aktiviert</b>\n\n"
        "Du erhältst jetzt:\n"
        "• Neue Analysen\n"
        "• Live-Updates\n"
        "• Tägliche Zusammenfassung"
    )
elif action == "off":
    await update.message.reply_html(
        "🔕 <b>Benachrichtigungen deaktiviert</b>\n\n"
        "Du erhältst keine automatischen Updates mehr.\n"
        "Nutze /alerts on zum Aktivieren."
    )
else:
    await update.message.reply_text("❌ Nutze: /alerts on oder /alerts off")
```

# ===== UTILITIES =====

async def export_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für /export Command”””

```
await update.message.reply_html(
    "📥 <b>EXPORT</b>\n\n"
    "⚠️ Export-Feature kommt bald!\n\n"
    "Nutze vorerst die Streamlit-App für Exports."
)
```

# ===== CALLBACK QUERY HANDLER (Buttons) =====

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für Inline-Keyboard Button Callbacks”””

```
query = update.callback_query
await query.answer()

data = query.data

if data.startswith("bet_"):
    match_id = data.split("_")[1]
    await query.edit_message_text("💰 Wett-Platzierung kommt bald!")
    
elif data.startswith("details_"):
    match_id = data.split("_")[1]
    await query.edit_message_text("📊 Detaillierte Ansicht kommt bald!")
    
elif data.startswith("export_"):
    match_id = data.split("_")[1]
    await query.edit_message_text("📤 Export kommt bald!")
    
elif data.startswith("full_analysis_"):
    match_id = data.split("_")[2]
    await query.edit_message_text("📊 Vollständige Analyse lädt...")
    # TODO: Load and display full analysis

else:
    await query.edit_message_text("⚠️ Unbekannte Aktion")
```

# ===== ERROR HANDLER =====

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
“”“Handler für Fehler”””
logger.error(f”Update {update} caused error {context.error}”, exc_info=context.error)

```
if update and update.effective_message:
    await update.effective_message.reply_text(
        "❌ Ein Fehler ist aufgetreten. Bitte versuche es erneut."
    )
```
