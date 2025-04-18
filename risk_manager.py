import json
import os
from datetime import datetime, timedelta

RISK_SETTINGS = {
    'default': 0.03,
    'meme': 0.02,
    'scalp': 0.03,
    'swing': 0.015,
    'altseason_multiplier': 1.5,
    'daily_loss_limit': 0.10,
    'emotional_pause_after_losses': 3,
    'emotional_pause_after_big_win': 2,
}

TRACK_FILE = 'logs/trade_risk_log.json'


def load_risk_log():
    if not os.path.exists(TRACK_FILE):
        return {
            'daily_loss': 0.0,
            'streak_losses': 0,
            'streak_wins': 0,
            'last_reset': datetime.utcnow().strftime('%Y-%m-%d'),
            'paused': False
        }
    with open(TRACK_FILE, 'r') as f:
        return json.load(f)


def save_risk_log(data):
    with open(TRACK_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def reset_daily_risk():
    data = load_risk_log()
    today = datetime.utcnow().strftime('%Y-%m-%d')
    if data['last_reset'] != today:
        data['daily_loss'] = 0.0
        data['streak_losses'] = 0
        data['streak_wins'] = 0
        data['paused'] = False
        data['last_reset'] = today
        save_risk_log(data)
    return data


def update_after_trade(pnl):
    data = load_risk_log()

    if pnl < 0:
        data['daily_loss'] += abs(pnl)
        data['streak_losses'] += 1
        data['streak_wins'] = 0
    else:
        data['streak_wins'] += 1
        data['streak_losses'] = 0

    # Pause logic
    if data['streak_losses'] >= RISK_SETTINGS['emotional_pause_after_losses']:
        data['paused'] = True
    elif data['streak_wins'] >= RISK_SETTINGS['emotional_pause_after_big_win']:
        data['paused'] = True

    save_risk_log(data)


def is_paused():
    data = load_risk_log()
    return data.get('paused', False)


def get_trade_risk(trade_type='default', is_altseason=False):
    data = reset_daily_risk()

    if data['paused']:
        return 0.0

    if data['daily_loss'] >= RISK_SETTINGS['daily_loss_limit']:
        return 0.0

    base_risk = RISK_SETTINGS.get(trade_type, RISK_SETTINGS['default'])

    # Altseason bonus
    if is_altseason:
        base_risk *= RISK_SETTINGS['altseason_multiplier']

    # Dynamic auto risk adjustment
    if data['streak_wins'] >= 2:
        base_risk *= 1.2  # confidence boost
    elif data['streak_losses'] >= 2:
        base_risk *= 0.7  # caution

    return round(base_risk, 4)
