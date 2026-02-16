"""
Formatierungsfunktionen fuer Telegram-Nachrichten
"""

from typing import Dict, List, Optional
from datetime import datetime


def escape_html(text):
    """Escaped HTML-Zeichen fuer Telegram"""
    return (
        text.replace("&", "&amp;")
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
    
    text = f"""<b>MATCH ANALYSE</b>

<b>{home_name}</b> vs <b>{away_name}</b>

Prognose: <b>{score}</b>
"""
    
    home_win = probs.get("home_win", 0)
    draw = probs.get("draw", 0)
    away_win = probs.get("away_win", 0)
    
    if home_win or draw or away_win:
        text += f"""
1X2 CHANCEN
Heim: {home_win:.1f}%
Draw: {draw:.1f}%
Gast: {away_win:.1f}%
"""
    
    over_25 = probs.get("over_25", 0)
    under_25 = probs.get("under_25", 0)
    
    if over_25 or under_25:
        text += f"""
OVER/UNDER 2.5
Over: {over_25:.1f}%
Under: {under_25:.1f}%
"""
    
    stars = "*" * risk
    text += f"\nRISIKO-SCORE: {risk}/5 {stars}\n"
    
    ml_info = result.get("ml_info", {})
    if ml_info.get("applied"):
        confidence = ml_info.get("confidence", 0) * 100
        text += f"\nML-Korrektur: Aktiv (Conf: {confidence:.0f}%)"
    
    return text


def format_match_list(matches, title="MATCHES"):
    """Formatiert eine Liste von Matches"""
    
    if not matches:
        return "Keine Matches gefunden"
    
    text = f"<b>{title}</b>\n\n"
    
    for i, match in enumerate(matches, 1):
        home = escape_html(match.get("home", "Heim"))
        away = escape_html(match.get("away", "Gast"))
        time = match.get("time", "")
        
        text += f"{i}. {home} vs {away}"
        
        if time:
            text += f" ({time})"
        
        text += "\n"
    
    text += f"\nTippe /analyze 1 fuer Details"
    
    return text


def format_performance_stats(stats):
    """Formatiert Performance-Statistiken"""
    
    text = """<b>DEINE PERFORMANCE</b>

<b>BANKROLL</b>
"""
    
    bankroll = stats.get("bankroll", {})
    current = bankroll.get("current", 0)
    start = bankroll.get("start", 0)
    profit = current - start
    profit_pct = (profit / start * 100) if start > 0 else 0
    
    text += f"Aktuell: EUR{current:.2f}\n"
    text += f"Start: EUR{start:.2f}\n"
    text += f"P&L: {profit:+.2f} ({profit_pct:+.1f}%)\n"
    
    text += "\n<b>STATISTIKEN</b>\n"
    
    total_bets = stats.get("total_bets", 0)
    wins = stats.get("wins", 0)
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    roi = stats.get("roi", 0)
    
    text += f"Wetten: {total_bets}\n"
    text += f"Wins: {wins} ({win_rate:.1f}%)\n"
    text += f"ROI: {roi:+.1f}%\n"
    
    return text


def format_active_positions(positions):
    """Formatiert aktive Wett-Positionen"""
    
    if not positions:
        return "Keine aktiven Wetten"
    
    text = f"<b>AKTIVE WETTEN ({len(positions)})</b>\n\n"
    
    for pos in positions:
        match = escape_html(pos.get("match", "N/A"))
        market = pos.get("market", "N/A")
        stake = pos.get("stake", 0)
        
        text += f"<b>{match}</b>\n"
        text += f"   {market} | EUR{stake:.2f}\n\n"
    
    return text


def format_ml_training_result(result):
    """Formatiert ML-Training Ergebnis"""
    
    if not result.get("success"):
        return f"<b>Training fehlgeschlagen</b>\n\n{result.get('message', 'Unbekannter Fehler')}"
    
    text = """<b>ML-TRAINING ABGESCHLOSSEN</b>

<b>Details</b>
"""
    
    text += f"Samples: {result.get('training_size', 0)}\n"
    text += f"Model: {result.get('model_type', 'N/A')}\n"
    
    text += "\nStatus: Aktiv und bereit"
    
    return text


def format_error_message(error_type, details=""):
    """Formatiert Fehlermeldung"""
    
    error_messages = {
        "timeout": "<b>Timeout</b>\nDie Operation hat zu lange gedauert",
        "not_found": "<b>Nicht gefunden</b>\nKeine Ergebnisse",
        "invalid_input": "<b>Ungueltige Eingabe</b>\nBitte Format pruefen",
        "api_error": "<b>API Fehler</b>\nProblem bei der Datenverarbeitung",
    }
    
    text = error_messages.get(error_type, f"<b>Fehler:</b> {error_type}")
    
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
    
    text = f"""<b>WETT-EMPFEHLUNG</b>

<b>{match}</b>

Market: {market}
Quote: {odds:.2f}
Stake: EUR{stake:.2f}

Risiko: {risk}/5
"""
    
    return text
