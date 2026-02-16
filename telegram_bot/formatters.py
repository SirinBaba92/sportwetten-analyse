“””
Formatierungsfunktionen für Telegram-Nachrichten
“””

from typing import Dict, List, Optional
from datetime import datetime

def escape_html(text: str) -> str:
“”“Escaped HTML-Zeichen für Telegram”””
return (
text.replace(”&”, “&”)
.replace(”<”, “<”)
.replace(”>”, “>”)
)

def format_analysis_result(result: Dict) -> str:
“””
Formatiert Analyse-Ergebnis für Telegram

```
Args:
    result: Dictionary von analyze_match_v47_ml()
    
Returns:
    Formatierte HTML-Nachricht
"""

home = result.get('home_team', {})
away = result.get('away_team', {})

home_name = home.get('name', 'Heim') if isinstance(home, dict) else str(home)
away_name = away.get('name', 'Gast') if isinstance(away, dict) else str(away)

score = result.get('predicted_score', '?-?')
probs = result.get('probabilities', {})
risk = result.get('risk_score', 0)

# Escape Namen für HTML
home_name = escape_html(home_name)
away_name = escape_html(away_name)

text = f"""⚽ <b>MATCH ANALYSE</b>
```

━━━━━━━━━━━━━━━━━━━━━━

🏠 {home_name}
🚗 {away_name}

📊 <b>PROGNOSE</b>
Score: <b>{score}</b>
“””

```
# 1X2 Wahrscheinlichkeiten
home_win = probs.get('home_win', 0)
draw = probs.get('draw', 0)
away_win = probs.get('away_win', 0)

if home_win or draw or away_win:
    text += f"""
```

🎯 <b>1X2 CHANCEN</b>
Heim: {home_win:.1f}%{’ ✅’ if home_win > 50 else ‘’}
Draw: {draw:.1f}%{’ ✅’ if draw > 35 else ‘’}
Gast: {away_win:.1f}%{’ ✅’ if away_win > 50 else ‘’}
“””

```
# Over/Under
over_25 = probs.get('over_25', 0)
under_25 = probs.get('under_25', 0)

if over_25 or under_25:
    text += f"""
```

📈 <b>OVER/UNDER 2.5</b>
Over: {over_25:.1f}%{’ ✅’ if over_25 > 60 else ‘’}
Under: {under_25:.1f}%{’ ✅’ if under_25 > 60 else ‘’}
“””

```
# BTTS
btts_yes = probs.get('btts_yes', 0)
btts_no = probs.get('btts_no', 0)

if btts_yes or btts_no:
    text += f"""
```

🎲 <b>BOTH TEAMS TO SCORE</b>
Ja: {btts_yes:.1f}%{’ ✅’ if btts_yes > 60 else ‘’}
Nein: {btts_no:.1f}%{’ ✅’ if btts_no > 60 else ‘’}
“””

```
# Risiko-Score
stars = '⭐' * risk
text += f"\n⚠️ <b>RISIKO-SCORE:</b> {risk}/5 {stars}\n"

# ML-Info
ml_info = result.get('ml_info', {})
if ml_info.get('applied'):
    confidence = ml_info.get('confidence', 0) * 100
    text += f"\n🤖 <b>ML-Korrektur:</b> Aktiv (Conf: {confidence:.0f}%)"

# Bet Recommendation (falls vorhanden)
if 'bet_recommendation' in result:
    bet = result['bet_recommendation']
    text += f"""
```

💰 <b>EMPFEHLUNG</b>
Market: {bet.get(‘market’, ‘N/A’)}
Quote: {bet.get(‘odds’, 0):.2f}
Einsatz: €{bet.get(‘stake’, 0):.2f}
“””

```
return text
```

def format_match_list(matches: List[Dict], title: str = “MATCHES”) -> str:
“””
Formatiert eine Liste von Matches

```
Args:
    matches: Liste von Match-Dictionaries
    title: Titel für die Liste
    
Returns:
    Formatierte Nachricht
"""

if not matches:
    return "❌ Keine Matches gefunden"

text = f"📅 <b>{title}</b>\n"
text += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

for i, match in enumerate(matches, 1):
    home = escape_html(match.get('home', 'Heim'))
    away = escape_html(match.get('away', 'Gast'))
    time = match.get('time', '')
    league = match.get('league', '')
    
    text += f"{i}️⃣ {home} vs {away}"
    
    if time:
        text += f" ({time})"
    
    if league:
        text += f"\n   <i>{league}</i>"
    
    text += "\n\n"

text += f"💡 Tippe /analyze {1} für Details\n"
text += f"⚡ oder /quick {1} für Schnellanalyse"

return text
```

def format_performance_stats(stats: Dict) -> str:
“””
Formatiert Performance-Statistiken

```
Args:
    stats: Dictionary mit Performance-Daten
    
Returns:
    Formatierte Nachricht
"""

text = """📊 <b>DEINE PERFORMANCE</b>
```

━━━━━━━━━━━━━━━━━━━━━━

💰 <b>BANKROLL</b>
“””

