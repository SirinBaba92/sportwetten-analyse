"""
Formatierungsfunktionen fuer Telegram-Nachrichten
"""

from typing import Dict, List, Optional
from datetime import datetime


def escape_html(text):
    """Escaped HTML-Zeichen fuer Telegram"""
    if not text:
        return ""
    return (
        str(text).replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_analysis_result(result):
    """Formatiert Analyse-Ergebnis fuer Telegram"""
    
    home = result.get("home_team", {})
    away = result.get("away_team", {})
    
    home_name = home.get("name", "Heim") if isinstance(home, dict) else str(home)
    away_name = away.get("name", "Gast") if isinstance(away, dict) else str(away)
    
    score = result.get("predicted_score", "?-?")
    probs = result.get("probabilities", {})
    risk = result.get("risk_score", 0)
    
    home_name = escape_html(home_name)
    away_name = escape_html(away_name)
    
    text = f"""⚽ <b>MATCH ANALYSE</b>
━━━━━━━━━━━━━━━━━━━━━━

🏠 <b>{home_name}</b>  vs  <b>{away_name}</b>

📊 <b>PROGNOSE</b>
└ Score: <b>{score}</b>
"""
    
    home_win = probs.get("home_win", 0)
    draw = probs.get("draw", 0)
    away_win = probs.get("away_win", 0)
    
    if home_win or draw or away_win:
        text += f"""
🎯 <b>1X2 CHANCEN</b>
├ Heim: {home_win:.1f}%{' ✅' if home_win > 50 else ''}
├ Draw: {draw:.1f}%{' ✅' if draw > 35 else ''}
└ Gast: {away_win:.1f}%{' ✅' if away_win > 50 else ''}
"""
    
    over_25 = probs.get("over_25", 0)
    under_25 = probs.get("under_25", 0)
    
    if over_25 or under_25:
        text += f"""
📈 <b>OVER/UNDER 2.5</b>
├ Over: {over_25:.1f}%{' ✅' if over_25 > 60 else ''}
└ Under: {under_25:.1f}%{' ✅' if under_25 > 60 else ''}
"""
    
    stars = "⭐" * risk
    text += f"""
⚠️ <b>RISIKO-SCORE</b>
└ {risk}/5 {stars}
"""
    
    ml_info = result.get("ml_info", {})
    if ml_info.get("applied"):
        confidence = ml_info.get("confidence", 0) * 100
        text += f"\n🤖 <b>ML-Korrektur:</b> Aktiv (Conf: {confidence:.0f}%)"
    
    return text


def format_match_list(matches, title="MATCHES"):
    """Formatiert eine Liste von Matches"""
    
    if not matches:
        return "📭 Keine Matches gefunden"
    
    text = f"📅 <b>{title}</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, match in enumerate(matches, 1):
        home = escape_html(match.get("home", "Heim"))
        away = escape_html(match.get("away", "Gast"))
        time = match.get("time", "")
        league = match.get("league", "")
        
        text += f"{i}. <b>{home}</b> vs <b>{away}</b>"
        
        if time:
            text += f"  🕐 {time}"
        
        if league:
            text += f"\n   <i>{league}</i>"
        
        text += "\n\n"
    
    text += f"💡 Tippe /quick [ID] für Schnellanalyse"
    
    return text


def format_performance_stats(stats):
    """Formatiert Performance-Statistiken"""
    
    text = """📊 <b>DEINE PERFORMANCE</b>
━━━━━━━━━━━━━━━━━━━━━━

💰 <b>BANKROLL</b>
"""
    
    bankroll = stats.get("bankroll", {})
    current = bankroll.get("current", 0)
    start = bankroll.get("start", 1000)
    profit = current - start
    profit_pct = (profit / start * 100) if start > 0 else 0
    
    # Trend-Pfeil
    trend = "📈" if profit > 0 else "📉" if profit < 0 else "➡️"
    
    text += f"├ Aktuell: €{current:.2f}\n"
    text += f"├ Start: €{start:.2f}\n"
    text += f"└ P&L: {trend} {profit:+.2f} ({profit_pct:+.1f}%)\n"
    
    text += "\n📈 <b>STATISTIKEN</b>\n"
    
    total_bets = stats.get("total_bets", 0)
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    roi = stats.get("roi", 0)
    
    text += f"├ Wetten: {total_bets}\n"
    text += f"├ Wins: {wins} ({win_rate:.1f}%)\n"
    text += f"├ Losses: {losses}\n"
    text += f"└ ROI: {roi:+.1f}%\n"
    
    # Persönliche Stats aus DB
    if "personal" in stats:
        personal = stats["personal"]
        text += f"\n👤 <b>PERSÖNLICH</b>\n"
        text += f"├ Analysen: {personal.get('analyzes', 0)}\n"
        text += f"└ Wetten platziert: {personal.get('bets_placed', 0)}\n"
    
    # Beste Markets
    if "best_markets" in stats:
        text += "\n🎯 <b>BESTE MARKETS</b>\n"
        markets = stats["best_markets"]
        for i, (market, wr) in enumerate(list(markets.items())[:3]):
            prefix = "├" if i < 2 else "└"
            text += f"{prefix} {market}: {wr:.1f}% WR\n"
    
    return text


def format_active_positions(positions):
    """Formatiert aktive Wett-Positionen"""
    
    if not positions:
        return "📭 Keine aktiven Wetten"
    
    text = f"💼 <b>AKTIVE WETTEN ({len(positions)})</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    total_stake = 0
    total_potential = 0
    
    for pos in positions:
        match = escape_html(pos.get("match", "N/A"))
        market = pos.get("market", "N/A")
        odds = pos.get("odds", 0)
        stake = pos.get("stake", 0)
        potential = stake * odds
        
        total_stake += stake
        total_potential += potential
        
        text += f"🎯 <b>{match}</b>\n"
        text += f"├ {market} @ {odds:.2f}\n"
        text += f"└ Einsatz: €{stake:.2f} → €{potential:.2f}\n\n"
    
    text += "━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"💰 Gesamt Risiko: €{total_stake:.2f}\n"
    text += f"🎲 Max Gewinn: €{total_potential:.2f}"
    
    return text


def format_ml_training_result(result):
    """Formatiert ML-Training Ergebnis"""
    
    if not result.get("success"):
        return f"❌ <b>Training fehlgeschlagen</b>\n\n{result.get('message', 'Unbekannter Fehler')}"
    
    text = """✅ <b>ML-TRAINING ABGESCHLOSSEN</b>
━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Details</b>
"""
    
    text += f"├ Samples: {result.get('training_size', 0)}\n"
    text += f"├ Model: {result.get('model_type', 'N/A')}\n"
    
    if "accuracy" in result:
        text += f"├ Accuracy: {result['accuracy']:.1%}\n"
    
    if "duration" in result:
        text += f"└ Dauer: {result['duration']:.1f}s\n"
    
    # Feature Importance
    if "feature_importance" in result:
        text += "\n🎯 <b>Top Features</b>\n"
        features = sorted(
            result["feature_importance"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        for i, (feat, imp) in enumerate(features):
            prefix = "├" if i < 2 else "└"
            text += f"{prefix} {feat}: {imp:.1%}\n"
    
    text += "\n✅ Status: Aktiv und bereit"
    
    return text


def format_error_message(error_type, details=""):
    """Formatiert Fehlermeldung"""
    
    error_messages = {
        "timeout": "⏱️ <b>Timeout</b>\nDie Operation hat zu lange gedauert",
        "not_found": "🔍 <b>Nicht gefunden</b>\nKeine Ergebnisse für deine Anfrage",
        "invalid_input": "❌ <b>Ungültige Eingabe</b>\nBitte Format prüfen",
        "permission": "🔒 <b>Keine Berechtigung</b>\nDieser Command ist nur für Admins",
        "rate_limit": "🚫 <b>Rate Limit</b>\nZu viele Anfragen, bitte warte kurz",
        "api_error": "⚠️ <b>API Fehler</b>\nProblem bei der Datenverarbeitung",
    }
    
    text = error_messages.get(error_type, f"❌ <b>Fehler:</b> {error_type}")
    
    if details:
        text += f"\n\n<i>{escape_html(details)}</i>"
    
    return text


def format_bet_recommendation(rec):
    """Formatiert Wett-Empfehlung"""
    
    match = escape_html(rec.get("match", "N/A"))
    market = rec.get("market", "N/A")
    odds = rec.get("odds", 0)
    stake = rec.get("stake", 0)
    risk = rec.get("risk_score", 0)
    confidence = rec.get("confidence", 0)
    
    potential = stake * odds
    profit = potential - stake
    
    stars = "⭐" * risk
    
    text = f"""🎯 <b>{match}</b>

├ Market: {market}
├ Quote: {odds:.2f}
├ Einsatz: €{stake:.2f}
├ Potential: €{potential:.2f}
└ Profit: +€{profit:.2f}

├ Risiko: {risk}/5 {stars}
└ Confidence: {confidence:.0%}
"""
    
    return text


def format_user_profile(user_data, settings):
    """Formatiert User-Profil"""
    
    joined = datetime.fromisoformat(user_data["joined_at"]).strftime("%d.%m.%Y")
    last_active = datetime.fromisoformat(user_data["last_active"]).strftime("%d.%m.%Y %H:%M")
    
    text = f"""👤 <b>USER PROFIL</b>
━━━━━━━━━━━━━━━━━━━━━━

<b>{escape_html(user_data['first_name'])}</b>
└ @{user_data['username']}

📅 <b>Mitglied seit:</b> {joined}
⏰ <b>Zuletzt aktiv:</b> {last_active}
📊 <b>Commands:</b> {user_data.get('total_commands', 0)}

💰 <b>BANKROLL</b>
└ €{settings.get('bankroll', 1000):.2f}

🔔 <b>BENACHRICHTIGUNGEN</b>
└ {'✅ Aktiv' if settings.get('notifications', True) else '❌ Deaktiviert'}

🌍 <b>SPRACHE</b>
└ {settings.get('language', 'de').upper()}
"""
    
    return text


def format_bot_stats(stats):
    """Formatiert Bot-Statistiken für Admins"""
    
    text = f"""📊 <b>BOT STATISTIKEN</b>
━━━━━━━━━━━━━━━━━━━━━━

👥 <b>USER</b>
├ Total: {stats['total_users']}
├ Heute aktiv: {stats['active_today']}
└ Diese Woche: {stats['active_week']}

⚡ <b>COMMANDS</b>
└ Total: {stats['total_commands']}

🎯 <b>TOP COMMANDS</b>
"""
    
    for cmd, count in stats['top_commands']:
        text += f"├ /{cmd}: {count}\n"
    
    # Entferne letzten ├ und ersetze mit └
    text = text.replace("├ /", "└ /", text.rfind("├ /"))
    
    return text