```
bankroll = stats.get('bankroll', {})
current = bankroll.get('current', 0)
start = bankroll.get('start', 0)
profit = current - start
profit_pct = (profit / start * 100) if start > 0 else 0

text += f"Aktuell: €{current:.2f}\n"
text += f"Start: €{start:.2f}\n"
text += f"P&L: {profit:+.2f} ({profit_pct:+.1f}%)\n"

text += "\n📈 <b>STATISTIKEN</b>\n"

total_bets = stats.get('total_bets', 0)
wins = stats.get('wins', 0)
losses = stats.get('losses', 0)
win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
roi = stats.get('roi', 0)

text += f"Wetten: {total_bets}\n"
text += f"Wins: {wins} ({win_rate:.1f}%)\n"
text += f"Losses: {losses}\n"
text += f"ROI: {roi:+.1f}%\n"

# Beste Markets
if 'best_markets' in stats:
    text += "\n🎯 <b>BESTE MARKETS</b>\n"
    for market, wr in stats['best_markets'].items():
        text += f"{market}: {wr:.1f}% WR\n"

return text
```

def format_active_positions(positions: List[Dict]) -> str:
“””
Formatiert aktive Wett-Positionen

```
Args:
    positions: Liste von aktiven Wetten
    
Returns:
    Formatierte Nachricht
"""

if not positions:
    return "📭 Keine aktiven Wetten"

text = f"💼 <b>AKTIVE WETTEN ({len(positions)})</b>\n"
text += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

total_stake = 0
total_potential = 0

for pos in positions:
    match = escape_html(pos.get('match', 'N/A'))
    market = pos.get('market', 'N/A')
    odds = pos.get('odds', 0)
    stake = pos.get('stake', 0)
    status = pos.get('status', 'pending')
    
    potential = stake * odds
    total_stake += stake
    total_potential += potential
    
    # Status Icon
    status_icons = {
        'pending': '🕐',
        'running': '✅',
        'at_risk': '⚠️',
        'won': '🎉',
        'lost': '❌'
    }
    icon = status_icons.get(status, '📊')
    
    text += f"{icon} <b>{match}</b>\n"
    text += f"   {market} @ {odds:.2f} | €{stake:.2f}\n"
    
    if status == 'running':
        current_score = pos.get('current_score', '')
        if current_score:
            text += f"   <i>Stand: {current_score}</i>\n"
    
    text += "\n"

text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
text += f"Gesamt Risiko: €{total_stake:.2f}\n"
text += f"Max Gewinn: €{total_potential:.2f}"

return text
```

def format_ml_training_result(result: Dict) -> str:
“””
Formatiert ML-Training Ergebnis

```
Args:
    result: Training-Ergebnis Dictionary
    
Returns:
    Formatierte Nachricht
"""

if not result.get('success'):
    return f"❌ <b>Training fehlgeschlagen</b>\n\n{result.get('message', 'Unbekannter Fehler')}"

text = """✅ <b>ML-TRAINING ABGESCHLOSSEN</b>
```

━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Details</b>
“””

```
text += f"Samples: {result.get('training_size', 0)}\n"
text += f"Model: {result.get('model_type', 'N/A')}\n"

if 'duration' in result:
    text += f"Duration: {result['duration']:.1f}s\n"

# Feature Importance (Top 3)
if 'feature_importance' in result:
    text += "\n🎯 <b>Top Features</b>\n"
    features = sorted(
        result['feature_importance'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]
    
    for feat, imp in features:
        text += f"{feat}: {imp:.1%}\n"

text += "\n✅ Status: Aktiv und bereit"

return text
```

def format_error_message(error_type: str, details: str = “”) -> str:
“””
Formatiert Fehlermeldung

```
Args:
    error_type: Typ des Fehlers
    details: Zusätzliche Details
    
Returns:
    Formatierte Fehlermeldung
"""

error_messages = {
    'timeout': '⏱️ <b>Timeout</b>\nDie Operation hat zu lange gedauert',
    'not_found': '🔍 <b>Nicht gefunden</b>\nKeine Ergebnisse für deine Anfrage',
    'invalid_input': '❌ <b>Ungültige Eingabe</b>\nBitte Format prüfen',
    'permission': '🔒 <b>Keine Berechtigung</b>\nDieser Command ist nur für Admins',
    'rate_limit': '🚫 <b>Rate Limit</b>\nZu viele Anfragen, bitte warte kurz',
    'api_error': '⚠️ <b>API Fehler</b>\nProblem bei der Datenverarbeitung',
}

text = error_messages.get(error_type, f"❌ <b>Fehler:</b> {error_type}")

if details:
    text += f"\n\n<i>{escape_html(details)}</i>"

return text
```

def format_bet_recommendation(rec: Dict) -> str:
“””
Formatiert Wett-Empfehlung

```
Args:
    rec: Recommendation Dictionary
    
Returns:
    Formatierte Nachricht
"""

match = escape_html(rec.get('match', 'N/A'))
market = rec.get('market', 'N/A')
odds = rec.get('odds', 0)
stake = rec.get('stake', 0)
risk = rec.get('risk_score', 0)
confidence = rec.get('confidence', 0)
potential = stake * odds
profit = potential - stake

text = f"""💰 <b>WETT-EMPFEHLUNG</b>
```

━━━━━━━━━━━━━━━━━━━━━━

⚽ <b>{match}</b>

🎯 Market: {market}
📊 Quote: {odds:.2f}
💵 Stake: €{stake:.2f}

📈 Potential: €{potential:.2f}
💚 Profit: +€{profit:.2f}

⭐ Risiko: {risk}/5 {‘⭐’ * risk}
🎲 Confidence: {confidence:.0%}
“””

```
return text
```
